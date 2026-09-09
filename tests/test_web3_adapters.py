"""web3_adapters unit tests — P11 Stage-2 port from stellcasp/zkkyc/adapters.

Hermetic: every test exercises only the fail-fast "unconfigured" paths of the
adapter — no RPC connection, no web3.py network calls, no testnet key.
Verifies the repo-local adaptations (WEB3_* env, sepolia-evm registry):

  - registry auto-registers `sepolia-evm` from agent.web3_adapters (or bare)
  - AdapterRegistry.get() lazy-instantiates + raises KeyError with guidance
  - verify_proof / mint_passport / revoke_passport raise AdapterDeploymentError
    with an actionable message when contracts are not configured
  - verify_credential falls back to invalid (never raises, no network)
  - get_deployment_info classifies network from RPC URL (sepolia -> testnet)
"""

import asyncio

import pytest

import agent.web3_adapters.ethereum as emod
import agent.web3_adapters.registry as rmod
from agent.web3_adapters.base import (
    AdapterConformanceError,
    AdapterDeploymentError,
)
from agent.web3_adapters.ethereum import EVMAdapter
from agent.web3_adapters.registry import AdapterRegistry


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch):
    """Point the adapter at an empty WEB3_* environment (no contracts, no key)."""
    monkeypatch.setenv("WEB3_RPC_URL", "https://rpc.sepolia.org")
    monkeypatch.setenv("WEB3_VERIFIER_CONTRACT", "")
    monkeypatch.setenv("WEB3_PASSPORT_CONTRACT", "")
    monkeypatch.setenv("WEB3_CHAIN_ID", "11155111")
    monkeypatch.setenv("WEB3_ORACLE_AUTHORITY_PRIVATE_KEY", "")
    emod.get_settings.cache_clear()
    yield
    emod.get_settings.cache_clear()


# ── Registry ────────────────────────────────────────────────────────


def test_registry_autoregisters_sepolia_evm():
    reg = rmod.get_adapter_registry()
    assert reg.is_registered("sepolia-evm")
    assert "sepolia-evm" in reg.list_available()


def test_registry_get_lazily_instantiates():
    reg = AdapterRegistry()

    async def _reg():
        await reg.register("sepolia-evm", EVMAdapter)

    _run(_reg())
    assert not reg._adapters  # class stored, not instantiated yet

    adapter = _run(reg.get("sepolia-evm"))
    assert isinstance(adapter, EVMAdapter)
    assert "sepolia-evm" in reg._adapters  # now cached as instance


def test_registry_get_unknown_raises_keyerror_with_guidance():
    reg = AdapterRegistry()

    async def _reg():
        await reg.register("sepolia-evm", EVMAdapter)

    _run(_reg())
    with pytest.raises(KeyError, match="sepolia-evm"):
        _run(reg.get("stellar"))  # not registered in this repo


def test_registry_register_rejects_non_adapter():
    reg = AdapterRegistry()
    with pytest.raises(AdapterConformanceError):

        async def _reg():
            await reg.register("bogus", 42)  # type: ignore[arg-type]

        _run(_reg())


# ── EVMAdapter behavior (unconfigured → fail-fast / invalid) ──────────


def test_verify_proof_raises_when_verifier_unconfigured():
    adapter = EVMAdapter()
    with pytest.raises(AdapterDeploymentError, match="WEB3_VERIFIER_CONTRACT"):
        _run(adapter.verify_proof("0x00", [1]))


def test_mint_passport_raises_when_passport_unconfigured():
    adapter = EVMAdapter()
    with pytest.raises(AdapterDeploymentError, match="WEB3_PASSPORT_CONTRACT"):
        _run(adapter.mint_passport("0xabc", "pol-1", 1_800_000_000, "0x" + "11" * 32))


def test_revoke_passport_raises_when_passport_unconfigured():
    adapter = EVMAdapter()
    with pytest.raises(AdapterDeploymentError, match="WEB3_PASSPORT_CONTRACT"):
        _run(adapter.revoke_passport("0xabc", "pol-1", "HIGH_RISK_UPDATE"))


def test_verify_credential_returns_invalid_without_contract():
    adapter = EVMAdapter()
    result = _run(adapter.verify_credential("0xabc", "pol-1"))
    assert result == {"valid": False, "expires_at": 0, "policy_id": "pol-1"}


def test_get_deployment_info_sepolia_is_testnet(monkeypatch):
    monkeypatch.setenv("WEB3_RPC_URL", "https://rpc.sepolia.org")
    monkeypatch.setenv("WEB3_PASSPORT_CONTRACT", "0xDeployedPassport")
    emod.get_settings.cache_clear()
    adapter = EVMAdapter()
    info = _run(adapter.get_deployment_info())
    assert info.network == "testnet"
    assert info.chain_id.startswith("sepolia-evm:")
    assert info.contract_address == "0xDeployedPassport"


def test_get_deployment_info_mainnet_when_not_sepolia(monkeypatch):
    monkeypatch.setenv("WEB3_RPC_URL", "https://mainnet.example-rpc.io")
    emod.get_settings.cache_clear()
    adapter = EVMAdapter()
    info = _run(adapter.get_deployment_info())
    assert info.network == "mainnet"


# ── DeploymentInfo shape (ported contract) ──────────────────────────


def test_deployment_info_to_dict_isoformat():
    from datetime import datetime, timezone

    from agent.web3_adapters.base import DeploymentInfo

    info = DeploymentInfo(
        chain_id="sepolia-evm:11155111",
        contract_address="0xabc",
        deployed_at=datetime.now(timezone.utc),
        network="testnet",
    )
    d = info.to_dict()
    assert d["chain_id"] == "sepolia-evm:11155111"
    assert d["network"] == "testnet"
    assert "Z" in d["deployed_at"] or "+" in d["deployed_at"]  # isoformat tz