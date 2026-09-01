"""Logic-correction tests for regime detection, strategy dispatch and risk sizing.

Covers the REF-grounded changes:
  * MeanReverting / LowVolatility regimes are now reachable。



  * SystemicStress requires a multi-cycle persistence gate (no whipsaw。
  * `signal_agent` dispatches on the Neo4j `signal_method` contract (not name substrings。
  * RiskAgent honors the KG `risk_weight` scaling and the correlation-breakdown cap。
"""
import os
import sys

# The agent modules import `from alpaca_data import provider` — resolve the
# bare module name by adding /app/agent (mirrors how the agent process runs)。
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
_AGENT = os.path.join(_REPO, "agent")
if _AGENT not in sys.path:
    sys.path.insert(0, _AGENT)
del os, sys, _REPO, _AGENT

import numpy as np
import pandas as pd
import pytest

from agent.regime_agent import RegimeAgent, STRESS_CONFIRM_CYCLES
from agent.signal_agent import SignalAgent
from agent.risk_agent import RiskAgent


def _feats(**over):
    f = RegimeAgent()._empty_features()
    f.update({
        "ewma_vol": 0.2,
        "vol_21":  0.2,
        "vol_zscore": 0.0,
        "ret_21":    -0.02,
        "price_vs_200ma":  0.01,
        "vr_21":    1.0,
        "corr_breakdown":   0.5,
        "cusum_alarm":  False,
        "hyg_dd_63":      0.0,
    })
    f.update(over)
    return f


def test_mean_reverting_reachable():
    agent = RegimeAgent()
    assert agent._classify_regime(_feats(vr_21=0.7)) == "MeanReverting"


def test_low_volatility_reachable():
    agent = RegimeAgent()
    assert agent._classify_regime(_feats(vol_zscore=-1.5)) == "LowVolatility"


def test_crisis_reachable():
    agent = RegimeAgent()
    feats = _feats(
        vol_zscore=2.0,
        price_vs_200ma=-0.1,
        corr_breakdown=0.85,
        cusum_alarm=True,
        hyg_dd_63=0.08,
    )
    assert agent._classify_regime(feats) == "Crisis"


def test_persistence_gate_requires_n_cycles():
    agent = RegimeAgent()
    feats = _feats(
        vol_zscore=1.5,
        price_vs_200ma=-0.1,
        corr_breakdown=0.85,
        cusum_alarm=True,
        hyg_dd_63=0.08,
    )
    # First N-1 consecutive stress-triple cycles: still Crisis (unconfirmed)。
    for _ in range(STRESS_CONFIRM_CYCLES - 1):
        assert agent._classify_regime(feats) == "Crisis"
    # Nth consecutive stress-triple cycle: SystemicStress confirmed。
    assert agent._classify_regime(feats) == "SystemicStress"
    # A single non-stress cycle resets the streak (no recalibration on one tick)。
    assert agent._classify_regime(_feats(vr_21=0.7)) == "MeanReverting"
    assert agent._classify_regime(feats) == "Crisis"


def test_dispatch_routes_by_signal_method():
    agent = SignalAgent()
    prices = pd.DataFrame({"SPY": np.linspace(100, 200, 300)})
    calls = []

    def stub(name):
        def f(*args, **kwargs):
            calls.append(name)
            return {"ticker": args[1], "score": 0.0, "reasoning": name}
        return f

    agent._momentum_signal = stub("momentum")
    agent._value_mr_signal = stub("value_mr")
    agent._vol_zscore_signal = stub("vol_zscore")
    agent._crisis_hedge_signal = stub("crisis_hedge")

    r = agent._compute_quant_signal(
        {"name": "Smart Beta Tilt", "signal_method": "value_mr", "ticker": "XLF"},
        prices, None,
    )
    assert calls == ["value_mr"] and r["ticker"] == "XLF"

    r = agent._compute_quant_signal(
        {"name": "Momentum Breakout", "signal_method": "momentum", "ticker": "QQQ"},
        prices, None,
    )
    assert calls == ["value_mr", "momentum"] and r["ticker"] == "QQQ"


def test_kelly_respects_risk_weight():
    agent = RiskAgent()
    base = agent._kelly_fraction({"score": 0.6})
    scaled = agent._kelly_fraction({"score": 0.6, "risk_weight": 0.5})
    assert abs(base * 0.5 - scaled) < 1e-9
    assert agent._kelly_fraction({"score":  0.6,  "risk_weight": 2.5}) == pytest.approx(base)


def test_corr_breakdown_spikes_on_perfect_corr():
    agent = RiskAgent()
    idx = pd.date_range("2024-01-01", periods=100, freq="B")
    r = np.random.default_rng(7).normal(0.001,  0.01,  100)

    s = pd.Series(100 * (1 + r).cumprod(), index=idx)
    prices = {t: s * (1 + i * 1e-9) for i, t in enumerate(["SPY", "QQQ", "XLF", "XLE", "GLD"])}
    assert agent._corr_breakdown(prices) >= 0.95


def test_neutral_has_active_strategies():
    from common.graph import get_db
    try:
        db = get_db()
        rows = list(db.execute_and_fetch(
            "MATCH (s:Strategy)-[:ACTIVATED_BY]->(r:Regime {name:'Neutral'}) "
            "WHERE s.status = 'active' RETURN count(*) AS n"
        ))
    except Exception:
        pytest.skip("Neo4j unreachable in test environment")
    assert rows and rows[0]["n"] >= 1