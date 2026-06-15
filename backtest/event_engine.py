from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import BacktestConfig, cfg
from .loaders import load_ohlcv
from .overlays import get_overlay
from .schemas import validate_signal
from .strategies import get_strategy, Strategy
from .universe import get_universe, lookup


@dataclass
class Signal:
    schema_version: int
    cycle_id: str
    timestamp: str
    regime: str
    strategy: str
    ticker: str
    venue: str
    venue_symbol: str
    asset_class: str
    direction: str
    score: float
    quant_score: float
    sentiment_score: float
    news_overlay: float
    macro_overlay: float
    kg_formula_contribution: float
    graph_path: List[str]
    contradiction_blocked: bool


@dataclass
class Fill:
    timestamp: str
    ticker: str
    direction: str
    quantity: float
    price: float
    fee: float
    slippage: float


class EventEngine:
    def __init__(
        self,
        start: str,
        end: str,
        rebal_freq: int = 5,
        use_graph: bool = True,
        disable_news_overlay: bool = False,
        disable_macro_overlay: bool = False,
        fee_pct: Optional[float] = None,
        slip_pct: Optional[float] = None,
    ) -> None:
        self.start = start
        self.end = end
        self.rebal_freq = rebal_freq
        self.use_graph = use_graph
        self.disable_news_overlay = disable_news_overlay
        self.disable_macro_overlay = disable_macro_overlay
        self.fee_pct = fee_pct if fee_pct is not None else cfg.equity_fee_pct
        self.slip_pct = slip_pct if slip_pct is not None else cfg.equity_slip_pct
        self.universe = get_universe()
        self.tickers = [u.ticker for u in self.universe]
        self._ticker_map = {u.ticker: u for u in self.universe}
        self.signals: List[Signal] = []
        self.trades: List[Fill] = []
        self._kg_cache: Dict[str, List[str]] = {}
        self._contradiction_cache: List[tuple] = []
        self._load_kg_cache()

    def _load_kg_cache(self) -> None:
        if not self.use_graph:
            return
        try:
            from gqlalchemy import Memgraph

            db = Memgraph(host=cfg.memgraph_host, port=cfg.memgraph_port)
            try:
                res = db.execute_and_fetch(
                    "MATCH (r:Regime)<-[:ACTIVATED_BY]-(s:Strategy) "
                    "WHERE s.status='active' RETURN r.name AS regime, collect(s.name) AS strats"
                )
                for row in res:
                    self._kg_cache[row["regime"]] = list(row["strats"])
            except Exception:
                pass
            try:
                res2 = db.execute_and_fetch(
                    "MATCH (c1:Concept)-[:CONTRADICTED_BY]-(c2:Concept) RETURN c1.name AS a, c2.name AS b"
                )
                for row in res2:
                    self._contradiction_cache.append(tuple(sorted((row["a"], row["b"]))))
            except Exception:
                pass
        except Exception:
            self.use_graph = False

    def run(self) -> None:
        prices = load_ohlcv(self.start, self.end, self.tickers, cfg.interval)
        rebal_steps = range(0, len(prices), self.rebal_freq)
        for idx in rebal_steps:
            if idx >= len(prices):
                break
            dt = prices.index[idx].to_pydatetime()
            regime = self._classify(prices, idx)
            active_strategies = self._get_active_strategies(regime)
            bar = self._build_bar(prices, idx)
            for strategy_name in active_strategies:
                self._process_strategy(strategy_name, bar, prices, idx, regime, dt)

    def _process_strategy(self, strategy_name: str, bar: Dict[str, Any], prices: pd.DataFrame, idx: int, regime: str, dt: datetime) -> None:
        ticker = self._strategy_ticker(strategy_name, bar)
        if ticker not in self._ticker_map:
            return
        u = self._ticker_map[ticker]
        try:
            strategy = get_strategy(strategy_name)
        except KeyError:
            return
        raw = strategy.generate_signal(bar, {})
        quant = float(np.clip(raw.get("quant_score", 0.0), -1.0, 1.0))
        sentiment = float(np.clip(raw.get("sentiment_score", 0.0), -1.0, 1.0))
        score_raw = cfg.quant_weight * quant + cfg.sentiment_weight * sentiment
        score_raw = float(np.clip(score_raw, -1.0, 1.0))

        news = get_overlay("news", ticker, dt, self.disable_news_overlay)
        macro = get_overlay("macro", ticker, dt, self.disable_macro_overlay)
        score_raw = float(np.clip(score_raw + news + macro, -1.0, 1.0))

        if abs(score_raw) < cfg.trade_threshold:
            direction = "hold"
        elif score_raw > 0:
            direction = "buy"
        else:
            direction = "sell"

        kg = 0.0
        if self.use_graph:
            kg = self._evaluate_kg(ticker, bar, dt)

        final_score = float(np.clip(score_raw + kg, -1.0, 1.0))
        if direction != "hold" and abs(final_score) < cfg.trade_threshold:
            direction = "hold"
        blocked = self._contradiction_blocked(ticker)
        sig = Signal(
            schema_version=cfg.schema_version,
            cycle_id=str(uuid.uuid4()),
            timestamp=dt.isoformat(),
            regime=regime,
            strategy=strategy_name,
            ticker=ticker,
            venue=u.venue,
            venue_symbol=u.venue_symbol,
            asset_class=u.asset_class,
            direction=direction,
            score=final_score,
            quant_score=quant,
            sentiment_score=sentiment,
            news_overlay=news,
            macro_overlay=macro,
            kg_formula_contribution=kg,
            graph_path=[],
            contradiction_blocked=blocked,
        )
        try:
            validate_signal(sig.__dict__)
        except ValueError:
            sig.score = 0.0
            sig.direction = "hold"
        self.signals.append(sig)

    def _evaluate_kg(self, ticker: str, bar: Dict[str, Any], dt: datetime) -> float:
        return 0.0

    def _contradiction_blocked(self, ticker: str) -> bool:
        if not self.use_graph:
            return False
        u = self._ticker_map.get(ticker)
        if u is None:
            return False
        concept = u.ticker
        return any(concept in pair for pair in self._contradiction_cache)

    def _classify(self, prices: pd.DataFrame, idx: int) -> str:
        w = prices.iloc[max(0, idx - 252):idx + 1]
        spy = w.get("SPY", pd.Series(dtype=float))
        vix = w.get("^VIX", pd.Series(dtype=float))
        if spy.empty or len(spy) < 22:
            return "LowVolatility"
        vix_now = float(vix.iloc[-1]) if not vix.empty else 20.0
        ret_21 = float(spy.pct_change(21).iloc[-1]) if len(spy) > 21 else 0.0
        vol_21 = float(spy.pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)) if len(spy) > 21 else 0.1
        ma_200 = float(spy.rolling(200).mean().iloc[-1]) if len(spy) >= 200 else float(spy.mean())
        if vix_now > 35:
            return "SystemicStress"
        if vix_now > 25 and ret_21 < -0.05:
            return "Crisis"
        if vol_21 > 0.25:
            return "HighVolatility"
        if spy.iloc[-1] < ma_200 * 0.95:
            return "BearMarket"
        if ret_21 > 0.03 and vix_now < 18:
            return "Trending"
        return "LowVolatility"

    def _get_active_strategies(self, regime: str) -> List[str]:
        if not self.use_graph:
            return ["MomentumOverlay"]
        cached = self._kg_cache.get(regime)
        if cached is not None:
            return cached or ["MomentumOverlay"]
        return ["MomentumOverlay"]

    def _strategy_ticker(self, strategy_name: str, bar: Dict[str, Any]) -> str:
        if strategy_name == "CrisisAlpha":
            return "SPY"
        for ticker in self.tickers:
            if ticker in bar:
                return ticker
        return "SPY"

    def _build_bar(self, prices: pd.DataFrame, idx: int) -> Dict[str, Any]:
        row = prices.iloc[idx]
        bar: Dict[str, Any] = {"ticker": "SPY"}
        for ticker in self.tickers:
            if ticker not in prices.columns:
                continue
            s = prices[ticker]
            start = max(0, idx - 252)
            w = s.iloc[start:idx + 1]
            bar[ticker] = {
                "close": float(row[ticker]),
                "return_21": float(w.pct_change(21).iloc[-1]) if len(w) > 21 else 0.0,
                "vol_21": float(w.pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)) if len(w) > 21 else np.nan,
                "ma21": float(w.rolling(21).mean().iloc[-1]) if len(w) >= 21 else np.nan,
                "ma50": float(w.rolling(50).mean().iloc[-1]) if len(w) >= 50 else np.nan,
                "ma200": float(w.rolling(200).mean().iloc[-1]) if len(w) >= 200 else np.nan,
                "annual_vol": float(w.pct_change().std() * np.sqrt(252)) if len(w) > 1 else np.nan,
            }
        bar["vix"] = float(row.get("^VIX", 20.0)) if "^VIX" in prices.columns else 20.0
        return bar
