import json
import os
from fastapi import APIRouter
import redis
import psycopg2

router = APIRouter(prefix="/agent", tags=["agent"])


def _redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


def _conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "graphalpha"),
        user=os.getenv("POSTGRES_USER", "graphalpha"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


@router.get("/status")
def agent_status():
    r = _redis()
    raw = r.get("graphalpha:agent_status")
    if raw:
        return json.loads(raw)
    return {
        "regime":            "LowVolatility",
        "regime_confidence": 0.65,
        "active_strategies": [],
        "signals_generated": 0,
        "orders_approved":   0,
        "last_cycle_at":     None,
        "halted":            False,
        "cycle_duration_s":  0.0,
    }


@router.get("/risk")
def agent_risk():
    """
    Returns pre-trade risk metrics: position concentration, gross/net exposure,
    drawdown vs limit, and Kelly fraction vs actual sizing.
    """
    r = _redis()
    raw_status = r.get("graphalpha:agent_status")
    status = json.loads(raw_status) if raw_status else {}

    # Pull positions and portfolio from Postgres
    positions = []
    portfolio = {"nav": 10000, "cash": 10000, "drawdown_pct": 0.0, "halted": False}
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ticker, direction, quantity, avg_entry_price, current_price,
                           quantity * (current_price - avg_entry_price) AS unrealised_pnl
                    FROM positions WHERE status = 'open'
                """)
                cols = ["ticker", "direction", "quantity", "avg_entry_price",
                        "current_price", "unrealised_pnl"]
                positions = [
                    {k: (float(v) if k not in ("ticker", "direction") else v)
                     for k, v in zip(cols, row)}
                    for row in cur.fetchall()
                ]

                cur.execute("""
                    SELECT cash_balance, nav, drawdown_pct, halted
                    FROM portfolio_state ORDER BY id DESC LIMIT 1
                """)
                row = cur.fetchone()
                if row:
                    portfolio = {"cash": float(row[0]), "nav": float(row[1]),
                                 "drawdown_pct": float(row[2]), "halted": row[3]}
    except Exception:
        pass

    nav = portfolio.get("nav", 10000) or 10000

    # Concentration: % NAV per ticker
    concentration = []
    gross_exposure = 0.0
    net_exposure = 0.0
    for p in positions:
        mkt_val = abs(p["quantity"] * p["current_price"])
        pct_nav = mkt_val / nav if nav else 0
        sign = 1 if p["direction"] == "buy" else -1
        gross_exposure += mkt_val
        net_exposure += sign * mkt_val
        concentration.append({
            "ticker":   p["ticker"],
            "mkt_val":  round(mkt_val, 2),
            "pct_nav":  round(pct_nav, 4),
            "direction": p["direction"],
            "pnl":      round(p["unrealised_pnl"], 2),
        })

    concentration.sort(key=lambda x: x["pct_nav"], reverse=True)

    # Drawdown limit (configurable via env, default 10%)
    dd_limit = float(os.getenv("DRAWDOWN_LIMIT", "0.10"))
    dd_current = portfolio.get("drawdown_pct", 0.0) or 0.0
    dd_remaining = max(0.0, dd_limit - dd_current)

    # Kelly criterion estimate from recent signals win rate
    kelly_fraction = None
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT AVG(CASE WHEN signal_score > 0 THEN 1.0 ELSE 0.0 END) AS win_rate,
                           AVG(ABS(signal_score)) AS avg_score
                    FROM order_audit
                    WHERE created_at > NOW() - INTERVAL '7 days'
                """)
                row = cur.fetchone()
                if row and row[0] is not None:
                    win_rate = float(row[0])
                    avg_score = float(row[1]) if row[1] else 1.0
                    # Simplified Kelly: f* = (bp - q) / b  where b=avg_score, p=win_rate, q=1-win_rate
                    b = avg_score
                    p = win_rate
                    q = 1 - win_rate
                    kelly_fraction = round(max(0.0, (b * p - q) / b), 4) if b > 0 else 0.0
    except Exception:
        pass

    return {
        "nav":              round(nav, 2),
        "gross_exposure":   round(gross_exposure, 2),
        "net_exposure":     round(net_exposure, 2),
        "gross_pct_nav":    round(gross_exposure / nav, 4) if nav else 0,
        "net_pct_nav":      round(net_exposure / nav, 4) if nav else 0,
        "drawdown_current": round(dd_current, 4),
        "drawdown_limit":   round(dd_limit, 4),
        "drawdown_remaining": round(dd_remaining, 4),
        "kelly_fraction":   kelly_fraction,
        "concentration":    concentration,
        "n_positions":      len(positions),
        "halted":           portfolio.get("halted", False),
    }
