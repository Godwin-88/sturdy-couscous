"""Hermetic tests for the H6-9 lending pool on the attested fund claim.

Covers the deterministic financial logic only (no network):
  - utilization-based pricing (HTD Ch.5 quadratic + reserve factor)
  - borrow capacity = min(ltv_cap, liquidity_cap, approved_decision)
  - human-gate: borrow refused without an approved decision / over cap
  - liquidation monitor (warn + liquidatable thresholds, closing price)
  - money-leg degradation (execution-service offline marks-to-model)
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import creditgraph.services.lending_pool as lp


class FakeRedis:
    """Minimal in-memory redis stand-in (get/set)."""

    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def get(self, key: str):
        return self._d.get(key)

    def set(self, key: str, value: str, ex=None) -> None:
        self._d[key] = value

    def delete(self, key: str) -> None:
        self._d.pop(key, None)


@pytest.fixture()
def fake_redis():
    fr = FakeRedis()
    # Keep the patch active for the ENTIRE test (module calls _r() throughout).
    with patch.object(lp, "_r", return_value=fr):
        # Force a clean, env-independent baseline so tests are hermetic.
        pool = lp._default_pool()
        pool["total_deposits"] = 0.0
        pool["active_loan"] = 0.0
        fr._d[lp.POOL_KEY] = json.dumps(pool)
        fr._d.pop("fund:attestation_report", None)
        yield fr


def _set_pool(fr: FakeRedis, pool: dict) -> None:
    fr._d[lp.POOL_KEY] = json.dumps(pool)


def _set_nav(fr: FakeRedis, nav: float) -> None:
    fr._d["fund:attestation_report"] = json.dumps({"nav": nav, "equity": nav})


def test_rates_zero_utilization(fake_redis):
    """u=0 -> borrow=base, lend=0 (lenders earn nothing while pool idle)."""
    pool = lp.load_pool()
    rates = lp.compute_rates(pool)
    assert rates["utilization"] == 0.0
    assert rates["borrow_rate_pct"] == lp.BASE_BORROW_RATE_PCT
    assert rates["lend_rate_pct"] == 0.0


def test_rates_quadratic_and_reserve(fake_redis):
    """u=0.5 -> borrow=base+slope*0.25; lend = borrow*u*(1-reserve)."""
    pool = lp.load_pool()
    pool["total_deposits"] = 1000.0
    pool["active_loan"] = 500.0
    rates = lp.compute_rates(pool)
    expected_borrow = lp.BASE_BORROW_RATE_PCT + lp.SLOPE_PCT * 0.25
    assert rates["utilization"] == pytest.approx(0.5)
    assert rates["borrow_rate_pct"] == pytest.approx(round(expected_borrow, 4))
    assert rates["lend_rate_pct"] == pytest.approx(
        round(expected_borrow * 0.5 * (1.0 - lp.RESERVE_FACTOR), 4)
    )


def test_borrow_capacity_min_ltv_liquidity(fake_redis):
    _set_nav(fake_redis, 100_000.0)
    pool = lp.load_pool()
    pool["total_deposits"] = 10_000.0
    _set_pool(fake_redis, pool)

    snap = lp.public_pool_snapshot()
    ltv_cap = 100_000.0 * lp.MAX_LTV_PCT / 100.0
    assert snap["borrowable"] == pytest.approx(min(ltv_cap, 10_000.0))
    assert snap["status"] == "open"


def test_borrow_requires_approved_decision(fake_redis):
    _set_nav(fake_redis, 100_000.0)
    pool = lp.load_pool()
    pool["total_deposits"] = 10_000.0
    _set_pool(fake_redis, pool)

    with patch.object(lp, "_approved_decision_cap", return_value={}):
        result = lp.borrow(100.0)
    assert result["ok"] is False
    assert "approval" in result["error"].lower()


def test_borrow_over_decision_recommendation_refused(fake_redis):
    _set_nav(fake_redis, 100_000.0)
    pool = lp.load_pool()
    pool["total_deposits"] = 10_000.0
    _set_pool(fake_redis, pool)
    approved = {"decision_id": "d1", "recommended_amount": 500.0}

    with patch.object(lp, "_approved_decision_cap", return_value=approved):
        result = lp.borrow(600.0)
    assert result["ok"] is False
    assert "recommendation" in result["error"]


def test_borrow_over_liquidity_refused(fake_redis):
    _set_nav(fake_redis, 1_000_000.0)
    pool = lp.load_pool()
    pool["total_deposits"] = 100.0
    _set_pool(fake_redis, pool)
    approved = {"decision_id": "d1", "recommended_amount": 10_000.0}

    with patch.object(lp, "_approved_decision_cap", return_value=approved):
        result = lp.borrow(500.0)
    assert result["ok"] is False
    assert "borrowable" in result["error"]


def test_borrow_success_marks_loan_and_degrades_money_leg(fake_redis):
    _set_nav(fake_redis, 100_000.0)
    pool = lp.load_pool()
    pool["total_deposits"] = 10_000.0
    _set_pool(fake_redis, pool)
    approved = {"decision_id": "d1", "recommended_amount": 5_000.0}

    with patch.object(lp, "_approved_decision_cap", return_value=approved), patch(
        "httpx.post", side_effect=Exception("execution-service offline")
    ):
        result = lp.borrow(2_000.0)  # money leg offline -> marks-to-model
    assert result["ok"] is True
    assert result["disbursement_tx"] is None
    assert result["pool"]["active_loan"] == pytest.approx(2_000.0)
    assert result["pool"]["utilization"] == pytest.approx(0.2)
    assert result["pool"]["last_borrow_decision"] == "d1"


def test_borrow_frozen_at_ltv_warning(fake_redis):
    _set_nav(fake_redis, 10_000.0)
    pool = lp.load_pool()
    pool["total_deposits"] = 9_000.0
    pool["active_loan"] = 7_100.0  # 71% LTV -> warning (>= 70%)
    _set_pool(fake_redis, pool)
    approved = {"decision_id": "d1", "recommended_amount": 5_000.0}

    monitor = lp.liquidation_monitor()
    assert monitor["health"] == "warning"

    with patch.object(lp, "_approved_decision_cap", return_value=approved):
        result = lp.borrow(10.0)
    assert result["ok"] is False
    assert "frozen" in result["error"].lower()


def test_liquidatable_at_ltv_breach(fake_redis):
    _set_nav(fake_redis, 10_000.0)
    pool = lp.load_pool()
    pool["total_deposits"] = 9_000.0
    pool["active_loan"] = 8_200.0  # 82% LTV -> liquidatable (>= 80%)
    _set_pool(fake_redis, pool)

    snap = lp.public_pool_snapshot()
    monitor = lp.liquidation_monitor()
    assert snap["status"] == "liquidatable"
    assert snap["warning"] == "ltv_breach"
    assert monitor["health"] == "liquidatable"
    assert monitor["closing_liquidation_price"] == pytest.approx(
        round(8_200.0 / (lp.LIQUIDATION_LTV_PCT / 100.0), 2)
    )


def test_deposit_withdraw_roundtrip(fake_redis):
    _set_nav(fake_redis, 100_000.0)
    r = lp.deposit(1_000.0, "lender_a")
    assert r["ok"] is True
    assert r["pool"]["total_deposits"] == pytest.approx(1_000.0)

    w = lp.withdraw(400.0, "lender_a")
    assert w["ok"] is True
    assert w["pool"]["total_deposits"] == pytest.approx(600.0)

    over = lp.withdraw(1_000.0, "lender_a")
    assert over["ok"] is False


def test_repay_reduces_active_loan(fake_redis):
    _set_nav(fake_redis, 100_000.0)
    pool = lp.load_pool()
    pool["total_deposits"] = 10_000.0
    pool["active_loan"] = 2_000.0
    _set_pool(fake_redis, pool)

    r = lp.repay(500.0)
    assert r["ok"] is True
    assert r["pool"]["active_loan"] == pytest.approx(1_500.0)
    assert r["pool"]["ltv_pct"] == pytest.approx(1.5)

    bad = lp.repay(10_000.0)
    assert bad["ok"] is False