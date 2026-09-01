"""
Alpaca integration endpoints.
Requires ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in .env.
"""

import os
from fastapi import APIRouter, HTTPException
from loguru import logger

try:
    from alpaca_client import alpaca
    _ALPACA_AVAILABLE = True
except ImportError:
    _ALPACA_AVAILABLE = False

router = APIRouter(prefix="/alpaca", tags=["alpaca"])


def _require_alpaca():
    if not _ALPACA_AVAILABLE:
        raise HTTPException(status_code=501, detail="alpaca-py not installed")
    if not alpaca.is_configured():
        raise HTTPException(status_code=503, detail="Alpaca credentials not configured")


@router.get("/account")
async def get_account():
    _require_alpaca()
    return await alpaca.get_account()


@router.get("/positions")
async def get_positions():
    _require_alpaca()
    return await alpaca.get_positions()


@router.get("/bars/{symbol}")
async def get_bars(symbol: str, timeframe: str = "1Day", limit: int = 252):
    _require_alpaca()
    return await alpaca.get_bars(symbol, timeframe, limit)
