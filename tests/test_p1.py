from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np


class UniverseTestCase(unittest.TestCase):
    def test_universe_entries_fields(self):
        from backtest.universe import get_universe
        for entry in get_universe():
            self.assertIn(entry.asset_class, {"equity_xstock", "macro_proxy", "crypto"})
            self.assertIn(entry.venue, {"ibkr", "kraken"})
            self.assertTrue(entry.venue_symbol.isascii())
            self.assertIsInstance(entry.sector, str)

    def test_universe_routing(self):
        from backtest.universe import get_universe, add
        for entry in get_universe():
            if entry.asset_class == "crypto":
                self.assertEqual(entry.venue, "kraken")
            else:
                self.assertEqual(entry.venue, "ibkr")

    def test_universe_validation(self):
        from backtest.universe import add, lookup
        add("TST", "equity_xstock", "ibkr", "TST", "Test")
        entry = lookup("TST")
        self.assertEqual(entry.venue_symbol, "TST")
        self.assertEqual(entry.sector, "Test")


class LoaderTestCase(unittest.TestCase):
    def test_load_equity(self):
        from backtest.loaders import load_for_ticker
        df = load_for_ticker("SPY", "2023-01-01", "2023-01-31")
        self.assertIn("SPY", df.columns)
        self.assertFalse(df.empty)

    def test_load_crypto(self):
        from backtest.loaders import load_for_ticker
        df = load_for_ticker("BTC-USD", "2023-01-01", "2023-01-31")
        self.assertIn("BTC-USD", df.columns)
        self.assertFalse(df.empty)

    def test_no_gap(self):
        from backtest.loaders import load_for_ticker
        with patch("backtest.loaders._is_crypto", return_value=True), \
             patch("backtest.loaders._load_coinbase_crypto") as mock_cb:
            mock_cb.return_value = None
            with self.assertRaises(Exception):
                load_for_ticker("BTC-USD", "2020-01-01", "2023-01-31")


class OverlaysTestCase(unittest.TestCase):
    def test_news_bounds(self):
        from backtest.overlays import NewsOverlay
        ov = NewsOverlay()
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(ov.get("SPY", dt), 0.0)

    def test_macro_disabled(self):
        from backtest.overlays import get_overlay
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(get_overlay("news", "SPY", dt, disabled=True), 0.0)
        self.assertEqual(get_overlay("macro", "SPY", dt, disabled=True), 0.0)


class StrategiesTestCase(unittest.TestCase):
    def _make_bar(self):
        return {
            "SPY": {"close": 100.0, "ma21": 99.0, "annual_vol": 0.2, "ma200": 98.0, "return_21": 0.05, "vol_21": 0.1},
            "QQQ": {"close": 200.0, "ma21": 199.0},
            "vix": 18.0,
        }

    def test_momentum(self):
        from backtest.strategies import MomentumOverlay
        out = MomentumOverlay().generate_signal(self._make_bar(), {})
        self.assertIsInstance(out, dict)
        self.assertTrue(-1.0 <= out["score"] <= 1.0)

    def test_crisis(self):
        from backtest.strategies import CrisisAlpha
        out = CrisisAlpha().generate_signal(self._make_bar(), {})
        self.assertEqual(out["ticker"], "SPY")


class EventEngineTestCase(unittest.TestCase):
    def test_mini_run(self):
        from backtest.event_engine import EventEngine
        ee = EventEngine(start="2023-01-01", end="2023-01-31", use_graph=False)
        ee.run()
        self.assertGreater(len(ee.signals), 0)
        for sig in ee.signals:
            self.assertEqual(sig.schema_version, 1)
            self.assertIn(sig.regime, {"Trending", "MeanReverting", "LowVolatility", "HighVolatility", "SystemicStress", "Crisis", "Recovery"})

    def test_no_graph_generates_signals(self):
        from backtest.event_engine import EventEngine
        ee = EventEngine(start="2023-01-01", end="2023-01-31", use_graph=False, disable_news_overlay=True, disable_macro_overlay=True)
        ee.run()
        self.assertTrue(any(s.strategy == "MomentumOverlay" for s in ee.signals))


class FeesTestCase(unittest.TestCase):
    def test_crypto_fee(self):
        from backtest.fees import fee_slippage_for
        fee, slip = fee_slippage_for("BTC-USD", "crypto", "kraken")
        self.assertEqual(fee, 0.0026)

    def test_equity_fee(self):
        from backtest.fees import fee_slippage_for
        fee, slip = fee_slippage_for("SPY", "equity_xstock", "ibkr")
        self.assertEqual(fee, 0.0010)


class ReplayExportTestCase(unittest.TestCase):
    def test_export_smoke(self):
        from backtest.event_engine import EventEngine
        from backtest.replay_export import export_signals
        ee = EventEngine(start="2023-01-01", end="2023-01-31", use_graph=False)
        ee.run()
        import tempfile, pathlib
        out = pathlib.Path(tempfile.mktemp(suffix=".jsonl"))
        meta = export_signals(ee.signals, str(out), "run1", use_graph=False, tickers=["SPY", "QQQ", "TLT", "GLD", "BTC-USD"])
        self.assertTrue(out.exists())
        lines = [l for l in out.read_text().splitlines() if l.strip() and not l.startswith("#")]
        self.assertGreater(len(lines), 0)
        for line in lines[:5]:
            import json
            sig = json.loads(line)
            self.assertEqual(sig["schema_version"], 1)


class DynamicUniverseTestCase(unittest.TestCase):
    def test_dynamic_tickers_any_asset(self):
        from backtest.universe import set_universe, get_universe
        set_universe(["AAPL", "MSFT", "TSLA"])
        entries = get_universe()
        tickers = [e.ticker for e in entries]
        self.assertIn("AAPL", tickers)
        self.assertIn("MSFT", tickers)
        self.assertTrue(all(e.venue == "ibkr" for e in entries))
        self.assertTrue(all(e.asset_class == "equity_xstock" for e in entries))

    def test_dynamic_crypto_tickers(self):
        from backtest.universe import set_universe, get_universe
        set_universe(["ETH-USD", "SOL-USD"])
        entries = get_universe()
        tickers = [e.ticker for e in entries]
        self.assertIn("ETH-USD", tickers)
        self.assertIn("SOL-USD", tickers)
        for e in entries:
            self.assertEqual(e.asset_class, "crypto")
            self.assertEqual(e.venue, "kraken")

    def test_universe_presets(self):
        from backtest.universe import use_preset, get_universe
        use_preset("crypto")
        self.assertEqual([e.ticker for e in get_universe()], ["BTC-USD", "ETH-USD"])
        use_preset("equity")
        self.assertEqual([e.ticker for e in get_universe()], ["SPY", "QQQ", "TLT", "GLD"])
