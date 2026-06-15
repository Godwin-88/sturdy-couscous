from __future__ import annotations

import io
import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from .config import cfg


class DataGapError(Exception):
    pass


_TS = "timestamp"
_OPEN = "Open"
_HIGH = "High"
_LOW = "Low"
_CLOSE = "Close"
_VOL = "Volume"


def load_ohlcv(
    start: str,
    end: str,
    tickers: List[str],
    interval: str = "1d",
) -> pd.DataFrame:
    equity_tickers = [t for t in tickers if not _is_crypto(t)]
    crypto_tickers = [t for t in tickers if _is_crypto(t)]
    frames: List[pd.DataFrame] = []

    if equity_tickers:
        frames.append(_load_yfinance(equity_tickers, start, end, interval))
    if crypto_tickers:
        frames.append(_load_coinbase_crypto(crypto_tickers, start, end, interval))

    if not frames:
        raise DataGapError("No tickers requested")

    out = pd.concat(frames, axis=1)
    out = out.loc[:, ~out.columns.duplicated()]
    out = out.sort_index()
    missing = [t for t in tickers if t not in out.columns or out[t].dropna().empty]
    if missing:
        raise DataGapError(
            f"No data for tickers: {missing} in range {start}..{end}"
        )
    return out


def load_for_ticker(ticker: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    df = load_ohlcv(start, end, [ticker], interval)
    return df[[ticker]].copy()


def _is_crypto(ticker: str) -> bool:
    return ticker.upper() in {u.ticker for u in _default_universe() if u.asset_class == "crypto"}


def _default_universe():
    from .universe import get_universe
    return get_universe()


_INTERVAL_TO_GRANULARITY = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "1d": 86400,
}


def _load_yfinance(
    tickers: List[str], start: str, end: str, interval: str
) -> pd.DataFrame:
    fetch = tickers + ["^VIX"] if interval == "1d" else tickers
    raw = yf.download(
        fetch,
        start=start,
        end=end,
        interval=interval,
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise DataGapError(f"yfinance returned empty for {tickers}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw
    raw = raw.loc[:, ~raw.columns.duplicated()]
    raw = raw.reindex(columns=tickers, fill_value=np.nan)
    raw = raw.sort_index()
    for col in raw.columns:
        raw[col] = raw[col].astype(float)
    raw.index = pd.to_datetime(raw.index).tz_localize("UTC") if raw.index.tz is None else raw.index.tz_convert("UTC")
    return raw


def _load_coinbase_crypto(
    tickers: List[str], start: str, end: str, interval: str
) -> pd.DataFrame:
    granularity = _INTERVAL_TO_GRANULARITY.get(interval, 86400)
    out: Dict[str, pd.Series] = {}
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    max_rows = 300

    for ticker in tickers:
        pair = _venue_symbol(ticker)
        rows = _cb_fetch_candles(pair, granularity, start_dt, end_dt, max_rows)
        if not rows:
            raise DataGapError(f"Coinbase returned no candles for {ticker} ({pair})")
        idx, op, hi, lo, cl, vol = zip(*rows)
        ts = pd.to_datetime(list(idx), utc=True)
        s = pd.DataFrame(
            {_OPEN: op, _HIGH: hi, _LOW: lo, _CLOSE: cl, _VOL: vol},
            index=ts,
        )
        s.index.name = _TS
        out[ticker] = s[_CLOSE]

    df = pd.concat(out.values(), axis=1)
    df.columns = list(out.keys())
    df = df.sort_index().ffill()
    for col in df.columns:
        df[col] = df[col].astype(float)
    return df


def _venue_symbol(ticker: str) -> str:
    from .universe import lookup
    return lookup(ticker).venue_symbol


def _cb_fetch_candles(
    product_id: str,
    granularity: int,
    start: datetime,
    end: datetime,
    max_rows: int = 300,
) -> List[Tuple[datetime, float, float, float, float, float]]:
    url = (
        f"https://api.exchange.coinbase.com/products/{product_id}/candles"
        f"?granularity={granularity}"
    )
    rows: List[List] = []
    cursor = end
    backoff = 1.0
    while cursor > start and len(rows) < max_rows:
        req_start = int((cursor - timedelta(seconds=granularity * max_rows)).timestamp())
        req = urllib.request.Request(
            f"{url}&start={req_start}&end={int(cursor.timestamp())}"
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
        except (urllib.error.URLError, ValueError) as exc:
            raise DataGapError(f"Coinbase API error for {product_id}: {exc}") from exc
        if not data:
            break
        for r in data:
            ts = datetime.fromtimestamp(r[0], tz=timezone.utc)
            if ts >= start and ts < cursor:
                rows.append((ts, float(r[3]), float(r[2]), float(r[1]), float(r[4]), float(r[5])))
        if not rows:
            cursor = datetime.fromtimestamp(data[-1][0], tz=timezone.utc) - timedelta(seconds=granularity)
            backoff = min(backoff * 2, 16)
        else:
            cursor = rows[-1][0] - timedelta(seconds=granularity)
            backoff = 1.0
    rows.sort(key=lambda x: x[0])
    return rows
