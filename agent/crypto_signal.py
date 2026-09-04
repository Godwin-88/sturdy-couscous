"""Crypto Signal Agent — GraphAlpha.
KG-grounded, loss-averse suggestion engine for spot crypto on Alpaca paper.
Spot-only: the chain-equivalent is the price/vol tape. Thin wrappers over existing
modules; orders execute only via the two-phase preview/confirm gate in
/signals/place (human-in-the-loop).
"""
from __future__ import annotations

import os
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from common.graph import get_db

LENS_META = {
    "defensive": {"lambda": 3.5, "max_loss_pct_nav": 0.05},
    "average":    {"lambda": 2.25, "max_loss_pct_nav": 0.10},
}


_CRYPTO_FALLBACK: list[dict] = [
    {"name": "Crypto Momentum",       "signal_method": "crypto_momentum",
     "threshold": None, "risk_weight": 0.5, "target": None,
     "description": "12-1 / 21-7 momentum carry on trend leaders."},
    {"name": "Crypto Trend Following", "signal_method": "crypto_trend",
     "threshold": None, "risk_weight": 0.4, "target": None,
     "description": "Follow 50/200-ma directional regime."},
    {"name": "Crypto Mean Reversion",  "signal_method": "crypto_mr",
     "threshold": None, "risk_weight": 0.3, "target": None,
     "description": "Mean-revert stretched pairs."},
    {"name": "BTC Portfolio Hedge",      "signal_method": "crypto_hedge",
     "threshold": None, "risk_weight": 0.5, "target": "BTC/USD",
     "description": "Directional hedge sleeve for the equity book."},
]


# Signal methods computable from the SPOT tape (no option chain required).
# Every KG strategy whose signal_method is in this set is eligible to score on
# crypto spot; the rest (spreads/butterfly/condor/… needing option legs) are
# surfaced in the picker but flagged "not computable on spot".
_TAPE_COMPUTABLE = {
    "momentum", "crypto_momentum",
    "trend", "crypto_trend",
    "value_mr", "crypto_mr",
    "vol_zscore", "garch_vol",
    "crisis_hedge", "crypto_hedge",
    "bn_macro", "contagion",
}


def _kg_crypto_strategies() -> list[dict]:
    """ALL active KG strategies (any venue) for the crypto picker.

    Each strategy carries its regime activation weights (ACTIVATED_BY edges) and a
    ``computable`` flag — true iff its signal_method can be computed from the spot
    tape. The scoring set (suggest_crypto) uses computable ones only; the picker
    UI shows the full library with the flag.
    """
    try:
        db = get_db()
        rows = list(db.execute_and_fetch(
            "MATCH (s:Strategy {status:'active'}) "
            "OPTIONAL MATCH (s)-[a:ACTIVATED_BY]->(r:Regime) "
            "RETURN s.name AS name, s.signal_method AS signal_method, "
            "s.tradeable_venue AS tradeable_venue, "
            "s.param_sell_threshold AS threshold, s.risk_weight AS risk_weight, "
            "s.target_ticker AS target, s.description AS description, "
            "collect(DISTINCT r.name) AS regimes, "
            "collect(DISTINCT a.weight) AS regime_weights "
            "ORDER BY s.name"))
        out: list[dict] = []
        for r in rows:
            name = r.get("name")
            method = r.get("signal_method") or ""
            if not name:
                continue
            s = {
                "name": name,
                "signal_method": method,
                "tradeable_venue": r.get("tradeable_venue"),
                "threshold": r.get("threshold"),
                "risk_weight": r.get("risk_weight"),
                "target": r.get("target"),
                "description": r.get("description"),
                "regimes": [x for x in (r.get("regimes") or []) if x],
                "regime_weights": [w for w in (r.get("regime_weights") or []) if w is not None],
                "computable": method in _TAPE_COMPUTABLE,
            }
            # A strategy inherits its method's computability even if the KG
            # didn't set one explicitly (equity/option strategies on a spot tape).
            out.append(s)
        return out
    except Exception as e:
        logger.warning(f"KG crypto strategies failed: {e}")
        out = [dict(s) for s in _CRYPTO_FALLBACK]
        for s in out:
            s["computable"] = (s.get("signal_method") in _TAPE_COMPUTABLE)
        return out


def _all_crypto_strategies() -> list[dict]:
    """Full selectable strategy library (every active KG strategy)."""
    return _kg_crypto_strategies()


def _get_crypto_strategy_by_name(name: str) -> dict | None:
    """Fetch a single crypto strategy by name, regime-independent."""
    name = str(name or "").strip()
    if not name:
        return None
    try:
        for s in _all_crypto_strategies():
            if (s.get("name") or "").lower() == name.lower():
                return s
    except Exception as e:
        logger.warning(f"_get_crypto_strategy_by_name failed: {e}")
    return None


def _tape(pair: str, days: int = 90) -> tuple[pd.DataFrame, dict]:
    """OHLCV tape (Alpaca provider, yfinance fallback) + summary indices."""
    try:
        from agent.alpaca_data import provider as _prov
        df = _prov.get_ohlcv(pair, days=days)
    except Exception as e:
        logger.warning(f"crypto tape failed for {pair}: {e}")
        return pd.DataFrame(), {}
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame(), {}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    close = df["Close"].astype(float)
    rets = close.pct_change().dropna()
    spot = float(close.iloc[-1]) if len(close) else 0.0
    idx: dict[str, Any] = {"spot": spot, "rows": len(df)}
    if len(close) > 22:
        mom_12_1 = float(close.iloc[-1] / close.iloc[-12] - 1)
        mom_21_7 = float(close.iloc[-21:].mean() / close.iloc[-7:].mean() - 1)
    else:
        mom_12_1 = mom_21_7 = 0.0
    idx["mom_12_1"] = round(mom_12_1, 4)
    idx["mom_21_7"] = round(mom_21_7, 4)
    rv = rets.rolling(21).std().dropna() * np.sqrt(365)
    if len(rv) >= 2:
        idx["rv_21"] = round(float(rv.iloc[-1]), 4)
        idx["rv_pctile"] = round(float((rv <= rv.iloc[-1]).mean()), 4)
        idx["rv_21_z"] = round(float((rv.iloc[-1] - rv.mean()) / (rv.std() or 1)), 2)
    if len(close) >= 200:
        m200 = close.rolling(200).mean()
        idx["above_200ma"] = bool(close.iloc[-1] > m200.iloc[-1])
        idx["dist_200ma_pct"] = round(float(close.iloc[-1] / m200.iloc[-1] - 1), 4)
    else:
        idx["above_200ma"] = None
        if len(close) >= 50:
            ma50 = close.rolling(50).mean()
            ma20 = close.rolling(20).mean()
            idx["ma_50"] = float(ma50.iloc[-1]) if ma50.iloc[-1] == ma50.iloc[-1] else None
            idx["ma_20"] = float(ma20.iloc[-1]) if ma20.iloc[-1] == ma20.iloc[-1] else None
    # MA cross (fallback trend proxy when 200d not available)
    ma_s = idx.get("ma_50")
    ma_l = idx.get("ma_20")
    if ma_s is not None and ma_l is not None:
        idx["ma_cross"] = bool(ma_s > ma_l)
    elif idx.get("above_200ma") is not None:
        idx["ma_cross"] = idx.get("above_200ma")
    if len(df) >= 60:
        m12 = close.pct_change(12).dropna()
        m12z = (m12.iloc[-1] - m12.mean()) / (m12.std() or 1)
        idx["mom_12_1_z"] = round(float(m12z), 2)
        m21_7 = (close.rolling(21).mean() / close.rolling(7).mean() - 1).dropna()
        z = (m21_7.iloc[-1] - m21_7.mean()) / (m21_7.std() or 1)
        idx["mom_21_7_z"] = round(float(z), 2)
    return df, idx


def _classify_crypto_regime(idx: dict) -> tuple[str, float]:
    """Per-pair regime from the pair's OWN tape (past data only).

    Crypto is rarely a mean-reverting asset, so MeanReverting is issued ONLY
    when vol is compressed AND price is range-bound near the trend proxy. The
    regime is computed from the pair's tape — it must NOT inherit the global
    SPY/equity label (that was the bug: chat anchored XRP on the SPY MeanReverting).
    """
    rvp = idx.get("rv_pctile")
    mz = idx.get("mom_12_1_z", 0.0) or 0.0
    above = idx.get("above_200ma")
    cross = idx.get("ma_cross")
    if above is None:
        above = cross
    dist = abs(float(idx.get("dist_200ma_pct") or 0.0))

    if rvp is None or idx.get("spot") is None:
        return "Neutral", 0.3

    # 1. Crisis: extreme vol + sharp negative momentum
    if rvp >= 0.9 and mz <= -1.0:
        return "Crisis", 0.75
    # 2. HighVolatility: elevated vol (directional or not)
    if rvp >= 0.8:
        return "HighVolatility", 0.7
    # 3. Trending: strong aligned momentum on reasonable vol
    if abs(mz) >= 0.8 and rvp <= 0.75:
        if above is not None:
            aligned = (mz > 0 and above) or (mz < 0 and not above)
        else:
            aligned = True
        if aligned:
            return "Trending", 0.65
    # 4. LowVolatility: compressed vol + quiet tape
    if rvp <= 0.25 and abs(mz) < 0.5:
        return "LowVolatility", 0.6
    # 5. MeanReverting ONLY when compressed vol AND range-bound (rare for crypto)
    if rvp <= 0.4 and abs(mz) < 0.7 and dist < 0.06:
        return "MeanReverting", 0.5
    # 6. Neutral: mixed / no clear signal
    return "Neutral", 0.4


def _score_strategy(strat: dict, idx: dict, pair: str, lens: str, nav: float,
                    regime: str | None = None) -> dict | None:
    """Score one strategy from the tape → an order-draft card, or None (gated).

    Handles the full ``_TAPE_COMPUTABLE`` signal_method set — any KG strategy
    whose metrics can be computed from the spot tape scores; pure option-leg
    strategies are skipped (caller flags them non-computable).
    ``regime`` drives a regime-fit bonus from the KG ACTIVATED_BY edge weight so
    switching regime actually changes the ranked cards (mirrors Options).
    """
    lm = LENS_META.get(lens, LENS_META["average"])
    sm = strat.get("signal_method")
    if sm not in _TAPE_COMPUTABLE:
        return None
    spot = idx.get("spot") or 0.0
    nav = max(nav, 1.0)
    name = strat["name"]
    side = "buy"
    score = 40.0
    # Budget scales with KG risk_weight when present (default 0.5).
    rw = float(strat.get("risk_weight") or 0.5) or 0.5
    budget = 0.02 * nav * rw

    # Regime fit: use the KG edge weight for the selected regime (default 0.5).
    regime = regime or idx.get("regime") or "Neutral"
    regime_set = {str(r).lower() for r in (strat.get("regimes") or [])}
    base_w = 0.5
    if regime.lower() in regime_set:
        ws = [float(w) for w in (strat.get("regime_weights") or [0.9]) if float(w) > 0]
        base_w = max(ws) if ws else 0.9

    if sm in ("momentum", "crypto_momentum"):
        z = idx.get("mom_12_1_z", 0.0)
        score = 35 + 20 * max(-1.0, min(1.0, z))
        side = "buy" if z >= 0 else "sell"
    elif sm in ("trend", "crypto_trend"):
        above = idx.get("above_200ma")
        if above is None:
            ma_s = idx.get("ma_50")
            ma_l = idx.get("ma_20")
            above = bool(ma_s and ma_l and ma_s > ma_l) if ma_s is not None and ma_l is not None else None
        if above is None:
            return None
        score = 40 + 20 * (1 if above else -1)
        side = "buy" if above else "sell"
    elif sm in ("value_mr", "crypto_mr"):
        z = idx.get("mom_12_1_z", 0.0)
        if abs(z) < 0.8:
            return None
        score = 40 + 20 * max(-1.0, min(1.0, -z))
        side = "buy" if z < 0 else "sell"
    elif sm == "vol_zscore":
        # RV percentile z: short vol (sell) when stretched high, buy when cheap.
        rvp = idx.get("rv_pctile")
        if rvp is None:
            return None
        z = (rvp - 0.5) * 2.0
        score = 40 + 20 * max(-1.0, min(1.0, -z))
        side = "sell" if z > 0.2 else "buy"
        budget = 0.01 * nav * rw  # tighter for vol
    elif sm == "garch_vol":
        # Vol regime: EWMA-realized proxy — high rv_z → reduce/sell, low → buy.
        rvz = idx.get("rv_21_z", 0.0)
        score = 40 + 20 * max(-1.0, min(1.0, -rvz))
        side = "sell" if rvz > 0.5 else "buy"
    elif sm in ("crisis_hedge", "crypto_hedge"):
        score = 45.0 + (10.0 if regime.lower() in ("crisis", "systemicstress", "highvolatility") else 0.0)
        side = "buy"
        budget = 0.01 * nav * rw
    elif sm == "bn_macro":
        # Macro regime overlay — favor broad risk-on/off from tape meta.
        if regime.lower() in ("crisis", "systemicstress", "highvolatility"):
            score = 42.0
            side = "sell" if idx.get("mom_12_1_z", 0.0) < 0 else "buy"
        else:
            score = 48.0
            side = "buy"
    elif sm == "contagion":
        # Contagion weakener: long BTC hedge only in stress; skips otherwise.
        if regime.lower() in ("crisis", "systemicstress"):
            score = 46.0
            side = "buy"
            budget = 0.01 * nav * rw
        else:
            return None
    else:
        return None

    # Regime-fit bonus applied AFTER the strategy raw score (so it isn't clobbered).
    score += 20.0 * base_w  # ≤ +20 regime-fit bonus

    # Size to the USD loss budget: qty = budget / spot. This clears Alpaca's
    # $10 minimum *notional* for any pair (high-price → small qty, low-price →
    # larger qty) without the broken max(10.0, ...) unit-floor that forced
    # e.g. 10 BTC (~$810k) regardless of budget.
    qty_rec = budget / max(spot, 1.0)
    max_loss = budget
    max_loss_pct_nav = max_loss / nav
    if max_loss_pct_nav > lm["max_loss_pct_nav"]:
        return None
    score -= lm["lambda"] * max_loss_pct_nav * 100
    return {
        "strategy": name,
        "signal_method": sm,
        "side": side,
        "qty_rec": round(qty_rec, 6),
        "est_premium": round(max_loss, 2),
        "max_profit_low": round(max_loss * 2.0, 2),
        "max_loss": round(max_loss, 2),
        "max_loss_pct_nav": round(max_loss_pct_nav, 4),
        "risk_reward_pct": 200.0,
        "score": round(score, 1),
        "regime": regime,
        "activated": regime.lower() in regime_set,
        "liquidity_ok": True,
        "notes": [f"Trade {pair} {side} at ~{spot:,.2f}",
                  f"regime-fit +{20 * base_w:.0f} · mom12-1z {idx.get('mom_12_1_z', 0):+.2f} · RVpct {idx.get('rv_pctile', 0)}"],
    }


def suggest_crypto(pair: str, lens: str = "defensive", nav: float = 100_000.0,
                   regime_override: str | None = None,
                   strategy_filter: str | None = None) -> dict:
    """Full crypto suggestion envelope: tape + ranked loss-averse cards.

    ``strategy_filter`` forces a specific strategy into the scoring set even when
    it is not ACTIVATED_BY the selected regime (mirrors Options); the envelope
    also returns ``all_strategies`` for the UI picker.
    """
    df, idx = _tape(pair)
    # Per-pair regime from the pair's OWN tape — NOT the global SPY label.
    # The user can still override via the UI toggle (regime_override).
    if regime_override:
        regime = regime_override
        regime_source = "user_override"
        regime_conf = 0.9
    else:
        regime, regime_conf = _classify_crypto_regime(idx)
        regime_source = "pair_tape"
    idx["lens"] = lens
    idx["regime"] = regime
    kg = _kg_crypto_strategies()
    cards = []
    base_envelope = {
        "pair": pair, "lens": lens, "nav": nav, "regime": idx.get("regime"),
        "regime_confidence": regime_conf, "regime_source": regime_source,
        "spot": idx.get("spot"), "mom_12_1": idx.get("mom_12_1"),
        "mom_21_7": idx.get("mom_21_7"), "rv_21": idx.get("rv_21"),
        "rv_pctile": idx.get("rv_pctile"), "above_200ma": idx.get("above_200ma"),
        "tape_rows": idx.get("rows", 0),
        "all_strategies": [{
            "name": s["name"], "method": s.get("signal_method"),
            "regimes": s.get("regimes") or [], "risk_weight": s.get("risk_weight"),
            "computable": bool(s.get("computable")),
            "tradeable_venue": s.get("tradeable_venue"),
        } for s in _all_crypto_strategies()],
    }

    # "Select any strategy" support — mirror Options: inject a specific strategy
    # even if it is not ACTIVATED_BY the current regime, so its accurate tape
    # metrics are computed and returned. Also expose the full picker library.
    if strategy_filter:
        sf = str(strategy_filter).strip().lower()
        matched = next((s for s in kg if (s.get("name") or "").lower() == sf), None)
        if matched is None:
            matched = _get_crypto_strategy_by_name(strategy_filter)
        if matched is not None:
            matched["regimes"] = matched.get("regimes") or []
            matched["regime_weights"] = matched.get("regime_weights") or []
            kg = [matched]
        else:
            return {
                **base_envelope, "strategy_filter": strategy_filter,
                "filter_note": f"Strategy '{strategy_filter}' not found in the KG.",
                "suggestions": [],
            }

    for s in kg:
        try:
            c = _score_strategy(s, idx, pair, lens, nav, regime=regime)
            if c:
                cards.append(c)
        except Exception as e:
            logger.warning(f"crypto score failed {s.get('name')}: {e}")
    cards.sort(key=lambda c: c["score"], reverse=True)

    # If the user force-selected a strategy that needs option legs (not tape-
    # computable), say so explicitly — no silent empty list.
    filter_note = ""
    if strategy_filter:
        sf = str(strategy_filter).strip().lower()
        sel = next((s for s in _all_crypto_strategies()
                    if (s.get("name") or "").lower() == sf), None)
        if sel is not None and not sel.get("computable"):
            filter_note = (f"{sel.get('name')} is not computable on crypto spot "
                           f"(needs option legs) — pick a tape-based strategy "
                           f"(momentum / trend / mean-reversion / vol / hedge / macro).")

    return {
        **base_envelope,
        "strategy_filter": strategy_filter,
        "filter_note": filter_note,
        "suggestions": cards,
    }


__all__ = ["suggest_crypto"]
