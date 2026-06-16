"""
Tests for GraphAlpha Schema v1 contracts and replay export.
Run with: python3 -m unittest tests.test_schemas -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.schema_validator import validate_signal, validate_order
from common.versioning import (
    MAX_SUPPORTED_SCHEMA_VERSION,
    validate_schema_version,
)
from backtest.replay_export import export_signals


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_signal(overrides=None):
    sig = {
        "schema_version": 1,
        "cycle_id": "00000000-0000-0000-0000-000000000000",
        "timestamp": "2025-01-01T00:00:00Z",
        "regime": "Trending",
        "strategy": "MomentumOverlay",
        "ticker": "SPY",
        "venue": "ibkr",
        "venue_symbol": "SPY",
        "asset_class": "equity_xstock",
        "direction": "buy",
        "score": 0.5,
        "quant_score": 0.5,
        "sentiment_score": 0.3,
        "news_overlay": 0.0,
        "macro_overlay": 0.0,
        "kg_formula_contribution": 0.0,
        "graph_path": ["Concept A", "HAS_FORMULA", "Formula B"],
        "contradiction_blocked": False,
    }
    if overrides:
        sig.update(overrides)
    return sig


def _make_order(overrides=None):
    order = {
        "schema_version": 1,
        "order_id": "00000000-0000-0000-0000-000000000000",
        "cycle_id": "00000000-0000-0000-0000-000000000000",
        "ticker": "SPY",
        "venue": "ibkr",
        "venue_symbol": "SPY",
        "direction": "buy",
        "quantity": 10.0,
        "notional_usd": 1500.0,
        "kelly_fraction": 0.18,
        "var_contribution_pct": 0.021,
        "mode": "paper",
        "risk_checks": {
            "position_pct_ok": True,
            "sector_pct_ok": True,
            "var_ok": True,
        },
    }
    if overrides:
        order.update(overrides)
    return order


# ── Versioning ───────────────────────────────────────────────────────────────

class TestVersioning(unittest.TestCase):
    def test_current_version_accepted(self):
        self.assertIsNone(validate_schema_version(MAX_SUPPORTED_SCHEMA_VERSION))

    def test_lower_version_accepted(self):
        self.assertIsNone(validate_schema_version(0))

    def test_higher_version_rejected(self):
        with self.assertRaises(ValueError, msg="Unsupported schema_version"):
            validate_schema_version(MAX_SUPPORTED_SCHEMA_VERSION + 1)

    def test_missing_version_rejected(self):
        with self.assertRaises(ValueError, msg="schema_version is required"):
            validate_schema_version(None)

    def test_non_integer_rejected(self):
        with self.assertRaises(ValueError, msg="must be an integer"):
            validate_schema_version("1")


# ── Signal validation ────────────────────────────────────────────────────────

class TestSignalValidation(unittest.TestCase):
    def test_happy_path(self):
        validate_signal(_make_signal())

    def test_invalid_regime_rejected(self):
        with self.assertRaises(Exception, msg="regime"):
            validate_signal(_make_signal({"regime": "GoblinMarket"}))

    def test_crypto_on_ibkr_rejected(self):
        with self.assertRaises(Exception, msg="asset_class"):
            validate_signal(_make_signal({
                "asset_class": "crypto",
                "venue": "ibkr",
                "venue_symbol": "XXBTZUSD",
            }))

    def test_equity_on_kraken_rejected(self):
        with self.assertRaises(Exception, msg="asset_class"):
            validate_signal(_make_signal({
                "asset_class": "equity_xstock",
                "venue": "kraken",
            }))

    def test_hold_above_threshold_rejected(self):
        os.environ["FUSION_THRESHOLD"] = "0.3"
        with self.assertRaises(Exception, msg="hold"):
            validate_signal(_make_signal({
                "direction": "hold",
                "score": 0.5,
            }))

    def test_hold_below_threshold_accepted(self):
        os.environ["FUSION_THRESHOLD"] = "0.3"
        validate_signal(_make_signal({
            "direction": "hold",
            "score": 0.2,
        }))

    def test_score_out_of_bounds_rejected(self):
        for bad in (-1.5, 1.5):
            with self.subTest(score=bad):
                with self.assertRaises(Exception, msg="score"):
                    validate_signal(_make_signal({"score": bad}))

    def test_schema_version_2_rejected(self):
        with self.assertRaises(Exception, msg="Unsupported schema_version"):
            validate_signal(_make_signal({"schema_version": 2}))


# ── ApprovedOrder validation ─────────────────────────────────────────────────

class TestOrderValidation(unittest.TestCase):
    def test_happy_path(self):
        validate_order(_make_order())

    def test_ibkr_live_rejected(self):
        with self.assertRaises(Exception, msg="ibkr"):
            validate_order(_make_order({"venue": "ibkr", "mode": "live"}))

    def test_kraken_live_accepted(self):
        validate_order(_make_order({"venue": "kraken", "mode": "live"}))

    def test_quantity_zero_rejected(self):
        with self.assertRaises(Exception, msg="quantity"):
            validate_order(_make_order({"quantity": 0.0}))

    def test_risk_check_false_rejected(self):
        with self.assertRaises(Exception, msg="risk_checks"):
            validate_order(_make_order({
                "risk_checks": {
                    "position_pct_ok": True,
                    "sector_pct_ok": False,
                    "var_ok": True,
                }
            }))

    def test_kelly_fraction_above_cap_rejected(self):
        with self.assertRaises(Exception, msg="kelly_fraction"):
            validate_order(_make_order({"kelly_fraction": 0.6}))

    def test_schema_version_2_rejected(self):
        with self.assertRaises(Exception, msg="Unsupported schema_version"):
            validate_order(_make_order({"schema_version": 2}))


# ── Replay export ───────────────────────────────────────────────────────────

class TestReplayExport(unittest.TestCase):
    def test_deterministic_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            signals = [_make_signal({"cycle_id": f"c{i:02d}"}) for i in range(3)]
            out = Path(tmp) / "replay.jsonl"
            export_signals(signals, out, "run1", use_graph=True, tickers=["SPY", "QQQ"])
            lines = out.read_text().splitlines()
            self.assertEqual(lines[0][:7], "# META ")
            self.assertEqual(len(lines), 4)  # 1 header + 3 signals
            second = Path(tmp) / "replay2.jsonl"
            export_signals(signals, second, "run1", use_graph=True, tickers=["SPY", "QQQ"])
            second_lines = second.read_text().splitlines()
            self.assertEqual(lines[0][:7], second_lines[0][:7])  # both start with # META
            self.assertEqual(lines[1:], second_lines[1:])  # signal lines are byte-identical

    def test_metadata_header_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            signals = [_make_signal()]
            out = Path(tmp) / "meta.jsonl"
            export_signals(signals, out, "run1", use_graph=False, tickers=[])
            header_line = out.read_text().splitlines()[0]
            self.assertEqual(header_line[:7], "# META ")
            meta = json.loads(header_line[7:])
            self.assertEqual(meta["schema_version"], 1)
            self.assertEqual(meta["signal_count"], 1)
            self.assertIn("run_id", meta)

    def test_invalid_signal_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            signals = [_make_signal({"score": 9.0})]
            with self.assertRaises(ValueError, msg="validation failed"):
                export_signals(signals, Path(tmp) / "bad.jsonl", "run1")

    def test_empty_list_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError, msg="empty signal list"):
                export_signals([], Path(tmp) / "empty.jsonl", "run1")


if __name__ == "__main__":
    unittest.main()
