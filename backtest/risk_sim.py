"""Standalone risk-sizing reference implementation.

Single source of truth for half-Kelly, sector caps, parametric VaR, and
circuit-breaker logic, extracted from agent/risk_agent.py.

Caller contract
---------------
  order = size_signal(signal, portfolio_state, prices)

Where
  signal        — Schema v1 dict (keys: ticker, direction, score, cycle_id, ...)
  portfolio     — PortfolioState (nav, cash, positions, drawdown_from_peak)
  prices        — dict[str, pd.Series] of daily close prices by ticker

Returns ApprovedOrder with rejection_reason set on failure, None on success.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

# ── Thresholds: .env only (matches agent/risk_agent.py defaults) ─────────────
KELLY_FRACTION    = float(os.getenv("AGENT_KELLY_FRACTION",      "0.5"))
MAX_POSITION_PCT  = float(os.getenv("AGENT_MAX_POSITION_PCT",     "0.20"))
MAX_SECTOR_PCT    = float(os.getenv("RISK_MAX_SECTOR_PCT",        "0.40"))
VAR_CONFIDENCE    = float(os.getenv("RISK_VAR_CONFIDENCE",        "0.99"))
MAX_VAR_PCT       = float(os.getenv("RISK_MAX_VAR_PCT",           "0.05"))
MAX_DRAWDOWN_HALT = float(os.getenv("AGENT_MAX_DRAWDOWN_HALT",    "0.10"))

SECTOR_MAP: dict[str, str] = {
    "SPY": "equity_broad",      "QQQ": "equity_tech",
    "XLF": "equity_financials", "XLE": "equity_energy",
    "BTC": "crypto",            "ETH": "crypto",
    "TLT": "macro_rates",       "GLD": "commodities",
}


@dataclass(frozen=True)
class PortfolioState:
    nav: float
    cash: float
    positions: dict[str, dict[str, Any]]
    drawdown_from_peak: float = 0.0


@dataclass(frozen=True)
class ApprovedOrder:
    order_id: str
    cycle_id: str
    ticker: str
    direction: str
    quantity: float
    notional_usd: float
    kelly_fraction: float
    var_contribution: float
    var_contribution_pct: float
    price_estimate: float
    risk_checks: dict[str, bool]
    mode: str = "paper"
    rejection_reason: str | None = None


def size_signal(
    signal: dict[str, Any],
    portfolio: PortfolioState,
    prices: dict[str, pd.Series],
) -> ApprovedOrder:
    """Size a single signal through the full risk stack.

    Returns ApprovedOrder on success (rejection_reason=None) or a structured
    rejection with a non-None rejection_reason:
      circuit_breaker_halt | sector_cap | var_cap | no_price | tiny_qty
    """
    ticker = signal["ticker"]
    cycle_id = signal.get("cycle_id", "")

    # ── 1. Circuit breaker ─────────────────────────────────────────────────
    if portfolio.drawdown_from_peak > MAX_DRAWDOWN_HALT:
        return ApprovedOrder(
            order_id=str(uuid.uuid4()),
            cycle_id=cycle_id,
            ticker=ticker,
            direction=signal.get("direction", "hold"),
            quantity=0.0,
            notional_usd=0.0,
            kelly_fraction=0.0,
            var_contribution=0.0,
            var_contribution_pct=0.0,
            price_estimate=0.0,
            risk_checks={},
            mode="paper",
            rejection_reason="circuit_breaker_halt",
        )

    # ── 2. Half-Kelly sizing ───────────────────────────────────────────────
    score  = abs(float(signal.get("score", 0.0)))
    p_win  = 0.5 + 0.25 * score
    p_lose = 1.0 - p_win
    b      = 1.5
    kelly  = max(0.0, (p_win * b - p_lose) / b / 2.0)
    target = portfolio.nav * kelly * MAX_POSITION_PCT

    # ── 3. Sector cap ─────────────────────────────────────────────────────
    sector = SECTOR_MAP.get(ticker, "other")
    sector_exposure = sum(
        p.get("notional", 0.0)
        for p in portfolio.positions.values()
        if p.get("sector", SECTOR_MAP.get(p.get("ticker", ""), "other")) == sector
    )
    sector_ok = sector_exposure + target <= portfolio.nav * MAX_SECTOR_PCT
    if not sector_ok:
        return _reject(cycle_id, ticker, signal, kelly, target,
                        sector_exposure, 0.0, 0.0, "sector_cap",
                        sector_ok=sector_ok, nav=portfolio.nav)

    # ── 4. Marginal VaR ───────────────────────────────────────────────────
    var_contrib = _marginal_var(ticker, target, portfolio.nav, prices)
    var_ok = var_contrib <= portfolio.nav * MAX_VAR_PCT
    if not var_ok:
        return _reject(cycle_id, ticker, signal, kelly, target,
                        sector_exposure, var_contrib,
                        var_contrib / max(portfolio.nav, 1e-9),
                        "var_cap", var_ok=var_ok, nav=portfolio.nav)

    # ── 5. Price check ────────────────────────────────────────────────────
    price = _get_price(ticker, prices)
    if price <= 0:
        return _reject(cycle_id, ticker, signal, kelly, target,
                        sector_exposure, var_contrib,
                        var_contrib / max(portfolio.nav, 1e-9),
                        "no_price", nav=portfolio.nav)

    # ── 6. Quantity floor ─────────────────────────────────────────────────
    qty = target / price
    if qty < 0.0001:
        return _reject(cycle_id, ticker, signal, kelly, target,
                        sector_exposure, var_contrib,
                        var_contrib / max(portfolio.nav, 1e-9),
                        "tiny_qty", price=price, nav=portfolio.nav)

    # ── 7. Approved ───────────────────────────────────────────────────────
    return ApprovedOrder(
        order_id=str(uuid.uuid4()),
        cycle_id=cycle_id,
        ticker=ticker,
        direction=signal.get("direction", "hold"),
        quantity=round(qty, 6),
        notional_usd=round(target, 2),
        kelly_fraction=round(kelly, 4),
        var_contribution=round(var_contrib, 2),
        var_contribution_pct=round(var_contrib / max(portfolio.nav, 1e-9), 4),
        price_estimate=round(price, 4),
        risk_checks={
            "position_pct_ok": target <= portfolio.nav * MAX_POSITION_PCT,
            "sector_pct_ok":   sector_ok,
            "var_ok":          var_ok,
        },
        mode="paper",
        rejection_reason=None,
    )


def _reject(
    cycle_id: str,
    ticker: str,
    signal: dict[str, Any],
    kelly: float,
    target: float,
    sector_exposure: float,
    var_contrib: float,
    var_pct: float,
    reason: str,
    sector_ok: bool = True,
    var_ok: bool = True,
    price: float = 0.0,
    nav: float = 10000.0,
) -> ApprovedOrder:
    return ApprovedOrder(
        order_id=str(uuid.uuid4()),
        cycle_id=cycle_id,
        ticker=ticker,
        direction=signal.get("direction", "hold"),
        quantity=0.0,
        notional_usd=0.0,
        kelly_fraction=round(kelly, 4),
        var_contribution=round(var_contrib, 2) if var_contrib else 0.0,
        var_contribution_pct=round(var_pct, 4) if var_pct else 0.0,
        price_estimate=round(price, 4) if price else 0.0,
        risk_checks={
            "position_pct_ok": target <= nav * MAX_POSITION_PCT,
            "sector_pct_ok":   sector_ok,
            "var_ok":          var_ok,
        },
        mode="paper",
        rejection_reason=reason,
    )


# ── Helpers (extracted verbatim from agent/risk_agent.py) ───────────────────

def _marginal_var(
    ticker: str,
    notional: float,
    nav: float,
    prices: dict[str, pd.Series],
) -> float:
    series = prices.get(ticker)
    if series is None or len(series) < 20:
        return notional * 0.03
    rets  = series.pct_change().dropna().tail(60)
    sigma = rets.std()
    z     = 2.326 if VAR_CONFIDENCE >= 0.99 else 1.645
    return float(notional * sigma * z)


def _get_price(ticker: str, prices: dict[str, pd.Series]) -> float:
    series = prices.get(ticker)
    if series is not None and not series.empty:
        return float(series.iloc[-1])
    return 0.0
