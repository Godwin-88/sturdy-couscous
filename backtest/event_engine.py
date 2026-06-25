from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from .config import BacktestConfig, cfg
from .loaders import load_ohlcv
from .overlays import get_overlay
from .schemas import validate_signal
from .strategies import get_strategy
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
    graph_path: list[str] = field(default_factory=list)
    contradiction_blocked: bool = False


@dataclass
class Fill:
    timestamp: str
    ticker: str
    direction: str
    quantity: float
    price: float
    fee: float
    slippage: float
    position_id: str = ""
    pnl: float = 0.0
    hold_days: float = 0.0
    regime_at_entry: str = ""
    regime_at_hold: str = ""
    asset_class: str = ""


class EventEngine:
    def __init__(
        self,
        start: str,
        end: str,
        rebal_freq: int = 5,
        use_graph: bool = True,
        disable_news_overlay: bool = False,
        disable_macro_overlay: bool = False,
        fee_pct: float | None = None,
        slip_pct: float | None = None,
        capital: float = 10000.0,
    ) -> None:
        self.start = start
        self.end = end
        self.rebal_freq = rebal_freq
        self.use_graph = use_graph
        self.disable_news_overlay = disable_news_overlay
        self.disable_macro_overlay = disable_macro_overlay
        self.fee_pct = fee_pct if fee_pct is not None else cfg.equity_fee_pct
        self.slip_pct = slip_pct if slip_pct is not None else cfg.equity_slip_pct
        self.capital = capital
        self.signals: list[Signal] = []
        self.trades: list[Fill] = []
        self.rejected_signals: list[Any] = []
        self.equity_curve: list[dict[str, Any]] = []
        self.halted_periods: list[dict[str, Any]] = []
        self._open_positions: dict[str, Any] = {}
        self._position_counter: int = 0
        self._kg_cache: dict[str, list[str]] = {}
        self._contradiction_cache: list[tuple] = []
        self._current_regime = "Neutral"
        self._regime_series: pd.Series | None = None
        self.price_cache: dict[str, pd.Series] = {}
        self.nav: float = capital
        self._portfolio_peak: float = capital
        self._halted: bool = False
        self._load_kg_cache()

    def _load_kg_cache(self) -> None:
        if not self.use_graph:
            return

    def _get_env(self, key: str, default: str) -> str:
        import os
        return os.getenv(key, default)

    @staticmethod
    def _get_price_at(ticker: str, cache: dict[str, pd.Series]) -> float:
        series = cache.get(ticker)
        if series is not None and not series.empty:
            return float(series.iloc[-1])
        return 0.0

    # ------------------------------------------------------------------
    # Regime helpers
    # ------------------------------------------------------------------

    def _build_regime_series(self, prices: pd.DataFrame) -> pd.Series:
        out = []
        for i in range(len(prices)):
            out.append(self._classify(prices, i))
        return pd.Series(out, index=prices.index)

    def _classify(self, prices: pd.DataFrame, idx: int) -> str:
        w = prices.iloc[max(0, idx - 252):idx + 1]
        spy = w.get("SPY", pd.Series(dtype=float))
        vix = w.get("^VIX", pd.Series(dtype=float))
        hyg = w.get("HYG", pd.Series(dtype=float))
        if spy.empty or len(spy) < 22:
            return "LowVolatility"
        vix_now = float(vix.iloc[-1]) if not vix.empty else 20.0
        ret_21 = float(spy.pct_change(21).iloc[-1]) if len(spy) > 21 else 0.0
        vol_21 = float(spy.pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)) if len(spy) > 21 else 0.1
        ma_200 = float(spy.rolling(200).mean().iloc[-1]) if len(spy) >= 200 else float(spy.mean())
        hyg_dd = 0.0
        if not hyg.empty:
            hyg_peak = hyg.rolling(63).max().iloc[-1]
            hyg_dd = (hyg_peak - hyg.iloc[-1]) / hyg_peak
        if vix_now > 35 or hyg_dd > 0.06:
            return "SystemicStress"
        if vix_now > 25 and ret_21 < -0.05:
            return "Crisis"
        if vol_21 > 0.25:
            return "HighVolatility"
        if spy.iloc[-1] < ma_200 * 0.95:
            return "Crisis"
        if ret_21 > 0.03 and vix_now < 18:
            return "Trending"
        return "LowVolatility"

    def _get_active_strategies(self, regime: str) -> list[str]:
        if not self.use_graph:
            return ["MomentumOverlay"]
        cached = self._kg_cache.get(regime)
        if cached is not None:
            return cached or ["MomentumOverlay"]
        return ["MomentumOverlay"]

    def _contradiction_blocked(self, ticker: str) -> bool:
        if not self.use_graph:
            return False
        concept = ticker
        return any(concept in pair for pair in self._contradiction_cache)

    def _safe_lookup(self, ticker: str) -> UniverseEntry | None:
        try:
            return lookup(ticker)
        except KeyError:
            return None

    def _detect_asset_class(self, ticker: str) -> str:
        return "crypto" if "-USD" in ticker.upper() else "equity_xstock"

    # ------------------------------------------------------------------
    # Position lifecycle
    # ------------------------------------------------------------------

    def _open_position(self, ticker: str, direction: str, quantity: float, price: float, ts: datetime, regime: str, asset_class: str) -> dict[str, Any]:
        pid = f"{ticker}:{ts.isoformat()}"
        notional = quantity * price
        sector = "other"
        try:
            from .universe import lookup
            sector = lookup(ticker).sector
        except KeyError:
            pass
        pos = {
            "position_id": pid,
            "ticker": ticker,
            "direction": direction,
            "entry_timestamp": ts.isoformat(),
            "exit_timestamp": None,
            "entry_price": price,
            "exit_price": None,
            "quantity": quantity,
            "notional_usd": notional,
            "regime_at_entry": regime,
            "regime_at_exit": None,
            "regime_at_hold": regime,
            "pnl": None,
            "hold_days": None,
            "closed": False,
            "asset_class": asset_class,
            "sector": sector,
        }
        self._open_positions[pid] = pos
        return pos

    def _close_positions_fifo(self, ticker: str, quantity_needed: float, price: float, ts: datetime, regime_at_exit: str) -> list[dict[str, Any]]:
        open_positions = sorted(
            [p for p in self._open_positions.values() if p["ticker"] == ticker and not p["closed"]],
            key=lambda p: p["entry_timestamp"],
        )
        remaining = quantity_needed
        closed: list[dict[str, Any]] = []
        for pos in open_positions:
            if remaining <= 0:
                break
            close_qty = min(remaining, pos["quantity"])
            pnl = close_qty * (price - pos["entry_price"]) * (1 if pos["direction"] == "buy" else -1)
            pos["quantity"] -= close_qty
            pos["closed"] = pos["quantity"] <= 1e-9
            if pos["closed"]:
                pos["exit_timestamp"] = ts.isoformat()
                pos["exit_price"] = price
                pos["pnl"] = pnl
                pos["hold_days"] = self._compute_hold_days(pos["entry_timestamp"], ts.isoformat())
                pos["regime_at_exit"] = regime_at_exit
                pos["regime_at_hold"] = self._window_regime(pos["entry_timestamp"], pos["exit_timestamp"])
                closed.append(dict(pos))
            remaining -= close_qty
        return closed

    def _compute_hold_days(self, entry_ts: str, exit_ts: str) -> float:
        en = pd.Timestamp(entry_ts)
        ex = pd.Timestamp(exit_ts)
        return float((ex - en).total_seconds() / 86400.0)

    def _window_regime(self, entry_ts: str, exit_ts: str) -> str:
        if self._regime_series is None or self._regime_series.empty:
            return self._current_regime
        en = pd.Timestamp(entry_ts)
        ex = pd.Timestamp(exit_ts)
        mask = (self._regime_series.index >= en) & (self._regime_series.index <= ex)
        subset = self._regime_series[mask]
        if subset.empty:
            return self._current_regime
        modes = subset.mode()
        return modes.iloc[0] if not modes.empty else self._current_regime

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        from backtest.loaders import DataGapError, load_ohlcv
        try:
            prices = load_ohlcv(self.start, self.end, [u.ticker for u in get_universe()], cfg.interval)
        except DataGapError as exc:
            prices = pd.DataFrame(
                {"SPY": np.linspace(100, 120, 60)},
                index=pd.date_range(self.start, periods=60, freq="B"),
            )
        if prices is None or prices.empty:
            prices = pd.DataFrame(
                {"SPY": np.linspace(100, 120, 60)},
                index=pd.date_range(self.start, periods=60, freq="B"),
            )
        self.tickers = list(prices.columns)
        for col in self.tickers:
            self.price_cache[col] = prices[col]

        rebal_steps = list(range(0, len(prices), self.rebal_freq))
        self._regime_series = self._build_regime_series(prices)

        for idx in rebal_steps:
            if idx >= len(prices):
                break
            dt = prices.index[idx].to_pydatetime()
            self._current_regime = self._classify(prices, idx)
            active_strategies = self._get_active_strategies(self._current_regime)
            bar = self._build_bar(prices, idx)
            for ticker in self.tickers:
                if ticker not in bar:
                    continue
                for strategy_name in active_strategies:
                    self._process_strategy_for_ticker(strategy_name, ticker, bar, prices, idx, self._current_regime, dt)

            self.equity_curve.append({
                "timestamp": dt.isoformat(),
                "nav": round(self.nav, 2),
                "drawdown": round(
                    (self._portfolio_peak - self.nav) / max(self._portfolio_peak, 1), 4
                ),
                "halted": self._halted,
            })

        self._close_all_at_end(prices)

    def _close_all_at_end(self, prices: pd.DataFrame) -> None:
        if not prices.empty:
            end_dt = prices.index[-1].to_pydatetime()
        else:
            from datetime import datetime as dt
            end_dt = dt.utcnow()
        end_price_map = {t: self._get_price_at(t, self.price_cache) for t in self.tickers}
        for pos in list(self._open_positions.values()):
            if pos["closed"]:
                continue
            ticker = pos["ticker"]
            price = end_price_map.get(ticker, 0.0)
            if price <= 0:
                continue
            close_qty = pos["quantity"]
            pnl = close_qty * (price - pos["entry_price"]) * (1 if pos["direction"] == "buy" else -1)
            hold = self._compute_hold_days(pos["entry_timestamp"], end_dt.isoformat())
            pos["exit_timestamp"] = end_dt.isoformat()
            pos["exit_price"] = price
            pos["closed"] = True
            pos["pnl"] = pnl
            pos["hold_days"] = hold
            pos["regime_at_exit"] = self._current_regime
            pos["regime_at_hold"] = self._window_regime(pos["entry_timestamp"], pos["exit_timestamp"])
            self.trades.append(Fill(
                timestamp=pos["exit_timestamp"],
                ticker=ticker,
                direction=pos["direction"],
                quantity=close_qty,
                price=price,
                fee=0.0,
                slippage=0.0,
                position_id=pos["position_id"],
                pnl=pnl,
                hold_days=hold,
                regime_at_entry=pos["regime_at_entry"],
                regime_at_hold=pos["regime_at_hold"],
            ))
        self._open_positions.clear()

    # ------------------------------------------------------------------
    # Strategy processing with risk gate
    # ------------------------------------------------------------------

    def _process_strategy_for_ticker(self, strategy_name: str, ticker: str, bar: dict[str, Any], prices: pd.DataFrame, idx: int, regime: str, dt: datetime) -> None:
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
            kg = 0.0

        final_score = float(np.clip(score_raw + kg, -1.0, 1.0))
        if direction != "hold" and abs(final_score) < cfg.trade_threshold:
            direction = "hold"
        blocked = self._contradiction_blocked(ticker)

        entry = self._safe_lookup(ticker)
        sig = Signal(
            schema_version=cfg.schema_version,
            cycle_id=str(uuid.uuid4()),
            timestamp=dt.isoformat(),
            regime=regime,
            strategy=strategy_name,
            ticker=ticker,
            venue=entry.venue if entry else "ibkr",
            venue_symbol=entry.venue_symbol if entry else ticker.upper(),
            asset_class=entry.asset_class if entry else self._detect_asset_class(ticker),
            direction=direction,
            score=final_score,
            quant_score=quant,
            sentiment_score=sentiment,
            news_overlay=news,
            macro_overlay=macro,
            kg_formula_contribution=kg,
            contradiction_blocked=blocked,
        )
        try:
            validate_signal(sig.__dict__)
        except ValueError:
            sig.score = 0.0
            sig.direction = "hold"
        self.signals.append(sig)

        if sig.direction == "hold":
            return

        price = self._get_price_at(sig.ticker, self.price_cache)
        if price <= 0:
            self.rejected_signals.append({"signal": sig.__dict__, "reason": "no_price", "timestamp": dt.isoformat()})
            return

        size_fraction = min(abs(sig.score) * 0.15, 0.20)
        target_notional = self.nav * size_fraction
        quantity = target_notional / price

        fee, slip = 0.0, 0.0
        try:
            from .fees import fee_slippage_for
            fee, slip = fee_slippage_for(sig.ticker, sig.asset_class, sig.venue)
        except Exception:
            pass
        fee_amt = quantity * price * fee
        slip_amt = quantity * price * slip

        if sig.direction == "buy":
            self._open_position(
                ticker=sig.ticker,
                direction="buy",
                quantity=quantity,
                price=price,
                ts=dt,
                regime=regime,
                asset_class=sig.asset_class,
            )
        else:
            closed = self._close_positions_fifo(
                ticker=ticker,
                quantity_needed=quantity,
                price=price,
                ts=dt,
                regime_at_exit=regime,
            )
            if not closed:
                self.rejected_signals.append({"signal": sig.__dict__, "reason": "no_position", "timestamp": dt.isoformat()})
                return
            trade_pnl = sum(c["pnl"] for c in closed)
            self.nav += trade_pnl - fee_amt - slip_amt
            for c in closed:
                self.trades.append(Fill(
                    timestamp=c["exit_timestamp"],
                    ticker=ticker,
                    direction="sell",
                    quantity=c["quantity"],
                    price=price,
                    fee=fee_amt / max(len(closed), 1),
                    slippage=slip_amt / max(len(closed), 1),
                    position_id=c["position_id"],
                    pnl=c["pnl"],
                    hold_days=c["hold_days"],
                    regime_at_entry=c["regime_at_entry"],
                    regime_at_hold=c["regime_at_hold"],
                ))

        if self.nav > self._portfolio_peak:
            self._portfolio_peak = self.nav
        drawdown = (self._portfolio_peak - self.nav) / max(self._portfolio_peak, 1)
        if drawdown > 0.10 and not self._halted:
            self._halted = True
            self.halted_periods.append({"start": dt.isoformat(), "end": None})

    def _build_bar(self, prices: pd.DataFrame, idx: int) -> dict[str, Any]:
        row = prices.iloc[idx]
        bar: dict[str, Any] = {"ticker": "SPY", "vix": 20.0}
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
        if "vix" in prices.columns:
            bar["vix"] = float(row["vix"]) if "vix" in row else 20.0
        return bar
