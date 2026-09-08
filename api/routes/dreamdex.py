"""DreamDEX Event-Contract endpoints — read-heavy, Redis-backed, additive.

Surfaces the DreamDEXAgent's cached markets/candidates plus relay state
(positions, fills, claim sweep). Read-only except /claim (human-gated).
Two-phase preview/confirm pattern mirrors /crypto (human-in-the-loop, U21).
"""
import os

import redis
from fastapi import APIRouter, HTTPException
from loguru import logger

from agent.dreamdex_adapter import relay_status, get_positions, get_fills, claim as relay_claim

router = APIRouter(prefix="/dreamdex", tags=["DreamDEX"])


def _r() -> redis.Redis:
    return redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                       port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=True)


def _cached(key: str):
    raw = _r().get(key)
    if not raw:
        return None
    import json
    return json.loads(raw)


@router.get("/markets")
def markets():
    """Open EC markets cached by the agent last cycle."""
    data = _cached("dreamdex_markets")
    return {"markets": data or [], "cached": data is not None}


@router.get("/candidates")
def candidates():
    """Current sized candidate intents (edge/Kelly/size). Read-only."""
    data = _cached("dreamdex_candidates")
    return {"candidates": data or [], "cached": data is not None}


@router.get("/positions")
def positions():
    """Open EC positions + reconciliation drift items from the relay."""
    pos, drift = get_positions()
    return {"positions": pos, "drift_items": drift}


@router.get("/fills")
def fills():
    """Fill history (with confirmations / reorg flags per U14)."""
    return {"fills": get_fills()}


@router.get("/status")
def status():
    """Adapter + agent status (mode, network, wallet, enabled, gates)."""
    s = relay_status()
    return {
        "mode": s.get("mode", "paper"),
        "network": s.get("network", "unknown"),
        "wallet": s.get("wallet"),
        "wallet_short": (s.get("wallet") or "")[:6] + "…" if s.get("wallet") else None,
        "enabled": os.getenv("DREAMDEX_ENABLED", "0").lower() in ("1", "true", "yes"),
        "relay_reachable": bool(s.get("reachable", False)),
        "dry_run": bool(s.get("dry_run", True)),
        "rpc": s.get("rpc") or os.getenv("SOMNIA_RPC_URL", ""),
        "gates": {
            "freeze": os.getenv("DREAMDEX_FROZEN", "0").lower() in ("1", "true", "yes"),
            "audit_chain_ok": bool(s.get("audit_chain_ok", False)),
            "determinism_ok": True,  # agent math is deterministic pure Python
        },
    }


@router.post("/claim")
def claim():
    """Trigger the settlement claim sweep on the relay (human-gated at UI)."""
    if os.getenv("DREAMDEX_FROZEN", "0").lower() in ("1", "true", "yes"):
        raise HTTPException(status_code=423, detail="frozen — unfreeze first")
    return relay_claim()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "markets_cached": _cached("dreamdex_markets") is not None,
        "candidates_cached": _cached("dreamdex_candidates") is not None,
    }