"""
Asset Universe API — yfinance-backed symbol search and types.

Provides a rich asset universe via Yahoo Finance Lookup:
- Asset types: equity, currency, cryptocurrency, etf, index, future, mutualfund
- Search scoped by type: when user selects "forex", results are currency pairs only.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import logging

router = APIRouter(prefix="/assets", tags=["assets"])

logger = logging.getLogger(__name__)

# yfinance Lookup types — maps to our asset categories
# When type=forex → we call get_currency(); type=crypto → get_cryptocurrency(); etc.
YF_LOOKUP_TYPES = [
    "all",
    "equity",
    "currency",
    "cryptocurrency",
    "etf",
    "index",
    "future",
    "mutualfund",
]

ASSET_TYPE_LABELS = {
    "all": "All",
    "equity": "Equities",
    "currency": "Forex",
    "cryptocurrency": "Crypto",
    "etf": "ETFs",
    "index": "Indices",
    "future": "Commodities",
    "mutualfund": "Mutual Funds",
}


@router.get("/providers")
def get_data_providers() -> List[str]:
    """Return available data providers for history, quote, and options (yfinance, openbb, nautilus)."""
    try:
        from app.assets.providers import VALID_PROVIDERS
        return list(VALID_PROVIDERS)
    except ImportError:
        return ["yfinance", "openbb", "nautilus"]


@router.get("/types")
def get_asset_types() -> List[dict]:
    """
    Return asset types supported by yfinance.
    Use these in search ?type= to scope results (e.g. forex → currency pairs only).
    """
    return [
        {"id": t, "label": ASSET_TYPE_LABELS.get(t, t)}
        for t in YF_LOOKUP_TYPES
    ]


def _map_type_to_yf_method(lookup_type: str):
    """Map API type to yfinance Lookup method name."""
    mapping = {
        "all": "get_all",
        "equity": "get_stock",
        "currency": "get_currency",
        "cryptocurrency": "get_cryptocurrency",
        "etf": "get_etf",
        "index": "get_index",
        "future": "get_future",
        "mutualfund": "get_mutualfund",
    }
    return mapping.get(lookup_type, "get_all")


@router.get("/search")
def search_assets(
    q: str = Query(..., min_length=1, description="Search query (symbol or name fragment)"),
    type: str = Query("all", description="Asset type filter (all, equity, currency, cryptocurrency, etf, index, future, mutualfund)"),
    count: int = Query(50, ge=5, le=100, description="Max results to return"),
) -> List[dict]:
    """
    Search assets via yfinance Lookup. Results are filtered by asset type.
    - type=currency → forex pairs only
    - type=cryptocurrency → crypto only
    - type=equity → stocks only
    - etc.
    """
    if type and type not in YF_LOOKUP_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid type. Use one of: {', '.join(YF_LOOKUP_TYPES)}")

    try:
        import yfinance as yf
        lookup = yf.Lookup(q.strip(), raise_errors=False)
        method_name = _map_type_to_yf_method(type)
        method = getattr(lookup, method_name, lookup.get_all)
        df = method(count=count)

        if df is None or df.empty:
            return []

        out = []
        seen = set()
        for symbol in df.index:
            if symbol in seen or not symbol:
                continue
            seen.add(symbol)
            row = df.loc[symbol]
            try:
                name = str(row.get("shortName", row.get("longName", symbol)))
            except Exception:
                name = str(symbol)
            if name == "nan" or not name:
                name = str(symbol)
            out.append({
                "symbol": str(symbol),
                "type": type,
                "name": name[:80],
            })
            if len(out) >= count:
                break

        return out

    except ImportError:
        logger.error("yfinance not installed")
        raise HTTPException(status_code=503, detail="Asset search requires yfinance")
    except Exception as e:
        logger.exception("Asset search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Market Movers ─────────────────────────────────────────────────────────────

# Per-category watchlists — broad cross-asset coverage for the ticker
_MOVERS_BY_CATEGORY: dict[str, dict] = {
    "equities": {
        "label": "Equities",
        "color": "blue",
        "symbols": [
            "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM",
            "GS", "BAC", "XOM", "CVX", "UNH", "JNJ", "V", "MA", "WMT", "HD",
            "PG", "KO", "NFLX", "ADBE", "AMD", "INTC", "ORCL", "CRM", "PYPL",
            "DIS", "NKE", "PFE",
        ],
    },
    "etfs": {
        "label": "ETFs",
        "color": "indigo",
        "symbols": [
            "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "GLD", "SLV", "TLT",
            "XLF", "XLK", "XLE", "XLV", "XLI", "XLY", "ARKK", "ARKG", "HYG",
            "LQD", "EEM",
        ],
    },
    "indices": {
        "label": "Indices",
        "color": "violet",
        "symbols": [
            "^GSPC", "^IXIC", "^DJI", "^RUT", "^FTSE", "^N225", "^HSI",
            "^DAX", "^CAC40", "^STOXX50E", "^AXJO", "^BSESN",
        ],
    },
    "crypto": {
        "label": "Crypto",
        "color": "orange",
        "symbols": [
            "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD",
            "AVAX-USD", "DOT-USD", "DOGE-USD", "MATIC-USD", "LINK-USD",
            "LTC-USD", "ATOM-USD", "UNI-USD", "NEAR-USD",
        ],
    },
    "forex": {
        "label": "Forex",
        "color": "teal",
        "symbols": [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
            "USDCHF=X", "NZDUSD=X", "EURGBP=X", "USDINR=X", "USDCNY=X",
            "USDMXN=X", "USDBRL=X",
        ],
    },
    "futures": {
        "label": "Futures",
        "color": "amber",
        "symbols": [
            "CL=F", "BZ=F", "GC=F", "SI=F", "HG=F", "NG=F",
            "ZC=F", "ZW=F", "ZS=F", "KC=F", "SB=F", "CT=F",
        ],
    },
    "volatility": {
        "label": "Volatility",
        "color": "red",
        "symbols": [
            "^VIX", "^VVIX", "^VXN", "^OVX", "^GVZ", "^SKEW",
        ],
    },
    "mutualfunds": {
        "label": "Mutual Funds",
        "color": "emerald",
        "symbols": [
            "VFINX", "FXAIX", "VTSAX", "FCNTX", "AGTHX", "DODGX",
            "PRGFX", "VTSMX",
        ],
    },
}

# Human-readable labels for non-obvious symbols
_DISPLAY_NAMES: dict[str, str] = {
    "^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^DJI": "Dow Jones",
    "^RUT": "Russell 2000", "^FTSE": "FTSE 100", "^N225": "Nikkei 225",
    "^HSI": "Hang Seng", "^DAX": "DAX", "^CAC40": "CAC 40",
    "^STOXX50E": "Euro Stoxx 50", "^AXJO": "ASX 200", "^BSESN": "Sensex",
    "^VIX": "VIX", "^VVIX": "VVIX", "^VXN": "VXN (NASDAQ Vol)",
    "^OVX": "OVX (Oil Vol)", "^GVZ": "GVZ (Gold Vol)", "^SKEW": "SKEW",
    "CL=F": "WTI Crude", "BZ=F": "Brent Crude", "GC=F": "Gold",
    "SI=F": "Silver", "HG=F": "Copper", "NG=F": "Nat Gas",
    "ZC=F": "Corn", "ZW=F": "Wheat", "ZS=F": "Soybeans",
    "KC=F": "Coffee", "SB=F": "Sugar", "CT=F": "Cotton",
    "EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY",
    "AUDUSD=X": "AUD/USD", "USDCAD=X": "USD/CAD", "USDCHF=X": "USD/CHF",
    "NZDUSD=X": "NZD/USD", "EURGBP=X": "EUR/GBP", "USDINR=X": "USD/INR",
    "USDCNY=X": "USD/CNY", "USDMXN=X": "USD/MXN", "USDBRL=X": "USD/BRL",
}

# Module-level cache — avoid repeated slow batch downloads
import time as _time
_movers_cache: dict = {"data": None, "ts": 0.0}
_MOVERS_CACHE_TTL = 300  # 5 minutes


def _ticker_label(sym: str) -> str:
    if sym in _DISPLAY_NAMES:
        return _DISPLAY_NAMES[sym]
    return sym.replace("=X", "").replace("-USD", "/USD").replace("^", "")


@router.get("/movers")
def get_market_movers(top: int = Query(5, ge=2, le=10)) -> dict:
    """
    Return top gainers and top losers per asset class (equities, ETFs, indices,
    crypto, forex, futures, volatility, mutual funds). Cached in-process for 5 min.
    """
    global _movers_cache

    # Return cached result if fresh
    now = _time.time()
    if _movers_cache["data"] is not None and (now - _movers_cache["ts"]) < _MOVERS_CACHE_TTL:
        return _movers_cache["data"]

    try:
        import yfinance as yf
        import numpy as np

        # Collect all symbols from all categories
        all_symbols: list[str] = []
        for cat in _MOVERS_BY_CATEGORY.values():
            all_symbols.extend(cat["symbols"])

        # Single batch download for all symbols
        raw = yf.download(
            all_symbols,
            period="2d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        if raw.empty:
            return {"categories": {}, "timestamp": ""}

        # Handle multi-level or single-level columns
        if isinstance(raw.columns, type(raw.columns)) and hasattr(raw.columns, "levels"):
            try:
                close = raw.xs("Close", axis=1, level=0)
            except Exception:
                close = raw["Close"] if "Close" in raw.columns else raw
        else:
            close = raw["Close"] if "Close" in raw.columns else raw

        if close.shape[0] < 2:
            return {"categories": {}, "timestamp": ""}

        prev = close.iloc[-2]
        curr = close.iloc[-1]
        pct  = ((curr - prev) / prev * 100)

        # Build per-category results
        categories: dict = {}
        for cat_id, cat_meta in _MOVERS_BY_CATEGORY.items():
            cat_results = []
            for sym in cat_meta["symbols"]:
                if sym not in pct.index:
                    continue
                try:
                    change = float(pct[sym])
                    price  = float(curr[sym])
                except Exception:
                    continue
                if np.isnan(change) or np.isnan(price):
                    continue
                if not (abs(change) < 1000 and price > 0):
                    continue
                cat_results.append({
                    "symbol":     sym,
                    "label":      _ticker_label(sym),
                    "price":      round(price, 4),
                    "change_pct": round(change, 2),
                })

            if not cat_results:
                continue

            cat_results.sort(key=lambda x: x["change_pct"], reverse=True)
            categories[cat_id] = {
                "label":   cat_meta["label"],
                "color":   cat_meta["color"],
                "gainers": cat_results[:top],
                "losers":  list(reversed(cat_results[-top:])),
            }

        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
        result = {"categories": categories, "timestamp": ts}

        _movers_cache["data"] = result
        _movers_cache["ts"]   = now
        return result

    except ImportError:
        raise HTTPException(status_code=503, detail="yfinance required for market movers")
    except Exception as e:
        logger.exception("Market movers failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


YF_PERIODS = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "ytd")

try:
    from app.assets.providers import VALID_PROVIDERS, get_asset_history_by_provider
except ImportError:
    VALID_PROVIDERS = ("yfinance", "openbb", "nautilus")
    get_asset_history_by_provider = None


@router.get("/history")
def get_asset_history(
    symbol: str = Query(..., min_length=1, description="Asset symbol (e.g. AAPL, BTC-USD)"),
    period: str = Query("1mo", description="Period: 1d, 5d, 1mo, 3mo, 6mo, 1y, ytd"),
    provider: str = Query("yfinance", description="Data source: yfinance, openbb, nautilus"),
) -> List[dict]:
    """
    Fetch OHLC historical data for charting. Provider: yfinance | openbb | nautilus.
    """
    if period not in YF_PERIODS:
        raise HTTPException(status_code=400, detail=f"Invalid period. Use one of: {', '.join(YF_PERIODS)}")
    if get_asset_history_by_provider is None:
        raise HTTPException(status_code=503, detail="Asset providers not available")
    try:
        return get_asset_history_by_provider(symbol, period, provider or "yfinance")
    except Exception as e:
        logger.exception("Asset history failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quote/{symbol}")
def get_asset_quote(
    symbol: str,
    provider: str = Query("yfinance", description="Data source: yfinance, openbb, nautilus"),
) -> dict:
    """
    Fetch current spot price, name, and currency. Provider: yfinance | openbb | nautilus.
    """
    try:
        from app.assets.providers import get_asset_quote_by_provider
        return get_asset_quote_by_provider(symbol, provider or "yfinance")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Asset quote failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/options/{symbol}")
def get_asset_options(
    symbol: str,
    n_expiries: int = Query(3, ge=1, le=6, description="Number of nearest expiries to include"),
    moneyness_range: float = Query(0.20, ge=0.05, le=0.50, description="Strike range around ATM as fraction"),
    provider: str = Query("yfinance", description="Data source: yfinance, openbb, nautilus"),
) -> dict:
    """
    Fetch option chain for Heston calibration. Provider: yfinance | openbb | nautilus.
    Returns call options (strike, expiry_years, mid_price, implied_vol) near ATM.
    """
    try:
        from app.assets.providers import get_asset_options_by_provider
        return get_asset_options_by_provider(symbol, provider or "yfinance", n_expiries, moneyness_range)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=503, detail="yfinance not installed")
    except Exception as e:
        logger.exception("Options fetch failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
