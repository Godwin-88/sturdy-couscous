"""Crypto endpoints — Alpaca universe, FE-agent-influenced, prefailable orders.

Spot-only (Alpaca crypto has no chains): the tape is the chain-equivalent.
Two-phase preview/confirm mirrors /signals/place (human-in-the-loop).
"""
import os
import uuid
from datetime import datetime, timedelta

import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger
import pandas as pd

from agent.crypto_signal import suggest_crypto

MIN_CRYPTO_NOTIONAL_USD = 10.0  # Alpaca rejects < $10 cost basis
from agent.alpaca_data import provider

router = APIRouter(prefix="/crypto", tags=["crypto"])


def _r() -> redis.Redis:
    return redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                       port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=True)


@router.get("/tape")
def tape(pair: str, days: int = 90):
    """Price/vol tape for a crypto pair (the chain-equivalent)."""
    try:
        df = provider.get_ohlcv(pair, days=days)
    except Exception as e:
        logger.warning(f"crypto tape failed {pair}: {e}")
        return {"pair": pair, "rows": 0, "prices": []}
    if df is None or getattr(df, "empty", True):
        return {"pair": pair, "rows": 0, "prices": []}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return {
        "pair": pair,
        "rows": int(len(df)),
        "prices": [{"t": str(i.date() if hasattr(i, "date") else i), "close": float(r["Close"]),
                     "volume": float(r.get("Volume") or 0)} for i, r in df.tail(120).iterrows()],
    }


@router.get("/suggestions")
def suggestions(pair: str, lens: str = "defensive", nav: float = 100_000.0,
                regime: str | None = None):
    try:
        return suggest_crypto(pair, lens=lens, nav=nav, regime_override=regime)
    except Exception as e:
        logger.error(f"crypto suggestions failed {pair}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


class PreviewRequest(BaseModel):
    pair: str
    side: str = "buy"
    qty: float = 1.0
    order_type: str = "market"
    limit_price: float | None = None


@router.post("/preview")
def preview(req: PreviewRequest):
    """Two-phase step 1: build proposal_token (10-min TTL), do NOT execute."""
    token = str(uuid.uuid4())
    proposal = {
        "pair": req.pair.upper(), "side": req.side, "qty": req.qty,
        "order_type": req.order_type, "limit_price": req.limit_price,
        "expires_at": (datetime.utcnow().replace(microsecond=0) + timedelta(minutes=10)).isoformat(),
    }
    key = f"graphalpha:crypto_proposals:{token}"
    _r().setex(key, 600, __import__("json").dumps(proposal))
    spot = 0.0
    try:
        df = provider.get_ohlcv(req.pair, days=2)
        if df is not None and not getattr(df, "empty", True):
            spot = float(df["Close"].iloc[-1])
    except Exception:
        pass
    notional = spot * req.qty if spot else req.limit_price or 0.0
    if spot and req.qty * spot < MIN_CRYPTO_NOTIONAL_USD:
        raise HTTPException(status_code=400,
                            detail=f"cost basis ${round(req.qty * spot,2)} below Alpaca ${MIN_CRYPTO_NOTIONAL_USD:.0f} minimum")
    return {
        "preview": True, "proposal_token": token, "spot": spot,
        "risk_preview": {
            "estimated_notional_usd": round(notional, 2),
            "estimated_fee_usd": round(notional * 0.0026, 2),
            "max_loss_est_usd": round(notional, 2),
            "note": "Preview only — no execution. Echo proposal_token back to confirm.",
        },
    }


class ConfirmRequest(BaseModel):
    pair: str
    side: str
    qty: float
    order_type: str = "market"
    limit_price: float | None = None
    proposal_token: str


@router.post("/confirm")
async def confirm(req: ConfirmRequest):
    """Two-phase step 2: one-time-use token → real Alpaca paper crypto order + audit."""
    r = _r()
    key = f"graphalpha:crypto_proposals:{req.proposal_token}"
    raw = r.get(key)
    if not raw:
        raise HTTPException(status_code=410, detail="proposal expired or already used")
    prop = json.loads(raw)
    if prop["pair"].upper() != req.pair.upper() or prop["qty"] != req.qty or prop["side"] != req.side:
        raise HTTPException(status_code=409, detail="intent does not match proposal token")
    r.delete(key)
    try:
        from agent.alpaca_client import alpaca
        result = await alpaca.place_crypto_order(req.pair, req.side, req.qty, req.order_type, req.limit_price)
    except Exception as e:
        logger.exception(f"crypto confirm order failed {req.pair}: {e}")
        raise HTTPException(status_code=502, detail=str(e))
    import psycopg2
    conn = psycopg2.connect(host=os.getenv("POSTGRES_HOST", "postgres"),
                            dbname=os.getenv("POSTGRES_DB", "graphalpha"),
                            user=os.getenv("POSTGRES_USER", "graphalpha"),
                            password=os.getenv("POSTGRES_PASSWORD", ""))

    raw_id = str(result.order_id or "")
    if raw_id and raw_id != "error":
        try:
            uuid.UUID(raw_id)
            order_id = raw_id
        except (ValueError, TypeError):
            order_id = str(uuid.uuid4())
    else:
        order_id = str(uuid.uuid4())
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO order_audit
                  (order_id, strategy, ticker, direction, quantity, fill_price, fee_usd, mode, venue, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (order_id, "crypto_signal", req.pair.upper(), req.side,
                  req.qty, float(result.filled_avg_price or 0) or req.limit_price or 0,
                  0.0, "paper", "alpaca", datetime.utcnow()))
        conn.commit()
    finally:
        conn.close()
    return {
        "order_id": order_id, "status": result.status, "mode": "paper",
        "venue": "alpaca", "pair": req.pair.upper(), "side": req.side, "qty": req.qty,
        "filled_avg_price": result.filled_avg_price,
        "created_at": datetime.utcnow().isoformat(),
    }


import json  # keep json import at module bottom-usable in confirm
