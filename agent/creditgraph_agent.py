"""
creditgraph_agent.py
────────────────────
Per-chain CreditGraph agent (P10 §8, tenet upgrades U18–U24).

Per orchestrator cycle:
  1. Probes the Attestcoin chain stack (attestation-service /chains) and the
     Creditcoin execution layer (execution-service /health) through the
     creditgraph_adapter — same defensive shape as DreamDEXAgent.
  2. For each demo borrower profile, pulls a deterministic credit score from
     the merged GraphAlpha gateway (/api/v1/risk/credit-score) — the shared
     kernel of GraphAlpha's quant engine, zero LLM drift on the number.
  3. Publish `creditgraph:*` Redis keys for the API + frontend panel.
  4. Produces *intent* candidates (never executed without a human-approved
     decision — U6/U21 gate).

Self-disables when CREDITGRAPH_ENABLED is unset/0 (identical to DreamDEX).
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import redis
from loguru import logger

try:
    import creditgraph_adapter as cadapter  # cwd = agent/ (agent-worker)
except ImportError:                          # pragma: no cover
    from agent import creditgraph_adapter as cadapter  # type: ignore

ENABLED = os.getenv("CREDITGRAPH_ENABLED", "0").lower() in ("1", "true", "yes")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
DEMO_BORROWERS_JSON = os.getenv(
    "CREDITGRAPH_DEMO_BORROWERS",
    json.dumps([
        {"borrower_id": "demo_borrower_1", "fico_score": 645.0,
         "dti_ratio": 0.35, "loan_to_value": 0.60,
         "requested_amount": 100_000.0},
        {"borrower_id": "demo_borrower_2", "fico_score": 720.0,
         "dti_ratio": 0.22, "loan_to_value": 0.45,
         "requested_amount": 60_000.0},
    ]),
)
MIN_CREDIT_SCORE = float(os.getenv("CREDITGRAPH_MIN_SCORE", "50.0"))


def _demo_borrowers() -> list[dict]:
    try:
        raw = json.loads(DEMO_BORROWERS_JSON)
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


class CreditGraphAgent:
    """Cross-chain credit-intelligence agent (shared KG, per-chain adapters)."""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self.enabled = ENABLED

    @property
    def redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
            )
        return self._redis

    # ── Main entry point (called by orchestrator, 1-line hook) ─────────────
    async def run(self, regime: str, signals: list[dict] | None = None) -> list[dict]:
        if not self.enabled:
            logger.debug("[CreditGraph] Agent disabled — set CREDITGRAPH_ENABLED=1")
            return []

        # 1. Chain-stack probe (best-effort; empty ⇒ graceful no-op).
        chains = cadapter.chains()
        exec_h = cadapter.execution_health()
        api_h = cadapter.merged_health()

        chain_ok = bool(chains)
        if not chain_ok:
            logger.warning(
                "[CreditGraph] attestation-service unreachable — 0 candidates this cycle"
            )

        self._cache(
            "creditgraph:services",
            {
                "chains": chains,
                "attestation_reachable": chain_ok,
                "execution_reachable": bool(exec_h.get("reachable", True)),
                "graphalpha_api_reachable": bool(api_h.get("status") == "ok"),
                "checked_at": _now(),
            },
        )

        # 2. Deterministic scoring of demo borrower profiles (shared quant core).
        candidates: list[dict] = []
        for b in _demo_borrowers():
            profile = {
                "borrower_id": b.get("borrower_id", ""),
                "fico_score": float(b.get("fico_score", 600.0)),
                "dti_ratio": float(b.get("dti_ratio", 0.3)),
                "loan_to_value": float(b.get("loan_to_value", 0.5)),
            }
            res = cadapter.credit_score(profile)
            score = float(res.get("score", -1.0))
            if score < 0:
                continue
            candidates.append(
                {
                    "kind": "credit-intent",
                    "borrower_id": profile["borrower_id"],
                    "score": round(score, 2),
                    "probability_of_default": round(
                        float(res.get("probability_of_default", 0.0)), 2
                    ),
                    "regime": regime,
                    "chain": "attestcoin/sepolia→creditcoin",
                    "status": "intent",       # U6/U21: never executes on its own
                    "decision": "approve" if score >= MIN_CREDIT_SCORE else "review",
                }
            )

        self._cache("creditgraph:candidates", candidates)

        logger.info(
            f"[CreditGraph] chains={len(chains)} | {len(candidates)} candidates "
            f"(regime={regime})"
        )
        return candidates

    # ── Persistence (best-effort, mirrors dreamdex_agent) ──────────────────
    def _cache(self, key: str, payload: Any):
        try:
            self.redis.set(key, json.dumps(payload), ex=300)
        except Exception as e:
            logger.warning(f"[CreditGraph] redis cache {key} failed: {e}")


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


__all__ = ["CreditGraphAgent"]