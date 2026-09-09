"""
Abstract PassportAdapter interface — ZK-KYC Compliance Agent (zkkyc.adapters.base)

Spec reference: EP-08 (F-08.1 — US-08.1.1)

The `PassportAdapterBase` abstract class defines the five operations every
chain-specific adapter must implement:

  1. verify_proof(proof_hex, public_inputs) -> bool
  2. mint_passport(wallet, policy_id, expires_at, proof_hash) -> tx_hash
  3. revoke_passport(wallet, policy_id, reason) -> tx_hash
  4. verify_credential(wallet, policy_id) -> {valid, expires_at}
  5. get_deployment_info() -> {chain_id, contract_address, deployed_at, network}

The Settlement Agent (EP-06 F-06.1.5) dispatches exclusively through this
interface. Adding a new chain requires only a new adapter subclass and a
registry entry — no changes to the agent pipeline or the ZK circuit.

Domain exceptions:
  - AdapterDeploymentError: raised when on-chain contract calls fail
  - AdapterConformanceError: raised when an adapter violates the conformance
    contract (e.g. returns malformed deployment info)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AdapterDeploymentError(Exception):
    """Raised when a chain-specific on-chain contract call fails.

    Carries the chain target and the underlying cause so the Settlement
    Agent can decide whether to retry or escalate to the error terminal.
    """

    def __init__(self, chain_target: str, message: str, cause: Exception | None = None):
        self.chain_target = chain_target
        self.cause = cause
        super().__init__(f"[{chain_target}] {message}")


class AdapterConformanceError(Exception):
    """Raised when an adapter violates the PassportAdapter conformance contract.

    Used by the conformance test suite (F-08.1.2) and by the registry at
    registration time to reject adapters that do not meet the interface
    contract.
    """

    def __init__(self, adapter_name: str, message: str):
        self.adapter_name = adapter_name
        super().__init__(f"[{adapter_name}] {message}")


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

@dataclass
class DeploymentInfo:
    """Structured deployment metadata returned by get_deployment_info()."""

    chain_id: str
    contract_address: str
    deployed_at: datetime
    network: str  # "testnet" | "mainnet" | "devnet"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "chain_id": self.chain_id,
            "contract_address": self.contract_address,
            "deployed_at": self.deployed_at.isoformat(),
            "network": self.network,
        }
        d.update(self.extra)
        return d


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class PassportAdapterBase(ABC):
    """Chain-agnostic Passport Adapter interface.

    Every target chain deployment must subclass this and implement all five
    abstract methods. The Settlement Agent resolves adapters through
    `AdapterRegistry` and calls these methods without knowing the underlying
    chain technology.

    Subclass contract:
      - Methods must not raise for expected business conditions (e.g. missing
        passport) — instead return structured sentinel values:
          verify_proof -> False
          verify_credential -> {"valid": False, "expires_at": 0}
      - Methods must return `str` tx_hash on successful on-chain writes.
      - get_deployment_info must return a DeploymentInfo with non-empty
        chain_id, contract_address, and network.
    """

    # ------------------------------------------------------------------
    # Abstract interface (US-08.1.1)
    # ------------------------------------------------------------------

    @abstractmethod
    async def verify_proof(self, proof_hex: str, public_inputs: list[int]) -> bool:
        """Verify a Noir UltraHonk proof against the on-chain verifier contract.

        Args:
            proof_hex: hex-encoded proof bytes from the Noir circuit.
            public_inputs: list of public input integers matching the circuit
                signature (e.g. [ci_threshold_scaled, manifold_threshold_scaled,
                policy_id_int]).

        Returns:
            True if the proof is valid and accepted by the verifier contract,
            False otherwise. Never raises for invalid proofs.
        """
        raise NotImplementedError

    @abstractmethod
    async def mint_passport(
        self,
        wallet: str,
        policy_id: str,
        expires_at: int,
        proof_hash: str,
    ) -> str:
        """Mint a non-transferable Compliance Passport for a wallet.

        Args:
            wallet: the target wallet address or public key in chain-native
                format.
            policy_id: human-readable compliance policy identifier.
            expires_at: UNIX timestamp when the passport expires.
            proof_hash: SHA-256 hash of the ZK proof for on-chain reference.

        Returns:
            The on-chain transaction hash as a hex string.

        Raises:
            AdapterDeploymentError: if the on-chain mint fails.
        """
        raise NotImplementedError

    @abstractmethod
    async def revoke_passport(self, wallet: str, policy_id: str, reason: str) -> str:
        """Revoke an active Compliance Passport.

        Args:
            wallet: the wallet address holding the passport.
            policy_id: the policy identifier of the passport to revoke.
            reason: a short reason code (e.g. "HIGH_RISK_UPDATE").

        Returns:
            The on-chain transaction hash as a hex string.

        Raises:
            AdapterDeploymentError: if the on-chain revoke fails.
        """
        raise NotImplementedError

    @abstractmethod
    async def verify_credential(self, wallet: str, policy_id: str) -> dict[str, Any]:
        """Check whether a wallet holds a valid, non-expired Compliance Passport.

        This is the read-only view any downstream protocol calls to gate access
        without re-running KYC.

        Args:
            wallet: the wallet address to query.
            policy_id: the policy identifier to check.

        Returns:
            Dict with keys:
              - valid (bool): True if a non-expired passport exists.
              - expires_at (int): UNIX timestamp of expiry, or 0 if invalid.
              - policy_id (str): echo of the requested policy.
              - Optional extra fields per chain (e.g. token_id on EVM).
        """
        raise NotImplementedError

    @abstractmethod
    async def get_deployment_info(self) -> DeploymentInfo:
        """Return structured metadata about the current adapter deployment.

        Used by the grant pipeline (F-08.5.1) and the API layer to expose
        deployment status to reviewers and auditors.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers (not abstract — subclasses may override)
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        info = self.get_deployment_info() if hasattr(self, "get_deployment_info") else None
        addr = info.contract_address if info else "unconfigured"
        return f"<{self.__class__.__name__} chain={info.chain_id if info else '?'} contract={addr}>"
