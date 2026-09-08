"""Tests for the Creditcoin execution adapter (E10)."""

from __future__ import annotations

import pytest
from httpx import Response

from creditgraph.models import (
    CreditDecision,
    CreditExecution,
    DecisionStatus,
    ExecutionStatus,
)
from creditgraph.services import execution as execution_service


class _FakeAsyncClient:
    """Minimal httpx.AsyncClient stand-in returning a canned response."""

    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self._status_code = status_code
        self._posted: dict | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url: str, json: dict | None = None, **kwargs):
        self._posted = json
        return Response(self._status_code, json=self._payload)


class _FakeTx:
    def __init__(self):
        self._queries: list[tuple[str, dict]] = []


class _FakeResult:
    def __init__(self, records):
        self._records = records

    async def single(self):
        return self._records[0] if self._records else None


class _FakeSession:
    def __init__(self, records=None):
        self._records = records or []
        self._queries: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query: str, *args, **params):
        if args and isinstance(args[0], dict):
            params = {**args[0], **params}
        self._queries.append((query, params))
        return _FakeResult(self._records)

    async def begin_transaction(self):
        return _FakeTxContext(self)


class _FakeTxContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query: str, *args, **params):
        if args and isinstance(args[0], dict):
            params = {**args[0], **params}
        self._session._queries.append((query, params))
        return _FakeResult([])


class _FakeDriver:
    def __init__(self, records=None):
        self._records = records or []
        self._sessions: list[_FakeSession] = []

    def session(self):
        sess = _FakeSession(self._records)
        self._sessions.append(sess)
        return sess


def _decision(approval_status: str = "approved") -> CreditDecision:
    return CreditDecision(
        decision_id="dec_1",
        borrower_id="borrower_demo_alice",
        requested_amount=100000.0,
        recommended_amount=80000.0,
        collateral_value=95000.0,
        required_collateral_ratio=0.25,
        credit_score=72.0,
        probability_of_default=0.03,
        expected_loss=2400.0,
        risk_regime="high_volatility",
        stress_result=1.9,
        decision_status=DecisionStatus.APPROVED,
        approval_status=approval_status,
    )


@pytest.mark.asyncio
async def test_execute_refuses_unapproved(monkeypatch):
    """A decision that is not human-approved must never be executed (E10 safety)."""
    decision = _decision(approval_status="pending")
    with pytest.raises(RuntimeError, match="approved"):
        await execution_service.execute_credit_decision(
            decision, to="5G1qRyfXeroVHGQx37gh6xGbMWXWFPESAFmUhLKxmU6J9nW"
        )


@pytest.mark.asyncio
async def test_execute_finalized(monkeypatch):
    """A finalized on-chain transfer yields FINALIZED execution."""
    payload = {
        "txHash": "0x123abc",
        "status": "finalized",
        "block": "12345",
        "blockHash": "0xdeadbeef",
        "extrinsicIndex": 3,
        "success": True,
    }
    fake = _FakeAsyncClient(payload)
    monkeypatch.setattr(execution_service.httpx, "AsyncClient", lambda **kw: fake)

    exec_ = await execution_service.execute_credit_decision(
        _decision(), to="0x350532caba9478983e37f2f83744293bb1a3c9d1"
    )

    assert exec_.status == ExecutionStatus.FINALIZED
    assert exec_.tx_hash == "0x123abc"
    assert exec_.block == "12345"
    assert exec_.extrinsic_index == 3
    assert exec_.failure is None
    assert fake._posted == {"to": "0x350532caba9478983e37f2f83744293bb1a3c9d1", "amount": "80000.0", "amountPlanck": None}


@pytest.mark.asyncio
async def test_execute_failed_dispatch(monkeypatch):
    """A dispatch failure is recorded as FAILED, never conflated with success."""
    payload = {
        "txHash": "0xbadd00d",
        "status": "finalized",
        "success": False,
        "dispatchError": "InsufficientBalance",
    }
    fake = _FakeAsyncClient(payload)
    monkeypatch.setattr(execution_service.httpx, "AsyncClient", lambda **kw: fake)

    exec_ = await execution_service.execute_credit_decision(
        _decision(), to="0x123"
    )

    assert exec_.status == ExecutionStatus.FAILED
    assert exec_.failure == "InsufficientBalance"


@pytest.mark.asyncio
async def test_execute_service_unreachable(monkeypatch):
    """When the execution service is down, status is TIMEOUT with reason."""

    class _RaisingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, **kwargs):
            raise execution_service.httpx.ConnectError("connection refused")

    monkeypatch.setattr(execution_service.httpx, "AsyncClient", lambda **kw: _RaisingClient())

    exec_ = await execution_service.execute_credit_decision(
        _decision(), to="0x123"
    )

    assert exec_.status == ExecutionStatus.TIMEOUT
    assert exec_.failure == "execution_service_unreachable"


@pytest.mark.asyncio
async def test_execute_executor_not_configured(monkeypatch):
    """A 503 from the execution service (no seed) maps to FAILED."""
    fake = _FakeAsyncClient({"error": "executor_not_configured"}, status_code=503)
    monkeypatch.setattr(execution_service.httpx, "AsyncClient", lambda **kw: fake)

    exec_ = await execution_service.execute_credit_decision(
        _decision(), to="0x123"
    )

    assert exec_.status == ExecutionStatus.FAILED
    assert exec_.failure == "executor_not_configured"


@pytest.mark.asyncio
async def test_approve_persists(monkeypatch):
    """Approve flips approval_status + decision_status to approved."""
    driver = _FakeDriver(records=[object()])
    monkeypatch.setattr(execution_service, "get_driver", lambda: driver)

    ok = await execution_service.approve_credit_decision("dec_1")

    assert ok is True
    queries = driver._sessions[0]._queries
    assert len(queries) == 1
    assert "approval_status = 'approved'" in queries[0][0]
    assert queries[0][1]["decision_id"] == "dec_1"


@pytest.mark.asyncio
async def test_persist_execution_emits_queries(monkeypatch):
    """persist_execution writes Execution node + EXECUTED_AS + flips decision."""
    driver = _FakeDriver()
    monkeypatch.setattr(execution_service, "get_driver", lambda: driver)

    exec_ = CreditExecution(
        execution_id="exec_1",
        decision_id="dec_1",
        borrower_id="borrower_demo_alice",
        to="0x123",
        amount=80000.0,
        status=ExecutionStatus.FINALIZED,
        tx_hash="0xabc",
        block="12345",
    )
    await execution_service.persist_execution(exec_)

    queries = driver._sessions[0]._queries
    assert len(queries) == 2
    # First query merges the CreditExecution node + EXECUTED_AS relationship.
    assert "MERGE (x:CreditExecution" in queries[0][0]
    assert "EXECUTED_AS" in queries[0][0]
    # Second query flips the decision to executed with the tx hash.
    assert "decision_status = 'executed'" in queries[1][0]
    assert queries[1][1]["tx_hash"] == "0xabc"


@pytest.mark.asyncio
async def test_persist_execution_pending_no_flip(monkeypatch):
    """A pending execution does not flip the decision to executed."""
    driver = _FakeDriver()
    monkeypatch.setattr(execution_service, "get_driver", lambda: driver)

    exec_ = CreditExecution(
        execution_id="exec_2",
        decision_id="dec_2",
        borrower_id="borrower_demo_alice",
        to="0xdef",
        amount=100.0,
        status=ExecutionStatus.PENDING,
    )
    await execution_service.persist_execution(exec_)

    queries = driver._sessions[0]._queries
    assert len(queries) == 1
    assert "decision_status" not in queries[0][0]