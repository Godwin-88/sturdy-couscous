"""CreditGraph financial-engineer chat wiring (P11 / BUIDL-CTC RWA).

Verifies the additive seams that make the per-screen chat + Credit→Fund console
CreditGraph-aware:
  1. SCREEN_HINTS has a credit entry (attested-collateral GraphRAG query) and a
     defi entry.
  2. _live_screen_data("credit") bundles the fund financing loop into the chat
     context (fund_status / fund_attestation_report / alpaca_portfolio) —
     guarded/empty when the API is down, never raising.
  3. The shared SYSTEM_PROMPT contains the CREDIT-ATTESTED-FUND RULE markers so
     the LLM answers as a financial engineer over the attested-NAV borrower
     (collateral = anchored NAV, engine PD/LTV ground-truth, human-gated CC3
     disbursement).
Hermetic: no network, no testnet, no LLM calls.
"""
from __future__ import annotations

import os

os.environ.setdefault("REDIS_HOST", "redis")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("API_PORT", "8000")

from agent.financial_engineer import SYSTEM_PROMPT  # noqa: E402
from routes.chat import SCREEN_HINTS, _live_screen_data  # noqa: E402


def test_screen_hint_has_credit():
    hint = SCREEN_HINTS.get("credit", "")
    assert hint, "credit screen hint missing"
    for kw in ("credit", "collateral", "attested nav", "probability of default", "loan to value"):
        assert kw in hint, f"credit hint missing keyword {kw!r}"


def test_screen_hint_has_defi():
    assert SCREEN_HINTS.get("defi", ""), "defi screen hint missing"


def test_live_screen_data_credit_hermetic(monkeypatch):
    """_live_screen_data('credit') must build the fund bundle with
    zero network access (patched httpx.get) and never raise."""

    class _Resp:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            pass

    def _fake_get(url, *a, **k):
        us = str(url)
        if "fund/status" in us:
            return _Resp({
                "borrower_id": "fund_graphalpha",
                "nav_anchor_contract": "0x7fe6Db5c…",
                "cc3_execution": {"reachable": True, "account": "5Fsti…", "free_ctc": 10000.0},
                "attestation_reachable": True,
                "latest_report": {"digest": "sha256:abcd", "anchor_tx": "0x799b…"},
                "latest_decision": {
                    "decision_id": "42bb30626c6e",
                    "collateral_value": 90658.05,
                    "credit_score": 36.5,
                    "probability_of_default": 0.214,
                    "approval_status": "pending",
                },
            })
        if "fund/attestation-report" in us:
            return _Resp({"report": {"nav": 95429.53, "digest": "sha256:abcd"}, "cached": True})
        if "alpaca/portfolio" in us:
            return _Resp({"equity": 95429.53, "cash": -14008.0})
        return _Resp({})

    import httpx

    monkeypatch.setattr(httpx, "get", _fake_get)

    out = _live_screen_data("credit")
    assert isinstance(out, dict)
    assert out["fund_status"]["borrower_id"] == "fund_graphalpha"
    assert out["fund_status"]["cc3_execution"]["free_ctc"] == 10000.0
    assert out["fund_status"]["latest_decision"]["approval_status"] == "pending"
    assert out["fund_attestation_report"]["report"]["nav"] == 95429.53
    assert out["alpaca_portfolio"]["equity"] == 95429.53


def test_system_prompt_has_credit_rule():
    for marker in (
        "CREDIT-ATTESTED-FUND RULE",
        "fund_graphalpha",
        "NAVAnchor",
        "probability_of_default",
        "transferKeepAlive",
        "human-gated",
    ):
        assert marker in SYSTEM_PROMPT, f"SYSTEM_PROMPT missing credit marker {marker!r}"