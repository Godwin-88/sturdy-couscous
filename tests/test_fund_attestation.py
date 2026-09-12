"""FundAttestation unit tests — H1–3 NAV-attestation loop (BUIDL CTC / RWA track).

Hermetic: fake Alpaca, in-memory chain store, fake web3, monkeypatched env.
No network, no testnet keys, no Docker deps beyond what the api container already
has (web3.py is required for the anchor ABI path and is installed).

Covers the financial-engineer invariants:
  G1  canonical digest is deterministic (stable floats / key order)
  G2  snapshot normalizes long/short market value + round trips
  G3  offline mode self-disables cleanly (no anchor, no attest, still chained)
  G4  live anchor follows CE-I (build -> sign -> send -> wait status==1)
  G5  attest is only attempted when a real (non-stub) source-chain tx exists
  G6  RedisChainStore round-trips the JSON ledger so the chain persists
"""

from __future__ import annotations

import asyncio
import os

import pytest

import agent.fund_attestation as famod
from agent.fund_attestation import (
    RedisChainStore,
    canonical_digest,
    fund_chain,
    run_fund_attestation,
    snapshot,
)


class FakeAlpaca:
    def __init__(self, equity=95_431.52, cash=-15_302.0, bp=244_692.0):
        self._e, self._c, self._b = equity, cash, bp

    async def get_account(self):
        return {"status": "active", "cash": self._c, "equity": self._e,
                "buying_power": self._b}

    async def get_positions(self):
        return [
            {"symbol": "SPY", "qty": 80.0, "market_value": 38_000.0, "unrealized_pl": 1200.0},
            {"symbol": "BTC/USD", "qty": -0.01548, "market_value": -1195.0, "unrealized_pl": -46.5},
            {"symbol": "AAA", "qty": 0.0, "market_value": 0.0, "unrealized_pl": 0.0},
        ]


def _fresh_env(monkeypatch, nav_anchor="0x000000000000000000000000000000000000dEaD",
               key="0x" + "11" * 32, relay=""):
    monkeypatch.setenv("NAV_ANCHOR_CONTRACT", nav_anchor)
    monkeypatch.setenv("CLAIM_TOKEN_PRIVATE_KEY", key)
    monkeypatch.setenv("WEB3_ORACLE_AUTHORITY_PRIVATE_KEY", "")
    monkeypatch.setenv("WEB3_RELAY_URL", relay)
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.delenv("FUND_BORROWER_ID", raising=False)


# ── G1: deterministic digest ───────────────────────────────────────────────────
def test_canonical_digest_deterministic():
    a = {"equity": 95431.52, "cash": -15302.0, "pos": [{"qty": 1.0, "x": 0.1}]}
    b = {"cash": -15302.0, "pos": [{"x": 0.10, "qty": 1.0}], "equity": 95431.52}
    assert canonical_digest(a) == canonical_digest(b)
    a2 = {"equity": 95431.5201, "cash": -15302.0, "pos": []}
    assert canonical_digest(a) != canonical_digest(a2)


# ── G2: snapshot ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_snapshot_normalizes_positions():
    snap = await snapshot(FakeAlpaca())
    assert snap["equity"] == 95_431.52
    assert snap["long_market_value"] == 38_000.0
    assert snap["short_market_value"] == 1195.0
    assert snap["venue"] == "alpaca"
    assert all(p["qty"] != 0.0 for p in snap["positions"])


# ── G3: offline mode ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_offline_self_disables(monkeypatch):
    _fresh_env(monkeypatch, nav_anchor="", key="", relay="")
    report = await run_fund_attestation(regime="Neutral", alpaca=FakeAlpaca(), store={})
    assert report["anchor"]["mode"] == "offline"
    assert report["attestation"]["status"] == "skipped"
    assert report["chain"]["verify_ok"] is True
    assert report["chain"]["root"]
# ── G4: live anchor consumes the NAVAnchor ABI correctly ───────────────────────
class _Fn:
    def __init__(self, result):
        self._r = result

    def build_transaction(self, tx):
        return {**tx, **self._r}


class _Functions:
    def setNAV(self, nav_scaled, nav_hash, block_ref):
        return _Fn({"nav_scaled": nav_scaled, "nav_hash": nav_hash.hex(),
                    "block_ref": block_ref})


class _Contract:
    @property
    def functions(self):
        return _Functions()


class FakeAccount:
    def __init__(self, key):
        self.key = key
        self.address = "0x000000000000000000000000000000000000dEaD"


class FakeEth:
    def __init__(self, status=1):
        self._status = status
        self.last = {}

    def contract(self, address=None, abi=None):
        return _Contract()

    def get_transaction_count(self, address):
        return 5

    @property
    def gas_price(self):
        return 1_000_000_000

    @property
    def account(self):
        return _AccountModule()

    def send_raw_transaction(self, raw):
        self.last["raw"] = raw
        return b"\x12" * 32

    def wait_for_transaction_receipt(self, tx_hash, timeout=120, poll_latency=2):
        self.last["tx_hash"] = tx_hash
        return {"status": self._status, "transactionHash": tx_hash}


class _AccountModule:
    def from_key(self, key):
        return FakeAccount(key)

    def sign_transaction(self, tx, private_key=None):
        import types

        return types.SimpleNamespace(rawTransaction=b"\x22" * 32)


class FakeW3:
    def __init__(self, status=1):
        self.eth = FakeEth(status)


DEAD = "0x000000000000000000000000000000000000dEaD"


@pytest.mark.asyncio
async def test_anchor_nav_success(monkeypatch):
    _fresh_env(monkeypatch, nav_anchor=DEAD)
    digest = canonical_digest({"equity": 95_431.52})
    w3 = FakeW3(status=1)
    tx_hash = await famod.anchor_nav(w3, FakeAccount("0x" + "11" * 32), DEAD,
                                     95_431.52, digest, decimals=6)
    assert tx_hash == "12" * 32
    assert w3.eth.last["raw"] is not None  # broadcast occurred


@pytest.mark.asyncio
async def test_anchor_nav_reverts_raise(monkeypatch):
    _fresh_env(monkeypatch, nav_anchor=DEAD)
    digest = canonical_digest({"equity": 1.0})
    w3 = FakeW3(status=0)
    with pytest.raises(RuntimeError):
        await famod.anchor_nav(w3, FakeAccount("0x" + "11" * 32), DEAD, 1.0, digest)
# ── G5: attest gating — no attest when tx is stub / none ───────────────────────
@pytest.mark.asyncio
async def test_no_attest_without_source_tx(monkeypatch):
    _fresh_env(monkeypatch)
    report = await run_fund_attestation(regime="Neutral", alpaca=FakeAlpaca(), store={})
    assert report["attestation"]["status"] == "skipped"


# ── G6: RedisChainStore round-trips the JSON ledger ────────────────────────────
def test_redis_store_roundtrip():
    class FakeRedis:
        def __init__(self):
            self.d = {}

        def get(self, k):
            return self.d.get(k)

        def set(self, k, v):
            self.d[k] = v

    r = FakeRedis()
    st = RedisChainStore(r, prefix="abc")
    st["abc:entries"] = [{"a": 1}]
    got = st.get("abc:entries", [])
    assert got == [{"a": 1}]
    assert isinstance(got, list)
    assert st.get("abc:missing", []) == []


# ── chain persistence across cycles ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_chain_links_across_cycles(monkeypatch):
    _fresh_env(monkeypatch, nav_anchor="", key="", relay="")
    store: dict = {}
    r1 = await run_fund_attestation(cycle_id="c1", regime="Neutral",
                                    alpaca=FakeAlpaca(), store=store)
    r2 = await run_fund_attestation(cycle_id="c2", regime="Neutral",
                                    alpaca=FakeAlpaca(), store=store)
    assert r1["chain"]["verify_ok"] is True
    assert r2["chain"]["verify_ok"] is True
    assert r2["chain"]["prev_root"] == r1["chain"]["root"]  # linked
    chain = fund_chain(store=store)
    assert chain.verify_chain() is True


# ── CLI entry does not crash in hermetic env ───────────────────────────────────
def test_main_entry(monkeypatch):
    _fresh_env(monkeypatch, nav_anchor="", key="", relay="")

    def boom():
        raise ConnectionError("no redis in hermetic test")

    monkeypatch.setattr(famod, "_redis", boom)

    async def _fake_report():
        return {"status": "ok", "chain": {"root": "sha256:abc"}}

    async def _run():
        orig = famod.run_fund_attestation
        famod.run_fund_attestation = lambda **kw: asyncio.ensure_future(_fake_report())
        try:
            await famod.main()
        finally:
            famod.run_fund_attestation = orig

    asyncio.run(_run())  # should not raise (Redis path swallowed by try/except)