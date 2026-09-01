"""
Signal Agent
Generates trading signals from active strategies.
Queries graph for formulas, runs quant models, fuses with LLM sentiment.
"""

import os
from typing import Any

import httpx
import numpy as np
import pandas as pd
import yfinance as yf
from arch import arch_model
from common.graph import get_db
from loguru import logger

LLM_URL = os.getenv("GROQ_BASE_URL", os.getenv("FEATHERLESS_BASE_URL", "https://api.groq.com/openai/v1"))
LLM_KEY = os.getenv("GROQ_API_KEY", os.getenv("FEATHERLESS_API_KEY", ""))
LLM_MODEL = os.getenv("GROQ_MODEL", os.getenv("FEATHERLESS_MODEL", "llama-3.3-70b-versatile"))

# xStocks available on Kraken — extend as needed
TICKER_MAP = {
    "SPY":  "SPYXUSD",
    "QQQ":  "QQQXUSD",
    "XLF":  "XLFXUSD",
    "XLE":  "XLEXUSD",
    "BTC":  "XXBTZUSD",
    "ETH":  "XETHZUSD",
}


class SignalAgent:
    def __init__(self):
        self.db = get_db()

    async def run(self, regime: str, active_strategies: list[dict]) -> list[dict]:
        prices = self._fetch_prices(list(TICKER_MAP.keys()))
        signals = []

        for strategy in active_strategies:
            try:
                formula = self._get_strategy_formula(strategy["name"])
                quant   = self._compute_quant_signal(strategy, prices, formula)
                sentiment = await self._get_sentiment(strategy["name"], regime)

                # Weighted fusion: 70% quant, 30% LLM sentiment
                fused_score = 0.70 * quant["score"] + 0.30 * sentiment["score"]

                # Pull CONTRADICTED_BY edges — if contradicted, block signal
                contradictions = self._check_contradictions(strategy["name"])
                if contradictions:
                    logger.warning(f"Strategy {strategy['name']} contradicted by "
                                   f"{contradictions} — blocking")
                    continue

                signal = {
                    "strategy":         strategy["name"],
                    "ticker":           quant["ticker"],
                    "direction":        "sell" if fused_score < -0.2 else
                                        "buy"  if fused_score > 0.2 else "hold",
                    "score":            fused_score,
                    "quant_score":      quant["score"],
                    "sentiment_score":  sentiment["score"],
                    "graph_path":       formula.get("graph_path", []),
                    "regime":           regime,
                }
                if signal["direction"] != "hold":
                    signals.append(signal)

            except Exception as e:
                logger.error(f"Signal error for {strategy['name']}: {e}")

        return signals

    # ── Market data ───────────────────────────────────────────────────────────
    def _fetch_prices(self, tickers: list[str]) -> pd.DataFrame:
        raw = yf.download(tickers, period="2y", auto_adjust=True, progress=False)
        return raw["Close"].dropna()

    # ── Graph: get formula for strategy ──────────────────────────────────────
    def _get_strategy_formula(self, strategy_name: str) -> dict:
        query = f"""
        MATCH (s:Strategy {{name: '{strategy_name}'}})-[:DERIVED_FROM]->(c:Concept)
        OPTIONAL MATCH (c)-[:HAS_FORMULA]->(f:Formula)
        RETURN c.name AS concept, f.id AS formula_id,
               f.expression AS expression, f.params AS params
        LIMIT 5
        """
        results = list(self.db.execute_and_fetch(query))
        if results:
            return {
                "formula_id": results[0].get("formula_id"),
                "expression": results[0].get("expression", ""),
                "params":     results[0].get("params", []),
                "graph_path": [r["concept"] for r in results],
            }
        return {"formula_id": None, "expression": "", "params": [], "graph_path": []}

    # ── Contradiction check ───────────────────────────────────────────────────
    def _check_contradictions(self, strategy_name: str) -> list[str]:
        """Returns names of contradicting active strategies."""
        query = f"""
        MATCH (s:Strategy {{name: '{strategy_name}'}})-[:DERIVED_FROM]->(c:Concept)
        MATCH (c)-[:CONTRADICTED_BY]->(c2:Concept)<-[:DERIVED_FROM]-(s2:Strategy)
        WHERE s2.status = 'active' AND s2.name <> '{strategy_name}'
        RETURN DISTINCT s2.name AS contradicting_strategy
        """
        results = list(self.db.execute_and_fetch(query))
        return [r["contradicting_strategy"] for r in results]

    # ── Quantitative signal ───────────────────────────────────────────────────
    def _compute_quant_signal(self, strategy: dict, prices: pd.DataFrame,
                               formula: dict) -> dict:
        name = strategy["name"]
        ticker = strategy.get("ticker", "SPY")
        sell_threshold = strategy.get("sell_threshold") or 0.35

        if "GARCH" in name or "Vol" in name:
            return self._garch_signal(prices, ticker, sell_threshold)
        if "Bayesian" in name or "BN" in name:
            return self._bn_signal(prices, ticker, sell_threshold)
        if "DYNOTEARS" in name or "Contagion" in name:
            return self._contagion_signal(prices, ticker, sell_threshold)
        if "Climate" in name or "Physical" in name:
            return self._climate_signal(prices, ticker, sell_threshold)
        return self._momentum_signal(prices, ticker, sell_threshold)

    def _garch_signal(self, prices: pd.DataFrame, ticker: str, threshold: float) -> dict:
        asset = prices.get(ticker)
        if asset is None or asset.empty:
            return {"ticker": ticker, "score": 0.0, "reasoning": f"No {ticker} data"}
        rets = np.log(asset).diff().dropna() * 100
        try:
            model = arch_model(rets, vol="Garch", p=1, q=1, dist="t")
            fit   = model.fit(disp="off", show_warning=False)
            cond_vol = fit.conditional_volatility.iloc[-1]
            ann_vol  = cond_vol * np.sqrt(252)
            score    = -min(1.0, (ann_vol - 0.15) / 0.30)
            return {
                "ticker": ticker,
                "score":  score,
                "reasoning": f"GARCH(1,1) annualised vol={ann_vol:.1%}"
            }
        except Exception as e:
            return {"ticker": ticker, "score": 0.0, "reasoning": f"GARCH error: {e}"}

    def _bn_signal(self, prices: pd.DataFrame, ticker: str, threshold: float) -> dict:
        asset = prices.get(ticker)
        if asset is None or asset.empty:
            return {"ticker": ticker, "score": 0.0, "reasoning": f"No {ticker} data"}
        vix_data = yf.download("^VIX", period="1mo", progress=False)["Close"]
        vix_now  = vix_data.iloc[-1] if not vix_data.empty else 20.0
        p_ir_high = min(0.95, 0.30 + vix_now / 100)
        p_sp_low  = 0.626 * p_ir_high
        score     = -(p_sp_low - threshold) / (1 - threshold)
        return {
            "ticker": ticker,
            "score":  float(np.clip(score, -1, 1)),
            "reasoning": f"BN: P({ticker}=low|macro)={p_sp_low:.3f}, threshold={threshold}"
        }

    def _contagion_signal(self, prices: pd.DataFrame, ticker: str, threshold: float) -> dict:
        if ticker == "XLF":
            fin_tickers = ["JPM", "BAC", "GS", "MS", "C"]
            fin_data = yf.download(fin_tickers, period="3mo",
                                   auto_adjust=True, progress=False)["Close"]
            if fin_data.empty:
                return {"ticker": ticker, "score": 0.0, "reasoning": "No data"}
            avg_corr = fin_data.pct_change().corr().values
            np.fill_diagonal(avg_corr, np.nan)
            mean_corr = np.nanmean(avg_corr)
            score = -(mean_corr - 0.5) / 0.5
            return {
                "ticker": ticker,
                "score":  float(np.clip(score, -1, 1)),
                "reasoning": f"DYNOTEARS proxy: mean financial corr={mean_corr:.2f}"
            }
        return self._momentum_signal(prices, ticker, threshold)

    def _climate_signal(self, prices: pd.DataFrame, ticker: str, threshold: float) -> dict:
        if ticker == "XLE":
            data = yf.download(["XLE", "SPY"], period="3mo",
                               auto_adjust=True, progress=False)["Close"]
            if data.empty:
                return {"ticker": ticker, "score": 0.0, "reasoning": "No data"}
            rel_perf = (data["XLE"] / data["SPY"]).pct_change(63).iloc[-1]
            score    = float(np.clip(rel_perf * 5, -1, 1))
            return {
                "ticker": ticker,
                "score":  score,
                "reasoning": f"Climate overlay: XLE vs SPY 3m rel perf={rel_perf:.1%}"
            }
        return self._momentum_signal(prices, ticker, threshold)

    def _momentum_signal(self, prices: pd.DataFrame, ticker: str, threshold: float) -> dict:
        asset = prices.get(ticker)
        if asset is None or asset.empty:
            return {"ticker": ticker, "score": 0.0, "reasoning": f"No {ticker} data"}
        mom_12_1 = asset.pct_change(252).iloc[-1] - asset.pct_change(21).iloc[-1]
        score    = float(np.clip(mom_12_1 * 5, -1, 1))
        return {
            "ticker": ticker,
            "score":  score,
            "reasoning": f"Momentum 12-1 on {ticker}: {mom_12_1:.1%}"
        }

    # ── LLM sentiment (Groq primary, Featherless fallback) ───────────────────
    async def _get_sentiment(self, strategy_name: str, regime: str) -> dict:
        if not LLM_KEY:
            return {"score": 0.0, "reasoning": "LLM key not set"}
        prompt = (
            f"Current market regime: {regime}. "
            f"Active trading strategy: {strategy_name}. "
            "Given current macroeconomic conditions, provide a sentiment score "
            "from -1.0 (strongly bearish, reduce exposure) to +1.0 "
            "(strongly bullish, increase exposure). "
            "Reply with a single float only, no explanation."
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{LLM_URL}/chat/completions",
                    json={
                        "model": LLM_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 8,
                        "temperature": 0.1,
                    },
                    headers={"Authorization": f"Bearer {LLM_KEY}"},
                )
                raw = r.json()["choices"][0]["message"]["content"].strip()
                score = float(raw)
                return {"score": float(np.clip(score, -1, 1)), "reasoning": raw}
        except Exception as e:
            logger.warning(f"LLM sentiment error: {e}")
            return {"score": 0.0, "reasoning": f"error: {e}"}
