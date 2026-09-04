"""
Alpaca integration endpoints.
Requires ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in .env.
"""

import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, Header
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


def _apply_active_alpaca(authorization: str | None):
    """If a bearer token is present, configure the Alpaca client to that
    user's active account (per-user vault). Falls back to env creds when no
    token / no active account is set (workstation default)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return
    try:
        from common.credentials import verify_token
        from agent.settings_client import resolve_active_alpaca
        token = authorization.split(" ", 1)[1].strip()
        uid, _ = verify_token(token)
        cred = resolve_active_alpaca(uid)
        if cred and cred.get("secret_key"):
            from agent.alpaca_client import alpaca as _c
            base = cred.get("base_url") or "https://paper-api.alpaca.markets"
            _c.configure(cred.get("key_id"), cred.get("secret_key"), base, cred.get("paper", True))
    except Exception:
        pass  # fall back to env creds


@router.get("/account")
async def get_account(authorization: str | None = Header(default=None)):
    _apply_active_alpaca(authorization)
    _require_alpaca()
    if _unconfigured():
        return {"status": "unconfigured", "cash": 0, "equity": 0, "buying_power": 0}
    return await alpaca.get_account()


@router.get("/crypto/assets")
def crypto_assets(q: str = "", authorization: str | None = Header(default=None)):
    """Search the FULL Alpaca crypto trading universe (no hardcoded set)."""
    _apply_active_alpaca(authorization)
    _require_alpaca()
    if _unconfigured():
        return []
    return alpaca.search_crypto_assets(q)


@router.get("/positions")
async def get_positions(authorization: str | None = Header(default=None)):
    _apply_active_alpaca(authorization)
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


@router.get("/portfolio")
async def get_portfolio_history(days: int = 30):
    """Real Alpaca account NAV + equity curve (replaces the fabricated $10k ledger)."""
    _require_alpaca()
    if _unconfigured():
        return {"source": "unconfigured"}
    account = await alpaca.get_account()
    hist = await alpaca.portfolio_history(days=days)
    nav_history = _normalise_nav(hist.get("nav_history", []))
    equity = float(account.get("equity", 0) or 0)
    cash = float(account.get("cash", 0) or 0)
    buying_power = float(account.get("buying_power", 0) or 0)
    drawdown_pct = 0.0
    peak = 0.0
    for pt in nav_history:
        e = float(pt.get("equity", 0) or 0)
        if e > peak:
            peak = e
        if peak > 0:
            drawdown_pct = max(drawdown_pct, (peak - e) / peak)
    return {
        "source": "alpaca",
        "nav": equity,
        "equity": equity,
        "cash": cash,
        "buying_power": buying_power,
        "drawdown_pct": drawdown_pct,
        "halted": False,
        "nav_history": nav_history[-days * 2:] or nav_history,
        "base_value": hist.get("base_value", 0),
        "updated_at": None,
    }


def _normalise_nav(nav_history: list) -> list:
    """Clean the broker history: ISO timestamps, positive equity only, sorted."""
    out = []
    for pt in nav_history or []:
        t = pt.get("t")
        e = float(pt.get("equity", 0) or 0)
        if e <= 0:
            continue  # first broker point is often a 0.0 baseline — drop it
        if isinstance(t, (int, float)) or (isinstance(t, str) and t.isdigit()):
            t = datetime.utcfromtimestamp(float(t)).isoformat() + "Z"
        out.append({"t": t, "equity": e})
    out.sort(key=lambda p: p["t"])
    return out
