import os
import json
import math
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import yfinance as yf
import redis
import pandas as pd
import numpy as np
from typing import Optional

router = APIRouter(prefix="/market", tags=["market"])


def _sanitize(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj


def _redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


CACHE_TTL = 60  # seconds

# Default cross-asset watchlist, grouped by asset class.
# yfinance conventions: indices use ^, FX use =X suffix, crypto use -USD suffix.
DEFAULT_WATCHLIST: dict[str, list[str]] = {
    "equity":    ["SPY", "QQQ", "IWM", "DIA"],
    "vol":       ["^VIX", "^VXN"],
    "rates":     ["TLT", "IEF", "HYG", "LQD"],
    "commodity": ["GLD", "SLV", "USO", "UNG"],
    "crypto":    ["BTC-USD", "ETH-USD"],
    "fx":        ["EURUSD=X", "GBPUSD=X", "JPY=X", "DX-Y.NYB"],
}

# Flat list for easy lookup
ALL_DEFAULT_TICKERS = [t for group in DEFAULT_WATCHLIST.values() for t in group]

# Display-friendly names for tickers that look cryptic
DISPLAY_NAME: dict[str, str] = {
    "^VIX":     "VIX",
    "^VXN":     "VXN",
    "DX-Y.NYB": "DXY",
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "JPY=X":    "USD/JPY",
    "BTC-USD":  "BTC",
    "ETH-USD":  "ETH",
}

# Asset class tag for each ticker (sent to frontend for colour-coding)
ASSET_CLASS: dict[str, str] = {
    t: cls
    for cls, tickers in DEFAULT_WATCHLIST.items()
    for t in tickers
}

# FRED series that are commonly useful
FRED_DEFAULT_SERIES: dict[str, str] = {
    "GDP":         "Gross Domestic Product",
    "UNRATE":      "Unemployment Rate",
    "CPIAUCSL":    "CPI All Urban Consumers",
    "FEDFUNDS":    "Federal Funds Rate",
    "DGS10":       "10-Year Treasury Yield",
    "DGS2":        "2-Year Treasury Yield",
    "T10Y2Y":      "10Y-2Y Treasury Spread",
    "SP500":       "S&P 500 (FRED)",
    "BAMLH0A0HYM2": "High Yield Spread",
    "VIXCLS":      "VIX Close (FRED)",
    "DTWEXBGS":    "Trade Weighted USD Index",
    "INDPRO":      "Industrial Production",
}


class DataDownloadRequest(BaseModel):
    tickers: list[str]                   # yfinance tickers
    start: str                           # "YYYY-MM-DD"
    end: str                             # "YYYY-MM-DD"
    interval: str = "1d"                 # 1d, 1h, etc.
    fred_series: list[str] = []          # FRED series IDs
    combine: bool = True                 # If True, merge all into one DataFrame; if False return separate


@router.post("/data")
def download_market_data(req: DataDownloadRequest):
    """
    Download OHLCV data from yfinance and/or FRED economic series.
    User chooses the tickers, date range, and optionally FRED series.
    Returns a JSON object with price data and FRED indicators.
    """
    result = {}

    # ── yfinance data ──────────────────────────────────────────────────────
    if req.tickers:
        try:
            raw = yf.download(
                req.tickers,
                start=req.start,
                end=req.end,
                interval=req.interval,
                auto_adjust=True,
                progress=False,
            )
            if raw.empty:
                result["error_yfinance"] = "yfinance returned empty data for the given tickers/range"
            else:
                # Normalise multi-index columns
                if isinstance(raw.columns, pd.MultiIndex):
                    # Reorganise: for each ticker, get Close prices
                    closes = raw.xs("Close", axis=1, level=0, drop_level=True) if "Close" in raw.columns.get_level_values(0) else raw
                else:
                    closes = raw

                closes = closes.loc[:, ~closes.columns.duplicated()]
                closes = closes.sort_index()

                if req.combine:
                    # Build a combined structure with each ticker as a column + date index
                    price_data = []
                    for idx, row in closes.iterrows():
                        pt = {"date": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx)}
                        for t in closes.columns:
                            val = float(row[t]) if pd.notna(row[t]) else None
                            pt[t] = _sanitize(val)
                        price_data.append(pt)

                    result["prices"] = price_data
                    result["tickers"] = list(closes.columns)
                    result["rows"] = len(price_data)
                else:
                    # Return separate per-ticker arrays
                    result["tickers"] = list(closes.columns)
                    result["prices_by_ticker"] = {}
                    for t in closes.columns:
                        series = []
                        for idx, row in closes.iterrows():
                            val = float(row[t]) if pd.notna(row[t]) else None
                            series.append({
                                "date": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                                "close": _sanitize(val),
                            })
                        result["prices_by_ticker"][t] = series
                    result["rows"] = sum(len(v) for v in result["prices_by_ticker"].values())

        except Exception as e:
            result["error_yfinance"] = str(e)

    # ── FRED data ──────────────────────────────────────────────────────────
    fred_api_key = os.getenv("FRED_API_KEY", "")
    if fred_api_key and req.fred_series:
        import urllib.request
        fred_data = {}
        for series_id in req.fred_series:
            if series_id not in FRED_DEFAULT_SERIES:
                fred_data[series_id] = {"error": f"Unknown FRED series: {series_id}"}
                continue
            try:
                url = (
                    f"https://api.stlouisfed.org/fred/series/observations"
                    f"?series_id={series_id}"
                    f"&api_key={fred_api_key}"
                    f"&file_type=json"
                    f"&observation_start={req.start}"
                    f"&observation_end={req.end}"
                    f"&sort_order=desc"
                    f"&limit=1000"
                )
                with urllib.request.urlopen(url, timeout=15) as resp:
                    body = json.loads(resp.read().decode())
                observations = body.get("observations", [])
                series = []
                for obs in observations:
                    val = obs.get("value")
                    if val and val != ".":
                        series.append({
                            "date": obs["date"],
                            "value": float(val),
                        })
                fred_data[series_id] = {
                    "series_id": series_id,
                    "name": FRED_DEFAULT_SERIES.get(series_id, series_id),
                    "data": series,
                    "count": len(series),
                }
            except Exception as e:
                fred_data[series_id] = {"error": str(e), "series_id": series_id}
        result["fred"] = fred_data

    result["start"] = req.start
    result["end"] = req.end
    result["interval"] = req.interval
    return _sanitize(result)


@router.get("/fred-series")
def list_fred_series():
    """Returns the mapping of known FRED series IDs to display names."""
    return {"series": [{"id": k, "name": v} for k, v in FRED_DEFAULT_SERIES.items()]}


@router.get("/quotes")
def get_quotes(tickers: str = ""):
    """
    Returns price, daily change, realized vol, and IV rank per ticker.
    If `tickers` is empty, returns the full cross-asset default watchlist.
    Active-position tickers from Redis are merged in on top.
    """
    r = _redis()

    # Resolve ticker list
    requested: list[str] = []
    if tickers:
        requested = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        # Start with the full default watchlist
        requested = list(ALL_DEFAULT_TICKERS)
        # Merge in any active-position tickers the agent is currently trading
        raw = r.get("graphalpha:agent_status")
        if raw:
            status = json.loads(raw)
            for t in status.get("active_tickers", []):
                if t not in requested:
                    requested.append(t)

    cache_key = f"graphalpha:market_quotes:{','.join(sorted(requested))}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)

    results = []
    for ticker in requested:
        try:
            t_obj = yf.Ticker(ticker)
            hist = t_obj.history(period="60d", interval="1d")
            if hist.empty:
                results.append({
                    "ticker":      ticker,
                    "display":     DISPLAY_NAME.get(ticker, ticker),
                    "asset_class": ASSET_CLASS.get(ticker, "other"),
                    "error":       "no data",
                })
                continue

            last_close = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last_close
            daily_chg  = (last_close - prev_close) / prev_close if prev_close else 0.0

            rets = hist["Close"].pct_change().dropna()
            realized_vol = float(rets.tail(20).std() * (252 ** 0.5)) if len(rets) >= 5 else 0.0

            iv_rank: float | None = None
            try:
                info = t_obj.fast_info
                iv_rank = getattr(info, "implied_volatility", None)
                if iv_rank is not None:
                    iv_rank = float(iv_rank)
            except Exception:
                pass

            results.append({
                "ticker":       ticker,
                "display":      DISPLAY_NAME.get(ticker, ticker),
                "asset_class":  ASSET_CLASS.get(ticker, "other"),
                "last":         round(last_close, 4),
                "prev_close":   round(prev_close, 4),
                "daily_chg":    round(daily_chg, 6),
                "realized_vol": round(realized_vol, 4),
                "iv_rank":      round(iv_rank, 4) if iv_rank is not None else None,
                "volume":       int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else None,
            })
        except Exception as e:
            results.append({
                "ticker":      ticker,
                "display":     DISPLAY_NAME.get(ticker, ticker),
                "asset_class": ASSET_CLASS.get(ticker, "other"),
                "error":       str(e),
            })

    r.setex(cache_key, CACHE_TTL, json.dumps(_sanitize(results)))
    return _sanitize(results)


@router.get("/watchlist")
def get_watchlist():
    """Returns the default watchlist grouped by asset class."""
    return DEFAULT_WATCHLIST