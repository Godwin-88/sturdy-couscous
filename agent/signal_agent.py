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
from alpaca_data import provider
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
        try:
            prices = self._fetch_prices(list(TICKER_MAP.keys()))
        except Exception as e:
            logger.warning(f"SignalAgent price fetch failed: {e}")
            prices = pd.DataFrame()
        if prices.empty:
            logger.warning("SignalAgent: no price data — no signals this cycle")
            return []
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
        return provider.get_close_series_many(tickers, days=500)

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
        signal_method = str(strategy.get("signal_method", "")).lower()

        # New dispatch contract: route on the graph signal_method (single source
        # of truth in Neo4j). Legacy name-based fallback kept for robustness.
        if signal_method == "momentum":
            return self._momentum_signal(prices, ticker, sell_threshold)
        if signal_method == "vol_zscore":
            return self._vol_zscore_signal(prices, ticker, sell_threshold)
        if signal_method == "value_mr":
            return self._value_mr_signal(prices, ticker, sell_threshold)
        if signal_method == "crisis_hedge":
            return self._crisis_hedge_signal(prices, ticker, sell_threshold)
        if signal_method == "contagion":
            return self._contagion_signal(prices, ticker, sell_threshold)
        if signal_method == "bn_macro":
            return self._bn_signal(prices, ticker, sell_threshold)
        if signal_method == "climate":
            return self._climate_signal(prices, ticker, sell_threshold)
        if signal_method == "garch_vol":
            return self._garch_signal(prices, ticker, sell_threshold)

        # Legacy name-based fallback (pre-migration nodes / unknown methods)
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
        vix_series = provider.get_vix_proxy(days=60)
        vix_now = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0
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
            fin_data = provider.get_close_series_many(fin_tickers, days=90)
            if fin_data.empty or len(fin_data.columns) < 2:
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
            data = provider.get_close_series_many(["XLE", "SPY"], days=90)
            if data.empty or "XLE" not in data.columns or "SPY" not in data.columns:
                return {"ticker": ticker, "score": 0.0, "reasoning": "No data"}
            rel_perf = (data["XLE"] / data["SPY"]).pct_change(63).iloc[-1]
            score    = float(np.clip(rel_perf * 5, -1, 1))
            return {
                "ticker": ticker,
                "score":  score,
                "reasoning": f"Climate overlay: XLE vs SPY 3m rel perf={rel_perf:.1%}"
            }
        return self._momentum_signal(prices, ticker, threshold)

    def _vol_zscore_signal(self, prices: pd.DataFrame, ticker: str, threshold: float) -> dict:
        """Vol mean-reversion: z-score of short vol vs 130d long vol.
        Elevated vol z -> negative score (de-risk); compressed -> positive."""
        asset = prices.get(ticker)
        if asset is None or asset.empty:
            return {"ticker": ticker, "score": 0.0, "reasoning": f"No {ticker} data"}
        rets = asset.pct_change().dropna()
        if len(rets) < 130:
            return {"ticker": ticker, "score": 0.0, "reasoning": "insufficient data"}
        short_vol = rets.rolling(10).std() * np.sqrt(252)
        long_vol = rets.rolling(130).std() * np.sqrt(252)
        if long_vol.std() < 1e-12:
            return {"ticker": ticker, "score": 0.0, "reasoning": "flat vol history"}
        z = (short_vol.iloc[-1] - long_vol.iloc[-1]) / long_vol.std()
        score = float(np.clip(-z / 2.0, -1, 1))
        return {
            "ticker": ticker,
            "score": score,
            "reasoning": f"Vol z-score {z:.2f} on {ticker} (10d vs 130d)",
        }

    def _value_mr_signal(self, prices: pd.DataFrame, ticker: str, threshold: float) -> dict:
        """Value/mean-reversion: distance from 200d MA, gated by VR(21)<1 so we
        only fade when the tape actually mean-reverts (REF variance-ratio rule)."""
        asset = prices.get(ticker)
        if asset is None or asset.empty:
            return {"ticker": ticker, "score": 0.0, "reasoning": f"No {ticker} data"}
        closes = asset.dropna()
        if len(closes) < 220:
            return {"ticker": ticker, "score": 0.0, "reasoning": "insufficient data"}
        ma200 = closes.rolling(200).mean().iloc[-1]
        if np.isnan(ma200) or ma200 <= 0:
            return {"ticker": ticker, "score": 0.0, "reasoning": "no 200d MA"}
        dist = closes.iloc[-1] / ma200 - 1.0
        logc = np.log(closes.replace(0.0, np.nan).dropna())
        r1 = logc.diff().iloc[-105:]
        rk = logc.diff(21).iloc[-105:]
        var1 = float(r1.var())
        vr = float(rk.var() / (21 * var1)) if var1 > 1e-12 else 1.0
        if vr >= 0.9:
            return {"ticker": ticker, "score": 0.0,
                    "reasoning": f"VR={vr:.2f}>=0.9 (not mean-reverting) — skip MR"}
        score = float(np.clip(-dist / 0.10, -1, 1))
        return {
            "ticker": ticker,
            "score": score,
            "reasoning": f"Value MR on {ticker}: dist-from-200MA={dist:.1%}, VR={vr:.2f}",
        }

    def _crisis_hedge_signal(self, prices: pd.DataFrame, ticker: str, threshold: float) -> dict:
        """Crisis hedge (GLD): gold relative strength vs SPY, amplified when
        equity is falling (the whole point — long gold as portfolio insurance)."""
        if ticker != "GLD":
            return self._momentum_signal(prices, ticker, threshold)
        data = provider.get_close_series_many(["GLD", "SPY"], days=130)
        if data.empty or "GLD" not in data.columns or "SPY" not in data.columns:
            return {"ticker": ticker, "score": 0.0, "reasoning": "No data"}
        gld = data["GLD"].dropna()
        spy = data["SPY"].dropna()
        if len(gld) < 64 or len(spy) < 64:
            return {"ticker": ticker, "score": 0.0, "reasoning": "insufficient data"}
        gld_ret_63 = gld.iloc[-1] / gld.iloc[-64] - 1.0
        spy_ret_63 = spy.iloc[-1] / spy.iloc[-64] - 1.0
        rel = gld_ret_63 - spy_ret_63
        spy_dn = -min(spy_ret_63, 0.0)
        score = float(np.clip(rel * 3 + spy_dn * 3, -1, 1))
        return {
            "ticker": ticker,
            "score": score,
            "reasoning": f"Crisis hedge GLD: 3m GLD={gld_ret_63:.1%} vs SPY={spy_ret_63:.1%}",
        }

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
                payload = r.json()
                choices = payload.get("choices") if isinstance(payload, dict) else None
                if not choices:
                    msg = payload.get("error", {}).get("message") if isinstance(payload, dict) else ""
                    raise ValueError(f"no choices in LLM response: {msg or payload}")
                raw = choices[0]["message"]["content"].strip()
                score = float(raw)
                return {"score": float(np.clip(score, -1, 1)), "reasoning": raw}
        except Exception as e:
            logger.warning(f"LLM sentiment error: {e}")
            return {"score": 0.0, "reasoning": f"error: {e}"}
