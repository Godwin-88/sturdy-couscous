"""Loss-averse ranking engine tests — the rating that protects the account.

Verifies that options suggestions are HARD-GATED by max-loss-as-%NAV and RANKED
by the Kahneman–Tversky loss-aversion score (raw score - lambda * max_loss_pct_nav)
rather than raw expected value, so a Bear Call with maxP $91 / maxL $408 is never
ranked #1 over a defined-risk trade.
"""
import numpy as np  # noqa: F401 (np used via _score elsewhere)

from agent.option_signal import (
    LOSS_AVERSION_LAMBDA,
    _hedge_requirement,
    _loss_aversion_score,
)


def test_loss_aversion_penalizes_high_max_loss():
    # Same raw score, vastly different max-loss exposure -> penalty crushes the
    # maxL=4080 one (4% NAV on 100k) vs the maxL=408 one (0.4% NAV).
    risky = _loss_aversion_score(60.0, 4080.0, 100000.0, lambda_=LOSS_AVERSION_LAMBDA)
    safe = _loss_aversion_score(60.0, 408.0, 100000.0, lambda_=LOSS_AVERSION_LAMBDA)
    assert safe > risky
    # Defensive lens penalises harder than average for the same exposure.
    dfl = _loss_aversion_score(60.0, 5000.0, 100000.0, lambda_=3.5)
    avg = _loss_aversion_score(60.0, 5000.0, 100000.0, lambda_=LOSS_AVERSION_LAMBDA)
    assert dfl < avg


def test_loss_aversion_never_above_raw_score():
    la = _loss_aversion_score(55.0, 500.0, 100000.0, lambda_=LOSS_AVERSION_LAMBDA)
    assert la <= 55.0 + 1e-9


def test_loss_aversion_score_scale():
    # 0 max loss -> unchanged; negative/zero nav -> unchanged raw.
    assert _loss_aversion_score(42.0, 0.0, 100000.0) == 42.0
    assert _loss_aversion_score(42.0, 500.0, 0.0) == 42.0


def test_defined_risk_spread_beats_naked_on_defensive():
    # Naked short straddle (max loss unbounded/large) vs iron condor (defined).
    straddle = _loss_aversion_score(80.0, 20000.0, 100000.0, lambda_=3.5)
    condor = _loss_aversion_score(65.0, 1200.0, 100000.0, lambda_=3.5)
    assert condor > straddle


def test_hedge_requirement_flags_short_gamma_in_stress():
    h = _hedge_requirement("short_straddle", [], "HighVolatility")
    assert h["hedge_req"] is True
    assert "hedge" in h["hedge_reason"].lower()
    # Hedge vehicles themselves are not flagged for re-hedging.
    h2 = _hedge_requirement("put_spread_hedge", [], "Crisis")
    assert h2["hedge_req"] is False


def test_hedge_requirement_calm_regime():
    h = _hedge_requirement("cash_secured_put", [], "Neutral")
    assert h["hedge_req"] is False