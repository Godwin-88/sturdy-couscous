"""
Alpaca integration endpoints.
Requires ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in .env.
"""

import os
from fastapi import APIRouter, HTTPException
from loguru import logger

try:
    from agent.alpaca_client import alpaca
    _ALPACA_AVAILABLE = True
except ImportError:
    try:
        from alpaca_client import alpaca
        _ALPACA_AVAILABLE = True
    except ImportError:
        _ALPACA_AVAILABLE = False
        alpaca = None  # type: ignore[assignment]

router = APIRouter(prefix="/alpaca", tags=["alpaca"])


def _require_alpaca():
    if not _ALPACA_AVAILABLE:
        raise HTTPException(status_code=501, detail="alpaca-py not installed")


def _unconfigured():
    return alpaca is None or not alpaca.is_configured()


@router.get("/account")
async def get_account():
    _require_alpaca()
    if _unconfigured():
        return {"status": "unconfigured", "cash": 0, "equity": 0, "buying_power": 0}
    return await alpaca.get_account()


@router.get("/positions")
async def get_positions():
    _require_alpaca()
    if _unconfigured():
        return []
    return await alpaca.get_positions()


@router.get("/bars/{symbol}")
async def get_bars(symbol: str, timeframe: str = "1Day", limit: int = 252):
    _require_alpaca()
    if _unconfigured():
        return []
    return await alpaca.get_bars(symbol, timeframe, limit)
