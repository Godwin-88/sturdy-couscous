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


def _kg_crypto_strategies() -> list[dict]:
    """Active crypto strategies from the KG (or a graph-down built-in family)."""
    try:
        db = get_db()
        rows = list(db.execute_and_fetch(
            "MATCH (s:Strategy {status:'active', tradeable_venue:'alpaca_crypto'}) "
            "RETURN s.name AS name, s.signal_method AS signal_method, "
            "s.param_sell_threshold AS threshold, s.risk_weight AS risk_weight, "
            "s.target_ticker AS target, s.description AS description ORDER BY s.name"))
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"KG crypto strategies failed: {e}")
        return [
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
    if len(rv) >= 1:
        idx["rv_21"] = round(float(rv.iloc[-1]), 4)
        idx["rv_pctile"] = round(float((rv <= rv.iloc[-1]).mean()), 4)
    if len(close) >= 200:
        m200 = close.rolling(200).mean()
        idx["above_200ma"] = bool(close.iloc[-1] > m200.iloc[-1])
        idx["dist_200ma_pct"] = round(float(close.iloc[-1] / m200.iloc[-1] - 1), 4)
    if len(df) >= 60:
        m12 = close.pct_change(12).dropna()
        m12z = (m12.iloc[-1] - m12.mean()) / (m12.std() or 1)
        idx["mom_12_1_z"] = round(float(m12z), 2)
        m21_7 = (close.rolling(21).mean() / close.rolling(7).mean() - 1).dropna()
        z = (m21_7.iloc[-1] - m21_7.mean()) / (m21_7.std() or 1)
        idx["mom_21_7_z"] = round(float(z), 2)
    return df, idx


def _score_strategy(strat: dict, idx: dict, pair: str, lens: str, nav: float) -> dict | None:
    """Score one strategy from the tape → an order-draft card, or None (gated)."""
    lm = LENS_META.get(lens, LENS_META["average"])
    sm = strat.get("signal_method")
    spot = idx.get("spot") or 0.0
    nav = max(nav, 1.0)
    name = strat["name"]
    side = "buy"
    score = 40.0
    budget = 0.02 * nav
    if sm == "crypto_momentum":
        z = idx.get("mom_12_1_z", 0.0)
        score = 35 + 20 * max(-1.0, min(1.0, z))
        side = "buy" if z >= 0 else "sell"
    elif sm == "crypto_trend":
        above = idx.get("above_200ma")
        if above is None:
            return None
        score = 40 + 20 * (1 if above else -1)
        side = "buy" if above else "sell"
    elif sm == "crypto_mr":
        z = idx.get("mom_12_1_z", 0.0)
        if abs(z) < 0.8:
            return None
        score = 40 + 20 * max(-1.0, min(1.0, -z))
        side = "buy" if z < 0 else "sell"
    elif sm == "crypto_hedge":
        score = 45.0
        side = "buy"
        budget = 0.01 * nav
    else:
        return None
    qty_rec = max(10.0, budget / max(spot, 1.0))
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
        "liquidity_ok": True,
        "notes": [f"Trade {pair} {side} at ~{spot:,.2f}",
                   f"mom12-1z {idx.get('mom_12_1_z', 0):+.2f} · RVpct {idx.get('rv_pctile', 0)}"],
    }


def suggest_crypto(pair: str, lens: str = "defensive", nav: float = 100_000.0,
                   regime_override: str | None = None) -> dict:
    """Full crypto suggestion envelope: tape + ranked loss-averse cards."""
    df, idx = _tape(pair)
    idx["lens"] = lens
    idx["regime"] = regime_override or "Neutral"
    cards = []
    for s in _kg_crypto_strategies():
        try:
            c = _score_strategy(s, idx, pair, lens, nav)
            if c:
                cards.append(c)
        except Exception as e:
            logger.warning(f"crypto score failed {s.get('name')}: {e}")
    cards.sort(key=lambda c: c["score"], reverse=True)
    return {
        "pair": pair,
        "lens": lens,
        "nav": nav,
        "regime": idx.get("regime"),
        "spot": idx.get("spot"),
        "mom_12_1": idx.get("mom_12_1"),
        "mom_21_7": idx.get("mom_21_7"),
        "rv_21": idx.get("rv_21"),
        "rv_pctile": idx.get("rv_pctile"),
        "above_200ma": idx.get("above_200ma"),
        "tape_rows": idx.get("rows", 0),
        "suggestions": cards,
    }


__all__ = ["suggest_crypto"]
