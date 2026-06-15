"""Regime, overlay-config, and asset-class breakdowns for backtest metrics."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from .metrics import (
    jobson_korkie,
    sharpe,
    summary,
    trade_summary,
    total_return,
)


def breakdown_by_regime(trades: list[dict[str, Any]]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        regime = t.get("regime_at_entry") or t.get("regime_at_hold") or "unknown"
        groups[regime].append(t)
    out: dict[str, dict] = {}
    for regime, group in sorted(groups.items()):
        pnls = np.array([float(t.get("pnl", 0.0)) for t in group], dtype=float)
        entries = [t.get("entry_ts") for t in group if t.get("entry_ts")]
        exits   = [t.get("exit_ts") for t in group if t.get("exit_ts")]
        entry_dates = [pd.Timestamp(e) for e in entries]
        exit_dates  = [pd.Timestamp(x) for x in exits]
        out[regime] = trade_summary(pnls, entry_dates, exit_dates)
    return out


def breakdown_by_overlay_config(
    results: dict[str, list[dict[str, Any]]]
) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for config, trades in sorted(results.items()):
        pnls = np.array([float(t.get("pnl", 0.0)) for t in trades], dtype=float)
        entries = [t.get("entry_ts") for t in trades if t.get("entry_ts")]
        exits   = [t.get("exit_ts") for t in trades if t.get("exit_ts")]
        entry_dates = [pd.Timestamp(e) for e in entries]
        exit_dates  = [pd.Timestamp(x) for x in exits]
        out[config] = trade_summary(pnls, entry_dates, exit_dates)
    return out


_BENCHMARK_TICKERS: dict[str, str] = {
    "equity_broad":     "SPY",
    "equity_tech":      "QQQ",
    "equity_financials":"XLF",
    "equity_energy":    "XLE",
    "crypto":           "BTC-USD",
    "macro_rates":      "TLT",
    "commodities":      "GLD",
    "other":            "SPY",
    "unknown":          "SPY",
}


def jk_by_asset_class(
    trades: list[dict[str, Any]],
    price_series: dict[str, pd.Series],
) -> dict[str, tuple[float, float, bool]]:
    class_trades: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        ac = t.get("asset_class") or t.get("sector") or "unknown"
        class_trades[ac].append(t)

    out: dict[str, tuple[float, float, bool]] = {}
    for ac, group in sorted(class_trades.items()):
        bench_ticker = _BENCHMARK_TICKERS.get(ac, "SPY")
        bench = price_series.get(bench_ticker)
        if bench is None or bench.empty or len(group) < 2:
            continue
        pnls = np.array([float(t.get("pnl", 0.0)) for t in group], dtype=float)
        bench_rets = bench.pct_change().dropna()
        if len(bench_rets) < 2:
            continue
        z, p = jobson_korkie(pnls, bench_rets.values[-len(pnls):] if len(bench_rets) >= len(pnls) else bench_rets.values)
        out[ac] = (round(z, 3), round(p, 4), bool(p < 0.05))
    return out
