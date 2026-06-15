from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .config import BacktestConfig, cfg
from .event_engine import EventEngine
from .schemas import validate_signal


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="GraphAlpha event-driven backtest (P1)")
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
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    engine = EventEngine(
        start=args.start,
        end=args.end,
        rebal_freq=args.rebal_freq,
        use_graph=args.use_graph,
        disable_news_overlay=args.disable_news_overlay,
        disable_macro_overlay=args.disable_macro_overlay,
        fee_pct=args.fee_pct,
        slip_pct=args.slip_pct,
    )
    engine.run()
    result = {
        "start": args.start,
        "end": args.end,
        "use_graph": args.use_graph,
        "n_signals": len(engine.signals),
    }
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
