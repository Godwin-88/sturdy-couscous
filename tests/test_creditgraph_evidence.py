"""Tests for the Attestcoin evidence adapter (E1)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient, Response

from creditgraph.models import AttestationStatus, Evidence
from creditgraph.services import evidence as evidence_service


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
    """Minimal transaction object for the fake session."""

    def __init__(self, tx_id: str):
        self.tx_id = tx_id


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


@pytest.mark.asyncio
async def test_verify_transaction_verified(monkeypatch):
    """A successful verification returns VERIFIED evidence with lineage fields."""
    payload = {
        "verified": True,
        "status": "verified",
        "txHash": "0xabc",
        "chainKey": 1,
        "headerNumber": 12345,
        "sourceChain": "ethereum-sepolia",
        "verifiedAt": "2026-01-01T00:00:00Z",
        "proof": {"merkleProof": {"root": "0x1"}, "continuityProof": {"roots": ["0x2"]}},
    }
    fake = _FakeAsyncClient(payload)
    monkeypatch.setattr(evidence_service.httpx, "AsyncClient", lambda **kw: fake)

    ev = await evidence_service.verify_transaction("0xabc", chain_key=1)

    assert ev.status == AttestationStatus.VERIFIED
    assert ev.verifier == "attestcoin-usc-sdk"
    assert ev.verified_at is not None
    assert ev.header_number == 12345
    assert ev.chain_key == 1
    assert ev.source_chain == "ethereum-sepolia"
    assert ev.proof["merkleProof"]["root"] == "0x1"
    assert fake._posted == {"txHash": "0xabc", "chainKey": 1}


@pytest.mark.asyncio
async def test_verify_transaction_unverified(monkeypatch):
    """A failed verification returns UNVERIFIED evidence, never conflated."""
    payload = {"verified": False, "status": "unverified", "reason": "transaction_not_found"}
    fake = _FakeAsyncClient(payload, status_code=422)
    monkeypatch.setattr(evidence_service.httpx, "AsyncClient", lambda **kw: fake)

    ev = await evidence_service.verify_transaction("0xdead")

    assert ev.status == AttestationStatus.UNVERIFIED
    assert ev.verifier is None
    assert ev.verified_at is None
    assert ev.reason == "transaction_not_found"


@pytest.mark.asyncio
async def test_verify_transaction_service_unreachable(monkeypatch):
    """When the attestation service is down, evidence is UNVERIFIED."""

    class _RaisingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, **kwargs):
            raise evidence_service.httpx.ConnectError("connection refused")

    monkeypatch.setattr(evidence_service.httpx, "AsyncClient", lambda **kw: _RaisingClient())

    ev = await evidence_service.verify_transaction("0xdead")

    assert ev.status == AttestationStatus.UNVERIFIED
    assert ev.reason == "service_unreachable"


@pytest.mark.asyncio
async def test_persist_evidence_emits_queries(monkeypatch):
    """persist_evidence writes Evidence + Attestation + borrower link."""
    driver = _FakeDriver()
    monkeypatch.setattr(evidence_service, "get_driver", lambda: driver)

    ev = Evidence(
        evidence_id="ev_1",
        source_chain="ethereum-sepolia",
        tx_id="0xabc",
        attestation_id="att_0xabc",
        status=AttestationStatus.VERIFIED,
        verifier="attestcoin-usc-sdk",
        header_number=12345,
        chain_key=1,
    )
    await evidence_service.persist_evidence(ev, borrower_id="borrower_demo_alice")

    queries = driver._sessions[0]._queries
    assert len(queries) == 2
    # First query merges Evidence + Attestation + VERIFIED_BY
    assert "MERGE (e:Evidence" in queries[0][0]
    assert "MERGE (a:Attestation" in queries[0][0]
    assert "VERIFIED_BY" in queries[0][0]
    # Second query links borrower
    assert "HAS_EVIDENCE" in queries[1][0]
    assert queries[1][1]["borrower_id"] == "borrower_demo_alice"