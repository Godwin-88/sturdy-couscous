import os
import json
import math
from fastapi import APIRouter
import yfinance as yf
import redis

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
