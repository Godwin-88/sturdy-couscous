import os
import psycopg2
from fastapi import APIRouter

router = APIRouter(prefix="/positions", tags=["positions"])

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
def get_portfolio():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT cash_balance, nav, drawdown_pct, halted, updated_at
                FROM portfolio_state ORDER BY id DESC LIMIT 1
            """)
            row = cur.fetchone()
    if not row:
        return {"nav": 10000, "cash": 10000, "drawdown_pct": 0.0, "halted": False}
    keys = ["cash","nav","drawdown_pct","halted","updated_at"]
    return dict(zip(keys, row))
