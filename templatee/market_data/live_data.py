"""
Live market data fetchers — yfinance and OpenBB Platform.

All fetchers are async and use the Redis-backed cache to avoid hammering
upstream APIs.  OpenBB is an optional dependency; when absent every
OpenBB function falls back to yfinance transparently.

Cache TTLs (configured via env vars)
─────────────────────────────────────
Real-time quote / IV  →  L1 30 s  |  L2 Redis 5 min   (CACHE_TTL_L2)
Options chain         →  L1 30 s  |  L2 Redis 5 min
OHLCV history         →  L1 30 s  |  L2 Redis 1 hr     (CACHE_TTL_L3)
OpenBB company info   →  L1 30 s  |  L2 Redis 1 hr

Namespace convention: "yf:<type>:<symbol>:…" / "openbb:<type>:<symbol>:…"
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.cache.redis_cache import get_cache, L2_TTL, L3_TTL

logger = structlog.get_logger(__name__)


# ── Cache key helper ──────────────────────────────────────────────────────────

def _ck(*parts: str) -> str:
    return ":".join(str(p) for p in parts)


# ─────────────────────────────────────────────────────────────────────────────
# yfinance fetchers
# ─────────────────────────────────────────────────────────────────────────────

async def get_yf_quote(symbol: str) -> Dict[str, Any]:
    """
    Real-time quote for *symbol* via yfinance.

    Returns keys: symbol, spot_price, bid, ask, volume, currency,
                  exchange, day_high, day_low, prev_close, timestamp, source.
    Cached for CACHE_TTL_L2 seconds (default 5 min).
    """
    cache = get_cache()
    key = _ck("yf", "quote", symbol.upper())
    cached = await cache.get(key)
    if cached is not None:
        return cached

    logger.info("yfinance: fetching quote", symbol=symbol)
    try:
        import yfinance as yf  # lazy — keeps startup fast when yf not needed
        ticker = yf.Ticker(symbol)
        fi = ticker.fast_info  # lightweight endpoint
        data: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "spot_price": _f(getattr(fi, "last_price", None)),
            "bid": _f(getattr(fi, "bid", None)),
            "ask": _f(getattr(fi, "ask", None)),
            "volume": _f(getattr(fi, "three_month_average_volume", None)),
            "day_high": _f(getattr(fi, "day_high", None)),
            "day_low": _f(getattr(fi, "day_low", None)),
            "prev_close": _f(getattr(fi, "previous_close", None)),
            "market_cap": _f(getattr(fi, "market_cap", None)),
            "currency": getattr(fi, "currency", "USD"),
            "exchange": getattr(fi, "exchange", ""),
            "timestamp": _now(),
            "source": "yfinance",
        }
    except Exception as exc:
        logger.error("yfinance quote error", symbol=symbol, error=str(exc))
        data = {"symbol": symbol.upper(), "error": str(exc), "timestamp": _now(), "source": "yfinance"}

    await cache.set(key, data, ttl=L2_TTL)
    return data


async def get_yf_history(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> Dict[str, Any]:
    """
    OHLCV history for *symbol* via yfinance.

    *period*   : 1d 5d 1mo 3mo 6mo 1y 2y 5y 10y ytd max
    *interval* : 1m 2m 5m 15m 30m 60m 90m 1h 1d 5d 1wk 1mo 3mo
    Cached for CACHE_TTL_L3 (default 1 hr).
    """
    cache = get_cache()
    key = _ck("yf", "history", symbol.upper(), period, interval)
    cached = await cache.get(key)
    if cached is not None:
        return cached

    logger.info("yfinance: fetching history", symbol=symbol, period=period, interval=interval)
    try:
        import yfinance as yf
        df = yf.Ticker(symbol).history(period=period, interval=interval)
        if df.empty:
            data: Dict[str, Any] = {
                "symbol": symbol.upper(), "rows": [], "error": "No data returned",
                "timestamp": _now(), "source": "yfinance",
            }
        else:
            df.index = df.index.strftime("%Y-%m-%d %H:%M:%S")
            data = {
                "symbol": symbol.upper(),
                "period": period,
                "interval": interval,
                "columns": list(df.columns),
                "rows": df.reset_index().rename(columns={"index": "date"}).fillna(0).to_dict(orient="records"),
                "row_count": len(df),
                "timestamp": _now(),
                "source": "yfinance",
            }
    except Exception as exc:
        logger.error("yfinance history error", symbol=symbol, error=str(exc))
        data = {"symbol": symbol.upper(), "rows": [], "error": str(exc), "timestamp": _now(), "source": "yfinance"}

    await cache.set(key, data, ttl=L3_TTL)
    return data


async def get_yf_options(
    symbol: str,
    expiry: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full options chain for *symbol* via yfinance.

    If *expiry* is None the nearest available expiration is used.
    Cached for CACHE_TTL_L2 (default 5 min).
    """
    cache = get_cache()
    key = _ck("yf", "options", symbol.upper(), expiry or "nearest")
    cached = await cache.get(key)
    if cached is not None:
        return cached

    logger.info("yfinance: fetching options", symbol=symbol, expiry=expiry)
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        expirations: tuple = ticker.options
        if not expirations:
            data: Dict[str, Any] = {
                "symbol": symbol.upper(), "error": "No expirations available",
                "chain": {}, "timestamp": _now(), "source": "yfinance",
            }
        else:
            target = expiry if (expiry and expiry in expirations) else expirations[0]
            chain = ticker.option_chain(target)

            def _df_records(df) -> List[Dict]:
                d = df.copy()
                if "lastTradeDate" in d.columns:
                    d["lastTradeDate"] = d["lastTradeDate"].astype(str)
                return d.fillna(0).to_dict(orient="records")

            data = {
                "symbol": symbol.upper(),
                "expiry": target,
                "available_expiries": list(expirations),
                "calls": _df_records(chain.calls),
                "puts": _df_records(chain.puts),
                "timestamp": _now(),
                "source": "yfinance",
            }
    except Exception as exc:
        logger.error("yfinance options error", symbol=symbol, error=str(exc))
        data = {
            "symbol": symbol.upper(), "error": str(exc),
            "calls": [], "puts": [], "timestamp": _now(), "source": "yfinance",
        }

    await cache.set(key, data, ttl=L2_TTL)
    return data


async def get_yf_implied_vol(symbol: str) -> Dict[str, Any]:
    """
    Approximate ATM implied vol from the nearest yfinance options chain.
    Cached for CACHE_TTL_L2.
    """
    cache = get_cache()
    key = _ck("yf", "iv", symbol.upper())
    cached = await cache.get(key)
    if cached is not None:
        return cached

    quote = await get_yf_quote(symbol)
    spot = quote.get("spot_price") or 0.0

    chain_data = await get_yf_options(symbol)
    calls = chain_data.get("calls", [])

    iv: Optional[float] = None
    atm_strike: Optional[float] = None
    if spot and calls:
        atm = min(calls, key=lambda c: abs((c.get("strike") or 0) - spot))
        raw_iv = atm.get("impliedVolatility")
        if raw_iv:
            iv = float(raw_iv)
            atm_strike = atm.get("strike")

    data: Dict[str, Any] = {
        "symbol": symbol.upper(),
        "implied_vol": iv,
        "atm_strike": atm_strike,
        "expiry": chain_data.get("expiry"),
        "spot_price": spot,
        "timestamp": _now(),
        "source": "yfinance",
    }
    await cache.set(key, data, ttl=L2_TTL)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# OpenBB Platform fetchers (optional dependency)
# ─────────────────────────────────────────────────────────────────────────────

async def get_openbb_quote(
    symbol: str,
    provider: str = "yfinance",
) -> Dict[str, Any]:
    """
    Real-time quote via OpenBB Platform SDK.

    Falls back to yfinance if ``openbb`` is not installed or the call fails.
    Cached for CACHE_TTL_L2.
    """
    cache = get_cache()
    key = _ck("openbb", "quote", symbol.upper(), provider)
    cached = await cache.get(key)
    if cached is not None:
        return cached

    data: Dict[str, Any] = {}
    try:
        from openbb import obb  # noqa: PLC0415
        logger.info("OpenBB: fetching quote", symbol=symbol, provider=provider)
        raw = obb.equity.price.quote(symbol=symbol, provider=provider)
        df = raw.to_df()
        if df.empty:
            raise ValueError("OpenBB returned empty DataFrame")
        row = df.iloc[0].to_dict()
        data = {
            "symbol": symbol.upper(),
            "spot_price": _f(row.get("last_price") or row.get("price")),
            "bid": _f(row.get("bid")),
            "ask": _f(row.get("ask")),
            "volume": _f(row.get("volume")),
            "change_percent": _f(row.get("change_percent")),
            "day_high": _f(row.get("high")),
            "day_low": _f(row.get("low")),
            "prev_close": _f(row.get("prev_close")),
            "timestamp": _now(),
            "source": f"openbb/{provider}",
        }
    except ImportError:
        logger.warning("openbb not installed — using yfinance fallback", symbol=symbol)
        data = {**await get_yf_quote(symbol), "source": "yfinance_fallback"}
    except Exception as exc:
        logger.error("OpenBB quote error", symbol=symbol, error=str(exc))
        data = {**await get_yf_quote(symbol), "source": "yfinance_fallback", "openbb_error": str(exc)}

    await cache.set(key, data, ttl=L2_TTL)
    return data


async def get_openbb_history(
    symbol: str,
    start_date: str = "2020-01-01",
    provider: str = "yfinance",
) -> Dict[str, Any]:
    """
    OHLCV history via OpenBB Platform. Falls back to yfinance.
    Cached for CACHE_TTL_L3 (1 hr).
    """
    cache = get_cache()
    key = _ck("openbb", "history", symbol.upper(), start_date, provider)
    cached = await cache.get(key)
    if cached is not None:
        return cached

    data: Dict[str, Any] = {}
    try:
        from openbb import obb  # noqa: PLC0415
        logger.info("OpenBB: fetching history", symbol=symbol, start_date=start_date, provider=provider)
        raw = obb.equity.price.historical(symbol=symbol, start_date=start_date, provider=provider)
        df = raw.to_df()
        df.index = df.index.astype(str)
        data = {
            "symbol": symbol.upper(),
            "start_date": start_date,
            "provider": provider,
            "columns": list(df.columns),
            "rows": df.reset_index().rename(columns={"index": "date"}).fillna(0).to_dict(orient="records"),
            "row_count": len(df),
            "timestamp": _now(),
            "source": f"openbb/{provider}",
        }
    except ImportError:
        logger.warning("openbb not installed — using yfinance fallback", symbol=symbol)
        data = {**await get_yf_history(symbol), "source": "yfinance_fallback"}
    except Exception as exc:
        logger.error("OpenBB history error", symbol=symbol, error=str(exc))
        data = {**await get_yf_history(symbol), "source": "yfinance_fallback", "openbb_error": str(exc)}

    await cache.set(key, data, ttl=L3_TTL)
    return data


async def get_openbb_news(
    symbol: str,
    limit: int = 10,
    provider: str = "benzinga",
) -> Dict[str, Any]:
    """
    Latest news headlines for *symbol* via OpenBB Platform.
    Falls back to an empty list when OpenBB is unavailable.
    Cached for CACHE_TTL_L2 (5 min).
    """
    cache = get_cache()
    key = _ck("openbb", "news", symbol.upper(), str(limit), provider)
    cached = await cache.get(key)
    if cached is not None:
        return cached

    data: Dict[str, Any] = {"symbol": symbol.upper(), "articles": [], "timestamp": _now()}
    try:
        from openbb import obb  # noqa: PLC0415
        logger.info("OpenBB: fetching news", symbol=symbol, provider=provider)
        raw = obb.news.company(symbol=symbol, limit=limit, provider=provider)
        df = raw.to_df()
        articles = []
        for _, row in df.iterrows():
            articles.append({
                "title": str(row.get("title", "")),
                "url": str(row.get("url", "")),
                "published": str(row.get("date", row.get("published", ""))),
                "source": str(row.get("source", provider)),
                "sentiment": str(row.get("sentiment", "")),
            })
        data = {
            "symbol": symbol.upper(),
            "articles": articles,
            "count": len(articles),
            "timestamp": _now(),
            "source": f"openbb/{provider}",
        }
    except ImportError:
        logger.warning("openbb not installed — news unavailable", symbol=symbol)
        data["error"] = "openbb not installed"
    except Exception as exc:
        logger.error("OpenBB news error", symbol=symbol, error=str(exc))
        data["error"] = str(exc)

    await cache.set(key, data, ttl=L2_TTL)
    return data


# ── Private helpers ───────────────────────────────────────────────────────────

def _f(v: Any) -> float:
    """Safely coerce a value to float (returns 0.0 on failure)."""
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
