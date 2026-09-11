"""
dreamdex_adapter.py
────────────────────
HTTP client for the DreamDEX / Somnia relay (:8450). The relay owns the
Somnia private key and the @somnia-chain/markets-sdk; this adapter is the
only Python surface that talks to it. Mirrors the crypto/alpaca provider
pattern (httpx + try/except + logger.warning fallback) so callers get
stub-safe results when the relay is down or disabled.

PAPER mode: the relay returns stub fills (dry-run, never broadcast).
LIVE mode:  the relay signs + broadcasts (only when the operator sets
            DRY_RUN=0 AND DREAMDEX_TRADING_MODE=live with a funded key).
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

RELAY_BASE = os.getenv("DREAMDEX_RELAY_URL", "http://localhost:8450")
RELAY_API_KEY = os.getenv("RELAY_API_KEY", "")
TIMEOUT = float(os.getenv("DREAMDEX_RELAY_TIMEOUT_SECONDS", 10))


def _headers() -> dict[str, str]:
    return {"X-Relay-Key": RELAY_API_KEY, "Content-Type": "application/json"}


def relay_status() -> dict[str, Any]:
    """Adapter state from the relay — mode, network, wallet, dry-run, health."""
    try:
        r = httpx.get(f"{RELAY_BASE}/status", headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        j = r.json()
        # Normalise relay camelCase -> snake_case + success flag so downstream
        # routes read stable keys (the relay response itself has no `reachable`).
        j["reachable"] = True
        j["dry_run"] = j.get("dryRun", j.get("dry_run", True))
        return j
    except Exception as e:
        logger.warning(f"[DreamDEX] relay /status failed: {e}")
        return {"mode": "paper", "network": "unknown", "reachable": False}


def get_markets() -> list[dict[str, Any]]:
    """All open Event Contract markets from the relay's on-chain-gated snapshot."""
    try:
        r = httpx.get(f"{RELAY_BASE}/markets", headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get("markets", [])
    except Exception as e:
        logger.warning(f"[DreamDEX] relay /markets failed: {e}")
        return []


def place_order(market_id: str, side: str, qty: int) -> dict[str, Any]:
    """Place a C-E-I order through the relay. Idempotent on intent_id."""
    try:
        r = httpx.post(
            f"{RELAY_BASE}/order",
            headers=_headers(),
            json={"marketId": market_id, "side": side, "qty": qty},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[DreamDEX] relay /order failed: {e}")
        return {"ok": False, "state": "rejected", "reason": f"relay_unreachable: {e}"}


def get_positions() -> tuple[list[dict], list[str]]:
    """Open positions + reconciliation drift items (U5)."""
    try:
        r = httpx.get(f"{RELAY_BASE}/positions", headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return data.get("positions", []), data.get("reconciliation", {}).get("driftItems", [])
    except Exception as e:
        logger.warning(f"[DreamDEX] relay /positions failed: {e}")
        return [], []


def get_fills() -> list[dict[str, Any]]:
    """Fill history (with confirmations / reorg flags per U14)."""
    try:
        r = httpx.get(f"{RELAY_BASE}/fills", headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get("fills", [])
    except Exception as e:
        logger.warning(f"[DreamDEX] relay /fills failed: {e}")
        return []


def get_balances() -> dict[str, Any]:
    """Live SOMI (gas) + tUSDC (collateral) balances from the relay (read-only)."""
    try:
        r = httpx.get(f"{RELAY_BASE}/balances", headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[DreamDEX] relay /balances failed: {e}")
        return {"somi": None, "tusdc": None}


def claim() -> dict[str, Any]:
    """Trigger the settlement claim sweep on the relay (human-gated at API layer)."""
    try:
        r = httpx.post(f"{RELAY_BASE}/claim", headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[DreamDEX] relay /claim failed: {e}")
        return {"results": []}


__all__ = [
    "relay_status",
    "get_markets",
    "place_order",
    "get_positions",
    "get_fills",
    "get_balances",
    "claim",
]