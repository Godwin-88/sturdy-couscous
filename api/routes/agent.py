import json
import os
from fastapi import APIRouter
import redis

router = APIRouter(prefix="/agent", tags=["agent"])


def _redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


@router.get("/status")
def agent_status():
    """
    Returns the latest cycle status written by the orchestrator.
    Falls back to safe defaults if the agent hasn't run yet.
    """
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
