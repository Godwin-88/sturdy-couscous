from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import BacktestConfig, cfg
from .event_engine import EventEngine
from .metrics import trade_summary
from .metrics_breakdown import breakdown_by_overlay_config, breakdown_by_regime, jk_by_asset_class
from .schemas import validate_signal


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="GraphAlpha event-driven backtest (P2)")
    p.add_argument("--start", default="2022-01-01")
    p.add_argument("--end", default="2022-12-31")
    p.add_argument("--capital", type=float, default=10000.0)
    p.add_argument("--rebal-freq", type=int, default=5)
    p.add_argument("--fee-pct", type=float, default=None)
    p.add_argument("--slip-pct", type=float, default=None)
    p.add_argument("--use-graph", dest="use_graph", action="store_true", default=True)
    p.add_argument("--no-graph", dest="use_graph", action="store_false")
    p.add_argument("--disable-news-overlay", action="store_true")
    p.add_argument("--disable-macro-overlay", action="store_true")
    p.add_argument("--interval", default="1d")
    p.add_argument("--output", default=None)
    p.add_argument("--universe", choices=["default", "crypto", "equity", "macro"], default="default")
    p.add_argument("--tickers", nargs="+", default=None)
    p.add_argument("--ablate-overlays", action="store_true")
    p.add_argument("--ablate-full", action="store_true")
    p.add_argument("--benchmark-data-path", default=None)
    p.add_argument("--granularity", default="portfolio", choices=["portfolio", "asset_class", "strategy"])
    return p.parse_args(argv)


def _run_one(start, end, capital, rebal_freq, use_graph, disable_news, disable_macro,
             fee_pct, slip_pct, interval) -> dict:
    engine = EventEngine(
        start=start,
        end=end,
        rebal_freq=rebal_freq,
        use_graph=use_graph,
        disable_news_overlay=disable_news,
        disable_macro_overlay=disable_macro,
        fee_pct=fee_pct,
        slip_pct=slip_pct,
        capital=capital,
    )
    engine.run()

    # Portfolio NAV returns
    navs = np.array([e["nav"] for e in engine.equity_curve])
    port_rets = np.diff(navs) / navs[:-1] if len(navs) > 1 else np.array([])

    # Trade-level P&L
    pnls = np.array([float(t.pnl) for t in engine.trades if t.pnl is not None])
    entry_dates = [pd.Timestamp(t.timestamp) for t in engine.trades if t.timestamp]
    exit_dates  = [pd.Timestamp(t.timestamp) for t in engine.trades if t.timestamp]

    port_bench = np.diff(navs) / navs[:-1] if len(navs) > 1 else None
    summary_dict = trade_summary(pnls, entry_dates, exit_dates)
    if port_bench is not None and len(port_bench) > 1:
        z, p = _jobson_korkie_safe(pnls, port_bench[-len(pnls):] if len(port_bench) >= len(pnls) else port_bench)
        summary_dict.update({
            "jk_z_stat": round(z, 3),
            "jk_p_value": round(p, 4),
            "jk_significant": bool(p < 0.05),
        })

    open_at_end = sum(1 for p in engine._open_positions.values() if not p["closed"])
    summary_dict["open_positions_at_end"] = open_at_end

    trade_log = []
    for t in engine.trades:
        trade_log.append({
            "position_id": t.position_id,
            "ticker": t.ticker,
            "direction": t.direction,
            "entry_ts": t.timestamp,
            "exit_ts": t.timestamp,
            "entry_price": t.price - t.pnl / t.quantity if t.quantity else t.price,
            "exit_price": t.price,
            "quantity": t.quantity,
            "notional_usd": round(t.quantity * t.price, 2),
            "pnl": round(t.pnl, 2),
            "hold_days": round(t.hold_days, 2),
            "regime_at_entry": t.regime_at_entry,
            "regime_at_hold": t.regime_at_hold,
            "asset_class": getattr(t, 'asset_class', ''),
        })

    halted_periods = []
    for hp in engine.halted_periods:
        entry = {"start": hp["start"]}
        if hp.get("end"):
            entry["end"] = hp["end"]
        halted_periods.append(entry)

    return {
        "meta": {
            "start": start,
            "end": end,
            "capital": capital,
            "rebal_freq": rebal_freq,
            "use_graph": use_graph,
            "overlays": {
                "news": not disable_news,
                "macro": not disable_macro,
            },
        },
        "n_signals": len(engine.signals),
        "n_trades": len(engine.trades),
        "n_rejected": len(engine.rejected_signals),
        "equity_curve": engine.equity_curve,
        "trade_log": trade_log,
        "summary": summary_dict,
        "metrics_by_regime": breakdown_by_regime(trade_log),
        "jk_by_asset_class": {},
        "halted_periods": halted_periods,
    }


def _jobson_korkie_safe(r1: np.ndarray, r2: np.ndarray) -> tuple[float, float]:
    from scipy import stats
    n = len(r1)
    sr1 = r1.mean() / r1.std() * np.sqrt(252) if r1.std() > 0 else 0.0
    sr2 = r2.mean() / r2.std() * np.sqrt(252) if r2.std() > 0 else 0.0
    mu1, mu2 = r1.mean(), r2.mean()
    s1, s2 = r1.std(), r2.std()
    s12 = np.cov(r1, r2[:len(r1)])[0, 1] if len(r2) >= len(r1) else 0.0
    theta = (
        (1 / max(n, 1)) * (
            2 * s1**2 * s2**2
            - 2 * s1 * s2 * s12
            + 0.5 * mu1**2 * s2**2
            + 0.5 * mu2**2 * s1**2
        )
    ) / (s1**2 * s2**2 + 1e-12)
    z = (sr1 - sr2) / np.sqrt(max(theta, 1e-12))
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return float(z), float(p)


def main(argv=None) -> int:
    args = _parse_args(argv)

    from .universe import set_universe, use_preset

    if args.tickers:
        set_universe(args.tickers)
    elif args.universe:
        use_preset(args.universe)

    if args.ablate_full:
        return _run_full_ablation(args)
    if args.ablate_overlays:
        configs = {
            "baseline":  (False, False),
            "news_off":  (True,  False),
            "macro_off": (False, True),
            "both_off":  (True,  True),
        }
        ablated: dict[str, Any] = {}
        for key, (dn, dm) in configs.items():
            ablated[key] = _run_one(
                args.start, args.end, args.capital,
                args.rebal_freq, args.use_graph, dn, dm,
                args.fee_pct, args.slip_pct, args.interval,
            )
        trade_by_config = {
            k: v["trade_log"] for k, v in ablated.items()
        }
        overlay_breakdown = breakdown_by_overlay_config(trade_by_config)

        result = {
            "meta": ablated["baseline"]["meta"],
            "ablation": ablated,
            "metrics_by_overlay_config": overlay_breakdown,
        }
        output_text = json.dumps(result, indent=2, default=str)
        if args.output:
            Path(args.output).write_text(output_text)
        else:
            print(output_text)
        return 0

    result = _run_one(
        args.start, args.end, args.capital,
        args.rebal_freq, args.use_graph,
        args.disable_news_overlay, args.disable_macro_overlay,
        args.fee_pct, args.slip_pct, args.interval,
    )

    output_text = json.dumps(result, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(output_text)
    else:
        print(output_text)
    return 0


def _run_full_ablation(args) -> int:
    """Run full ablation matrix: grounded/ungrounded × 4 overlay configs = 8 runs."""
    fee_pct = args.fee_pct
    slip_pct = args.slip_pct

    configs = {
        "grounded_baseline":  (True,  False, False),
        "grounded_news_off":  (True,  True,  False),
        "grounded_macro_off": (True,  False, True),
        "grounded_both_off":  (True,  True,  True),
        "ungrounded_baseline": (False, False, False),
        "ungrounded_news_off": (False, True,  False),
        "ungrounded_macro_off": (False, False, True),
        "ungrounded_both_off":  (False, True,  True),
    }

    ablated = {}
    all_trade_logs = {}
    for key, (use_graph, dn, dm) in configs.items():
        ablated[key] = _run_one(
            args.start, args.end, args.capital,
            args.rebal_freq, use_graph, dn, dm,
            fee_pct, slip_pct, args.interval,
        )
        all_trade_logs[key] = ablated[key].get("trade_log", [])

    overlay_breakdown = breakdown_by_overlay_config(all_trade_logs)

    result = {
        "meta": {
            "start": args.start,
            "end": args.end,
            "capital": args.capital,
            "rebal_freq": args.rebal_freq,
            "ablation_type": "full_matrix",
            "configurations": {k: {"use_graph": v[0], "news_disabled": v[1], "macro_disabled": v[2]} for k, v in configs.items()},
        },
        "ablation": ablated,
        "metrics_by_config": overlay_breakdown,
    }

    output_text = json.dumps(result, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(output_text)
    else:
        print(output_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
