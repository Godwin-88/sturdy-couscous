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
    """Fund end-to-end status: anchor gates + live CC3 executor account/balance +
    latest attested-NAV report + fund credit-decision status (read-only, non-fatal).

    Sources, in order: Redis (attestation report) → CreditGraph decision list →
    execution-service /account + /balance (CC3). Any failure degrades to
    ``reachable=false`` — never raises (the dashboard must stay up on paper).
    """
    import httpx

    borrower_id = os.getenv("FUND_BORROWER_ID", "fund_graphalpha")
    exc_url = os.getenv("EXECUTION_SERVICE_URL", "http://execution-service:8081")
    att_url = os.getenv("ATTESTATION_SERVICE_URL", "http://attestation-service:8080")

    report = _cached("fund:attestation_report")

    # ── CC3 executor (lender) account + live balance ─────────────────────
    cc3 = {"reachable": False, "account": None, "free_planck": None, "free_ctc": None}
    try:
        acc = httpx.get(f"{exc_url}/account", timeout=4).json()
        cc3["account"] = acc.get("address")
        cc3["ss58_format"] = acc.get("ss58Format")
        bal = httpx.get(f"{exc_url}/balance",
                        params={"address": acc.get("address")}, timeout=6).json()
        cc3["free_planck"] = bal.get("freePlanck")
        free = bal.get("freePlanck")
        if free:
            # polkadot/api returns hex-encoded balance values on some versions
            # ("0x...") and decimal strings on others — auto-detect base.
            cc3["free_ctc"] = round(int(free, 0) / 1e18, 6)  # 1 CTC = 1e18 planck
        cc3["reachable"] = True
    except Exception:
        cc3["reachable"] = False

    # ── Attestation service reachability (the /verify path) ───────────────
    attest_reachable = False
    try:
        r = httpx.get(f"{att_url}/health", timeout=3)
        attest_reachable = r.status_code == 200
    except Exception:
        attest_reachable = False

    # ── Latest fund credit decision (from the KG, read-only) ──────────────
    decision = None
    try:
        from creditgraph.graph.credit_graph import list_credit_decisions
        import asyncio

        async def _latest() -> dict | None:
            rows = await list_credit_decisions(borrower_id)
            if not rows:
                return None
            d = rows[0]
            return {
                "decision_id": d.decision_id,
                "recommended_amount": d.recommended_amount,
                "collateral_value": d.collateral_value,
                "credit_score": d.credit_score,
                "probability_of_default": d.probability_of_default,
                "decision_status": d.decision_status.value,
                "approval_status": d.approval_status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }

        decision = asyncio.run(_latest())
    except Exception:
        decision = None

    return {
        "borrower_id": borrower_id,
        "nav_anchor_contract": os.getenv("NAV_ANCHOR_CONTRACT", "").strip()[:10] + "…"
        if os.getenv("NAV_ANCHOR_CONTRACT", "").strip() else None,
        "relay_configured": bool(os.getenv("WEB3_RELAY_URL", "").strip()),
        "offline_ok": True,
        "cc3_execution": cc3,
        "attestation_reachable": attest_reachable,
        "latest_report": report,
        "latest_decision": decision,
    }
