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
import os
import uuid
from datetime import datetime

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

try:
    from agent.option_utils import parse_contract_symbol
    from agent.alpaca_client import alpaca
    from agent.options_market import options_provider
    _ALPACA_AVAILABLE = True
except ImportError:
    try:
        from option_utils import parse_contract_symbol
        from alpaca_client import alpaca
        from options_market import options_provider
        _ALPACA_AVAILABLE = True
    except ImportError:
        _ALPACA_AVAILABLE = False
        alpaca = None  # type: ignore[assignment]
        options_provider = None  # type: ignore[assignment]
        parse_contract_symbol = None  # type: ignore[assignment]

router = APIRouter(prefix="/options", tags=["options"])


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
@router.post("/place")
async def place_option_order(req: "PlaceOptionOrderRequest"):
    """Place a manual option order on the Alpaca paper account and record an audit row."""
    _require_alpaca()
    symbol = req.contract_symbol.upper()
    try:
        root, expiry, right, strike = parse_contract_symbol(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await alpaca.place_option_order(
        contract_symbol=symbol,
        qty=req.qty,
        side=req.side,
        position_intent=req.position_intent,
        order_type=req.order_type,
        limit_price=req.limit_price,
    )
    if result.status == "error":
        raise HTTPException(status_code=502, detail=str(result.raw.get("error", "option order failed")))

    now = datetime.utcnow()
    order_id = str(uuid.uuid4())
    raw = {
        "contract_symbol": symbol,
        "underlying_symbol": root,
        "expiration_date": str(expiry),
        "contract_type": "call" if right == "C" else "put",
        "strike_price": strike,
        "position_intent": req.position_intent,
        "alpaca_order_id": str(result.order_id) if result.order_id else "",
        "status": result.status,
        "filled_avg_price": result.filled_avg_price,
    }
    mode = os.getenv("TRADING_MODE", "paper")
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
        "position_intent": req.position_intent,
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