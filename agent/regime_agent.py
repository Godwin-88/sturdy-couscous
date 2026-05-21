"""
Regime Agent
Classifies current market regime and queries Memgraph for active strategies.
Graph query: MATCH (r:Regime)<-[:ACTIVATED_BY]-(s:Strategy {status:'active'})
"""

import os
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from gqlalchemy import Memgraph
from loguru import logger


REGIME_NAMES = [
    "BullMarket", "BearMarket", "HighVolatility",
    "LowVolatility", "SystemicStress", "CrisisRegime", "RecoveryRegime"
]


class RegimeAgent:
    def __init__(self):
        self.db = Memgraph(
            host=os.getenv("MEMGRAPH_HOST", "memgraph"),
            port=int(os.getenv("MEMGRAPH_PORT", 7687))
        )

    async def run(self) -> dict[str, Any]:
        prices  = self._fetch_market_data()
        regime  = self._classify_regime(prices)
        conf    = self._regime_confidence(prices, regime)
        strategies = self._query_active_strategies(regime)

        return {
            "regime": regime,
            "confidence": conf,
            "active_strategies": strategies,
        }

    # ── Market data ───────────────────────────────────────────────────────────
    def _fetch_market_data(self) -> pd.DataFrame:
        """Pull SPY, VIX proxy (^VIX), and 10Y yield (^TNX) for regime signals."""
        tickers = ["SPY", "^VIX", "^TNX", "HYG"]
        raw = yf.download(tickers, period="1y", auto_adjust=True, progress=False)
        return raw["Close"].dropna()

    # ── Regime classification ─────────────────────────────────────────────────
    def _classify_regime(self, prices: pd.DataFrame) -> str:
        spy   = prices["SPY"]
        vix   = prices["^VIX"]
        hyg   = prices.get("HYG", pd.Series(dtype=float))

        # Rolling metrics (use only past data — no lookahead)
        ret_21     = spy.pct_change(21).iloc[-1]
        vol_21     = spy.pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)
        ma_200     = spy.rolling(200).mean().iloc[-1]
        vix_now    = vix.iloc[-1]
        vix_ma_30  = vix.rolling(30).mean().iloc[-1]

        # Credit spread proxy: HYG drawdown
        hyg_dd = 0.0
        if not hyg.empty:
            hyg_peak = hyg.rolling(63).max().iloc[-1]
            hyg_dd   = (hyg_peak - hyg.iloc[-1]) / hyg_peak

        # Priority-ordered regime rules
        if vix_now > 35 or hyg_dd > 0.06:
            return "SystemicStress"
        if vix_now > 25 and ret_21 < -0.05:
            return "CrisisRegime"
        if vol_21 > 0.25:
            return "HighVolatility"
        if spy.iloc[-1] < ma_200 * 0.95:
            return "BearMarket"
        if ret_21 > 0.03 and vix_now < 18:
            return "BullMarket"
        if ret_21 > 0.0 and vix_now < vix_ma_30:
            return "RecoveryRegime"
        return "LowVolatility"

    def _regime_confidence(self, prices: pd.DataFrame, regime: str) -> float:
        """Simple confidence: how far are we from the nearest regime boundary?"""
        vix = prices["^VIX"].iloc[-1]
        vol = prices["SPY"].pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)

        if regime == "SystemicStress":
            return min(1.0, (vix - 35) / 15 + 0.6)
        if regime == "HighVolatility":
            return min(1.0, (vol - 0.20) / 0.10 + 0.6)
        if regime == "BullMarket":
            spy = prices["SPY"]
            dist = (spy.iloc[-1] / spy.rolling(200).mean().iloc[-1]) - 1
            return min(1.0, dist / 0.10 + 0.6)
        return 0.65  # default confidence

    # ── Graph query ───────────────────────────────────────────────────────────
    def _query_active_strategies(self, regime: str) -> list[dict]:
        query = f"""
        MATCH (r:Regime {{name: '{regime}'}})<-[:ACTIVATED_BY]-(s:Strategy)
        WHERE s.status = 'active'
        RETURN s.name AS name,
               s.strategy_type AS type,
               s.param_sell_threshold AS sell_threshold,
               s.param_exposure_cut AS exposure_cut,
               s.derived_from AS derived_from
        """
        try:
            results = list(self.db.execute_and_fetch(query))
            logger.debug(f"Graph returned {len(results)} active strategies for {regime}")
            return results
        except Exception as e:
            logger.error(f"Graph query failed: {e}")
            return []
