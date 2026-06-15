"""
Signal Replay Export — deterministic JSONL stream of Schema v1 Signals for C++ parity testing.
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.schema_validator import validate_signal


def export_signals(
    signals: list[dict[str, Any]],
    metadata: dict[str, Any],
    output_path: Path,
) -> None:
    if not signals:
        raise ValueError("Cannot export an empty signal list.")

    sorted_signals = sorted(
        signals,
        key=lambda s: (
            s.get("timestamp", ""),
            s.get("cycle_id", ""),
            s.get("strategy", ""),
        ),
    )

    for idx, sig in enumerate(sorted_signals):
        try:
            validate_signal(sig)
        except Exception as exc:
            raise ValueError(
                f"Signal at index {idx} (strategy={sig.get('strategy')!r}) "
                f"failed validation: {exc}"
            ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as fh:
        header = {
            "run_id": str(uuid.uuid4()),
            "schema_version": 1,
            "date_range": metadata.get("date_range", ""),
            "use_graph": metadata.get("use_graph", False),
            "instrument_universe": metadata.get("instrument_universe", []),
            "signal_count": len(sorted_signals),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        fh.write(f"# META {json.dumps(header, sort_keys=True, default=str)}\n")
        for sig in sorted_signals:
            fh.write(json.dumps(sig, sort_keys=True, default=str) + "\n")


def _build_metadata_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "date_range": f"{args.start} -> {args.end}",
        "use_graph": args.use_graph,
        "instrument_universe": [t.strip() for t in args.universe.split(",") if t.strip()],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export backtest signals for C++ replay/parity testing")
    parser.add_argument("--input", required=True, help="Path to JSON/JSONL file containing a list of Signal dicts")
    parser.add_argument("--output", required=True, help="Path to write the deterministic JSONL export")
    parser.add_argument("--start", default="", help="Backtest start date (for metadata)")
    parser.add_argument("--end", default="", help="Backtest end date (for metadata)")
    parser.add_argument("--use-graph", dest="use_graph", action="store_true")
    parser.add_argument("--no-graph", dest="use_graph", action="store_false")
    parser.set_defaults(use_graph=True)
    parser.add_argument("--universe", default="", help="Comma-separated instrument universe")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as fh:
        raw = fh.read().strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Input is not valid JSON: {exc}")

    if isinstance(data, dict):
        data = data.get("signals", [])

    if not isinstance(data, list):
        raise SystemExit("Input JSON must be a list of Signal objects.")

    metadata = _build_metadata_from_args(args)
    export_signals(data, metadata, Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
