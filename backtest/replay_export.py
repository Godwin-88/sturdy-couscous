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
    output_path: str | Path,
    run_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    out_path = output_path if isinstance(output_path, Path) else Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.is_dir():
        out_path = out_path / "export.jsonl"
    if not signals:
        raise ValueError("Cannot export an empty signal list.")

    def _sig_get(sig, key, default=""):
        if isinstance(sig, dict):
            return sig.get(key, default)
        return getattr(sig, key, default)

    sorted_signals = sorted(
        signals,
        key=lambda s: (
            _sig_get(s, "timestamp", ""),
            _sig_get(s, "cycle_id", ""),
            _sig_get(s, "strategy", ""),
        ),
    )

    metadata = {
        "use_graph": kwargs.get("use_graph", True),
        "instrument_universe": kwargs.get("tickers", []),
    }

    for idx, sig in enumerate(sorted_signals):
        try:
            payload = sig.__dict__ if hasattr(sig, "__dict__") else sig
            validate_signal(payload)
        except Exception as exc:
            raise ValueError(
                f"Signal at index {idx} (strategy={_sig_get(sig, 'strategy')!r}) "
                f"failed validation: {exc}"
            ) from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)

    header = {
        "run_id": run_id,
        "schema_version": 1,
        "date_range": "",
        "use_graph": metadata.get("use_graph", True),
        "instrument_universe": metadata.get("instrument_universe", []),
        "signal_count": len(sorted_signals),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(f"# META {json.dumps(header, sort_keys=True, default=str)}\n")
        for sig in sorted_signals:
            out = sig.__dict__ if hasattr(sig, "__dict__") else sig
            fh.write(json.dumps(out, sort_keys=True, default=str) + "\n")

    header["output_path"] = str(output_path)
    return header


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
    parser.add_argument("--run-id", default="run", help="Run identifier for the exported header")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit("Input file not found")

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

    tickers = [t.strip() for t in args.universe.split(",") if t.strip()]
    export_signals(data, Path(args.output), args.run_id, use_graph=args.use_graph, tickers=tickers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
