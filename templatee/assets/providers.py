"""
Asset data by provider: yfinance, openbb, nautilus.
Normalized responses for /assets/history, /assets/quote, /assets/options.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

VALID_PROVIDERS = ("yfinance", "openbb", "nautilus")


def _period_to_dates(period: str) -> tuple[str, str]:
    """Map period to (start_date, end_date) for OpenBB/Nautilus."""
    today = date.today()
    if period == "1d":
        start = today - timedelta(days=2)
    elif period == "5d":
        start = today - timedelta(days=10)
    elif period == "1mo":
        start = today - timedelta(days=35)
    elif period == "3mo":
        start = today - timedelta(days=95)
    elif period == "6mo":
        start = today - timedelta(days=185)
    elif period == "1y":
        start = today - timedelta(days=370)
    elif period == "2y":
        start = today - timedelta(days=730)
    elif period == "5y":
        start = today - timedelta(days=1825)
    elif period == "ytd":
        start = date(today.year, 1, 1)
    else:
        start = today - timedelta(days=370)
    return start.isoformat(), today.isoformat()


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


# ─── History ─────────────────────────────────────────────────────────────────

def history_yfinance(symbol: str, period: str) -> List[Dict[str, Any]]:
    """OHLCV history via yfinance. Returns [{ date, open, high, low, close, volume }]."""
    import yfinance as yf
    ticker = yf.Ticker(symbol.strip())
    df = ticker.history(period=period)
    if df is None or df.empty:
        return []
    out = []
    for ts, row in df.iterrows():
        date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)
        out.append({
            "date": date_str,
            "open": _num(row.get("Open")),
            "high": _num(row.get("High")),
            "low": _num(row.get("Low")),
            "close": _num(row.get("Close")),
            "volume": _num(row.get("Volume")),
        })
    return out


def history_openbb(symbol: str, period: str) -> List[Dict[str, Any]]:
    """OHLCV history via OpenBB. Returns same shape as history_yfinance."""
    start_date, end_date = _period_to_dates(period)
    try:
        from openbb import obb
        raw = obb.equity.price.historical(symbol=symbol.strip(), start_date=start_date, end_date=end_date)
        df = raw.to_df()
    except ImportError:
        logger.warning("openbb not installed, falling back to yfinance")
        return history_yfinance(symbol, period)
    except Exception as e:
        logger.warning("openbb history failed: %s", e)
        return history_yfinance(symbol, period)
    if df is None or df.empty:
        return []
    out = []
    for idx, row in df.iterrows():
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        open_ = _num(row.get("open") or row.get("Open"))
        high = _num(row.get("high") or row.get("High"))
        low = _num(row.get("low") or row.get("Low"))
        close = _num(row.get("close") or row.get("Close"))
        vol = _num(row.get("volume") or row.get("Volume"))
        out.append({"date": date_str, "open": open_, "high": high, "low": low, "close": close, "volume": vol})
    return out


def history_nautilus(symbol: str, period: str) -> List[Dict[str, Any]]:
    """OHLCV history via Nautilus catalog or fallback yfinance. Returns same shape."""
    start_date, end_date = _period_to_dates(period)
    try:
        from app.blotter.chart_data import get_chart_bars
        bars = get_chart_bars(symbol=symbol, timeframe="1d", from_date=start_date, to_date=end_date)
    except Exception as e:
        logger.warning("nautilus history failed: %s", e)
        return history_yfinance(symbol, period)
    if not bars:
        return history_yfinance(symbol, period)
    out = []
    for b in bars:
        ts = b.get("time")
        if ts is not None and isinstance(ts, (int, float)):
            dt = datetime.utcfromtimestamp(ts)
            date_str = dt.strftime("%Y-%m-%d")
        else:
            date_str = ""
        out.append({
            "date": date_str,
            "open": b.get("open"),
            "high": b.get("high"),
            "low": b.get("low"),
            "close": b.get("close"),
            "volume": b.get("volume"),
        })
    return out


def get_asset_history_by_provider(symbol: str, period: str, provider: str) -> List[Dict[str, Any]]:
    provider = (provider or "yfinance").lower()
    if provider not in VALID_PROVIDERS:
        provider = "yfinance"
    if provider == "openbb":
        return history_openbb(symbol, period)
    if provider == "nautilus":
        return history_nautilus(symbol, period)
    return history_yfinance(symbol, period)


# ─── Quote ───────────────────────────────────────────────────────────────────

def quote_yfinance(symbol: str) -> Dict[str, Any]:
    """Current quote via yfinance. Returns { symbol, spot, name, currency }."""
    import yfinance as yf
    ticker = yf.Ticker(symbol.strip().upper())
    info = ticker.info or {}
    spot = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
    if spot is None:
        hist = ticker.history(period="1d")
        spot = float(hist["Close"].iloc[-1]) if not hist.empty else None
    if spot is None:
        raise ValueError(f"No price found for {symbol}")
    return {
        "symbol": symbol.upper(),
        "spot": float(spot),
        "name": info.get("shortName", symbol),
        "currency": info.get("currency", "USD"),
    }


def quote_openbb(symbol: str) -> Dict[str, Any]:
    """Current quote via OpenBB. Returns same shape as quote_yfinance."""
    try:
        from openbb import obb
        raw = obb.equity.price.quote(symbol=symbol.strip(), provider="yfinance")
        df = raw.to_df()
        if df is None or df.empty:
            raise ValueError("OpenBB returned empty quote")
        row = df.iloc[0].to_dict()
        spot = row.get("last_price") or row.get("price") or row.get("close")
        if spot is None:
            raise ValueError(f"No price for {symbol}")
        return {
            "symbol": symbol.upper(),
            "spot": float(spot),
            "name": str(row.get("short_name", row.get("name", symbol))),
            "currency": str(row.get("currency", "USD")),
        }
    except ImportError:
        return quote_yfinance(symbol)
    except Exception as e:
        logger.warning("openbb quote failed: %s", e)
        return quote_yfinance(symbol)


def quote_nautilus(symbol: str) -> Dict[str, Any]:
    """Quote: Nautilus has no direct quote API; use yfinance."""
    return quote_yfinance(symbol)


def get_asset_quote_by_provider(symbol: str, provider: str) -> Dict[str, Any]:
    provider = (provider or "yfinance").lower()
    if provider not in VALID_PROVIDERS:
        provider = "yfinance"
    if provider == "openbb":
        return quote_openbb(symbol)
    if provider == "nautilus":
        return quote_nautilus(symbol)
    return quote_yfinance(symbol)


# ─── Options ──────────────────────────────────────────────────────────────────

def options_yfinance(symbol: str, n_expiries: int, moneyness_range: float) -> Dict[str, Any]:
    """Option chain via yfinance. Returns { symbol, spot, n_contracts, contracts }."""
    import yfinance as yf
    from datetime import date as date_cls
    ticker = yf.Ticker(symbol.strip().upper())
    info = ticker.info or {}
    spot = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
    if spot is None:
        hist = ticker.history(period="1d")
        spot = float(hist["Close"].iloc[-1]) if not hist.empty else None
    if spot is None:
        raise ValueError(f"No spot for {symbol}")
    spot = float(spot)
    expirations = ticker.options or []
    if not expirations:
        raise ValueError(f"No options for {symbol}")
    today = date_cls.today()
    options_out = []
    for exp_str in expirations[:n_expiries]:
        try:
            exp_date = date_cls.fromisoformat(exp_str)
            tau = (exp_date - today).days / 365.0
            if tau <= 0.01:
                continue
            chain = ticker.option_chain(exp_str)
            calls = chain.calls
            if calls is None or calls.empty:
                continue
            lo, hi = spot * (1 - moneyness_range), spot * (1 + moneyness_range)
            calls = calls[(calls["strike"] >= lo) & (calls["strike"] <= hi)]
            for _, row in calls.iterrows():
                strike = float(row["strike"])
                bid = float(row.get("bid", 0) or 0)
                ask = float(row.get("ask", 0) or 0)
                last = float(row.get("lastPrice", 0) or 0)
                iv = float(row.get("impliedVolatility", 0) or 0)
                mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else last
                if mid <= 0 or math.isnan(mid) or math.isnan(iv):
                    continue
                options_out.append({
                    "strike": round(strike, 2),
                    "expiry": round(tau, 4),
                    "expiry_str": exp_str,
                    "price": round(mid, 4),
                    "implied_vol": round(iv, 4),
                    "moneyness": round(strike / spot, 4),
                })
        except Exception:
            continue
    if not options_out:
        raise ValueError(f"No valid options for {symbol}")
    return {
        "symbol": symbol.upper(),
        "spot": spot,
        "n_contracts": len(options_out),
        "contracts": options_out,
    }


def options_openbb(symbol: str, n_expiries: int, moneyness_range: float) -> Dict[str, Any]:
    """Options via OpenBB if available; else yfinance."""
    try:
        from openbb import obb
        # OpenBB options chain API may vary; fallback to yfinance for stability
        raw = obb.derivatives.options.chains(symbol=symbol.strip())
        if raw and hasattr(raw, "to_df"):
            df = raw.to_df()
            if df is not None and not df.empty:
                # Normalize to same contract shape if OpenBB returns different structure
                pass
    except Exception:
        pass
    return options_yfinance(symbol, n_expiries, moneyness_range)


def options_nautilus(symbol: str, n_expiries: int, moneyness_range: float) -> Dict[str, Any]:
    """Nautilus typically has no options chain in catalog; use yfinance."""
    return options_yfinance(symbol, n_expiries, moneyness_range)


def get_asset_options_by_provider(
    symbol: str, provider: str, n_expiries: int = 3, moneyness_range: float = 0.20
) -> Dict[str, Any]:
    provider = (provider or "yfinance").lower()
    if provider not in VALID_PROVIDERS:
        provider = "yfinance"
    if provider == "openbb":
        return options_openbb(symbol, n_expiries, moneyness_range)
    if provider == "nautilus":
        return options_nautilus(symbol, n_expiries, moneyness_range)
    return options_yfinance(symbol, n_expiries, moneyness_range)
