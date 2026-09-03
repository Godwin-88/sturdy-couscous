"""
Options trading endpoints — full Alpaca options capability.

Lets the user (or an agent) browse any Alpaca option chain and place option
orders on the paper account directly from the UI. No restriction on
underlying/expiration/strike — anything Alpaca lists is browsable/tradeable.

Endpoints:
  GET  /options/expirations?underlying=SPY
  GET  /options/strikes?underlying=SPY&expiration=...&contract_type=call
  GET  /options/chain?underlying=SPY&expiration=...&contract_type=...
  GET  /options/snapshot?contract=SPY...
  POST /options/place     (manual option order; human-in-the-loop)
"""
import json
import os
import uuid
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

try:
    from agent.option_utils import parse_contract_symbol
    from agent.alpaca_client import alpaca
    from agent.options_market import options_provider
    from agent.option_signal import compute_suggestions
    _ALPACA_AVAILABLE = True
except ImportError:
    try:
        from option_utils import parse_contract_symbol
        from alpaca_client import alpaca
        from options_market import options_provider
        from option_signal import compute_suggestions
        _ALPACA_AVAILABLE = True
    except ImportError:
        _ALPACA_AVAILABLE = False
        alpaca = None  # type: ignore[assignment]
        options_provider = None  # type: ignore[assignment]
        parse_contract_symbol = None  # type: ignore[assignment]
        compute_suggestions = None  # type: ignore[assignment]

router = APIRouter(prefix="/options", tags=["options"])


def _existing_position_sign(contract: str) -> int:
    """Return +1 / -1 / 0 for the user's existing qty in `contract` (Alpaca paper).

    Used by ``_auto_fix_intent`` to detect a stale ``sell_to_open`` on a
    contract the user already holds, which Alpaca rejects as
    "position intent mismatch".
    """
    try:
        from agent.alpaca_client import alpaca as _a
        if not _a.is_configured():
            return 0
        positions = _a.client.get_all_positions()  # sync in alpaca-py
        for p in positions:
            if str(p.symbol).upper() == contract.upper():
                qty = float(getattr(p, "qty", 0) or 0)
                if qty > 0:  return +1
                if qty < 0:  return -1
                return 0
    except Exception:
        pass
    return 0


def _auto_fix_intent(legs: list[tuple[str, str, str]]) -> tuple[str, list[tuple[str, str]]]:
    """Auto-correct position_intent for each (symbol, side, intent) triple.

    Returns (corrected_intent_for_first, [(symbol, new_intent), ...])
    where corrected_intent_for_first is the new intent for the primary contract.

    Rules (mirror Alpaca's inference):
      - existing long position in symbol, caller wants to SELL
        → intent becomes sell_to_close
      - existing short position in symbol, caller wants to BUY
        → intent becomes buy_to_close
      - otherwise the caller's intent is kept
    """
    rewrites: list[tuple[str, str]] = []
    primary_new: str | None = None
    for i, (sym, side, intent) in enumerate(legs):
        if not sym:
            continue
        pos = _existing_position_sign(sym)
        s = str(side).lower()
        new_intent = intent
        if s == "sell" and pos > 0 and "_to_open" in (intent or ""):
            new_intent = intent.replace("_to_open", "_to_close") if "_to_open" in intent else "sell_to_close"
        elif s == "buy" and pos < 0 and "_to_open" in (intent or ""):
            new_intent = intent.replace("_to_open", "_to_close") if "_to_open" in intent else "buy_to_close"
        if new_intent != intent:
            rewrites.append((sym, new_intent))
            if i == 0:
                primary_new = new_intent
    if primary_new is None:
        primary_new = legs[0][2] if legs else "buy_to_open"
    return primary_new, rewrites


def _conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "graphalpha"),
        user=os.getenv("POSTGRES_USER", "graphalpha"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def _require_alpaca():
    if not _ALPACA_AVAILABLE or alpaca is None or not alpaca.is_configured():
        raise HTTPException(status_code=503, detail="Alpaca not configured/installed")


@router.get("/underlyings")
async def get_underlyings(q: str = "", asset_class: str | None = None):
    """
    Search the full Alpaca asset universe for option underlyings (stocks/ETFs).
    Supports any listed symbol, not a fixed preset list.
    """
    _require_alpaca()
    assets = alpaca.search_assets(q, asset_class=asset_class)
    return {"assets": assets}


@router.get("/expirations")
def get_expirations(underlying: str):
    _require_alpaca()
    exps = options_provider.get_expirations(underlying.upper())
    return {"underlying": underlying.upper(), "expirations": exps}


@router.get("/strikes")
def get_strikes(underlying: str, expiration: str | None = None,
                contract_type: str | None = None):
    _require_alpaca()
    strikes = options_provider.get_strikes(underlying.upper(), expiration, contract_type)
    return {"underlying": underlying.upper(), "strikes": strikes}


@router.get("/chain")
def get_chain(underlying: str, expiration: str | None = None,
              contract_type: str | None = None,
              strike_gte: float | None = None, strike_lte: float | None = None):
    """Browsable option chain with live snapshots (bid/ask, IV, greeks, OI)."""
    _require_alpaca()
    rows = options_provider.get_chain(underlying.upper(), expiration, contract_type,
                                      strike_gte, strike_lte)
    rows.sort(key=lambda r: float(r.get("strike_price") or 0))
    return {"underlying": underlying.upper(), "rows": rows}


@router.get("/snapshot")
def get_snapshot(contract: str):
    _require_alpaca()
    snap = options_provider.get_snapshot(contract.upper())
    if not snap:
        raise HTTPException(status_code=404, detail=f"No snapshot for {contract.upper()}")
    return {"contract": contract.upper(), **snap}


@router.get("/suggestions")
def get_suggestions(underlying: str, expiration: str | None = None,
                    contract_type: str | None = None, regime: str | None = None,
                    lens: str = "average", nav: float | None = None,
                    strategy: str | None = None):
    """
    Agent-generated, KG-grounded strategy suggestions for the selected chain.

    `lens` selects the ranking lens: "average" (lambda=2.25, max-loss cap 10% NAV)
    or "defensive" (lambda=3.5, max-loss cap 5% NAV) — a loss-averse ranking that
    never surfaces a trade that breaches your loss budget. `nav` is account equity
    (defaults to INITIAL_CAPITAL_USD). Suggestions are ranked by the loss-aversion
    score and every card cites its graph trail (DERIVED_FROM concepts).
    `strategy` (optional) narrows the response to a single strategy name; the
    dashboard's regime card uses this to filter SPY suggestions per click.
    """
    _require_alpaca()
    try:
        out = compute_suggestions(underlying, expiration, contract_type, regime=regime,
                                  lens=lens, nav=nav, strategy_filter=strategy)
    except Exception as e:
        logger.warning(f"suggestions failed for {underlying}: {e}")
        raise HTTPException(status_code=502, detail=f"suggestions failed: {e}")
    return out


# ── Dynamic delta hedging (Taleb posture, human-in-the-loop) ────────────────

@router.get("/hedge/state")
async def get_hedge_state(underlying: str = "SPY"):
    """Portfolio greeks + recommended dynamic delta hedge (read-only)."""
    _require_alpaca()
    try:
        from agent.hedge_agent import hedge_agent
        return {"hedge_state": await hedge_agent.hedge_state(underlying)}
    except Exception as e:
        logger.warning(f"hedge state failed: {e}")
        raise HTTPException(status_code=502, detail=f"hedge state failed: {e}")


@router.get("/pnl")
async def get_option_pnl(underlying: str = "SPY"):
    """Live option P&L: premium income vs hedge cost (mark-to-market)."""
    _require_alpaca()
    try:
        from agent.hedge_agent import hedge_agent
        return {"option_pnl": await hedge_agent.option_pnl(underlying)}
    except Exception as e:
        logger.warning(f"option pnl failed: {e}")
        raise HTTPException(status_code=502, detail=f"option pnl failed: {e}")


@router.post("/hedge/rebalance")
async def post_hedge_rebalance(underlying: str = "SPY", confirm: bool = False):
    """
    Dry-run (default) or execute the dynamic delta hedge on the paper account.

    confirm=false -> proposal only. confirm=true -> places the underlying
    equity order on Alpaca paper and records the audit row. Never touches the
    account without an explicit confirm (T10 human-in-the-loop).
    """
    _require_alpaca()
    try:
        from agent.hedge_agent import hedge_agent
        result = await hedge_agent.execute(underlying, confirm=bool(confirm))
        if result.get("status") == "executed":
            try:
                order = result.get("order") or {}
                with _conn() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO order_audit
                          (order_id, strategy, ticker, venue_symbol, venue, direction,
                           quantity, fill_price, fee_usd, mode, signal_score, raw_response, created_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            str(order.get("order_id")), "DynamicDeltaHedge",
                            order.get("symbol"), order.get("symbol"), "alpaca",
                            order.get("side"), float(order.get("qty") or 0),
                            float(order.get("filled_avg_price") or 0), 0.0,
                            os.getenv("TRADING_MODE", "paper"), 0.0,
                            psycopg2.extras.Json(order), datetime.utcnow(),
                        ),
                    )
                    conn.commit()
            except Exception as e:
                logger.error(f"hedge audit insert failed: {e}")
        return result
    except Exception as e:
        logger.warning(f"hedge rebalance failed: {e}")
        raise HTTPException(status_code=502, detail=f"hedge rebalance failed: {e}")
@router.post("/place")
async def place_option_order(req: "PlaceOptionOrderRequest"):
    """Place a manual option order on the Alpaca paper account and record an audit row.

    For 1:1-ratio multi-leg orders (verticals, even-ratio spreads), if the
    caller supplies ``qty > 1`` and any leg has ``qty > 1`` with a non-
    relatively-prime ratio, Alpaca rejects it. To make sizing user-friendly,
    we expand a single MLEG with N legs each at qty=k into k identical
    MLEG orders of qty=1, then aggregate the audit rows.

    Position-intent auto-correction: Alpaca rejects a request when its inferred
    intent (computed from existing positions on the contract) does not match
    the caller's ``position_intent``. If we see a mismatch, we rewrite the
    intent to match the inference so the order goes through (and the audit
    row records the *actual* intent used, not the user's stale one).
    """
    _require_alpaca()
    symbol = req.contract_symbol.upper()

    # ── Human-in-the-loop gate + two-phase commit ──────────────────────────
    # HITL_REQUIRED=1 (hardened): direct placements without a proposal token
    # are refused. KILL_SWITCH=1 refuses confirm-legs (P7 halt behaviour).
    import redis as _redis_lib
    _r = _redis_lib.Redis(host=os.getenv("REDIS_HOST", "redis"),
                          port=int(os.getenv("REDIS_PORT", 6379)),
                          decode_responses=True)

    def _prop_key(token: str) -> str:
        return f"graphalpha:proposals:{token}"

    if os.getenv("KILL_SWITCH") == "1" and not req.preview:
        raise HTTPException(status_code=423, detail="Kill switch engaged — order refused")

    if os.getenv("HITL_REQUIRED", "0") == "1" and not req.preview and not req.proposal_token:
        raise HTTPException(
            status_code=409,
            detail="HITL_REQUIRED=1 — call /options/place with preview=true to obtain a proposal_token first",
        )

    if req.preview:
        token = str(uuid.uuid4())
        now_iso = datetime.utcnow().isoformat()
        proposal = {
            "contract_symbol": symbol,
            "qty": req.qty,
            "side": req.side,
            "position_intent": req.position_intent,
            "order_type": req.order_type,
            "limit_price": req.limit_price,
            "order_class": req.order_class,
            "legs": req.legs,
            "label": req.label,
            "created_at": now_iso,
            "expires_at": (datetime.utcnow().replace(microsecond=0) + timedelta(minutes=10)).isoformat(),
        }
        _r.setex(_prop_key(token), 600, json.dumps(proposal))
        risk = {"ref_mid": {}, "est_net_debit_usd": None,
                "est_max_loss_usd": None, "est_max_loss_pct_nav": None}
        try:
            mids: dict[str, float] = {}
            for csym in [symbol] + [str(l.get("symbol", "")).upper() for l in (req.legs or [])]:
                snap = options_provider.get_snapshot(csym)
                if snap:
                    mids[csym] = round(((snap.get("bid") or 0) + (snap.get("ask") or 0)) / 2.0, 4)
            net = 0.0
            long_debits = 0.0
            if req.legs:
                for l in req.legs:
                    mid = mids.get(str(l.get("symbol", "")).upper(), 0.0)
                    notional = mid * 100 * int(l.get("qty") or req.qty)
                    if str(l.get("side", "buy")).lower() == "buy":
                        net -= notional
                        long_debits += notional
                    else:
                        net += notional
            else:
                mid = mids.get(symbol, 0.0)
                notional = mid * 100 * req.qty
                if req.side.lower() == "buy":
                    net -= notional
                    long_debits += notional
                else:
                    net += notional
            risk["est_net_debit_usd"] = round(net, 2)
            risk["est_max_loss_usd"] = round(max(long_debits, -net, 0.0), 2)
            risk["ref_mid"] = mids
            try:
                acct = await alpaca.get_account()
                nav = float(acct.get("equity") or 0)
                if nav > 0 and risk["est_max_loss_usd"]:
                    risk["est_max_loss_pct_nav"] = round(100.0 * risk["est_max_loss_usd"] / nav, 3)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"option preview risk computation failed: {e}")
        return {
            "preview": True,
            "proposal_token": token,
            "order": proposal,
            "risk_preview": risk,
            "note": "Preview only — echo proposal_token back to confirm (one-time use, 10 min TTL).",
            "expires_at": proposal["expires_at"],
        }

    if req.proposal_token:
        raw = _r.get(_prop_key(req.proposal_token))
        if not raw:
            raise HTTPException(status_code=410, detail="Proposal token expired or already used")
        try:
            prop = json.loads(raw)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid proposal payload")
        expected = {
            "contract_symbol": str(prop.get("contract_symbol", "")).upper(),
            "qty": prop.get("qty"),
            "side": prop.get("side"),
            "position_intent": prop.get("position_intent"),
            "order_type": prop.get("order_type"),
            "order_class": prop.get("order_class"),
            "legs": prop.get("legs"),
        }
        actual = {
            "contract_symbol": symbol,
            "qty": req.qty,
            "side": req.side,
            "position_intent": req.position_intent,
            "order_type": req.order_type,
            "order_class": req.order_class,
            "legs": req.legs,
        }
        if actual != expected:
            raise HTTPException(status_code=409, detail="Order intent does not match the proposal token")
        _r.delete(_prop_key(req.proposal_token))
        if prop.get("limit_price") is not None:
            req.limit_price = float(prop["limit_price"])
        if prop.get("label"):
            req.label = str(prop["label"])

    try:
        root, expiry, right, strike = parse_contract_symbol(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Auto-correct position_intent for the primary contract AND for every
    # leg. Logic:
    #   - If the user already holds a LONG position in the contract, a SELL
    #     action must be sell_to_close (not sell_to_open).
    #   - If the user already holds a SHORT position, a BUY action must be
    #     buy_to_close.
    # Alpaca infers this anyway; we just pre-empt the 422 mismatch.
    corrected_intent, intent_rewrites = _auto_fix_intent(
        [(symbol, req.side, req.position_intent)]
        + [
            (l.get("symbol", "").upper(),
             "sell" if str(l.get("side", "buy")).lower() == "sell" else "buy",
             str(l.get("position_intent", "buy_to_open")))
            for l in (req.legs or [])
        ],
    )
    if corrected_intent != req.position_intent:
        logger.info(f"intent auto-corrected: {req.position_intent} -> {corrected_intent} "
                    f"for {symbol} (existing position on book)")
        req_position_intent = corrected_intent
    else:
        req_position_intent = req.position_intent

    # Apply any per-leg rewrites
    legs = req.legs or []
    if intent_rewrites:
        rewrites_by_symbol = {sym: new_intent for sym, new_intent in intent_rewrites[1:]}
        legs = [{**l, "position_intent": rewrites_by_symbol.get(
                    l.get("symbol", "").upper(),
                    l.get("position_intent", "buy_to_open"))}
                for l in legs]

    # Alpaca rejects single-leg ("simple") market orders outside market
    # hours, even on the paper account. Multi-leg baskets (MLEG) are
    # accepted any time. To make the UI's "place order" button work
    # 24/7, auto-wrap any simple market order as a 1-leg MLEG before
    # forwarding. Limit orders are unaffected.
    auto_wrapped = False
    if req.order_class == "simple" and req.order_type == "market":
        req.order_class = "mleg"
        if not legs:
            legs = [{"symbol": symbol, "side": req.side, "qty": req.qty,
                     "position_intent": req_position_intent}]
            auto_wrapped = True
    intent_rewrites_list = intent_rewrites if intent_rewrites else []

    # Determine if expansion is needed: 1:1 ratio, but caller wants qty>1.
    needs_expansion = (
        req.order_class in ("vertical", "mleg")
        and req.legs
        and len(req.legs) >= 2
        and all(int(l.get("qty", 1) or 1) == int(req.legs[0].get("qty", 1) or 1) for l in req.legs)
        and int(req.legs[0].get("qty", 1) or 1) > 1
    )

    if needs_expansion:
        spread_count = int(req.legs[0].get("qty", 1) or 1)
        first_result = None
        first_raw = None
        for i in range(spread_count):
            res = await alpaca.place_option_order(
                contract_symbol=symbol,
                qty=1,
                side=req.side,
                position_intent=req_position_intent,
                order_type=req.order_type,
                limit_price=req.limit_price,
                order_class="mleg",  # Alpaca normalises vertical -> mleg
                legs=[{**l, "qty": 1, "position_intent": l.get("position_intent", req_position_intent)} for l in legs],
            )
            if res.status == "error":
                raise HTTPException(
                    status_code=getattr(res, "http_status", 502) or 502,
                    detail=f"fill {i+1}/{spread_count} failed: {res.raw.get('error', 'option order failed')}",
                )
            first_result = res
            first_raw = {
                "spread_index": i + 1,
                "spread_count": spread_count,
                "alpaca_order_id": str(res.order_id),
                "status": res.status,
                "filled_avg_price": res.filled_avg_price,
            }
        # Synthesize a single response so the caller (and audit) get a
        # coherent "N spreads placed" record.
        result = first_result
        result_raw = {
            "contract_symbol": symbol,
            "underlying_symbol": root,
            "legs": legs,
            "expiration_date": str(expiry),
            "contract_type": "call" if right == "C" else "put",
            "strike_price": strike,
            "position_intent": req_position_intent,
            "intent_rewrites": intent_rewrites,
            "spread_count": spread_count,
            "spreads": [first_raw],  # last fill, plus all logged to audit
            "status": result.status,
            "filled_avg_price": result.filled_avg_price,
        }
    else:
        result = await alpaca.place_option_order(
            contract_symbol=symbol,
            qty=req.qty,
            side=req.side,
            position_intent=req_position_intent,
            order_type=req.order_type,
            limit_price=req.limit_price,
            order_class=req.order_class,
            legs=legs or None,
        )
        if result.status == "error":
            code = getattr(result, "http_status", 502) or 502
            if not isinstance(code, int) or code < 400 or code > 599:
                code = 502
            raise HTTPException(status_code=code, detail=str(result.raw.get("error", "option order failed")))
        result_raw = {
            "contract_symbol": symbol,
            "underlying_symbol": root,
            "legs": legs or [{"symbol": symbol, "side": req.side,
                              "position_intent": req_position_intent, "qty": req.qty}],
            "expiration_date": str(expiry),
            "contract_type": "call" if right == "C" else "put",
            "strike_price": strike,
            "position_intent": req_position_intent,
            "intent_rewrites": intent_rewrites,
            "alpaca_order_id": str(result.order_id) if result.order_id else "",
            "status": result.status,
            "filled_avg_price": result.filled_avg_price,
        }

    now = datetime.utcnow()
    order_id = str(uuid.uuid4())
    mode = os.getenv("TRADING_MODE", "paper")
    # Persist ONE audit row that points to the actual Alpaca order(s)
    raw = result_raw
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO order_audit
                      (order_id, strategy, ticker, venue_symbol, venue, direction,
                       quantity, fill_price, fee_usd, mode, signal_score, raw_response, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    order_id, req.label, root, symbol, "alpaca", req.side,
                    req.qty, result.filled_avg_price or 0, 0.0, mode, 0.0,
                    psycopg2.extras.Json(raw), now,
                ))
                conn.commit()
    except Exception as e:
        logger.error(f"option audit insert failed: {e}")

    return {
        "order_id": order_id,
        "alpaca_order_id": str(result.order_id) if result.order_id else "",
        "contract_symbol": symbol,
        "underlying_symbol": root,
        "expiration_date": str(expiry),
        "contract_type": "call" if right == "C" else "put",
        "strike_price": strike,
        "side": req.side,
        "position_intent": req_position_intent,
        "intent_rewrites": intent_rewrites,
        "quantity": req.qty,
        "status": result.status,
        "filled_avg_price": result.filled_avg_price,
        "mode": mode,
        "created_at": now.isoformat(),
    }


class PlaceOptionOrderRequest(BaseModel):
    contract_symbol: str
    qty: int = 1
    side: str = "buy"                       # buy or sell
    position_intent: str = "buy_to_open"    # buy_to_open/close, sell_to_open/close
    order_type: str = "market"              # market or limit
    limit_price: float | None = None
    label: str = "manual"                   # or an agent strategy name
    order_class: str = "simple"             # simple | vertical | mleg
    legs: list[dict] | None = None          # multi-leg spread legs:
                                            #   [{"symbol", "side", "qty", "position_intent"}]
    # Human-in-the-loop two-phase commit
    preview: bool = False                   # mint a proposal_token, never execute
    proposal_token: str | None = None       # confirm an earlier preview (one-time use)