"""
Chain-agnostic Passport Adapter package — ported into GraphAlpha from
stellcasp/zkkyc/adapters (SK-08 / EP-08). P11 Stage-2.

Each adapter implements the `PassportAdapterBase` interface for a specific
target venue. The DeFiAgent (P11) resolves adapters exclusively through
`AdapterRegistry.get(chain_target)` — no if/elif branching in agent code.

Available adapters (this repo):
  - sepolia-evm  — EVM/L2 via Noir Solidity verifier + ERC-721 soulbound
"""

from .base import (
    AdapterConformanceError,
    AdapterDeploymentError,
    PassportAdapterBase,
)
from .registry import AdapterRegistry, get_adapter_registry

__all__ = [
    "AdapterConformanceError",
    "AdapterDeploymentError",
    "PassportAdapterBase",
    "AdapterRegistry",
    "get_adapter_registry",
]