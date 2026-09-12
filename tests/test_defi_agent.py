"""DeFiAgent unit tests — P11 Stage-3 D1–D8 sector engine + U28–U33 gates.

Hermetic: stubs the relay (get_markets), the KG belief engine (suggest_crypto),
the oracle feed (relay_status), Redis (_cache), and Neo4j (get_db) via
monkeypatch — no network, no Docker deps, no testnet key.

Verifies per docs/p11_web3_defi_expansion.md §6 + tenet ledger U28–U33:
  D1  AMM concentrated-LP edge = fee − IL(x·y=k) − gas, U28 reject when ≤0
  D2  Lending carry spread threshold + U29 liquidation-distance guard
  D3  Yield-farm risk-adj APY ranking + U32 leverage cap
  D4  Perp funding carry (regime-gated)
  D5  EC cross-hedge (correlation floor + binary-Kelly sizing)
  D7  EC tail-hedge (Crisis/Stress regime, premium cap, U32 position cap)
  U30/D6  oracle staleness breaker
  U33  unattested feed → treated stale
  U21  candidates are intents only
"""
from __future__ import annotations

import asyncio

import pytest

import agent.defi_agent as dmod
from agent.defi_agent import DeFiAgent, _binary_kelly, _il_divergence


def _run(coro):
    return asyncio.run(coro)


def _mk_lp(market_id="lp1", fee_apy=0.25, price_ratio=1.2, gas=0.001,
           width=10.0, **kw):
    return {"is_lp": True, "market_id": market_id, "name": f"AMM-{market_id}",
            "fee_apy": fee_apy, "price_ratio_entry": price_ratio,
            "gas_cost_pct": gas, "range_width_pct": width, **kw}


def _mk_lending(market_id="ld1", lend=0.12, borrow=0.05, collat=1.6,
                liq_ratio=0.8, **kw):
    # liquidation distance = collat*liq_ratio - 1 = 1.6*0.8 - 1 = 0.28 (>0.10)
    return {"is_lending": True, "market_id": market_id, "name": f"Aave-{market_id}",
            "lend_rate": lend, "borrow_rate": borrow, "collat_price": collat,
            "liquidation_ratio": liq_ratio, **kw}


def _mk_vault(market_id="vy1", raw_apy=0.35, hack=0.05, liq=0.03, il=0.02,
              leverage=1.0, **kw):
    return {"is_vault": True, "market_id": market_id, "name": f"Vault-{market_id}",
            "raw_apy": raw_apy, "hack_prior_apy": hack,
            "liquidation_risk_apy": liq, "il_risk_apy": il,
            "leverage_x": leverage, **kw}


def _mk_perp(market_id="pp1", funding=0.08, **kw):
    return {"is_perp": True, "market_id": market_id, "name": f"Perp-{market_id}",
            "funding_rate": funding, **kw}


def _mk_ec(market_id="ec1", asset="BTC", correlation=0.8, ask=0.35, strike=0.0,
           **kw):
    return {"is_ec": True, "market_id": market_id, "symbol": f"{asset}-1HR#YES",
            "asset": asset, "correlation": correlation,
            "hedge_direction": "cross", "up": {"ask": ask, "bid": ask - 0.02},
            "strike": strike, **kw}


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch):
    """Point the agent's module-level imports at hermetic fakes."""
    monkeypatch.setattr(dmod, "get_markets", lambda: [])
    monkeypatch.setattr(DeFiAgent, "_cache", lambda self, k, v: None)
    monkeypatch.setattr(DeFiAgent, "_oracle_feeds", lambda self: [])
    # defi_agent binds get_db at import (from common.graph import get_db) — patch
    # the bound name on dmod, not the source module.
    monkeypatch.setattr(dmod, "get_db", lambda: None)

    # Fake KG belief: spot 64000, strike 66000 → p_up modest.
    def _fake_suggest(pair, lens="defensive", regime_override=None, **kw):
        return {"spot": 64000.0, "rv_21": 0.05, "regime": regime_override,
                "suggestions": []}
    # NOTE: defi_agent binds suggest_crypto into its own namespace at import
    # (from crypto_signal import suggest_crypto), so patch the bound name on
    # dmod, not the source module attribute.
    monkeypatch.setattr(dmod, "suggest_crypto", _fake_suggest)


# ── Pure math helpers ──────────────────────────────────────────────────────

def test_il_divergence_book_table():
    # *How to DeFi* Ch.3: 3×→13.4%, 4×→20%, 5×→25.5%
    assert abs(_il_divergence(3.0) - 0.134) < 0.005
    assert abs(_il_divergence(4.0) - 0.20) < 0.005
    assert abs(_il_divergence(5.0) - 0.255) < 0.005
    assert _il_divergence(1.0) == 0.0


def test_binary_kelly_floor_at_zero():
    assert _binary_kelly(0.4, 0.5) == 0.0       # p < ask → no stake
    assert _binary_kelly(0.8, 0.4) > 0.0        # p > ask → stake
    assert 0.0 <= _binary_kelly(0.2, 0.9) <= 1.0
# ── D1: AMM concentrated-LP ────────────────────────────────────────────────

def test_d1_lp_emits_intent_when_edge_positive():
    a = DeFiAgent()
    # raw = fee*(1-IL) - gas; price_ratio=1.2 → IL ≈ 0.00455
    m = _mk_lp(fee_apy=0.25, price_ratio=1.2, gas=0.001)
    out = a._strategy_d1_lp([m], "Bull Trend")
    assert len(out) == 1
    assert out[0]["status"] == "intent"          # U21
    assert out[0]["sector"] == "D1"


def test_d1_lp_rejected_when_il_dominates():
    # price_ratio=5 → IL≈25.5%; with a small 3% fee, fee*(1-IL) - gas = 0.0214
    # → net below MIN_LP_EDGE_PCT → rejected (U28)
    a = DeFiAgent()
    out = a._strategy_d1_lp([_mk_lp(fee_apy=0.03, price_ratio=5.0)], "Bull Trend")
    assert out == []


def test_d1_range_width_cap():
    a = DeFiAgent()
    out = a._strategy_d1_lp([_mk_lp(width=50.0)], "Bull Trend")
    assert out == []


# ── D2: Lending carry ──────────────────────────────────────────────────────

def test_d2_lending_emits_when_spread_and_distance_ok():
    a = DeFiAgent()
    out = a._strategy_d2_lending([_mk_lending()], "Bull Trend")
    assert len(out) == 1
    assert out[0]["sector"] == "D2"


def test_d2_rejected_when_spread_too_low():
    a = DeFiAgent()
    out = a._strategy_d2_lending([_mk_lending(lend=0.07, borrow=0.06)], "Bull Trend")
    assert out == []


def test_d2_rejected_when_liquidation_too_close():
    # collat 1.1 * liq_ratio 0.8 = 0.88 - 1 = -0.12 < 0.10 → rejected (U29)
    a = DeFiAgent()
    out = a._strategy_d2_lending(
        [_mk_lending(collat=1.1, liq_ratio=0.8)], "Bull Trend")
    assert out == []


# ── D3: Yield-farm ranking ─────────────────────────────────────────────────

def test_d3_yield_emits_when_risk_adjusted_positive():
    a = DeFiAgent()
    out = a._strategy_d3_yield([_mk_vault()], "Bull Trend")
    assert len(out) == 1
    assert out[0]["sector"] == "D3"


def test_d3_yield_rejected_when_leverage_exceeds_cap():
    # U32: leverage > MAX_LEVERAGE_X → rejected
    a = DeFiAgent()
    out = a._strategy_d3_yield([_mk_vault(leverage=5.0)], "Bull Trend")
    assert out == []


# ── D4: Perp funding carry ─────────────────────────────────────────────────

def test_d4_perp_emits_in_active_regime():
    # Funding must clear the CONFIGURED gate (MIN_FUNDING_CARRY_PCT may be set
    # above the code default in .env — e.g. 0.10) — derive the fixture from
    # the live module constant so the test is immune to env drift.
    gate = dmod.MIN_FUNDING_CARRY_PCT
    a = DeFiAgent()
    out = a._strategy_d4_perp([_mk_perp(funding=gate * 2)], "High Volatility")
    assert len(out) == 1
    assert out[0]["sector"] == "D4"


def test_d4_perp_rejected_when_below_gate():
    # U28/D4: funding below the configured threshold → no intent.
    gate = dmod.MIN_FUNDING_CARRY_PCT
    a = DeFiAgent()
    out = a._strategy_d4_perp([_mk_perp(funding=gate * 0.5)], "High Volatility")
    assert out == []


# ── D5: EC cross-hedge ─────────────────────────────────────────────────────

def test_d5_ec_hedge_emits_when_corr_and_edge_ok():
    a = DeFiAgent()
    # explicit strike 50000 < spot 64000 → p=0.75 → edge = (0.75-0.35)/0.35 > MIN
    m = _mk_ec(ask=0.35, strike=50000.0)
    out = a._strategy_d5_ec_hedge([m], [], "Bull Trend")
    assert len(out) == 1
    assert out[0]["sector"] == "D5"
    assert out[0]["binary_kelly"] > 0


def test_d5_rejected_below_correlation():
    a = DeFiAgent()
    out = a._strategy_d5_ec_hedge([_mk_ec(correlation=0.3)], [], "Bull Trend")
    assert out == []


def test_d5_rejected_when_no_edge():
    # ask very high relative to p → no edge (U28-EC)
    a = DeFiAgent()
    out = a._strategy_d5_ec_hedge([_mk_ec(ask=0.85)], [], "Bull Trend")
    assert out == []


# ── D7: EC tail-hedge ──────────────────────────────────────────────────────

def test_d7_tail_emits_in_crisis():
    a = DeFiAgent()
    out = a._strategy_d7_ec_tail([_mk_ec(ask=0.20)], "Crisis")
    assert len(out) == 1
    assert out[0]["sector"] == "D7"
    # U32: size ≤ cap
    assert out[0]["size_usd"] <= 100_000.0 * dmod.MAX_EC_TAILHEDGE_PCT


def test_d7_tail_empty_outside_crisis():
    a = DeFiAgent()
    assert a._strategy_d7_ec_tail([_mk_ec(ask=0.20)], "Bull Trend") == []


def test_d7_tail_rejected_when_premium_too_high():
    a = DeFiAgent()
    out = a._strategy_d7_ec_tail([_mk_ec(ask=0.50)], "Crisis")
    assert out == []


# ── U30/D6: oracle staleness breaker ───────────────────────────────────────

def test_u30_stale_feed_pauses_ec(monkeypatch):
    monkeypatch.setattr(dmod, "ORACLE_STALE_MS", 1000.0)
    monkeypatch.setenv("_NOW_MS", "5000")
    a = DeFiAgent()
    monkeypatch.setattr(
        a, "_oracle_feeds",
        lambda: [{"venue": "somnia", "updated_ts": 1.0,   # stale (5s vs 1s)
                  "deviation_bps": 0.0, "attested": True}])
    gov = a._oracle_governor()
    assert gov["paused_ec"] is True
    assert gov["paused_evm"] is False


def test_u33_unattested_feed_treated_stale(monkeypatch):
    monkeypatch.setattr(dmod, "ORACLE_STALE_MS", 1000.0)
    monkeypatch.setenv("_NOW_MS", "5000")
    a = DeFiAgent()
    monkeypatch.setattr(
        a, "_oracle_feeds",
        lambda: [{"venue": "somnia", "updated_ts": 5000.0,  # fresh
                  "deviation_bps": 0.0, "attested": False}])  # but unattested
    gov = a._oracle_governor()
    assert gov["paused_ec"] is True        # U33: unattested → treated stale


def test_fresh_attested_feed_no_pause(monkeypatch):
    monkeypatch.setattr(dmod, "ORACLE_STALE_MS", 1000.0)
    monkeypatch.setenv("_NOW_MS", "5000")
    a = DeFiAgent()
    monkeypatch.setattr(
        a, "_oracle_feeds",
        lambda: [{"venue": "somnia", "updated_ts": 5000.0,
                  "deviation_bps": 0.0, "attested": True}])
    gov = a._oracle_governor()
    assert gov["paused_ec"] is False


# ── run() integration + U21 + exposure cap ─────────────────────────────────

def test_run_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(dmod, "ENABLED", False)
    assert _run(DeFiAgent().run("Bull Trend")) == []


def test_run_pauses_paused_venue(monkeypatch):
    monkeypatch.setattr(dmod, "ENABLED", True)
    monkeypatch.setattr(dmod, "ORACLE_STALE_MS", 1000.0)
    monkeypatch.setattr(dmod, "get_markets", lambda: [_mk_lp(), _mk_ec()])
    a = DeFiAgent()
    monkeypatch.setattr(
        a, "_oracle_feeds",
        lambda: [{"venue": "somnia", "updated_ts": 1.0,   # stale → pause EC
                  "deviation_bps": 0.0, "attested": True}])
    monkeypatch.setenv("_NOW_MS", "5000")
    cands = _run(a.run("Bull Trend"))
    # EVM D1 survives; EC D5/D7 filtered out
    assert all(c["venue"] != "somnia-relay" for c in cands)
    assert any(c["venue"] == "sepolia-evm" for c in cands)


def test_run_exposure_cap(monkeypatch):
    monkeypatch.setattr(dmod, "ENABLED", True)
    monkeypatch.setattr(dmod, "MAX_DEFI_EXPOSURE_PCT", 0.001)   # tiny book
    monkeypatch.setattr(dmod, "get_markets",
                        lambda: [_mk_ec(ask=0.2), _mk_ec(ask=0.2, market_id="ec2")])
    a = DeFiAgent()
    cands = _run(a.run("Crisis"))
    total = sum(float(c.get("size_usd") or 0.0) for c in cands)
    assert total <= 100_000.0 * dmod.MAX_DEFI_EXPOSURE_PCT


def test_d4_perp_rejected_outside_active_regime():
    a = DeFiAgent()
    out = a._strategy_d4_perp([_mk_perp(funding=0.08)], "Crisis")
    assert out == []


def test_d4_perp_rejected_when_funding_below_threshold():
    a = DeFiAgent()
    out = a._strategy_d4_perp([_mk_perp(funding=0.01)], "Bull Trend")
    assert out == []
