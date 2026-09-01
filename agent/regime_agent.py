"""
Regime Agent
Classifies the current market regime using a features-first, evidence-weighted
rule engine grounded in the REF quantitative-finance corpus (EWMA vol,
variance-ratio mean reversion, CUSUM structural-break confirmation,
downside-vol leverage probe, cross-asset correlation breakdown), then queries
Neo4j for the strategies activated in that regime.

Design notes (logic-correction pass):
  * ^VIX / ^TNX are not on Alpaca's IEX feed, so the vol gauge is the
    realized-volatility VIX proxy of SPY (realized_vix_proxy; VIX-index scale).
  * Regime flips require a persistence gate (two-stage break verification):
    a single-day crossing does not cause a recalibration.
  * MeanReverting and LowVolatility are now reachable (previously the old
    classifier never emitted them), via VR(21) < 0.9 and EWMA-vol z <= -1.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from alpaca_data import provider
from common.graph import get_db
from loguru import logger

# Assets used for the correlation-breakdown gauge (REF: correlations -> 1 in stress)
CORR_UNIVERSE = ["SPY", "QQQ", "XLF", "XLE", "GLD"]

# EWMA RiskMetrics decay (REF section 1.2.6)
EWMA_LAMBDA = 0.94

# CUSUM params (REF section 3.4: S+/S- with k = half-std slack, h = 5*sigma alarm)
CUSUM_K_MULT = 0.5
CUSUM_H_MULT = 5.0

# A stress regime must be confirmed STRESS_CONFIRM_CYCLES consecutive cycles.
STRESS_CONFIRM_CYCLES = 3


class RegimeAgent:
    def __init__(self):
        self.db = get_db()
        self._prev_regime = None
        self._stress_streak = 0
        self._persistence_days = 0
        self._recent_regimes = []

    async def run(self) -> dict:
        try:
            prices = self._fetch_market_data()
            features = self._compute_regime_features(prices)
            regime = self._classify_regime(features)
            self._update_persistence(regime, features)
            features["regime_persistence"] = self._persistence_days
            confidence = self._regime_confidence(features, regime)
            strategies = self._query_active_strategies(regime)
        except Exception as e:
            logger.warning(f"RegimeAgent run failed: {e}")
            regime = "Neutral"
            confidence = 0.0
            features = self._empty_features()
            strategies = []
        return {
            "regime": regime,
            "confidence": confidence,
            "features": features,
            "active_strategies": strategies,
        }

    def _empty_features(self) -> dict:
        return {
            "ewma_vol": 0.0,
            "vol_21": 0.0,
            "vol_zscore": 0.0,
            "downside_ratio": 1.0,
            "ret_21": 0.0,
            "price_vs_200ma": 0.0,
            "hyg_dd_63": 0.0,
            "hyg_relative": 0.0,
            "vr_21": 1.0,
            "corr_breakdown": 0.5,
            "cusum_alarm": False,
            "vix_now": 0.0,
            "vix_ma30": 0.0,
            "regime_persistence": 0,
        }

    def _fetch_market_data(self) -> pd.DataFrame:
        """Pull closes for the correlation universe + HYG via the Alpaca provider."""
        symbols = list(dict.fromkeys(CORR_UNIVERSE + ["HYG"]))
        frames = {}
        for sym in symbols:
            df = provider.get_ohlcv(sym, days=260)
            if isinstance(df, pd.DataFrame) and not df.empty and "Close" in df.columns:
                frames[sym] = df["Close"].rename(sym)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, axis=1).dropna(how="all")

    def _compute_regime_features(self, prices: pd.DataFrame) -> dict:
        """Feature extraction (past-data only, no lookahead) for the rule engine."""
        f = self._empty_features()
        if prices is None or prices.empty or "SPY" not in prices.columns:
            return f
        spy = prices["SPY"].dropna()
        if len(spy) < 60:
            return f
        rets = spy.pct_change().dropna()
        closes_log = np.log(spy.replace(0.0, np.nan).dropna())

        # EWMA RiskMetrics vol (annualized) + 21d realized vol + z-score
        ewma_var = (rets ** 2).ewm(alpha=1.0 - EWMA_LAMBDA, adjust=False).mean()
        if ewma_var.iloc[-1] > 0:
            f["ewma_vol"] = float(np.sqrt(ewma_var.iloc[-1]) * np.sqrt(252))
        vol_21 = rets.rolling(21).std() * np.sqrt(252)
        if not np.isnan(vol_21.iloc[-1]):
            f["vol_21"] = float(vol_21.iloc[-1])
        hist = vol_21.dropna()
        if len(hist) >= 63 and hist.std() > 1e-12:
            f["vol_zscore"] = float((hist.iloc[-1] - hist.mean()) / hist.std())

        # Downside ratio (semi-dev / total vol; leverage probe)
        mu = rets.mean()
        down = rets[rets < mu]
        if len(down) >= 2:
            total_var = float(rets.var())
            if total_var > 1e-12:
                downside_var = float(np.sum((down - mu) ** 2) / max(len(rets) - 1, 1))
                f["downside_ratio"] = float(np.sqrt(downside_var) / np.sqrt(total_var))

        # Returns vs recent + distance from 200d MA
        if len(spy) > 21:
            f["ret_21"] = float(spy.iloc[-1] / spy.iloc[-22] - 1.0)
        ma200 = spy.rolling(200).mean()
        if not np.isnan(ma200.iloc[-1]) and ma200.iloc[-1] > 0:
            f["price_vs_200ma"] = float(spy.iloc[-1] / ma200.iloc[-1] - 1.0)

        # HYG credit-spread proxy
        hyg = prices["HYG"].dropna() if "HYG" in prices.columns else pd.Series(dtype=float)
        if not hyg.empty:
            peak = hyg.rolling(63).max()
            if not np.isnan(peak.iloc[-1]) and peak.iloc[-1] > 0:
                f["hyg_dd_63"] = float((peak.iloc[-1] - hyg.iloc[-1]) / peak.iloc[-1])
        if len(hyg) > 21 and len(spy) > 21:
            ratio = (hyg / spy).dropna()
            if len(ratio) > 21 and ratio.iloc[-1] != 0.0 and not np.isnan(ratio.iloc[-1]):
                f["hyg_relative"] = float(ratio.iloc[-1] / ratio.iloc[-22] - 1.0)

        # Variance Ratio VR(21) - below 1 implies mean reversion
        if len(closes_log) > 60:
            r1 = closes_log.diff().iloc[-105:]
            rk = closes_log.diff(21).iloc[-105:]
            var1 = float(r1.var())
            if var1 > 1e-12:
                f["vr_21"] = float(rk.var() / (21 * var1))

        # Cross-asset correlation breakdown (60d rolling mean pairwise corr)
        univ = [t for t in CORR_UNIVERSE if t in prices.columns]
        if len(univ) >= 3:
            rmat = prices[univ].pct_change().dropna().tail(60)
            if len(rmat) >= 21:
                cmat = rmat.corr().values
                tri = cmat[np.triu_indices(n=len(univ), k=1)]
                if tri.size and not np.isnan(tri).all():
                    f["corr_breakdown"] = float(np.nanmean(tri))

        # CUSUM structural-break alarm on daily returns
        x = rets - rets.mean()
        std = rets.std()
        if std > 1e-12:
            kc = CUSUM_K_MULT * std
            hc = CUSUM_H_MULT * std
            s_up, s_dn = 0.0, 0.0
            alarm = False
            for xv in x.values:
                s_up = max(0.0, s_up + xv - kc)
                s_dn = max(0.0, s_dn - xv - kc)
                if s_up >= hc or s_dn >= hc:
                    alarm = True
                    break
            f["cusum_alarm"] = alarm

        # VIX proxy levels (VIX-index scale; uses EWMA/realized vol * 100)
        if f["ewma_vol"] > 0:
            f["vix_now"] = float(f["ewma_vol"] * 100.0)
        if f["vol_21"] > 0:
            f["vix_ma30"] = float(f["vol_21"] * 100.0)

        return f
    def _classify_regime(self, features: dict) -> str:
        """Priority-ordered rule engine over the feature vector."""
        if features.get("ewma_vol", 0.0) <= 0 or features.get("vol_21", 0.0) <= 0:
                return "Neutral"

        # 1. Systemic stress: all confirmations + persistence gate.
        # Two-stage break verification (REF Module 5 / Model Failure & Crises):
        # the first alarm just starts a confirmation streak;; only after
        # STRESS_CONFIRM_CYCLES consecutive cycles do we declare the regime。
        stress_triple = (
                bool(features.get("cusum_alarm"))
                and features.get("corr_breakdown", 0.0) >= 0.7
                and features.get("hyg_dd_63", 0.0) > 0.04
                and features.get("vol_zscore", 0.0) >= 1.0
        )
        if stress_triple:
            self._stress_streak += 1
        else:
            self._stress_streak = 0
        if stress_triple and self._stress_streak >= STRESS_CONFIRM_CYCLES:
                return "SystemicStress"

        # 2. Crisis: severe vol spike + broken trend, or extreme downside asymmetry
        if features.get("vol_zscore", 0.0) >= 1.5 and features.get("price_vs_200ma", 0.0) < -0.05:
                return "Crisis"
        if features.get("downside_ratio", 1.0) >= 1.6 and features.get("vol_zscore", 0.0) >= 1.0:
                return "Crisis"

        # 3. Mean-reverting tape (VR(21) < 0.9 + bounded range) - newly reachable
        if features.get("vr_21", 1.0) < 0.9 and abs(features.get("price_vs_200ma", 0.0)) < 0.08:
                return "MeanReverting"

        # 4. Compressed vol (EWMA-vol z <= -1) - newly reachable
        if features.get("vol_zscore", 0.0) <= -1.0:
                return "LowVolatility"

        # 5. High-vol regime (z-calibrated)
        if features.get("vol_zscore", 0.0) >= 1.0:
                return "HighVolatility"

        # 6. Trend / recovery (low-vol context)
        if features.get("ret_21", 0.0) > 0.03 and features.get("vol_zscore", 0.0) < 0.5:
                return "Trending"
        if features.get("ret_21", 0.0) > 0.0 and features.get("vix_now", 0.0) < features.get("vix_ma30", 1.0):
                return "Recovery"

        return "Neutral"
    def _stress_confirmed(self) -> bool:
        """Persistence gate: the stress signature must hold for N consecutive cycles."""
        if not hasattr(self, "_recent_regimes") or self._recent_regimes is None:
            self._recent_regimes = []
        recent = self._recent_regimes[-STRESS_CONFIRM_CYCLES:]
        if len(recent) < STRESS_CONFIRM_CYCLES:
            return False
        return all(r == "SystemicStress" for r in recent)

    def _update_persistence(self, regime: str, features: dict) -> None:
        prev = getattr(self, "_prev_regime", None)
        if regime != prev:
            self._prev_regime = regime
            self._persistence_days = 0
        else:
            self._persistence_days = min(self._persistence_days + 1, 90)
        if not hasattr(self, "_recent_regimes") or self._recent_regimes is None:
            self._recent_regimes = []
        self._recent_regimes.append(regime)
        self._recent_regimes = self._recent_regimes[-(STRESS_CONFIRM_CYCLES + 2):]

    def _regime_confidence(self, features: dict, regime: str) -> float:
        vz = float(features.get("vol_zscore", 0.0) or 0.0)
        corr = float(features.get("corr_breakdown", 0.5) or 0.5)
        vr = float(features.get("vr_21", 1.0) or 1.0)
        ret = float(features.get("ret_21", 0.0) or 0.0)

        if regime == "SystemicStress":
            return float(np.clip(0.5 + (corr - 0.7) / 0.2, 0.0, 1.0))
        if regime == "Crisis":
            return float(np.clip(0.5 + (vz - 1.5) / 1.0, 0.0, 1.0))
        if regime == "HighVolatility":
            return float(np.clip(0.5 + (vz - 1.0) / 1.0, 0.0, 1.0))
        if regime == "LowVolatility":
            return float(np.clip(0.5 + (-vz - 1.0) / 1.0, 0.0, 1.0))
        if regime == "MeanReverting":
            return float(np.clip(0.5 + (0.9 - vr) / 0.2, 0.0, 1.0))
        if regime == "Trending":
            return float(np.clip(0.5 + (ret - 0.03) / 0.05, 0.0, 1.0))
        if regime == "Recovery":
            return 0.65
        return float(np.clip(0.35 + self._persistence_days * 0.05, 0.0, 1.0))

    def _query_active_strategies(self, regime: str) -> list:
        query = f"""
        MATCH (r:Regime {{name: '{regime}'}})<-[:ACTIVATED_BY]-(s:Strategy)
        WHERE s.status = 'active'
        RETURN s.name AS name,
               s.strategy_type AS type,
               s.signal_method AS signal_method,
               s.param_sell_threshold AS sell_threshold,
               s.param_exposure_cut AS exposure_cut,
               s.derived_from AS derived_from,
               s.target_ticker AS ticker,
               s.risk_weight AS risk_weight
        """
        try:
            results = list(self.db.execute_and_fetch(query))
            logger.debug(f"Graph returned {len(results)} active strategies for {regime}")
            return results
        except Exception as e:
            logger.error(f"Graph query failed: {e}")
            return []
