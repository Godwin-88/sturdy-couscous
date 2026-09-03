import json
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
import os
import redis
from loguru import logger

router = APIRouter(prefix="/signals", tags=["signals"])

def _conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "graphalpha"),
        user=os.getenv("POSTGRES_USER", "graphalpha"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


import re as _re
from datetime import datetime as _dt

_OPT_RE = _re.compile(r"^[A-Z]{1,5}\d{6}[CP]\d{8}$")


def _option_meta(symbol: str) -> dict | None:
    """Best-effort display metadata for an OCC option row.

    envelope of strike / expiry / DTE / mid premium / delta / IV populated from
    the OCC symbol + a cached live snapshot. Never raises — missing data stays null.
    """
    try:
        from agent.option_utils import parse_contract_symbol
        root, expiry, right, strike = parse_contract_symbol(symbol)
        dte = max(0, (expiry - _dt.utcnow().date()).days)
        meta = {
            "contract_type": "call" if right == "C" else "put",
            "strike": round(float(strike), 2),
            "expiry": str(expiry),
            "dte": int(dte),
            "delta": None,
            "premium": None,
            "iv": None,
        }
        try:
            from agent.options_market import provider as _oprov
            snap = _oprov.get_snapshot(symbol)
            if not isinstance(snap, dict):
                return meta
            g = snap.get("greeks") or {}
            if isinstance(g, dict) and g.get("delta") is not None:
                meta["delta"] = round(float(g["delta"]), 3)
            v = snap.get("implied_volatility")
            if v is not None:
                meta["iv"] = round(float(v), 4)
            b = snap.get("bid")
            a = snap.get("ask")
            if b is not None and a is not None and float(b) > 0 and float(a) > 0:
                meta["premium"] = round((float(b) + float(a)) / 2.0, 2)
        except Exception:
            pass
        return meta
    except Exception:
        return None


class PlaceOrderRequest(BaseModel):
    ticker: str
    direction: str  # "buy" or "sell"
    quantity: float
    order_type: str = "market"  # "market" or "limit"
    limit_price: float | None = None
    venue: str = "alpaca"
    signal_id: str | None = None  # optional link back to a suggested signal

    # ── Two-phase commit (WebMCP agent surface) ─────────────────────────────
    preview: bool = False  # when True, do NOT execute — return a proposal_token
    proposal_token: str | None = None  # required to confirm a previewed order


@router.get("")
def get_signals(limit: int = 50):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT order_id, strategy, ticker, direction, quantity,
                       fill_price, mode, signal_score, created_at
                FROM order_audit
                ORDER BY created_at DESC LIMIT %s
            """, (limit,))
            cols = ["order_id","strategy","ticker","direction","quantity",
                    "fill_price","mode","signal_score","created_at"]
            rows = cur.fetchall()
    out = []
    for r in (dict(zip(cols, row)) for row in rows):
        sym = str(r.get("ticker") or "")
        r["option"] = _option_meta(sym) if _OPT_RE.match(sym) else None
        out.append(r)
    return out


@router.get("/suggested")
def get_suggested_signals(limit: int = 100, ticker: str | None = None):
    """All signals suggested by the agent, durably stored in signal_archive.

    `signal_id` is the schema-v1 signal UUID from the live agent cycle, and
    `order_id` is populated once the signal has been used to place an order
    (so the UI can link a suggestion to its execution).
    """
    sql = """
        SELECT signal_id, cycle_id, timestamp, strategy, ticker, venue,
               venue_symbol, asset_class, regime, direction, score,
               quant_score, sentiment_score, news_overlay, macro_overlay,
               kg_formula_contribution, contradiction_blocked, graph_path,
               kelly_fraction, var_contribution_pct, order_id,
               fill_price, fill_timestamp, slippage_bps, created_at
        FROM signal_archive
        WHERE (%(ticker)s IS NULL OR ticker = %(ticker)s)
        ORDER BY timestamp DESC NULLS LAST
        LIMIT %(limit)s
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"limit": limit, "ticker": ticker})
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    out = []
    for r in rows:
        sym = str(r.get("venue_symbol") or r.get("ticker") or "")
        r["option"] = _option_meta(sym) if _OPT_RE.match(sym) else None
        out.append(r)
    return out


@router.get("/live")
def get_live_signals():
    """Latest signals cached in Redis by the agent worker."""
    import redis
    r = redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )
    raw = r.get("graphalpha:latest_signals")
    return json.loads(raw) if raw else []


@router.post("/place")
def place_order(req: PlaceOrderRequest):
    """
    Place a manual order through the configured venue (Alpaca/Kraken/IBKR).
    In paper mode, simulates the fill and writes to order_audit.

    When venue == "alpaca", routes through the real Alpaca paper client (paper fills,
    real order id, status). Falls back to a simulated fill when unconfigured (tests stay hermetic).
    """
    mode = os.getenv("KRAKEN_TRADING_MODE", "paper")
    order_id = str(uuid.uuid4())
    now = datetime.utcnow()
    status = "submitted"
    venue = req.venue
    fill_price = 0.0
    fee_usd = 0.0

    # ── Two-phase commit: proposal token authority (Redis-backed) ────────────
    _r = redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )

    def _proposal_key(token: str) -> str:
        return f"graphalpha:proposals:{token}"

    if req.preview:
        # Generate a proposal token, persist intent (10 min TTL), do NOT execute.
        token = str(uuid.uuid4())
        proposal = {
            "ticker": req.ticker.upper(),
            "direction": req.direction,
            "quantity": req.quantity,
            "order_type": req.order_type,
            "limit_price": req.limit_price,
            "venue": req.venue,
            "signal_id": req.signal_id,
            "created_at": now.isoformat(),
            "expires_at": (datetime.utcnow().replace(microsecond=0) + timedelta(minutes=10)).isoformat(),
        }
        _r.setex(_proposal_key(token), 600, json.dumps(proposal))
        # Reference price for notional / risk preview: limit price or last close fallback.
        ref_price = req.limit_price or 100.0
        try:
            import yfinance as yf
            h = yf.Ticker(req.ticker.upper()).history(period="1d", interval="1m")
            if not h.empty:
                ref_price = float(h["Close"].iloc[-1])
        except Exception:
            pass
        return {
            "preview": True,
            "proposal_token": token,
            "order": {
                "ticker": proposal["ticker"],
                "direction": proposal["direction"],
                "quantity": proposal["quantity"],
                "order_type": proposal["order_type"],
                "limit_price": proposal["limit_price"],
                "venue": proposal["venue"],
                "signal_id": proposal["signal_id"],
            },
            "risk_preview": {
                "ref_price": round(ref_price, 2),
                "estimated_notional_usd": round(abs(proposal["quantity"]) * ref_price, 2),
                "estimated_fee_usd": round(abs(proposal["quantity"]) * ref_price * 0.0026, 2),
                "max_loss_est_usd": round(abs(proposal["quantity"]) * ref_price, 2),
                "note": "Preview only — no execution. Echo proposal_token back to confirm.",
            },
            "expires_at": proposal["expires_at"],
            "created_at": now.isoformat(),
        }

    if req.proposal_token:
        raw = _r.get(_proposal_key(req.proposal_token))
        if not raw:
            raise HTTPException(status_code=410, detail="Proposal token expired or already used")
        try:
            prop = json.loads(raw)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid proposal payload")
        expected = {
            "ticker": req.ticker.upper(),
            "direction": req.direction,
            "quantity": req.quantity,
            "order_type": req.order_type,
            "venue": req.venue,
        }
        actual = {
            "ticker": prop.get("ticker"),
            "direction": prop.get("direction"),
            "quantity": prop.get("quantity"),
            "order_type": prop.get("order_type"),
            "venue": prop.get("venue"),
        }
        if actual != expected:
            raise HTTPException(status_code=409, detail="Order intent does not match the proposal token")
        # One-time use: consume the token before executing.
        _r.delete(_proposal_key(req.proposal_token))
        if prop.get("limit_price"):
            req.limit_price = float(prop["limit_price"])
        if prop.get("signal_id"):
            req.signal_id = str(prop["signal_id"])

    # Alpaca: real paper orders when configured, simulation otherwise
    if venue == "alpaca":
        try:
            from agent.alpaca_client import alpaca
        except ImportError:
            try:
                from alpaca_client import alpaca
            except ImportError:
                alpaca = None
        if alpaca is not None and alpaca.is_configured():
            try:
                result = alpaca.place_order(req.ticker.upper(), req.direction, req.quantity,
                                              req.order_type)
                order_id = result.order_id or order_id
                status = result.status or status
                fill_price = float(result.filled_avg_price or 0) or req.limit_price or 0.0
                mode = "paper"
                venue = "alpaca"
            except Exception as e:
                logger.warning(f"Alpaca place_order failed: {e} — falling back to simulation")
        else:
            logger.info("Alpaca not configured — simulating paper fill for alpaca venue")

    # Simulation fill price
    if fill_price == 0.0:
        if req.order_type == "limit" and req.limit_price:
            fill_price = req.limit_price
        else:
            import yfinance as yf
            try:
                t = yf.Ticker(req.ticker)
                hist = t.history(period="1d", interval="1m")
                if not hist.empty:
                    fill_price = float(hist["Close"].iloc[-1])
                else:
                    fill_price = 100.0
            except Exception:
                fill_price = 100.0

    fee_usd = abs(req.quantity * fill_price * 0.0026)
    signal_score = 0.0  # manual order, no signal score

    # Write to order_audit
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO order_audit
                    (order_id, strategy, ticker, direction, quantity,
                     fill_price, fee_usd, mode, signal_score, venue, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                order_id, "manual", req.ticker.upper(), req.direction,
                req.quantity, round(fill_price, 4), round(fee_usd, 4),
                mode, signal_score, venue, now,
            ))
            # Link this order back to the suggested signal (if it came from one)
            if req.signal_id:
                cur.execute("""
                    UPDATE signal_archive
                    SET order_id = %s, fill_price = %s, fill_timestamp = %s
                    WHERE signal_id = %s
                """, (order_id, round(fill_price, 4), now, req.signal_id))
            conn.commit()

    return {
        "order_id": order_id,
        "status": status,
        "mode": mode,
        "venue": venue,
        "ticker": req.ticker.upper(),
        "direction": req.direction,
        "quantity": req.quantity,
        "fill_price": round(fill_price, 4),
        "fee_usd": round(fee_usd, 4),
        "signal_id": req.signal_id,
        "created_at": now.isoformat(),
    }
