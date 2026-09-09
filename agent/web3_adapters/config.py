"""
Minimal Settings dataclass for the web3_adapters package — adapted from
stellcasp/zkkyc/config.py (which is a plain @dataclass over os.getenv).

This repo does not use pydantic-settings for agents; the adapter reads the
P11 §9 WEB3_* environment block directly, mirroring dreamdex_adapter.py.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass


@dataclass
class Settings:
    # NOTE: defaults are read at instance-construction time (__post_init__),
    # NOT at class-import time — unlike the stellcasp original, whose
    # class-level `os.getenv(...)` defaults bake once at import and break
    # runtime env overrides (e.g. tests, per-deployment config).
    web3_rpc_url: str = ""
    web3_verifier_contract_address: str = ""
    web3_passport_contract_address: str = ""
    web3_chain_id: int = 11155111
    web3_oracle_authority_private_key: str = ""

    def __post_init__(self) -> None:
        self.web3_rpc_url = os.getenv(
            "WEB3_RPC_URL", self.web3_rpc_url or "https://rpc.sepolia.org"
        )
        self.web3_verifier_contract_address = os.getenv(
            "WEB3_VERIFIER_CONTRACT", self.web3_verifier_contract_address
        )
        self.web3_passport_contract_address = os.getenv(
            "WEB3_PASSPORT_CONTRACT", self.web3_passport_contract_address
        )
        self.web3_chain_id = int(os.getenv("WEB3_CHAIN_ID", str(self.web3_chain_id)))
        self.web3_oracle_authority_private_key = os.getenv(
            "WEB3_ORACLE_AUTHORITY_PRIVATE_KEY",
            self.web3_oracle_authority_private_key,
        )


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the (cached) adapter Settings."""
    return Settings()