"""Deterministic credit risk + decision tests (DoD)."""

import asyncio

import pytest

from creditgraph.models import (
    Collateral,
    CurrentBorrowerState,
    DecisionStatus,
    Liability,
    RiskRegime,
)
from creditgraph.services import credit_risk


def _state(**overrides) -> CurrentBorrowerState:
    s = CurrentBorrowerState(
        borrower_id="borrower_test",
        requested_amount=100_000.0,
        fico_score=645.0,
        total_collateral_value=95_000.0,
        total_liabilities=12_000.0,
        market_regime=RiskRegime.HIGH_VOLATILITY,
        collateral=[
            Collateral(
                asset_id="eth_usdc_pool",
                symbol="ETH+USDC",
                valuation=95_000.0,
                quantity=1.0,
                haircut=0.15,
                correlated_group="eth_l2",
            )
        ],
        liabilities=[Liability(protocol="Aave", outstanding=12_000.0, asset_symbol="USDC")],
        attestation_refs=["attest_eth_deposit_001", "attest_usdc_loan_002"],
    )
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_pd_deterministic():
    s = _state()
    a = credit_risk.probability_of_default(s)["outputs"]["probability_of_default"]
    b = credit_risk.probability_of_default(s)["outputs"]["probability_of_default"]
    assert a == b


def test_pd_bounds():
    pd = credit_risk.probability_of_default(_state())["outputs"]["probability_of_default"]
    assert 0.001 <= pd <= 0.50


def test_score_range():
    s = _state()
    r = credit_risk.credit_score(
        s,
        credit_risk.probability_of_default(s),
        credit_risk.compute_ltv(s, s.requested_amount),
        credit_risk.concentration_factor(s),
    )
    assert 0 <= r["outputs"]["score"] <= 100


def test_recommendation_leq_request():
    s = _state()
    pd = credit_risk.probability_of_default(s)
    ltv = credit_risk.compute_ltv(s, s.requested_amount)
    stress = credit_risk.stress_ltv(
        s, s.requested_amount, ltv["inputs"]["adjusted_collateral"]
    )
    conc = credit_risk.concentration_factor(s)
    rec = credit_risk.recommended_exposure(s, pd, ltv, stress, conc)["outputs"]["recommended_amount"]
    assert rec <= s.requested_amount


def test_build_assessment_decision_shape():
    s = _state()
    assessment, decision, model_results = credit_risk.build_assessment_and_decision(s)
    assert assessment.borrower_id == "borrower_test"
    assert decision.borrower_id == "borrower_test"
    assert decision.decision_status == DecisionStatus.RECOMMENDED
    assert "m_credit_score" in model_results
    assert decision.model_versions
    assert decision.attestation_references == ["attest_eth_deposit_001", "attest_usdc_loan_002"]


def test_persist_decision_emits_queries(monkeypatch):
    """Verify the graph persistence layer executes queries (no DB needed)."""
    from creditgraph.graph import credit_graph

    calls = []

    class FakeTx:
        async def run(self, q, *args, **params):
            if args and isinstance(args[0], dict):
                params = {**args[0], **params}
            calls.append(q)
            return None

    class FakeSession:
        def __init__(self):
            self._tx = FakeTx()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def begin_transaction(self):
            """Return an async CM yielding a FakeTx (matches neo4j driver)."""

            class _Ctx:
                def __init__(self, tx):
                    self._tx = tx

                async def __aenter__(self):
                    return self._tx

                async def __aexit__(self, *a):
                    return False

            return _Ctx(self._tx)

    class FakeDriver:
        def session(self):
            return FakeSession()

    monkeypatch.setattr(credit_graph, "get_driver", lambda: FakeDriver())

    s = _state()
    assessment, decision, model_results = credit_risk.build_assessment_and_decision(s)

    async def run():
        await credit_graph.persist_credit_decision(decision, assessment, model_results)

    asyncio.run(run())
    assert calls, "persist should emit at least one query"
