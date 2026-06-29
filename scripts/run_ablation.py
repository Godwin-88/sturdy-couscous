#!/usr/bin/env python3
"""Full ablation study runner for P8 Feature 1.

Runs the complete ablation matrix: {grounded, ungrounded} × {baseline, news-off, macro-off, both-off} = 8 configurations.

Usage:
    python scripts/run_ablation.py --start 2020-01-01 --end 2024-12-31 --output ablation_results.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.cli import _run_one
from backtest.metrics_breakdown import breakdown_by_overlay_config, jk_by_asset_class
from backtest.overlays import _MacroCalendar
from backtest.loaders import load_ohlcv
from backtest.universe import get_universe


def run_ablation(start: str, end: str, capital: float, rebal_freq: int, fee_pct: float, slip_pct: float) -> dict[str, Any]:
    configs = {
        "grounded_baseline":    (True,  False, False),
        "grounded_news_off":    (True,  True,  False),
        "grounded_macro_off":   (True,  False, True),
        "grounded_both_off":    (True,  True,  True),
        "ungrounded_baseline":  (False, False, False),
        "ungrounded_news_off":  (False, True,  False),
        "ungrounded_macro_off": (False, False, True),
        "ungrounded_both_off":  (False, True,  True),
    }

    ablated = {}
    all_trade_logs = {}
    ticker_list = [u.ticker for u in get_universe()]

    for key, (use_graph, dn, dm) in configs.items():
        ablated[key] = _run_one(
            start, end, capital, rebal_freq, use_graph, dn, dm, fee_pct, slip_pct, "1d"
        )
        all_trade_logs[key] = ablated[key].get("trade_log", [])

    overlay_breakdown = breakdown_by_overlay_config(all_trade_logs)

    prices: dict[str, Any] = {}
    try:
        price_df = load_ohlcv(start, end, ticker_list, "1d")
        for col in price_df.columns:
            prices[col] = price_df[col]
    except Exception:
        pass

    return {
        "meta": {
            "start": start,
            "end": end,
            "capital": capital,
            "rebal_freq": rebal_freq,
            "ablation_type": "full_matrix_8way",
            "configurations": {
                k: {
                    "use_graph": v[0],
                    "news_disabled": v[1],
                    "macro_disabled": v[2],
                }
                for k, v in configs.items()
            },
        },
        "ablation": ablated,
        "metrics_by_config": overlay_breakdown,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P8 full ablation study")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--capital", type=float, default=10000.0)
    parser.add_argument("--rebal-freq", type=int, default=5)
    parser.add_argument("--fee-pct", type=float, default=None)
    parser.add_argument("--slip-pct", type=float, default=None)
    parser.add_argument("--output", default="ablation_results.json")
    args = parser.parse_args()

    result = run_ablation(args.start, args.end, args.capital, args.rebal_freq, args.fee_pct, args.slip_pct)

    Path(args.output).write_text(json.dumps(result, indent=2, default=str))
    print(f"Ablation results written to {args.output}")

    summary = []
    for key, data in result["ablation"].items():
        summary.append(f"{key}: TR={data['summary'].get('total_return', 0):.2%} SR={data['summary'].get('sharpe_ratio', 0):.2f}")
    print("\nQuick Summary:")
    for s in summary:
        print(f"  {s}")

    return 0


if __name__ == "__main__":
    sys.exit(main())