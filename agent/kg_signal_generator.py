"""
KG Signal Generator — evaluates Formula node expressions from the Knowledge Graph
using live price/indicator data, then emits scored trading signals.

The KG stores Formula nodes like:
  {id: "momentum_12_1", name: "12-1 Momentum", expression: "(P_t - P_t-252) / P_t-252",
   output: "momentum_score"}

This agent:
1. Queries all active Formula nodes (via ACTIVATED_BY edges from live regime)
2. Fetches the required price history for each formula's ticker set
3. Evaluates expressions symbolically / numerically
4. Returns raw scored signals that get merged into the SignalAgent output
"""

import os
import re
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import yfinance as yf
from common.graph import get_db
from loguru import logger

# ── Symbolic expression evaluator ────────────────────────────────────────────
# Supported tokens in Formula.expression strings:
#   P_t           → current close price
#   P_t-N         → close N trading days ago
#   VOL_N         → N-day realised volatility (annualised)
#   SMA_N         → N-day simple moving average
#   EMA_N         → N-day exponential moving average
#   RSI_N         → N-day RSI
#   ATR_N         → N-day average true range
#   (arithmetic)  → standard +, -, *, /

# Lookback needed per formula type
LOOKBACK_DAYS = 504   # ~2 years of daily bars


def _safe_divide(a: float, b: float) -> float:
    return a / b if abs(b) > 1e-10 else 0.0


def _compute_features(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> dict[str, float]:
    """Compute all possible formula primitives from price arrays."""
    n   = len(closes)
    out: dict[str, float] = {}

    out["P_t"] = float(closes[-1])

    # P_t-N
    for lag in [1, 5, 10, 21, 63, 126, 252]:
        if n > lag:
            out[f"P_t-{lag}"] = float(closes[-(lag + 1)])

    # Volatility
    if n >= 21:
        rets = np.diff(np.log(closes[-22:]))
        out["VOL_21"] = float(np.std(rets) * np.sqrt(252))
    if n >= 63:
        rets = np.diff(np.log(closes[-64:]))
        out["VOL_63"] = float(np.std(rets) * np.sqrt(252))

    # SMA
    for period in [10, 20, 50, 100, 200]:
        if n >= period:
            out[f"SMA_{period}"] = float(np.mean(closes[-period:]))

    # EMA (pandas-style)
    for period in [12, 26, 50]:
        if n >= period:
            alpha = 2.0 / (period + 1)
            ema   = closes[0]
            for p in closes:
                ema = alpha * p + (1 - alpha) * ema
            out[f"EMA_{period}"] = float(ema)

    # RSI
    for period in [14, 21]:
        if n > period + 1:
            deltas = np.diff(closes[-(period + 2):])
            gain   = np.mean(np.maximum(deltas, 0))
            loss   = np.mean(np.maximum(-deltas, 0))
            rs     = gain / loss if loss > 1e-10 else 100.0
            out[f"RSI_{period}"] = float(100 - 100 / (1 + rs))

    # ATR
    if n >= 15 and len(highs) >= 15 and len(lows) >= 15:
        h, l, c = highs[-15:], lows[-15:], closes[-15:]
        prev_c  = closes[-16:-1] if n >= 16 else c[:-1]
        tr      = np.maximum(h[1:] - l[1:],
                  np.maximum(np.abs(h[1:] - prev_c),
                             np.abs(l[1:] - prev_c)))
        out["ATR_14"] = float(np.mean(tr))

    return out


def _evaluate_expression(expr: str, features: dict[str, float]) -> float | None:
    """
    Evaluate a simple arithmetic expression using the feature dict.
    Returns None if the expression cannot be evaluated.
    """
    # Sort by length descending so longer token names are substituted first
    tokens = sorted(features.keys(), key=len, reverse=True)
    safe_expr = expr
    for token in tokens:
        safe_expr = safe_expr.replace(token, str(features[token]))

    # Only allow safe characters
    if not re.match(r"^[\d\s\.\+\-\*/\(\)]+$", safe_expr):
        return None

    try:
        result = eval(safe_expr, {"__builtins__": {}})  # noqa: S307
        return float(result) if np.isfinite(float(result)) else None
    except Exception:
        return None


def _normalise_score(raw: float | None, low: float = -3.0, high: float = 3.0) -> float:
    """Clip and normalise raw formula output to [-1, 1]."""
    if raw is None:
        return 0.0
    return float(np.clip(raw / max(abs(high), abs(low), 1.0), -1.0, 1.0))


class KGSignalGenerator:
    def __init__(self):
        self.db = get_db()
        self._price_cache: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

    async def run(self, regime: str, tickers: list[str]) -> list[dict[str, Any]]:
        """
        Evaluate all active Formula nodes for the current regime.
        Returns a list of signal dicts compatible with SignalAgent output.
        """
        formulas = self._fetch_active_formulas(regime)
        if not formulas:
            logger.debug("KGSignalGenerator: no active formulas for regime=%s", regime)
            return []

        signals: list[dict] = []
        price_data = self._fetch_prices(tickers)

        for formula in formulas:
            for ticker in tickers:
                if ticker not in price_data:
                    continue
                closes, highs, lows = price_data[ticker]
                features  = _compute_features(closes, highs, lows)
                raw_score = _evaluate_expression(formula["expression"], features)
                norm      = _normalise_score(raw_score)

                if abs(norm) < 0.15:    # dead-band: ignore weak signals
                    continue

                signals.append({
                    "strategy":     f"kg_{formula['formula_id']}",
                    "ticker":       ticker,
                    "direction":    "long" if norm > 0 else "short",
                    "signal_score": round(norm, 3),
                    "regime":       regime,
                    "source":       "KGFormula",
                    "formula_name": formula.get("name", formula["formula_id"]),
                })

        logger.info(f"KGSignalGenerator: {len(formulas)} formulas × "
                    f"{len(tickers)} tickers → {len(signals)} signals")
        return signals

    def _fetch_active_formulas(self, regime: str) -> list[dict]:
        """Query KG for Formula nodes active in the current regime."""
        try:
            rows = list(self.db.execute_and_fetch(f"""
            MATCH (r:Regime {{name: '{regime}'}})<-[:ACTIVATED_BY]-(s:Strategy)
                  -[:HAS_FORMULA]->(f:Formula)
            RETURN f.id AS formula_id, f.name AS name, f.expression AS expression
            LIMIT 50
            """))
            return [dict(r) for r in rows if r.get("expression")]
        except Exception as e:
            logger.debug(f"KG formula query failed: {e}")
            # Fallback: query all formulas without regime filter
            try:
                rows = list(self.db.execute_and_fetch("""
                MATCH (f:Formula)
                WHERE f.expression IS NOT NULL
                RETURN f.id AS formula_id, f.name AS name, f.expression AS expression
                LIMIT 20
                """))
                return [dict(r) for r in rows if r.get("expression")]
            except Exception:
                return []

    def _fetch_prices(
        self, tickers: list[str]
    ) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """Fetch OHLC bars for all tickers. Returns {ticker: (closes, highs, lows)}."""
        end   = datetime.utcnow()
        start = end - timedelta(days=LOOKBACK_DAYS)
        out:  dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

        for ticker in tickers:
            if ticker in self._price_cache:
                out[ticker] = self._price_cache[ticker]
                continue
            try:
                df = yf.download(
                    ticker, start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    progress=False, auto_adjust=True,
                )
                if df.empty or len(df) < 30:
                    continue
                closes = df["Close"].values.astype(float)
                highs  = df["High"].values.astype(float)
                lows   = df["Low"].values.astype(float)
                self._price_cache[ticker] = (closes, highs, lows)
                out[ticker] = (closes, highs, lows)
            except Exception as e:
                logger.debug(f"Price fetch failed for {ticker}: {e}")

        return out
