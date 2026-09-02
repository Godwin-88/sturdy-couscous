"""
Agentic option signal engine - GraphAlpha.

Computes ranked, KG-grounded strategy suggestions for any Alpaca-listed option
chain the user selects. Every suggestion is derived from LIVE contract metrics
(greeks, IV, spread, OI), gated to the strategies the knowledge graph has
activated for the CURRENT market regime (ACTIVATED_BY edges), and cites its
graph trail (DERIVED_FROM concepts).

This is the "select an option symbol -> the agent renders suggestions" path
driving the frontend Options tab (GET/POST /options/suggestions).
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import date, datetime
from typing import Any

import numpy as np
from loguru import logger

try:
    from agent.options_market import options_provider
except ImportError:  # pragma: no cover - api container mounts agent/ as package
    from options_market import options_provider  # type: ignore

try:
    from agent.option_utils import build_contract_symbol, parse_contract_symbol
except ImportError:  # pragma: no cover
    from option_utils import build_contract_symbol, parse_contract_symbol  # type: ignore

try:
    from common.graph import get_db
except ImportError:  # pragma: no cover
    from common.graph import get_db  # type: ignore

REGIME_CACHE_TTL = float(os.getenv("OPTION_REGIME_CACHE_TTL", "300"))
_regime_cache: dict = {"at": 0.0, "regime": "Neutral", "confidence": 0.0}

MULT = 100

# ── Loss-aversion (Kahneman–Tversky / Taleb) ranking knobs ─────────────────────
# lambda_ penalises max_loss as a FRACTION of NAV in the ranking. A trade with
# max loss 5% of NAV loses lambda*5 points off its raw score; a 15% max-loss
# tail risk gets crushed unless it is a *defined-risk* hedge.
LOSS_AVERSION_LAMBDA = float(os.getenv("OPTION_LOSS_AVERSION_LAMBDA", "2.25"))
LOSS_AVERSION_LAMBDA_DEFENSIVE = float(os.getenv("OPTION_LOSS_AVERSION_LAMBDA_DEFENSIVE", "3.5"))
# Hard gates: max_loss as % of NAV above these caps is EXCLUDED before ranking.
MAX_LOSS_CAP_PCT_AVERAGE = float(os.getenv("OPTION_MAX_LOSS_CAP_PCT_AVERAGE", "10.0"))
MAX_LOSS_CAP_PCT_DEFENSIVE = float(os.getenv("OPTION_MAX_LOSS_CAP_PCT_DEFENSIVE", "5.0"))
DEFAULT_NAV = float(os.getenv("OPTION_DEFAULT_NAV", os.getenv("INITIAL_CAPITAL_USD", "10000")))

SUGGESTIONS_CACHE_TTL = float(os.getenv("OPTION_SUGGESTIONS_CACHE_TTL", "60"))
_suggestions_cache: dict[str, tuple[float, dict]] = {}


def _mid(row: dict) -> float:
    if row.get("mid") is not None:
        return float(row["mid"])
    b = row.get("bid")
    a = row.get("ask")
    if b is not None and a is not None:
        return (float(b) + float(a)) / 2.0
    return float(row.get("last") or 0.0)


def _abs_delta(row: dict) -> float | None:
    g = row.get("greeks") or {}
    d = g.get("delta")
    return abs(float(d)) if d is not None else None


def _dte(expiration: str) -> int:
    try:
        exp = datetime.strptime(str(expiration)[:10], "%Y-%m-%d").date()
        return max((exp - date.today()).days, 0)
    except Exception:
        return 0


async def current_regime() -> dict:
    """Best-effort current regime via RegimeAgent (cached)."""
    global _regime_cache
    now = time.time()
    if now - _regime_cache["at"] < REGIME_CACHE_TTL:
        return {"regime": _regime_cache["regime"], "confidence": _regime_cache["confidence"]}
    try:
        try:
            from agent.regime_agent import RegimeAgent
        except ModuleNotFoundError:
            import sys as _sys
            _agent_dir = os.path.dirname(os.path.abspath(__file__))
            if _agent_dir not in _sys.path:
                _sys.path.insert(0, _agent_dir)
            from regime_agent import RegimeAgent
        agent = RegimeAgent()
        out = await agent.run()
        _regime_cache = {
            "at": now,
            "regime": out.get("regime", "Neutral"),
            "confidence": float(out.get("confidence", 0.0)),
        }
    except Exception as e:
        logger.warning(f"regime lookup failed for options suggestions: {e}")
        _regime_cache = {"at": now, "regime": "Neutral", "confidence": 0.0}
    return {"regime": _regime_cache["regime"], "confidence": _regime_cache["confidence"]}


def _kg_option_strategies(regime: str) -> list[dict]:
    """Active option strategies for `regime`, with params + graph trail."""
    out: list[dict] = []
    try:
        db = get_db()
        q = """
        MATCH (s:Strategy {status:'active', tradeable_venue:'alpaca_options'})
              -[a:ACTIVATED_BY]->(r:Regime {name: $regime})
        OPTIONAL MATCH (s)-[:DERIVED_FROM]->(c:Concept)
        RETURN s.name AS name,
               s.signal_method AS method,
               a.weight AS weight,
               s.param_budget_pct AS budget,
               s.param_delta_lo AS dlo,
               s.param_delta_hi AS dhi,
               s.param_dte_lo AS tlo,
               s.param_dte_hi AS thi,
               collect(DISTINCT c.name) AS concepts
        ORDER BY a.weight DESC
        """
        for row in db.execute_and_fetch(q, {"regime": regime}):
            if not row.get("name"):
                continue
            out.append({
                "name": row["name"],
                "method": row.get("method"),
                "weight": float(row.get("weight") or 0.0),
                "budget_pct": float(row.get("budget") or 0.05),
                "delta_lo": float(row.get("dlo") or 0.0),
                "delta_hi": float(row.get("dhi") or 0.5),
                "dte_lo": int(row.get("tlo") or 7),
                "dte_hi": int(row.get("thi") or 60),
                "concepts": [c for c in (row.get("concepts") or []) if c],
            })
    except Exception as e:
        logger.warning(f"_kg_option_strategies failed: {e}")
    return out


def _pick_near_delta(rows: list[dict], target_delta: float, want_call: bool,
                     exclude_strike: float | None = None) -> dict | None:
    """Pick the row whose |delta| is closest to target (of the given type)."""
    best, best_err = None, 1e9
    for r in rows:
        rt = (r.get("contract_type") or "").lower()
        if want_call and rt != "call":
            continue
        if not want_call and rt != "put":
            continue
        if exclude_strike is not None and abs(float(r.get("strike_price") or 0) - exclude_strike) < 1e-6:
            continue
        d = _abs_delta(r)
        if d is None or d <= 0 or d > 0.99:
            continue
        err = abs(d - target_delta)
        if err < best_err:
            best, best_err = r, err
    return best


def _chain_rows(underlying: str, expiration: str | None, contract_type: str | None) -> list[dict]:
    rows: list[dict] = []
    for ct in (["call", "put"] if contract_type is None else [contract_type]):
        got = options_provider.get_chain(underlying, expiration=expiration,
                                         contract_type=ct, with_snapshots=True)
        if got:
            rows.extend(got)
    rows.sort(key=lambda r: float(r.get("strike_price") or 0))
    return rows


def _spot_estimate(rows: list[dict]) -> float | None:
    """ATM proxy = strike whose |delta| is closest to 0.50 (standard ATM).

    Falls back to the max-mid contract when greeks are unavailable.
    """
    best, best_err = None, 1e9
    for r in rows:
        if not r.get("bid") or not r.get("ask"):
            continue
        b = float(r["bid"])
        a = float(r["ask"])
        if b <= 0 or a <= 0 or a <= b:
            continue
        d = _abs_delta(r)
        if d is None or d <= 0 or d >= 1:
            continue
        err = abs(d - 0.50)
        if err < best_err:
            best, best_err = r, err
    if best is not None:
        return float(best.get("strike_price"))
    # fallback: max-mid contract
    best2 = None
    for r in rows:
        if _mid(r) <= 0:
            continue
        if best2 is None or _mid(r) > _mid(best2):
            best2 = r
    return float(best2.get("strike_price")) if best2 is not None else None


def _iv_rank(row: dict, rows: list[dict]) -> float | None:
    """Cross-sectional IV percentile of this contract within its chain."""
    ivs = sorted(float(r.get("implied_volatility") or 0.0) for r in rows if r.get("implied_volatility"))
    iv = row.get("implied_volatility")
    if iv is None or not ivs:
        return None
    return float(np.searchsorted(ivs, float(iv)) / max(len(ivs), 1))


def _liquidity(row: dict) -> bool:
    spread_pct = row.get("spread_pct")
    if spread_pct is not None and float(spread_pct) > 0.05:
        return False
    oi = row.get("open_interest")
    if oi is not None and float(oi) < 200:
        return False
    return _mid(row) > 0


def _card(name: str, method: str, weight: float, budget_pct: float, regime: str,
          confidence: float, concepts: list[str], legs: list[dict], max_loss: float,
          max_profit: float, score: float, notes: list[str],
          nav: float | None = None) -> dict:
    roi = None
    if max_loss > 0:
        roi = (max_profit / max_loss) * 100.0
    max_loss_pct_nav = round((max_loss / nav) * 100.0, 2) if nav and nav > 0 else None
    return {
        "strategy": name,
        "signal_method": method,
        "regime": regime,
        "regime_weight": weight,
        "confidence": round(confidence, 3),
        "graph_path": concepts,
        "legs": legs,
        "est_premium": round(sum(_mid(l) * MULT * int(l.get("contracts") or 1) for l in legs), 2),
        "max_profit_low": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "max_loss_pct_nav": max_loss_pct_nav,
        "risk_reward_pct": round(roi, 1) if roi is not None else None,
        "score": round(score, 1),
        "notes": notes,
        "budget_pct": budget_pct,
        "liquidity_ok": all(_liquidity(l) for l in legs),
    }


def _score(method: str, row: dict | None, regime_weight: float, iv_rank: float | None,
           dte: int, liquidity: bool) -> float:
    """Composite 0-100 score: regime fit + liquidity + IV edge + time edge."""
    s = 0.0
    s += min(regime_weight * 40.0, 40.0)
    s += 25.0 if liquidity else 0.0
    if iv_rank is not None:
        # Hull Ch11 BS11.2: market prices already embed views → buy vol when
        # *cheap* (low IV rank), sell/premium-harvest when *rich* (high IV rank).
        short_vol = {"short_straddle", "short_strangle", "iron_condor", "covered_call",
                     "cash_secured_put", "put_credit_spread", "call_credit_spread",
                     "short_butterfly"}
        long_vol = {"long_straddle", "long_strangle", "protective_put", "put_spread_hedge",
                    "butterfly", "strip", "strap", "reverse_calendar"}
        if method in short_vol:
            s += min(20.0, iv_rank * 20.0)
        elif method in long_vol:
            s += min(20.0, (1.0 - iv_rank) * 15.0 + (iv_rank * 5.0))
        else:
            s += 10.0
    if row and method in ("covered_call", "cash_secured_put", "put_credit_spread"):
        g = row.get("greeks") or {}
        theta = g.get("theta")
        if theta is not None and dte > 0:
            pct_per_day = abs(float(theta)) / max(_mid(row), 1e-9) / dte
            s += min(15.0, pct_per_day * 200.0)
    return float(np.clip(s, 0.0, 100.0))


def _loss_aversion_score(raw_score: float, max_loss: float, nav: float | None,
                         lambda_: float = LOSS_AVERSION_LAMBDA) -> float:
    """Penalise raw score by lambda * max_loss(%NAV) — the leave-a-hamster
    lens: an un-hedged 15%-of-NAV max loss gets crushed even with decent RR,
    while defined-risk spreads (small max loss) keep most of their raw score.

    Loss-aversion score = raw_score − lambda·(max_loss/NAV)·100  (points).
    """
    if nav is None or nav <= 0 or max_loss <= 0:
        return float(raw_score)
    loss_pct_nav = max_loss / nav
    return float(np.clip(raw_score - lambda_ * 100.0 * loss_pct_nav, 0.0, 100.0))


def _hedge_requirement(method: str, legs: list[dict], regime: str) -> dict:
    """Flag structures that need a dynamic delta hedge or a tail-hedge sleeve.

    Taleb posture: naked/gamma-negative shorts are never run un-hedged in
    HighVol/Crisis; long volatility (straddle) is self-hedging directionally
    but gamma-positive — a small delta hedge may still be warranted.
    """
    need_hedge = False
    reason = ""
    if regime in ("HighVolatility", "Crisis", "SystemicStress"):
        if method in ("short_straddle", "short_strangle", "short_butterfly",
                      "covered_call", "cash_secured_put"):
            need_hedge = True
            reason = f"{method} carries short gamma in {regime} — dynamic delta hedge required"
        if method in ("put_spread_hedge", "protective_put"):
            need_hedge = False  # already a hedge vehicle
    elif method in ("short_straddle", "short_strangle"):
        need_hedge = True
        reason = f"{method} is short vega+gamma — band-triggered delta hedge recommended"
    return {"hedge_req": need_hedge, "hedge_reason": reason}


def _build_legs(strat: dict, rows_c: list[dict], rows_p: list[dict], underlying: str) -> list[dict] | None:
    """Construct concrete option orders for a KG strategy from the live chain.

    Returns a list of leg dicts (each with max_loss / max_profit set on the
    first leg) or None when the chain cannot support the strategy.
    """
    method = strat["method"]
    mid_delta = (strat["delta_lo"] + strat["delta_hi"]) / 2.0
    legs: list[dict] = []

    # Two-expiration constructs (calendar/diagonal/reverse-calendar) and the
    # American box spread (Hull Ch11 BS11.1 early-assignment risk) are not
    # built on a single-expiry chain — they stay in the KG as research_only.
    if method in ("calendar_spread", "diagonal_spread", "reverse_calendar", "box_spread"):
        return None

    def _leg(r: dict, side: str) -> dict:
        return {
            "symbol": r["symbol"],
            "strike": r["strike_price"],
            "contract_type": (r.get("contract_type") or "").lower(),
            "side": side,
            "contracts": 1,
            "mid": round(_mid(r), 2),
            "delta": round(_abs_delta(r), 3) if _abs_delta(r) is not None else None,
            "bid": r.get("bid"),
            "ask": r.get("ask"),
            "spread_pct": r.get("spread_pct"),
            "open_interest": r.get("open_interest"),
            "implied_volatility": r.get("implied_volatility"),
        }

    if method == "covered_call":
        r = _pick_near_delta(rows_c, mid_delta, True)
        if r is None:
            return None
        premium = _mid(r) * MULT
        leg = _leg(r, "sell_to_open")
        leg["premium_total"] = round(premium, 2)
        leg["max_profit"] = round(premium, 2)
        leg["max_loss"] = 0.0  # underlying drawdown; flagged to user
        return [leg]

    if method == "cash_secured_put":
        r = _pick_near_delta(rows_p, mid_delta, False)
        if r is None:
            return None
        prem = _mid(r) * MULT
        collat = float(r["strike_price"]) * MULT
        leg = _leg(r, "sell_to_open")
        leg["premium_total"] = round(prem, 2)
        leg["collateral_required"] = round(collat, 2)
        leg["max_profit"] = round(prem, 2)
        leg["max_loss"] = round(collat - prem, 2)
        return [leg]

    if method == "put_credit_spread":
        short_r = _pick_near_delta(rows_p, mid_delta, False)
        long_r = _pick_near_delta(rows_p, 0.10, False,
                                  exclude_strike=short_r["strike_price"] if short_r else None)
        if short_r is None or long_r is None:
            return None
        credit = (_mid(short_r) - _mid(long_r)) * MULT
        if credit <= 0:
            return None
        width = abs(float(long_r["strike_price"]) - float(short_r["strike_price"])) * MULT
        legs = [_leg(short_r, "sell_to_open"), _leg(long_r, "buy_to_open")]
        legs[0]["max_profit"] = round(credit, 2)
        legs[0]["max_loss"] = round(abs(width) - credit, 2)
        legs[0]["net_credit"] = round(credit, 2)
        return legs

    if method == "call_debit_spread":
        buy = _pick_near_delta(rows_c, 0.30, True)
        sell = _pick_near_delta(rows_c, 0.15, True,
                                exclude_strike=buy["strike_price"] if buy else None)
        if buy is None or sell is None:
            return None
        debit = (_mid(buy) - _mid(sell)) * MULT
        if debit <= 0:
            return None
        width = abs(float(sell["strike_price"]) - float(buy["strike_price"])) * MULT
        legs = [_leg(buy, "buy_to_open"), _leg(sell, "sell_to_open")]
        legs[0]["max_profit"] = round(abs(width) - debit, 2)
        legs[0]["max_loss"] = round(debit, 2)
        legs[0]["net_debit"] = round(debit, 2)
        return legs

    if method == "put_debit_spread":
        buy = _pick_near_delta(rows_p, 0.30, False)
        sell = _pick_near_delta(rows_p, 0.15, False,
                                exclude_strike=buy["strike_price"] if buy else None)
        if buy is None or sell is None:
            return None
        debit = (_mid(buy) - _mid(sell)) * MULT
        if debit <= 0:
            return None
        width = abs(float(buy["strike_price"]) - float(sell["strike_price"])) * MULT
        legs = [_leg(buy, "buy_to_open"), _leg(sell, "sell_to_open")]
        legs[0]["max_profit"] = round(abs(width) - debit, 2)
        legs[0]["max_loss"] = round(debit, 2)
        legs[0]["net_debit"] = round(debit, 2)
        return legs

    if method == "iron_condor":
        sc = _pick_near_delta(rows_c, 0.20, True)
        lc = _pick_near_delta(rows_c, 0.10, True,
                              exclude_strike=sc["strike_price"] if sc else None)
        sp = _pick_near_delta(rows_p, 0.20, False)
        lp = _pick_near_delta(rows_p, 0.10, False,
                              exclude_strike=sp["strike_price"] if sp else None)
        if any(x is None for x in (sc, lc, sp, lp)):
            return None
        credit = (_mid(sc) - _mid(lc) + _mid(sp) - _mid(lp)) * MULT
        if credit <= 0:
            return None
        width = abs(float(lc["strike_price"]) - float(sc["strike_price"])) * MULT
        legs = [_leg(sc, "sell_to_open"), _leg(lc, "buy_to_open"),
                _leg(sp, "sell_to_open"), _leg(lp, "buy_to_open")]
        legs[0]["max_profit"] = round(credit, 2)
        legs[0]["max_loss"] = round(abs(width) - credit, 2)
        legs[0]["net_credit"] = round(credit, 2)
        return legs

    # Hull Ch11 §11.3 — Long Butterfly: buy K1 + K3 wings, sell 2× ATM K2.
    if method == "butterfly":
        atm = _pick_near_delta(rows_c, 0.5, True) if rows_c else None
        if atm is None:
            return None
        spot_k = float(atm["strike_price"])
        width = max(spot_k * 0.02, 1.0) if rows_c else 1.0
        k1 = min(rows_c, key=lambda r: abs(float(r["strike_price"]) - (spot_k - width)))
        k2 = min(rows_c, key=lambda r: abs(float(r["strike_price"]) - spot_k))
        k3 = min(rows_c, key=lambda r: abs(float(r["strike_price"]) - (spot_k + width)))
        if not (float(k1["strike_price"]) < float(k2["strike_price"]) < float(k3["strike_price"])):
            return None
        debit = (_mid(k1) + _mid(k3) - 2 * _mid(k2)) * MULT
        if debit <= 0:
            return None
        width_m = abs(float(k3["strike_price"]) - float(k1["strike_price"])) * MULT
        k1l = _leg(k1, "buy_to_open"); k1l["contracts"] = 1
        k2l = _leg(k2, "sell_to_open"); k2l["contracts"] = 2  # Alpaca ratio_qty=2
        k3l = _leg(k3, "buy_to_open"); k3l["contracts"] = 1
        legs = [k1l, k2l, k3l]
        legs[0]["max_profit"] = round(width_m - debit, 2)
        legs[0]["max_loss"] = round(debit, 2)
        legs[0]["net_debit"] = round(debit, 2)
        return legs

    # Hull Ch11 §11.3 — Short Butterfly: reverse of the long butterfly.
    if method == "short_butterfly":
        atm = _pick_near_delta(rows_c, 0.5, True) if rows_c else None
        if atm is None:
            return None
        spot_k = float(atm["strike_price"])
        width = max(spot_k * 0.02, 1.0) if rows_c else 1.0
        k1 = min(rows_c, key=lambda r: abs(float(r["strike_price"]) - (spot_k - width)))
        k2 = min(rows_c, key=lambda r: abs(float(r["strike_price"]) - spot_k))
        k3 = min(rows_c, key=lambda r: abs(float(r["strike_price"]) - (spot_k + width)))
        if not (float(k1["strike_price"]) < float(k2["strike_price"]) < float(k3["strike_price"])):
            return None
        credit = (2 * _mid(k2) - _mid(k1) - _mid(k3)) * MULT
        if credit <= 0:
            return None
        width_m = abs(float(k3["strike_price"]) - float(k1["strike_price"])) * MULT
        k1l = _leg(k1, "sell_to_open"); k1l["contracts"] = 1
        k2l = _leg(k2, "buy_to_open"); k2l["contracts"] = 2
        k3l = _leg(k3, "sell_to_open"); k3l["contracts"] = 1
        legs = [k1l, k2l, k3l]
        legs[0]["max_profit"] = round(credit, 2)
        legs[0]["max_loss"] = round(width_m - credit, 2)
        legs[0]["net_credit"] = round(credit, 2)
        return legs

    # Hull Ch11 §11.4 — Strip: 1 call + 2 puts (bearish big-move bet).
    if method == "strip":
        c = _pick_near_delta(rows_c, 0.5, True) if rows_c else None
        p = _pick_near_delta(rows_p, 0.5, False) if rows_p else None
        if c is None or p is None:
            return None
        debit = (_mid(c) + 2 * _mid(p)) * MULT
        cl = _leg(c, "buy_to_open"); cl["contracts"] = 1
        pl = _leg(p, "buy_to_open"); pl["contracts"] = 2  # 2 puts in a strip
        legs = [cl, pl]
        legs[0]["max_profit"] = round(0.0, 2)
        legs[0]["max_loss"] = round(debit, 2)
        legs[0]["net_debit"] = round(debit, 2)
        return legs

    # Hull Ch11 §11.4 — Strap: 2 calls + 1 put (bullish big-move bet).
    if method == "strap":
        c = _pick_near_delta(rows_c, 0.5, True) if rows_c else None
        p = _pick_near_delta(rows_p, 0.5, False) if rows_p else None
        if c is None or p is None:
            return None
        debit = (2 * _mid(c) + _mid(p)) * MULT
        cl = _leg(c, "buy_to_open"); cl["contracts"] = 2  # 2 calls in a strap
        pl = _leg(p, "buy_to_open"); pl["contracts"] = 1
        legs = [cl, pl]
        legs[0]["max_profit"] = round(0.0, 2)
        legs[0]["max_loss"] = round(debit, 2)
        legs[0]["net_debit"] = round(debit, 2)
        return legs

    # Hull Ch11 §11.4 — Short Strangle: sell OTM call + OTM put, range income.
    if method == "short_strangle":
        sc = _pick_near_delta(rows_c, 0.2, True) if rows_c else None
        sp = _pick_near_delta(rows_p, 0.2, False) if rows_p else None
        if sc is None or sp is None:
            return None
        credit = (_mid(sc) + _mid(sp)) * MULT
        if credit <= 0:
            return None
        legs = [_leg(sc, "sell_to_open"), _leg(sp, "sell_to_open")]
        legs[0]["max_profit"] = round(credit, 2)
        legs[0]["max_loss"] = round(0.0, 2)
        legs[0]["net_credit"] = round(credit, 2)
        return legs

    # Hull Ch11 §11.2 — Bear Call Credit Spread: sell low call, buy high call.
    if method == "call_credit_spread":
        short_r = _pick_near_delta(rows_c, mid_delta, True)
        long_r = _pick_near_delta(rows_c, 0.10, True,
                                  exclude_strike=short_r["strike_price"] if short_r else None)
        if short_r is None or long_r is None:
            return None
        credit = (_mid(short_r) - _mid(long_r)) * MULT
        if credit <= 0:
            return None
        width = abs(float(long_r["strike_price"]) - float(short_r["strike_price"])) * MULT
        legs = [_leg(short_r, "sell_to_open"), _leg(long_r, "buy_to_open")]
        legs[0]["max_profit"] = round(credit, 2)
        legs[0]["max_loss"] = round(abs(width) - credit, 2)
        legs[0]["net_credit"] = round(credit, 2)
        return legs

    # Protections / hedges: single long put at a lower OTM delta.
    if method in ("protective_put", "put_spread_hedge", "long_straddle",
                  "long_strangle", "calendar_spread", "diagonal_spread",
                  "short_straddle", "collar"):
        # Basic single-leg construction for hedges/direction.
        if method in ("protective_put", "put_spread_hedge"):
            r = _pick_near_delta(rows_p, strat["delta_lo"], False)
            if r is None:
                return None
            debit = _mid(r) * MULT
            leg = _leg(r, "buy_to_open")
            leg["max_profit"] = round(None if method == "protective_put" else 0.0, 2) if False else round(0.0, 2)
            leg["max_loss"] = round(debit, 2)  # max loss = premium for a hedge
            leg["net_debit"] = round(debit, 2)
            leg["max_profit"] = round(debit, 2) if method == "put_spread_hedge" else round(0.0, 2)
            return [leg]
        if method == "long_straddle":
            c = _pick_near_delta(rows_c, 0.5, True) if rows_c else None
            p = _pick_near_delta(rows_p, 0.5, False) if rows_p else None
            if c is None or p is None:
                return None
            debit = (_mid(c) + _mid(p)) * MULT
            legs = [_leg(c, "buy_to_open"), _leg(p, "buy_to_open")]
            legs[0]["max_profit"] = round(0.0, 2)
            legs[0]["max_loss"] = round(debit, 2)
            legs[0]["net_debit"] = round(debit, 2)
            return legs
        if method == "short_straddle":
            c = _pick_near_delta(rows_c, 0.5, True) if rows_c else None
            p = _pick_near_delta(rows_p, 0.5, False) if rows_p else None
            if c is None or p is None:
                return None
            credit = (_mid(c) + _mid(p)) * MULT
            legs = [_leg(c, "sell_to_open"), _leg(p, "sell_to_open")]
            legs[0]["max_profit"] = round(credit, 2)
            legs[0]["max_loss"] = round(0.0, 2)
            legs[0]["net_credit"] = round(credit, 2)
            return legs
        if method == "collar":
            p = _pick_near_delta(rows_p, 0.25, False)
            c = _pick_near_delta(rows_c, 0.20, True)
            if p is None or c is None:
                return None
            credit = _mid(c) - _mid(p)
            legs = [_leg(p, "buy_to_open"), _leg(c, "sell_to_open")]
            legs[0]["max_profit"] = round(credit * MULT, 2)
            legs[0]["max_loss"] = round(abs(credit) * MULT, 2)
            legs[0]["net_credit"] = round(credit * MULT, 2)
            return legs
        return None

    return None


def _build_cards(rows_c: list[dict], rows_p: list[dict], kg: list[dict],
                 underlying: str, expiration: str, contract_type: str,
                 regime: str, confidence: float, dte: int,
                 nav: float, max_loss_cap_pct: float, lambda_: float,
                 lens: str) -> tuple[list[dict], list[dict]]:
    """Run the KG strategy library against a single chain.

    Returns (cards, rejected). Each card is tagged with the expiration /
    contract_type it was built from so the caller can dedupe across chains
    and surface the alt-expiry variants to the user as comparable plays.
    """
    cards: list[dict] = []
    rejected: list[dict] = []
    chain_label = f"{dte}DTE/{contract_type}"

    for strat in kg:
        method = strat["method"]
        try:
            legs = _build_legs(strat, rows_c, rows_p, underlying)
        except Exception:
            legs = None
        if not legs:
            continue
        if len(legs) == 4:
            notes = [f"Condor {legs[0]['strike']}/{legs[1]['strike']} calls + "
                     f"{legs[2]['strike']}/{legs[3]['strike']} puts"]
        elif len(legs) == 2:
            notes = [f"Long {legs[0]['strike']} {legs[0]['contract_type']} / "
                     f"short {legs[1]['strike']} {legs[1]['contract_type']}"]
        else:
            notes = [f"Trade {underlying} {legs[0]['strike']} {legs[0]['contract_type']}"]
        if legs[0].get("collateral_required"):
            notes.append(f"Collateral required: {legs[0]['collateral_required']:.0f}")
        if legs[0].get("net_credit") is not None:
            notes.append(f"Net credit: {legs[0]['net_credit']:.0f}")
        if legs[0].get("net_debit") is not None:
            notes.append(f"Net debit: {legs[0]['net_debit']:.0f}")
        max_loss = float(legs[0].get("max_loss") or 0.0)
        max_profit = float(legs[0].get("max_profit") or 0.0)
        raw_score = _score(method, legs[0], strat["weight"], _iv_rank(legs[0], rows_c + rows_p),
                           dte, all(_liquidity(l) for l in legs))
        # ── Loss-aversion hard gate (leave the account, not the strategy) ─────
        max_loss_pct_nav = (max_loss / nav) * 100.0 if nav > 0 and max_loss > 0 else 0.0
        if max_loss_pct_nav > max_loss_cap_pct:
            rejected.append({
                "strategy": strat["name"], "signal_method": method,
                "max_loss": round(max_loss, 2),
                "max_loss_pct_nav": round(max_loss_pct_nav, 2),
                "reason": f"max loss {max_loss_pct_nav:.1f}% > {max_loss_cap_pct:.0f}% NAV cap ({lens} lens)",
                "expiration": expiration,
                "contract_type": contract_type,
            })
            continue
        card = _card(strat["name"], method, strat["weight"], strat["budget_pct"],
                     regime, confidence, strat["concepts"], legs,
                     max_loss, max_profit, raw_score, notes, nav=nav)
        card["loss_aversion_score"] = round(
            _loss_aversion_score(raw_score, max_loss, nav, lambda_), 1)
        card["lens"] = lens
        card["hedge"] = _hedge_requirement(method, legs, regime)
        # Tag with the chain this card was built from — the UI uses this to
        # surface "compare with next-nearest expiry" without re-querying.
        card["expiration"] = expiration
        card["contract_type"] = contract_type
        card["dte"] = dte
        card["chain_label"] = chain_label
        card["chain_source"] = "primary"
        cards.append(card)

    return cards, rejected


def _nearby_expirations(underlying: str, primary: str, n: int = 2) -> list[str]:
    """Return up to `n` additional expirations nearest to `primary`.

    Used by compute_suggestions to evaluate the same KG strategies against
    near-expiry chains so the user can compare plays at 2 DTE vs 9 DTE vs
    16 DTE side-by-side. Excludes 0-DTE and the primary itself.
    """
    if not primary:
        return []
    try:
        all_exps = options_provider.get_expirations(underlying) or []
    except Exception:
        return []
    primary_dte = _dte(primary)
    out: list[tuple[int, str]] = []
    for e in all_exps:
        if e == primary:
            continue
        ed = _dte(e)
        if ed < 1:
            continue
        out.append((abs(ed - primary_dte), e))
    out.sort(key=lambda t: t[0])
    return [e for _, e in out[:n]]


def _dedupe_cards(cards: list[dict]) -> list[dict]:
    """Drop duplicate (strategy, expiration, contract_type) cards, keep best."""
    best: dict[tuple[str, str, str], dict] = {}
    for c in cards:
        key = (c.get("strategy", ""), c.get("expiration", ""), c.get("contract_type", ""))
        prev = best.get(key)
        if prev is None or c.get("loss_aversion_score", 0) > prev.get("loss_aversion_score", 0):
            best[key] = c
    return list(best.values())


def compute_suggestions(underlying: str, expiration: str | None,
                        contract_type: str | None, regime: str | None = None,
                        confidence: float = 0.0,
                        lens: str = "average", nav: float | None = None) -> dict[str, Any]:
    """Ranked, KG-grounded option strategy suggestions for the selected chain.

    `lens` selects the ranking lens:
      - "average"   — K&T lambda=2.25, hard cap max_loss <= 10% NAV.
      - "defensive" — K&T lambda=3.5,  hard cap max_loss <= 5% NAV (loss-averse).
    `nav` is the account equity used to express max_loss as %NAV.
    """
    cache_key = "|".join([
        str(underlying or "").strip().upper(), str(expiration or ""),
        str(contract_type or ""), str(regime or ""), lens, f"{float(nav or 0):.0f}",
    ])
    now = time.time()
    hit = _suggestions_cache.get(cache_key)
    if hit and now - hit[0] < SUGGESTIONS_CACHE_TTL:
        return hit[1]

    if lens not in ("average", "defensive"):
        lens = "average"
    nav = float(nav) if nav and nav > 0 else DEFAULT_NAV
    lambda_ = LOSS_AVERSION_LAMBDA_DEFENSIVE if lens == "defensive" else LOSS_AVERSION_LAMBDA
    max_loss_cap_pct = MAX_LOSS_CAP_PCT_DEFENSIVE if lens == "defensive" else MAX_LOSS_CAP_PCT_AVERAGE

    underlying = str(underlying or "").strip().upper()
    if expiration is None:
        try:
            exps = options_provider.get_expirations(underlying)
            # Prefer an expiration with real time left (skip 0-DTE). Nearest to
            # ~40 DTE wins; in short-horizon sandboxes fall back to the longest
            # listed expiry.
            if not exps:
                expiration = None
            else:
                usable = [e for e in exps if _dte(e) >= 1]
                if not usable:
                    usable = exps
                usable.sort(key=lambda e: abs(_dte(e) - 40))
                expiration = usable[0] if _dte(usable[0]) <= 60 else max(usable, key=_dte)
        except Exception:
            expiration = None

    regime_state = {"regime": "Neutral", "confidence": 0.0}
    if regime:
        regime = str(regime).strip()
    else:
        regime_state = asyncio.run(current_regime())
        regime = regime_state["regime"]
    confidence = confidence or float(regime_state["confidence"])

    rows = _chain_rows(underlying, expiration, contract_type)
    by_key: dict[str, dict] = {}
    for r in rows:
        by_key[r.get("symbol") or (str(r.get("contract_type")) + str(r.get("strike_price")))] = r
    rows = list(by_key.values())
    rows.sort(key=lambda r: float(r.get("strike_price") or 0))
    rows_c = [r for r in rows if (r.get("contract_type") or "").lower() == "call"]
    rows_p = [r for r in rows if (r.get("contract_type") or "").lower() == "put"]
    spot = _spot_estimate(rows)
    dte = _dte(expiration or "")

    kg = _kg_option_strategies(regime)
    primary_ct = (contract_type or "call").lower()
    cards, rejected = _build_cards(
        rows_c, rows_p, kg, underlying, expiration or "", primary_ct,
        regime, confidence, dte, nav, max_loss_cap_pct, lambda_, lens,
    )

    # ── Nearby-strike + nearby-expiry expansion ────────────────────────────────
    # Evaluate the same KG strategy library against the next-nearest expiries
    # so the user can compare e.g. 2-DTE vs 9-DTE vs 16-DTE plays for the same
    # underlying side-by-side. This is what makes the strategy filter chips
    # actually useful — without it, most queries return a single card.
    alt_exps = _nearby_expirations(underlying, expiration or "", n=2)
    primary_idx = 0
    for alt_idx, alt_exp in enumerate(alt_exps, start=1):
        try:
            alt_rows = _chain_rows(underlying, alt_exp, contract_type)
        except Exception:
            continue
        if not alt_rows:
            continue
        alt_rows.sort(key=lambda r: float(r.get("strike_price") or 0))
        alt_c = [r for r in alt_rows if (r.get("contract_type") or "").lower() == "call"]
        alt_p = [r for r in alt_rows if (r.get("contract_type") or "").lower() == "put"]
        alt_dte = _dte(alt_exp)
        alt_cards, alt_rej = _build_cards(
            alt_c, alt_p, kg, underlying, alt_exp, primary_ct,
            regime, confidence, alt_dte, nav, max_loss_cap_pct, lambda_, lens,
        )
        for c in alt_cards:
            c["chain_source"] = f"alt_expiry_{alt_idx}"
        cards.extend(alt_cards)
        rejected.extend(alt_rej)

    # Also try the OPPOSITE contract type on the primary expiry (e.g. user
    # picked a call, but the regime favors puts). Gives one more comparison
    # axis without re-hitting the network twice.
    opposite_ct = "put" if primary_ct == "call" else "call"
    try:
        opp_rows = _chain_rows(underlying, expiration or "", opposite_ct)
    except Exception:
        opp_rows = []
    if opp_rows:
        opp_rows.sort(key=lambda r: float(r.get("strike_price") or 0))
        opp_c = [r for r in opp_rows if (r.get("contract_type") or "").lower() == "call"]
        opp_p = [r for r in opp_rows if (r.get("contract_type") or "").lower() == "put"]
        opp_cards, opp_rej = _build_cards(
            opp_c, opp_p, kg, underlying, expiration or "", opposite_ct,
            regime, confidence, dte, nav, max_loss_cap_pct, lambda_, lens,
        )
        for c in opp_cards:
            c["chain_source"] = "alt_type"
        cards.extend(opp_cards)
        rejected.extend(opp_rej)

    # Dedupe (strategy, expiration, contract_type) — keep the highest-ranked.
    cards = _dedupe_cards(cards)
    primary_idx = len(cards)

    # ── Rank by the LOSS-AVERSION lens, not raw EV ─────────────────────────────
    # Primary-chain cards float to the top, then alt-expiry, then alt-type.
    _source_rank = {"primary": 0, "alt_expiry_1": 1, "alt_expiry_2": 2, "alt_type": 3}
    cards.sort(key=lambda c: (
        _source_rank.get(c.get("chain_source", "primary"), 9),
        -float(c.get("loss_aversion_score", 0)),
    ))
    for i, c in enumerate(cards, start=1):
        c["rank"] = i

    # Cap to the top MAX_SUGGESTIONS so the UI doesn't get a wall of cards.
    # Primary chain always shows; alternates compete on loss-aversion score.
    MAX_SUGGESTIONS = int(os.getenv("OPTION_MAX_SUGGESTIONS", "10"))
    primary_count = sum(1 for c in cards if c.get("chain_source") == "primary")
    truncated = cards[:MAX_SUGGESTIONS]
    alt_count = len(truncated) - primary_count

    out: dict[str, Any] = {
        "underlying": underlying,
        "expiration": expiration,
        "regime": regime,
        "regime_confidence": confidence,
        "spot_estimate": spot,
        "dte": dte,
        "chain_size": len(rows),
        "lens": lens,
        "nav": nav,
        "max_loss_cap_pct": max_loss_cap_pct,
        "active_strategies": [s["name"] for s in kg],
        "suggestions": truncated,
        "rejected": rejected,
        "alt_expirations": alt_exps,
        "alt_count": alt_count,
        "primary_count": primary_count,
    }
    _suggestions_cache[cache_key] = (time.time(), out)
    return out


__all__ = ["compute_suggestions", "current_regime"]
