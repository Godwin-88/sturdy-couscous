"""
Option contract codec — pure functions, no dependencies.

OCC symbol format:  SPY250919C00700000  ->  root:SPY  exp:2025-09-19  C  strike:700.00
strike is stored scaled by 1000, zero-padded to 8 digits.
"""
from __future__ import annotations

from datetime import datetime


def parse_contract_symbol(symbol: str) -> tuple[str, object, str, float]:
    """Parse an OCC option symbol into (root, expiry_date, right, strike)."""
    symbol = str(symbol or "").strip().upper()
    if len(symbol) < 15:
        raise ValueError(f"Not an OCC option symbol: {symbol!r}")
    try:
        strike8 = symbol[-8:]
        right = symbol[-9]
        date6 = symbol[-15:-9]
        root = symbol[:-15]
        strike = float(strike8) / 1000.0
        expiry = datetime.strptime(date6, "%y%m%d").date()
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Cannot parse option symbol {symbol!r}: {e}") from e
    if right not in ("C", "P"):
        raise ValueError(f"Cannot parse option symbol {symbol!r}: bad right {right!r}")
    return root, expiry, right, strike


def build_contract_symbol(root: str, expiry, right: str, strike: float) -> str:
    """Build an OCC option symbol from its components."""
    root = str(root or "").strip().upper()
    right = str(right or "").strip().upper()[:1]
    if right not in ("C", "P"):
        raise ValueError(f"right must be C or P, got {right!r}")
    d = datetime.strptime(str(expiry), "%Y-%m-%d") if isinstance(expiry, str) else expiry
    strike_scaled = int(round(float(strike) * 1000))
    if not (0 <= strike_scaled < 100_000_000):
        raise ValueError(f"strike {strike} out of OCC range")
    return f"{root}{d.strftime('%y%m%d')}{right}{strike_scaled:08d}"


__all__ = ["parse_contract_symbol", "build_contract_symbol"]