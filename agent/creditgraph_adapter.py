"""
creditgraph_adapter.py
──────────────────────
HTTP adapters for the CreditGraph (P10) chain stack.

Mirrors the dreamdex_adapter conventions (try/except + logger.warning,
graceful degradation) while talking to:

  - attestation-service  (:8080, Node, @gluwa/usc-sdk)  — Attestcoin evidence
  - execution-service    (:8081, Node, @polkadot/api)   — Creditcoin execution
  - GraphAlpha merged API (:8000, /api/v1/*)            — deterministic scoring

Every call is defensive: on transport/HTTP error it logs and returns a
zero-value fallback so the agent can never crash the orchestrator cycle.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from loguru import logger

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

ATTESTATION_URL = os.getenv("ATTESTATION_SERVICE_URL", "http://attestation-service:8080")
EXECUTION_URL = os.getenv("EXECUTION_SERVICE_URL", "http://execution-service:8081")
GRAPHALPHA_API_URL = os.getenv("GRAPHALPHA_API_URL", "http://api:8000")
TIMEOUT = float(os.getenv("CREDITGRAPH_HTTP_TIMEOUT", "10"))


def _client() -> Any:
    if httpx is None:
        raise RuntimeError("httpx not installed")
    return httpx.Client(timeout=TIMEOUT)


# ── Attestation service (Attestcoin evidence) ──────────────────────────────────
def attestation_health() -> dict:
    try:
        r = _client().get(f"{ATTESTATION_URL}/health")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[CreditGraph] attestation /health failed: {e}")
        return {"reachable": False}


def chains() -> list[dict]:
    """Supported Attestcoin source chains (e.g. Ethereum Sepolia chainKey 1)."""
    try:
        r = _client().get(f"{ATTESTATION_URL}/chains")
        r.raise_for_status()
        return r.json().get("chains", [])
    except Exception as e:
        logger.warning(f"[CreditGraph] attestation /chains failed: {e}")
        return []


def verify_evidence(tx_hash: str, chain_key: Optional[int] = None) -> dict:
    """POST /verify → transaction inclusion proof + attestation status."""
    try:
        payload: dict[str, Any] = {"txHash": tx_hash}
        if chain_key is not None:
            payload["chainKey"] = chain_key
        r = _client().post(f"{ATTESTATION_URL}/verify", json=payload)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[CreditGraph] attestation /verify failed: {e}")
        return {"verified": False, "status": "unverified", "reason": "service_unreachable"}


# ── Execution service (Creditcoin) ────────────────────────────────────────────
def execution_health() -> dict:
    try:
        r = _client().get(f"{EXECUTION_URL}/health")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[CreditGraph] execution /health failed: {e}")
        return {"reachable": False}


def execution_account() -> dict:
    try:
        r = _client().get(f"{EXECUTION_URL}/account")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[CreditGraph] execution /account failed: {e}")
        return {"reachable": False}


def execution_balance(address: str) -> dict:
    try:
        r = _client().get(f"{EXECUTION_URL}/balance", params={"address": address})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[CreditGraph] execution /balance failed: {e}")
        return {"address": address, "freePlanck": "0"}


def execute_transfer(to: str, amount: Optional[float] = None, amount_planck: Optional[str] = None) -> dict:
    """POST /execute — only reachable when the executor seed is configured (human-gated)."""
    try:
        payload: dict[str, Any] = {"to": to}
        if amount is not None:
            payload["amount"] = amount
        if amount_planck is not None:
            payload["amountPlanck"] = amount_planck
        r = _client().post(f"{EXECUTION_URL}/execute", json=payload)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[CreditGraph] execution /execute failed: {e}")
        return {"ok": False, "error": "service_unreachable"}


def monitor_transfer(tx_hash: str) -> dict:
    try:
        r = _client().post(f"{EXECUTION_URL}/monitor", json={"txHash": tx_hash})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[CreditGraph] execution /monitor failed: {e}")
        return {"status": "unknown"}


# ── Merged GraphAlpha API (deterministic scoring) ─────────────────────────────
def credit_score(profile: dict) -> dict:
    """POST /api/v1/risk/credit-score on the merged GraphAlpha gateway."""
    try:
        r = _client().post(f"{GRAPHALPHA_API_URL}/api/v1/risk/credit-score", json=profile)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[CreditGraph] merged API credit-score failed: {e}")
        return {"score": -1.0, "probability_of_default": -1.0}


def merged_health() -> dict:
    try:
        r = _client().get(f"{GRAPHALPHA_API_URL}/api/v1/health")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[CreditGraph] merged API /api/v1/health failed: {e}")
        return {"reachable": False}


__all__ = [
    "attestation_health", "chains", "verify_evidence",
    "execution_health", "execution_account", "execution_balance",
    "execute_transfer", "monitor_transfer", "credit_score", "merged_health",
]