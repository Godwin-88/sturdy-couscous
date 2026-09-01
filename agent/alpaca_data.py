"""
Alpaca Market Data Provider — GraphAlpha perception layer (T1/T8).

Single market-data source for the live agent loop. Wraps alpaca-py historical
data clients (stock + crypto), returns pandas Series/DataFrames drop-in for
the yfinance paths they replace.

Rules:
  * Equities SPY/QQQ/XLF/XLE/GLD/TLT/HYG (+ JPM/BAC/GS/MS/C) -> stock client.
  * Crypto "BTC"/"BTC-USD"/"ETH"/"ETH-USD" -> "BTC/USD","ETH/USD" crypto client.
  * ^VIX / ^TNX are NOT on the Alpaca IEX feed. RegimeAgent + Bayesian signal
    use a realized-volatility VIX proxy from SPY (realized_vix_proxy) — a
    deliberate, documented calibration change vs yfinance.

Fallback chain: alpaca-py configured AND ALPACA_MARKET_DATA=1 -> yfinance ->
empty. Never raises out into the agent loop.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from loguru import logger

try:
    from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    _ALPACA_AVAILABLE = True
except ImportError:
    _ALPACA_AVAILABLE = False

CRYPTO_MAP = {"BTC": "BTC/USD", "BTC-USD": "BTC/USD",
              "ETH": "ETH/USD", "ETH-USD": "ETH/USD"}
EQUITY_SYMBOLS = {"SPY", "QQQ", "XLF", "XLE", "GLD", "TLT", "HYG", "IWM",
                  "ITA", "JPM", "BAC", "GS", "MS", "C"}

DATA_CACHE_TTL_SECONDS = float(os.getenv("ALPACA_DATA_CACHE_TTL", 240))


def _normalize_index(df):
    """Daily bars arrive tz-aware UTC; normalise to naive dates and dedupe."""
    if df.empty:
        return df
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df = df.tz_localize(None)
    df = df[~df.index.duplicated(keep="last")]
    return df.sort_index()


def realized_vix_proxy(spy_close, mult=None):
    """VIX proxy: annualised 21d realized vol of SPY * MULT (default 1.5)."""
    mult = mult if mult is not None else float(os.getenv("REGIME_VIX_PROXY_MULT", 1.5))
    spy = spy_close.dropna()
    if spy is None or len(spy) < 25:
        return pd.Series(dtype=float)
    rv = spy.pct_change().rolling(21, min_periods=21).std() * np.sqrt(252) * 100
    return (rv * mult).dropna()


class AlpacaDataProvider:
    def __init__(self):
        self.key_id = os.getenv("ALPACA_API_KEY_ID", "")
        self.secret_key = os.getenv("ALPACA_API_SECRET_KEY", "")
        self.data_url = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")
        self._stock_client = None
        self._crypto_client = None
        self._cache = {}

    def is_configured(self):
        # Treat placeholder "your_..." values as NOT configured so the demo
        # (and any env without real keys) never makes bogus 401 round-trips.
        if self.key_id.startswith("your_") or self.secret_key.startswith("your_"):
            return False
        return bool(self.key_id and self.secret_key and _ALPACA_AVAILABLE)

    def is_enabled(self):
        return self.is_configured() and (
            os.getenv("ALPACA_MARKET_DATA", "0").lower() in ("1", "true", "yes"))

    def source_name(self):
        return "alpaca" if self.is_enabled() else "yfinance"

    @property
    def stock_client(self):
        if self._stock_client is None and self.is_configured():
            self._stock_client = StockHistoricalDataClient(
                api_key=self.key_id, secret_key=self.secret_key)
        return self._stock_client

    @property
    def crypto_client(self):
        if self._crypto_client is None and self.is_configured():
            self._crypto_client = CryptoHistoricalDataClient(
                api_key=self.key_id, secret_key=self.secret_key)
        return self._crypto_client

    def resolve_symbol(self, symbol):
        if symbol in CRYPTO_MAP:
            return "crypto", CRYPTO_MAP[symbol]
        return "stock", symbol

    @staticmethod
    @staticmethod
    def _barset_to_frame(resp, symbol):
        """Convert an alpaca-py BarSet response into an OHLCV DataFrame.

        BarSet exposes a canonical `.df` DataFrame with MultiIndex (symbol, timestamp)
        (preferred) AND pydantic dict-style `resp["SYM"]` (list of bar dicts).
        Plain `sym in resp` (contains) is NOT implemented on BarSet.
        """
        df = getattr(resp, "df", None)
        if isinstance(df, pd.DataFrame) and not df.empty:
            if symbol in df.index.get_level_values(0):
                df = df.xs(symbol, level=0)
            df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                     "close": "Close", "volume": "Volume"})
            keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
            if keep:
                return _normalize_index(df[keep])
        try:
            bars = resp[symbol]
        except (KeyError, TypeError):
            return None
        if not bars:
            return None
        rows = [{"Open": float(b["open"]), "High": float(b["high"]), "Low": float(b["low"]),
                 "Close": float(b["close"]), "Volume": float(b["volume"])} for b in bars]
        index = [b["timestamp"] for b in bars]
        return _normalize_index(pd.DataFrame(rows, index=index))
    def get_close_series(self, symbol, days=400):
        df = self.get_ohlcv(symbol, days)
        if df.empty:
            return pd.Series(dtype=float)
        return df["Close"].rename(symbol)

    def get_ohlcv(self, symbol, days=400):
        if self.is_enabled():
            df = self._fetch_alpaca(symbol, days)
            if df is not None:
                return df
            logger.debug(f"Alpaca empty for {symbol} — yfinance fallback")
        return self._fetch_yfinance(symbol, days)

    def get_close_series_many(self, symbols, days=400):
        frames = {}
        for sym in symbols:
            try:
                s = self.get_close_series(sym, days)
                if not s.empty:
                    frames[sym] = s
            except Exception as e:
                logger.debug(f"get_close_series({sym}) failed: {e}")
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, axis=1).sort_index()

    def get_vix_proxy(self, days=90, mult=None):
        spy = self.get_close_series("SPY", days=days)
        if spy.empty:
            return pd.Series(dtype=float)
        return realized_vix_proxy(spy, mult)

    def _fetch_alpaca(self, symbol, days):
        key = (symbol, days)
        now = time.time()
        if key in self._cache and now - self._cache[key][0] < DATA_CACHE_TTL_SECONDS:
            return self._cache[key][1]
        kind, sym = self.resolve_symbol(symbol)
        start = datetime.utcnow() - timedelta(days=days + 5)
        try:
            if kind == "crypto":
                req = CryptoBarsRequest(symbol_or_symbols=sym, timeframe=TimeFrame.Day, start=start)
                resp = self.crypto_client.get_crypto_bars(req)
            else:
                req = StockBarsRequest(symbol_or_symbols=sym, timeframe=TimeFrame.Day, start=start)
                resp = self.stock_client.get_stock_bars(req)
            df = self._barset_to_frame(resp, sym)
            if df is None or df.empty:
                return None
            df = df.resample("1D").ffill().dropna(subset=["Close"])
            self._cache[key] = (now, df)
            return df
        except Exception as e:
            logger.warning(f"Alpaca data fetch failed for {symbol}: {e}")
            return None

    def _fetch_yfinance(self, symbol, days):
        try:
            import yfinance as yf
            start = (datetime.utcnow() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
            end = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
            df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
            if df is None or df.empty or len(df) < 2:
                return pd.DataFrame()
            df.columns = [str(c)[0].upper() + str(c)[1:] for c in df.columns]
            return _normalize_index(df)
        except Exception as e:
            logger.debug(f"yfinance fallback failed for {symbol}: {e}")
            return pd.DataFrame()


provider = AlpacaDataProvider()
