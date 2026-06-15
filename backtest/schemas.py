from __future__ import annotations

from pathlib import Path

_SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
_SCHEMA_VERSION = 1
SCHEMA_VERSION = _SCHEMA_VERSION

try:
    from common.schema_validator import validate_signal, validate_order
    from common.versioning import validate_schema_version
except ImportError:  # backtest profile may not have agent/ on sys.path
    import json
    import os
    import sys

    AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
    if str(AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(AGENT_DIR))
    from common.schema_validator import validate_signal, validate_order  # type: ignore[no-redef]
    from common.versioning import validate_schema_version  # type: ignore[no-redef]


def make_signal(**kwargs) -> dict:
    defaults = {
        "schema_version": _SCHEMA_VERSION,
        "cycle_id": "00000000-0000-0000-0000-000000000000",
        "timestamp": "2024-01-01T00:00:00Z",
        "regime": "Trending",
        "strategy": "TestStrategy",
        "ticker": "SPY",
        "venue": "ibkr",
        "venue_symbol": "SPY",
        "asset_class": "equity_xstock",
        "direction": "hold",
        "score": 0.0,
        "quant_score": 0.0,
        "sentiment_score": 0.0,
        "news_overlay": 0.0,
        "macro_overlay": 0.0,
        "kg_formula_contribution": 0.0,
        "graph_path": [],
        "contradiction_blocked": False,
    }
    defaults.update(kwargs)
    return defaults

