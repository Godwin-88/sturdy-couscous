"""HedgeAgent unit tests - dynamic delta hedging, Taleb posture, dry-run safety.

Verifies portfolio-greek aggregation math (equity delta + option contracts x100),
hedge-share computation, regime-scaled bands (tighter in stress), the tail-sleeve
recommendation, the human-in-the-loop gate (confirm=False never executes), and the
new option_pnl (premium income vs hedge cost) report.

The agent is now async (it awaits the Alpaca coroutines) so the tests wrap each
call in asyncio.run and stub the network via monkeypatched async fakes.
"""
import asyncio

import pytest

import agent.hedge_agent as hmod
from agent.hedge_agent import HedgeAgent, _BAND_MULT


def _run(coro):
    return asyncio.run(coro)


def _agent_with_greeks(delta: float, gamma: float = 0.0, theta: float = 0.0,
                       vega: float = 0.0, positions: list | None = None,
                       regime: str = "Neutral"):
    class _SnapProvider:
        def get_snapshot(self, symbol):
            return {"greeks": {"delta": delta, "gamma": gamma, "theta": theta,
                               "vega": vega, "implied_volatility": 0.2}}

    hmod.options_provider = _SnapProvider()

    async def _fake_positions():
        return positions if positions is not None else [
            {"symbol": "SPY", "qty": 100, "avg_entry_price": 760.0,
             "current_price": 762.0, "market_value": 76200.0},
            {"symbol": "SPY260904C00770000", "qty": 1, "avg_entry_price": 3.0,
             "current_price": 2.5, "market_value": 250.0},
        ]

    async def _fake_regime():
        return {"regime": regime, "confidence": 0.8}

    async def _fake_spot(underlying):
        return 762.0

    ha = HedgeAgent()
    ha._fetch_positions = _fake_positions
    ha.regime          = _fake_regime
    ha.spot            = _fake_spot
    return ha


def test_portfolio_greeks_equity_plus_option():
    ha = _agent_with_greeks(delta=0.5, gamma=0.01, theta=-2.0, vega=0.8)
    g = _run(ha.portfolio_greeks())
    assert g["greeks"]["delta"] == pytest.approx(150.0)
    assert g["greeks"]["gamma"] == pytest.approx(1.0)
    assert g["greeks"]["theta"] == pytest.approx(-200.0)
    assert g["greeks"]["vega"] == pytest.approx(80.0)
    assert len(g["positions"]) == 2


def test_short_option_negates_greeks():
    ha = _agent_with_greeks(delta=0.5, gamma=0.01, theta=-2.0, vega=0.8,
                            positions=[{"symbol": "SPY260904C00770000", "qty": -1,
                                        "avg_entry_price": 3.0, "current_price": 2.5,
                                        "market_value": -250.0}])
    g = _run(ha.portfolio_greeks())
    assert g["greeks"]["delta"] == pytest.approx(-50.0)
    assert g["greeks"]["gamma"] == pytest.approx(-1.0)


def test_hedge_shares_math_and_band():
    ha = _agent_with_greeks(delta=0.5, gamma=0.01)
    st = _run(ha.hedge_state("SPY"))
    assert st["hedge_shares"] == pytest.approx(-0.20, abs=1e-2)
    assert st["needs_rebalance"] is False
    assert st["proposal"] is None


def test_hedge_triggers_on_big_delta():
    ha = _agent_with_greeks(delta=0.6,
                            positions=[{"symbol": "SPY260904C00770000", "qty": 20,
                                        "avg_entry_price": 3.0, "current_price": 2.5,
                                        "market_value": 5000.0}])
    st = _run(ha.hedge_state("SPY"))
    assert st["needs_rebalance"] is True
    assert st["proposal"]["side"] == "sell"
    assert st["proposal"]["qty"] >= 1


def test_stress_regime_tightens_band_and_triggers_sooner():
    assert _BAND_MULT["Neutral"] == 1.5
    assert _BAND_MULT["HighVolatility"] == 0.5
    assert _BAND_MULT["Crisis"] == 0.25
    assert _BAND_MULT["Crisis"] < _BAND_MULT["Neutral"]
    ha_stress = _agent_with_greeks(delta=0.6, regime="Crisis",
                            positions=[{"symbol": "SPY260904C00770000", "qty": 20,
                                        "avg_entry_price": 3.0, "current_price": 2.5,
                                        "market_value": 5000.0}])
    st = _run(ha_stress.hedge_state("SPY"))
    assert st["needs_rebalance"] is True
    assert st["band_shares"] < 20.0


def test_execute_requires_confirm():
    ha = _agent_with_greeks(delta=0.6,
                            positions=[{"symbol": "SPY260904C00770000", "qty": 20,
                                        "avg_entry_price": 3.0, "current_price": 2.5,
                                        "market_value": 5000.0}])
    res = _run(ha.execute("SPY", confirm=False))
    assert res["status"] == "dry_run"
    assert "confirm=true" in res["message"]


def test_tail_sleeve_stress_only():
    ha = _agent_with_greeks(delta=0.0)
    calm = ha.tail_sleeve({"gamma": 0.0, "theta": -10.0}, "Neutral", 762.0)
    assert calm["recommended"] is False
    stress = ha.tail_sleeve({"gamma": -200.0, "theta": -10.0}, "HighVolatility", 762.0)
    assert stress["recommended"] is True
    assert "puts" in stress["suggest"].lower()


def test_option_pnl_income_vs_cost():
    positions = [
        {"symbol": "SPY", "qty": 100, "avg_entry_price": 760.0,
         "current_price": 762.0, "market_value": 76200.0},
        {"symbol": "SPY260904P00750000", "qty": 1, "avg_entry_price": 4.0,
         "current_price": 3.0, "market_value": 300.0},
        {"symbol": "SPY260904C00770000", "qty": -1, "avg_entry_price": 2.0,
         "current_price": 2.5, "market_value": -250.0},
    ]
    ha = _agent_with_greeks(delta=0.5, positions=positions)
    pnl = _run(ha.option_pnl())
    assert pnl["contracts"] == 2
    assert pnl["premium_income_usd"] == pytest.approx(200.0)
    assert pnl["premium_cost_usd"] == pytest.approx(400.0)
    assert pnl["net_premium_usd"] == pytest.approx(-200.0)
    assert pnl["unrealized_pnl_usd"] == pytest.approx(-150.0)
    assert pnl["hedge_sleeve_mv_usd"] == pytest.approx(76200.0)


def test_singleton_exists():
    assert hmod.hedge_agent is not None
    assert hmod.hedge_agent.min_shares > 0
