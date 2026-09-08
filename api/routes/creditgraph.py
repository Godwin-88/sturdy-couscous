"""CreditGraph endpoints — read-heavy, Redis-backed, additive (P10).

Surfaces the CreditGraphAgent's cached chain-stack state and credit-intent
candidates. Read-only: execution never bypasses the human-approved decision
flow (U6/U21) — the merged /api/v1/risk/* surface owns writes.
"""
import os

import redis
from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/creditgraph", tags=["CreditGraph"])


def _r() -> redis.Redis:
    return redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                       port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=True)


def _cached(key: str):
    raw = _r().get(key)
    if not raw:
        return None
    import json
    return json.loads(raw)


@router.get("/services")
def services():
    """Chain-stack probe cached by the agent last cycle."""
    data = _cached("creditgraph:services")
    return {"services": data or {}, "cached": data is not None}


@router.get("/candidates")
def candidates():
    """Current credit-intent candidates from the shared quant core."""
    data = _cached("creditgraph:candidates")
    return {"candidates": data or [], "cached": data is not None}


@router.get("/status")
def status():
    """Agent status + human gates."""
    return {
        "enabled": os.getenv("CREDITGRAPH_ENABLED", "0").lower() in ("1", "true", "yes"),
        "freeze": os.getenv("CREDITGRAPH_FROZEN", "0").lower() in ("1", "true", "yes"),
        "llm_provider": os.getenv("LLM_PROVIDER", "deterministic"),
        "min_score": float(os.getenv("CREDITGRAPH_MIN_SCORE", "50.0")),
    }


@router.get("/health")
def health():
    return {
        "status": "ok",
        "services_cached": _cached("creditgraph:services") is not None,
        "candidates_cached": _cached("creditgraph:candidates") is not None,
    }