import json
from fastapi import APIRouter
import psycopg2
import os

router = APIRouter(prefix="/signals", tags=["signals"])

def _conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "graphalpha"),
        user=os.getenv("POSTGRES_USER", "graphalpha"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


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
