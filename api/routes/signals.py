import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
import os
from loguru import logger

router = APIRouter(prefix="/signals", tags=["signals"])

def _conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "graphalpha"),
        user=os.getenv("POSTGRES_USER", "graphalpha"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


class PlaceOrderRequest(BaseModel):
    ticker: str
    direction: str  # "buy" or "sell"
    quantity: float
    order_type: str = "market"  # "market" or "limit"
    limit_price: float | None = None
    venue: str = "alpaca"


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
    return [dict(zip(cols, r)) for r in rows]


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
        "created_at": now.isoformat(),
    }
