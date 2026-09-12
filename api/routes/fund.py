"""Fund NAV-attestation endpoints — read-only, Redis-backed (H1–3 / RWA track).

Surfaces the strategy fund's latest attested-NAV report (snapshot digest, on-chain
anchor status, attestation status, evidence-chain root) that fund_attestation.py
publishes to Redis each cycle. Read-only: no execution endpoint — anchoring stays
behind operator-held keys (U6/U31).
"""
import os
import json

import redis
from fastapi import APIRouter

router = APIRouter(prefix="/fund", tags=["Fund"])


def _r() -> redis.Redis:
    return redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                       port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=True)


def _cached(key: str):
    raw = _r().get(key)
    if not raw:
        return None
    return json.loads(raw)


@router.get("/attestation-report")
def attestation_report():
    """Latest fund NAV-attestation report (snapshot/digest/anchor/chain)."""
    data = _cached("fund:attestation_report")
    return {"report": data, "cached": data is not None}


@router.get("/status")
def status():
    """Fund attestation config: anchor mode gates + borrower id (no secrets)."""
    return {
        "borrower_id": os.getenv("FUND_BORROWER_ID", "fund_graphalpha"),
        "nav_anchor_contract": bool(os.getenv("NAV_ANCHOR_CONTRACT", "").strip()),
        "relay_configured": bool(os.getenv("WEB3_RELAY_URL", "").strip()),
        "offline_ok": True,
    }