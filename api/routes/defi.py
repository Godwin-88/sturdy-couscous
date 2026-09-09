"""DeFi endpoints — read-heavy, Redis-backed, additive (P11 Stage-5).

Surfaces the DeFiAgent's cached D1–D8 candidate stream plus the D6 oracle
integrity governor, EC/EVM positions, and the tamper-evident EvidenceChain
(cryptographic assurance layer, U25/U26). Read-only: no execution endpoint here
— every order stays behind the two-phase human gate (U6/U21) and the
eth_call-simulate-first relay path (U31).
"""
import os
import json

import redis
from fastapi import APIRouter, HTTPException
from loguru import logger

router = APIRouter(prefix="/defi", tags=["DeFi"])


def _r() -> redis.Redis:
    return redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                       port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=True)


def _cached(key: str):
    raw = _r().get(key)
    if not raw:
        return None
    return json.loads(raw)


@router.get("/candidates")
def candidates():
    """Current D1–D8 candidate stream (edge/Kelly/size), read-only."""
    data = _cached("defi:candidates")
    return {"candidates": data or [], "cached": data is not None}


@router.get("/governor")
def governor():
    """D6 oracle-integrity governor state (paused_evm / paused_ec)."""
    data = _cached("defi:governor")
    return {"governor": data or {}, "cached": data is not None}


@router.get("/sectors")
def sectors():
    """Candidate stream grouped by sector D1–D8 (venue + notional)."""
    data = _cached("defi:candidates") or []
    agg: dict[str, dict] = {}
    total = 0.0
    for c in data:
        s = c.get("sector") or "?"
        a = agg.setdefault(s, {"count": 0, "venue": c.get("venue"), "size_usd": 0.0})
        a["count"] += 1
        a["size_usd"] += float(c.get("size_usd") or 0.0)
        total += float(c.get("size_usd") or 0.0)
    return {"sectors": agg, "total_size_usd": total, "cached": bool(data)}


@router.get("/positions")
def positions():
    """Open EC positions (somnia relay, P9) + cached EVM positions (Stage-6 relay)."""
    pos, drift = [], []
    try:
        from agent.dreamdex_adapter import get_positions as ec_positions
        pos, drift = ec_positions()
    except Exception as e:  # pragmatic: relay down must not 500 the panel
        logger.warning(f"[Defi] EC positions read failed (non-fatal): {e}")
    evm = _cached("defi:evm_positions") or []
    return {"positions": pos, "drift_items": drift, "evm_positions": evm}


@router.get("/evidence")
def evidence():
    """EvidenceChain head/root/merkle + verify — the auditable decision trail."""
    out = {"head": None, "root": "", "merkle_root": "", "verify_ok": False, "cached": False}
    try:
        from agent.evidence_chain import EvidenceChain
        chain = EvidenceChain(store=_r())
        out["head"] = chain.head()
        out["root"] = chain.root()
        try:
            out["merkle_root"] = chain.merkle_root()
        except Exception:
            out["merkle_root"] = ""
        out["verify_ok"] = chain.verify_chain()
        out["cached"] = True
    except Exception as e:
        logger.warning(f"[DeFi] evidence read failed (non-fatal): {e}")
    return out


@router.get("/status")
def status():
    s = {}
    try:
        from agent.dreamdex_adapter import relay_status
        s = relay_status()
    except Exception:
        s = {}
    return {
        "enabled": os.getenv("DEFI_ENABLED", "0").lower() in ("1", "true", "yes"),
        "mode": os.getenv("DREAMDEX_TRADING_MODE", "paper"),
        "venue": "sepolia-evm + somnia-relay",
        "relay_reachable": bool(s.get("reachable", False)),
        "dry_run": bool(s.get("dry_run", True)),
        "gates": {
            "freeze": os.getenv("DEFI_FROZEN", "0").lower() in ("1", "true", "yes"),
            "min_lp_edge_pct": float(os.getenv("MIN_LP_EDGE_PCT", "0.03")),
            "min_lending_spread_pct": float(os.getenv("MIN_LENDING_SPREAD_PCT", "0.02")),
            "min_ec_edge_pct": float(os.getenv("MIN_EC_EDGE_PCT", "0.03")),
            "max_defi_exposure_pct": float(os.getenv("MAX_DEFI_EXPOSURE_PCT", "0.02")),
        },
    }


@router.get("/health")
def health():
    return {
        "status": "ok",
        "candidates_cached": _cached("defi:candidates") is not None,
        "governor_cached": _cached("defi:governor") is not None,
    }