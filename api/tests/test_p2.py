import os

os.environ.setdefault("AGENT_KELLY_FRACTION", "0.5")
os.environ.setdefault("AGENT_MAX_POSITION_PCT", "0.20")
os.environ.setdefault("RISK_MAX_SECTOR_PCT", "0.40")
os.environ.setdefault("RISK_VAR_CONFIDENCE", "0.99")
os.environ.setdefault("RISK_MAX_VAR_PCT", "0.05")
os.environ.setdefault("AGENT_MAX_DRAWDOWN_HALT", "0.10")

import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class ProfitFactorTest(unittest.TestCase):
    def test_profit_loss(self):
        from backtest.metrics import profit_factor
        pnls = np.array([100.0, -50.0, 75.0])
        self.assertAlmostEqual(profit_factor(pnls), 175.0 / 50.0)

    def test_loss_zero(self):
        from backtest.metrics import profit_factor
        self.assertIsNone(profit_factor(np.array([100.0, 50.0])))

    def test_empty(self):
        from backtest.metrics import profit_factor
        self.assertIsNone(profit_factor(np.array([])))

    def test_all_loss(self):
        from backtest.metrics import profit_factor
        self.assertEqual(profit_factor(np.array([-10.0, -20.0])), 0.0)


class WinRateTest(unittest.TestCase):
    def test_basic(self):
        from backtest.metrics import win_rate
        pnls = np.array([10.0, -5.0, 15.0, -2.0])
        self.assertAlmostEqual(win_rate(pnls), 0.5)

    def test_empty(self):
        from backtest.metrics import win_rate
        self.assertEqual(win_rate(np.array([])), 0.0)

    def test_all_wins(self):
        from backtest.metrics import win_rate
        self.assertEqual(win_rate(np.array([1.0, 2.0, 3.0])), 1.0)


class AvgHoldDaysTest(unittest.TestCase):
    def test_average(self):
        from backtest.metrics import avg_hold_days
        en = [pd.Timestamp("2022-01-01"), pd.Timestamp("2022-01-05")]
        ex = [pd.Timestamp("2022-01-06"), pd.Timestamp("2022-01-15")]
        self.assertAlmostEqual(avg_hold_days(en, ex), 7.5)

    def test_empty(self):
        from backtest.metrics import avg_hold_days
        self.assertIsNone(avg_hold_days([], []))

    def test_mismatched_lengths(self):
        from backtest.metrics import avg_hold_days
        self.assertIsNone(avg_hold_days([pd.Timestamp("2022-01-01")], []))


class TradeSummaryTest(unittest.TestCase):
    def test_keys_present(self):
        from backtest.metrics import trade_summary
        pnls = np.array([10.0, -5.0])
        result = trade_summary(pnls)
        for k in ["total_return", "sharpe_ratio", "calmar_ratio", "max_drawdown",
                   "ann_volatility", "n_days", "profit_factor", "win_rate", "avg_hold_days"]:
            self.assertIn(k, result)


class BreakdownByRegimeTest(unittest.TestCase):
    def test_groups(self):
        from backtest.metrics_breakdown import breakdown_by_regime
        trades = [
            {"pnl": 10.0, "regime_at_entry": "Trending", "entry_ts": "2022-01-01", "exit_ts": "2022-01-05"},
            {"pnl": -5.0, "regime_at_entry": "Crisis", "entry_ts": "2022-02-01", "exit_ts": "2022-02-10"},
            {"pnl": 3.0,  "regime_at_entry": "Trending", "entry_ts": "2022-03-01", "exit_ts": "2022-03-05"},
        ]
        out = breakdown_by_regime(trades)
        self.assertIn("Trending", out)
        self.assertIn("Crisis", out)


class BreakdownByOverlayConfigTest(unittest.TestCase):
    def test_keys(self):
        from backtest.metrics_breakdown import breakdown_by_overlay_config
        data = {
            "baseline": [
                {"pnl": 10.0, "entry_ts": "2022-01-01", "exit_ts": "2022-01-05"},
            ],
            "news_off": [
                {"pnl": 5.0, "entry_ts": "2022-01-01", "exit_ts": "2022-01-05"},
            ],
        }
        out = breakdown_by_overlay_config(data)
        self.assertEqual(len(out), 2)
        for v in out.values():
            self.assertIn("profit_factor", v)
            self.assertIn("win_rate", v)


class RiskSimDeterminismTest(unittest.TestCase):
    def test_deterministic(self):
        from backtest.risk_sim import PortfolioState, size_signal
        prices = {
            "SPY": pd.Series(np.linspace(100, 110, 60)),
        }
        signal = {
            "ticker": "SPY",
            "direction": "buy",
            "score": 0.8,
            "cycle_id": "c1",
        }
        portfolio = PortfolioState(nav=10000.0, cash=10000.0, positions={})
        orders = [size_signal(signal, portfolio, prices) for _ in range(20)]
        qty0 = orders[0].quantity
        for o in orders[1:]:
            self.assertAlmostEqual(o.quantity, qty0)


class RiskSimKellyTest(unittest.TestCase):
    def test_half_kelly(self):
        from backtest.risk_sim import PortfolioState, size_signal
        prices = {"SPY": pd.Series(np.linspace(100, 110, 60))}
        signal = {"ticker": "SPY", "direction": "buy", "score": 1.0, "cycle_id": "c1"}
        portfolio = PortfolioState(nav=10000.0, cash=10000.0, positions={})
        order = size_signal(signal, portfolio, prices)
        self.assertIsNotNone(order.rejection_reason or order.quantity)
        if order.quantity > 0:
            p_win = 0.5 + 0.25 * 1.0
            kelly = max(0.0, (p_win * 1.5 - (1.0 - p_win)) / 1.5 / 2.0)
            expected = 10000.0 * kelly * 0.20
            actual = order.notional_usd
            self.assertAlmostEqual(actual, expected, delta=expected * 1e-6)


class RiskSimSectorCapTest(unittest.TestCase):
    def test_rejected(self):
        from backtest.risk_sim import PortfolioState, size_signal
        prices = {"SPY": pd.Series(np.linspace(100, 110, 60))}
        signal = {"ticker": "SPY", "direction": "buy", "score": 0.9, "cycle_id": "c1"}
        positions = {
            "p1": {"notional": 4500.0, "sector": "equity_broad", "ticker": "SPY"},
        }
        portfolio = PortfolioState(nav=10000.0, cash=5500.0, positions=positions)
        order = size_signal(signal, portfolio, prices)
        self.assertEqual(order.rejection_reason, "sector_cap")


class RiskSimVaRTest(unittest.TestCase):
    def test_rejected(self):
        from backtest.risk_sim import PortfolioState, size_signal
        np.random.seed(42)
        high_vol = pd.Series(np.cumsum(np.random.randn(60) * 0.05))
        prices = {"SPY": high_vol}
        signal = {"ticker": "SPY", "direction": "buy", "score": 1.0, "cycle_id": "c1"}
        portfolio = PortfolioState(nav=10000.0, cash=10000.0, positions={})
        with patch("backtest.risk_sim.MAX_VAR_PCT", 0.0001):
            order = size_signal(signal, portfolio, prices)
        self.assertEqual(order.rejection_reason, "var_cap")


class RiskSimCircuitBreakerTest(unittest.TestCase):
    def test_halted(self):
        from backtest.risk_sim import PortfolioState, size_signal
        prices = {"SPY": pd.Series(np.linspace(100, 110, 60))}
        signal = {"ticker": "SPY", "direction": "buy", "score": 1.0, "cycle_id": "c1"}
        portfolio = PortfolioState(nav=10000.0, cash=10000.0, positions={}, drawdown_from_peak=0.15)
        order = size_signal(signal, portfolio, prices)
        self.assertEqual(order.rejection_reason, "circuit_breaker_halt")


class RiskSimNoPriceTest(unittest.TestCase):
    def test_no_price(self):
        from backtest.risk_sim import PortfolioState, size_signal
        signal = {"ticker": "SPY", "direction": "buy", "score": 1.0, "cycle_id": "c1"}
        portfolio = PortfolioState(nav=10000.0, cash=10000.0, positions={})
        order = size_signal(signal, portfolio, {})
        self.assertEqual(order.rejection_reason, "no_price")


class EventEngineIntegrationTest(unittest.TestCase):
    def test_produces_output_arrays(self):
        from backtest.event_engine import EventEngine
        ee = EventEngine(start="2022-01-01", end="2022-03-31", use_graph=False,
                         disable_news_overlay=True, disable_macro_overlay=True)
        ee.run()
        self.assertIsInstance(ee.signals, list)
        self.assertIsInstance(ee.trades, list)
        self.assertIsInstance(ee.rejected_signals, list)
        self.assertIsInstance(ee.equity_curve, list)
        self.assertIsInstance(ee.halted_periods, list)
        self.assertGreater(len(ee.signals), 0)

    def test_fifo_position_matching(self):
        from backtest.event_engine import EventEngine
        ee = EventEngine(start="2022-01-01", end="2022-06-30", use_graph=False,
                         disable_news_overlay=True, disable_macro_overlay=True)
        ee.run()
        if ee.trades:
            for t in ee.trades:
                self.assertIsNotNone(t.position_id)
                self.assertIsNotNone(t.regime_at_entry)

    def test_equity_curve_nonempty(self):
        from backtest.event_engine import EventEngine
        ee = EventEngine(start="2022-01-01", end="2022-03-31", use_graph=False,
                         disable_news_overlay=True, disable_macro_overlay=True)
        ee.run()
        self.assertGreater(len(ee.equity_curve), 0)
        for e in ee.equity_curve:
            self.assertIn("nav", e)
            self.assertIn("timestamp", e)


class CLISmokeTest(unittest.TestCase):
    def test_single_run(self):
        from backtest.cli import main
        import io, json
        old = sys.stdout
        sys.stdout = io.StringIO()
        rc = main(["--start", "2022-01-01", "--end", "2022-03-31",
                   "--use-graph", "--disable-news-overlay", "--disable-macro-overlay"])
        out = sys.stdout.getvalue()
        sys.stdout = old
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertIn("summary", data)
        self.assertIn("trade_log", data)
        self.assertIn("equity_curve", data)

    def test_ablation_run(self):
        from backtest.cli import main
        import io, json
        old = sys.stdout
        sys.stdout = io.StringIO()
        rc = main(["--start", "2022-01-01", "--end", "2022-03-31",
                   "--use-graph", "--ablate-overlays",
                   "--disable-news-overlay"])
        out = sys.stdout.getvalue()
        sys.stdout = old
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertIn("ablation", data)
        self.assertIn("metrics_by_overlay_config", data)


class EnvAlignmentTest(unittest.TestCase):
    def test_thresholds_match_dotenv(self):
        from backtest.risk_sim import (
            KELLY_FRACTION, MAX_POSITION_PCT, MAX_SECTOR_PCT,
            VAR_CONFIDENCE, MAX_VAR_PCT, MAX_DRAWDOWN_HALT,
        )
        self.assertAlmostEqual(MAX_SECTOR_PCT, 0.40)
        self.assertAlmostEqual(VAR_CONFIDENCE, 0.99)
        self.assertAlmostEqual(MAX_VAR_PCT, 0.05)
        self.assertAlmostEqual(KELLY_FRACTION, 0.5)
        self.assertAlmostEqual(MAX_POSITION_PCT, 0.20)
        self.assertAlmostEqual(MAX_DRAWDOWN_HALT, 0.10)


if __name__ == "__main__":
    unittest.main()
