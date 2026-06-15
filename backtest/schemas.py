from __future__ import annotations

from pathlib import Path

_SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
_SCHEMA_VERSION = 1

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
