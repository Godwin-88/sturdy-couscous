import os
from datetime import datetime
import psycopg2
from fastapi import APIRouter

router = APIRouter(prefix="/positions", tags=["positions"])


def _normalise_nav(nav_history: list) -> list:
    """Clean the broker history: ISO timestamps, positive equity only, sorted."""
    out = []
    for pt in nav_history or []:
        t = pt.get("t")
        e = float(pt.get("equity", 0) or 0)
        if e <= 0:
            continue
        if isinstance(t, (int, float)) or (isinstance(t, str) and t.isdigit()):
            t = datetime.utcfromtimestamp(float(t)).isoformat() + "Z"
        out.append({"t": t, "equity": e})
    out.sort(key=lambda p: p["t"])
    return out

def _conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "graphalpha"),
        user=os.getenv("POSTGRES_USER", "graphalpha"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


@router.get("")
def get_positions():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ticker, direction, quantity, avg_entry_price,
                       current_price,
                       quantity * (current_price - avg_entry_price) AS unrealised_pnl,
                       status, opened_at
                FROM positions WHERE status = 'open'
                ORDER BY opened_at DESC
            """)
            cols = ["ticker","direction","quantity","avg_entry_price",
                    "current_price","unrealised_pnl","status","opened_at"]
            rows = cur.fetchall()
    return [dict(zip(cols, r)) for r in rows]


@router.get("/portfolio")
async def get_portfolio():
    """Real Alpaca broker NAV when configured; internal ledger otherwise."""
    try:
        from agent.alpaca_client import alpaca as _a
    except Exception:
        _a = None
    if _a is not None and hasattr(_a, "is_configured") and _a.is_configured():
        account = await _a.get_account()
        hist = await _a.portfolio_history(days=30)
        nav_history = _normalise_nav(hist.get("nav_history", []))
        equity = float(account.get("equity", 0) or 0)
        cash = float(account.get("cash", 0) or 0)
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
            "buying_power": float(account.get("buying_power", 0) or 0),
            "drawdown_pct": drawdown_pct,
            "halted": False,
            "nav_history": nav_history,
            "updated_at": None,
        }
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT cash_balance, nav, drawdown_pct, halted, updated_at
                FROM portfolio_state ORDER BY id DESC LIMIT 1
            """)
            row = cur.fetchone()
    if not row:
        return {"source": "ledger", "nav": 10000, "cash": 10000, "equity": 10000,
                "drawdown_pct": 0.0, "halted": False, "nav_history": [], "updated_at": None}
    keys = ["cash","nav","drawdown_pct","halted","updated_at"]
    out = dict(zip(keys, row))
    out["source"] = "ledger"
    out["equity"] = out["nav"]
    out["nav_history"] = []
    out["buying_power"] = 0
    return out
