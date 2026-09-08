"""Hermetic tests for the P10 CreditGraphAgent + creditgraph_adapter.

Runs entirely in-process (no Neo4j / Redis / testnet). Stubs the adapter's
http surface — the same 3-layer hermetic style as tests/test_dreamdex_agent.py.
"""

from __future__ import annotations

import asyncio

import pytest

import agent.creditgraph_agent as cgmod
import agent.creditgraph_adapter as cad
from agent.creditgraph_agent import CreditGraphAgent


def _run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch):
    """Point the adapter's http surface at hermetic fakes (no network)."""
    monkeypatch.setattr(cgmod, "ENABLED", True)
    monkeypatch.setattr(CreditGraphAgent, "_cache", lambda self, k, v: None)

    # The agent calls `cadapter.*` (module-level import). Patch that bound name,
    # not the `cad` re-import (which the agent never sees).
    monkeypatch.setattr(cgmod, "cadapter", cad)
    monkeypatch.setattr(cad, "chains", lambda: [])
    monkeypatch.setattr(cad, "execution_health", lambda: {"reachable": False})
    monkeypatch.setattr(cad, "merged_health", lambda: {"reachable": False})
    monkeypatch.setattr(cad, "credit_score", lambda profile: {"score": -1.0})


def test_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(cgmod, "ENABLED", False)
    assert _run(CreditGraphAgent().run(regime="Bull Trend")) == []


def test_chains_down_returns_empty():
    """attestation-service unreachable ⇒ zero candidates, no crash."""
    assert _run(CreditGraphAgent().run(regime="Bull Trend")) == []


def test_chains_up_produces_intents(monkeypatch):
    monkeypatch.setattr(cad, "chains", lambda: [{"chainKey": 1, "name": "ethereum-sepolia"}])
    monkeypatch.setattr(cad, "execution_health", lambda: {"status": "ok"})
    monkeypatch.setattr(cad, "merged_health", lambda: {"status": "ok"})

    def _score(profile):
        return {
            "score": 72.5 if profile["borrower_id"].endswith("1") else 41.0,
            "probability_of_default": 2.3 if profile["borrower_id"].endswith("1") else 91.0,
        }

    monkeypatch.setattr(cad, "credit_score", _score)

    cands = _run(CreditGraphAgent().run(regime="High Volatility"))
    assert len(cands) == 2
    c1, c2 = cands
    # Strong borrower → approve intent; weak → review
    assert c1["decision"] == "approve" and c1["status"] == "intent"
    assert c2["decision"] == "review" and c2["status"] == "intent"
    # Never autonomously executes
    assert "approval_status" not in c1 or c1.get("approval_status") is None


def test_candidate_shape():
    cands = _run(CreditGraphAgent().run(regime="Recession"))
    for c in cands:
        assert {"borrower_id", "kind", "score", "regime", "chain", "status"} <= set(c)


def test_adapter_credit_score_graceful(monkeypatch):
    """httpx transport failure ⇒ -1 score fallback, never raises."""

    class _Fail:
        def post(self, url, json=None, **kw):
            raise RuntimeError("refused")

    monkeypatch.setattr(cad, "_client", lambda: _Fail())
    assert cad.credit_score({"fico_score": 600})["score"] == -1.0


def test_adapter_verify_evidence_graceful(monkeypatch):
    class _Fail:
        def post(self, url, json=None, **kw):
            raise RuntimeError("refused")

    monkeypatch.setattr(cad, "_client", lambda: _Fail())
    res = cad.verify_evidence("0xabc")
    assert res["verified"] is False and res["status"] == "unverified"