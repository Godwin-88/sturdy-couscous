"""
GraphAlpha Analytics Intelligence Platform — Backend Service
Phase 1: Universal Time Series + Descriptive Statistics
"""

import hashlib
import json
import math
import os
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, TimeoutError
from datetime import datetime, date, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
import redis
import yfinance as yf
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from scipy import stats as sp_stats

router = APIRouter(prefix="/analytics", tags=["analytics"])

# ── Constants ──────────────────────────────────────────────────────────────────
CACHE_TTL = 300  # 5 minutes for analytics data

# Default watchlist tickers available for analysis
AVAILABLE_TICKERS = [
    "SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK", "XLV",
    "TLT", "IEF", "HYG", "LQD", "GLD", "SLV", "USO", "UNG",
    "BTC-USD", "ETH-USD", "^VIX", "^VXN",
]

# Available system metrics (from Postgres)
SYSTEM_METRICS = [
    "signal_score", "quant_score", "sentiment_score", "news_overlay",
    "macro_overlay", "kg_formula_contribution", "kelly_fraction",
    "var_contribution_pct", "slippage_bps",
]


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5,
    )


def _conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "graphalpha"),
        user=os.getenv("POSTGRES_USER", "graphalpha"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        connect_timeout=5,
        options="-c statement_timeout=10000",
    )


def _sanitize(obj: Any) -> Any:
    """Recursively sanitize for JSON serialization."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(obj, 8)
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (datetime, date, pd.Timestamp)):
        return obj.isoformat()
    if isinstance(obj, np.ndarray):
        return [_sanitize(v) for v in obj.tolist()]
    if isinstance(obj, np.floating):
        return round(float(obj), 8)
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


def _fetch_yfinance(
    ticker: str,
    start_date: str,
    end_date: str,
    interval: str = "1d",
) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data from yfinance with Redis caching."""
    cache_key = f"graphalpha:analytics:yf:{ticker}:{start_date}:{end_date}:{interval}"
    r = _redis()
    cached = r.get(cache_key)
    if cached:
        return pd.read_json(pd.io.common.StringIO(cached))

    try:
        t = yf.Ticker(ticker)
        df = t.history(start=start_date, end=end_date, interval=interval)
        if df.empty:
            return None
        # Cache
        r.setex(cache_key, CACHE_TTL, df.to_json(date_format="iso"))
        return df
    except Exception:
        return None


def _fetch_system_series(
    metric: str,
    strategy: Optional[str] = None,
    ticker: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10000,
) -> pd.DataFrame:
    """Fetch system signal metrics from signal_archive."""
    conditions = ["created_at IS NOT NULL"]
    params: list[Any] = []

    if start_date:
        conditions.append("timestamp >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("timestamp <= %s")
        params.append(end_date)
    if strategy:
        conditions.append("strategy = %s")
        params.append(strategy)
    if ticker:
        conditions.append("ticker = %s")
        params.append(ticker)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"""
                    SELECT timestamp, {metric}, strategy, ticker
                    FROM signal_archive
                    {where}
                    ORDER BY timestamp ASC LIMIT %s
                """, params + [limit])
                rows = cur.fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        return df
    except Exception:
        return pd.DataFrame()


def _fetch_portfolio_nav(start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
    """Fetch portfolio NAV history from portfolio_state."""
    conditions: list[str] = []
    params: list[Any] = []
    if start_date:
        conditions.append("updated_at >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("updated_at <= %s")
        params.append(end_date)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"""
                    SELECT updated_at, nav, cash_balance, drawdown_pct, halted
                    FROM portfolio_state
                    {where}
                    ORDER BY updated_at ASC LIMIT 10000
                """, params)
                rows = cur.fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["updated_at"] = pd.to_datetime(df["updated_at"])
        df.set_index("updated_at", inplace=True)
        return df
    except Exception:
        return pd.DataFrame()


def _fetch_regime_history(start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
    """Fetch regime classification history from agent_cycle_audit."""
    conditions: list[str] = []
    params: list[Any] = []
    if start_date:
        conditions.append("timestamp >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("timestamp <= %s")
        params.append(end_date)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"""
                    SELECT timestamp, regime, regime_confidence, cycle_id
                    FROM agent_cycle_audit
                    {where}
                    ORDER BY timestamp ASC LIMIT 10000
                """, params)
                rows = cur.fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        return df
    except Exception:
        return pd.DataFrame()


# ── Pydantic Models ────────────────────────────────────────────────────────────

class OptimizeRequest(BaseModel):
    tickers: list[str] = Field(..., description="List of tickers to optimize")
    method: str = Field("mvo", description="Optimization method: mvo, risk_parity, max_diversification")
    constraint_long_only: bool = True
    max_weight: float = Field(0.25, ge=0.05, le=1.0)
    target_return: Optional[float] = None
    risk_free_rate: float = 0.05


class ForecastRequest(BaseModel):
    ticker: str = Field(..., description="Ticker to forecast")
    model: str = Field("arima", description="Model: arima, ets, var, vecm")
    horizon: int = Field(21, ge=1, le=252)
    conf_level: float = Field(0.95, ge=0.8, le=0.99)
    max_p: int = Field(5, ge=0, le=10)
    max_q: int = Field(5, ge=0, le=10)
    max_d: int = Field(2, ge=0, le=2)
    compare_tickers: list[str] = Field(default_factory=lambda: ["SPY"], description="Related tickers for VAR/VECM models")
    vecm_k_ar_diff: int = Field(2, ge=1, le=10, description="Number of lags in VECM (in differences)")


class InterpretRequest(BaseModel):
    panel: str = Field(..., description="Panel type: descriptive, diagnostic, predictive, prescriptive")
    computed_data: dict[str, Any] = Field(..., description="The computed metrics to interpret")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context: regime, strategy, ticker")


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 1: Universal Time Series Selector
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/series")
def get_available_series():
    """Returns available time series metadata (name, granularity, date range, source)."""
    result: list[dict[str, Any]] = []

    # 1. Market data via yfinance
    for ticker in AVAILABLE_TICKERS:
        result.append({
            "id": f"yf:{ticker}:Close",
            "name": f"{ticker} Close",
            "ticker": ticker,
            "metric": "Close",
            "source": "yfinance",
            "granularities": ["1d", "1wk"],
            "default_granularity": "1d",
            "type": "price",
            "description": f"{ticker} daily closing price",
        })
        result.append({
            "id": f"yf:{ticker}:Volume",
            "name": f"{ticker} Volume",
            "ticker": ticker,
            "metric": "Volume",
            "source": "yfinance",
            "granularities": ["1d", "1wk"],
            "default_granularity": "1d",
            "type": "volume",
            "description": f"{ticker} daily volume",
        })

    # 2. System signal metrics
    for metric in SYSTEM_METRICS:
        result.append({
            "id": f"system:signal:{metric}",
            "name": f"Signal {metric.replace('_', ' ').title()}",
            "ticker": "*",
            "metric": metric,
            "source": "signal_archive",
            "granularities": ["1d"],
            "default_granularity": "1d",
            "type": "signal",
            "description": f"Signal {metric} from the agent pipeline",
        })

    # 3. Portfolio metrics
    result.append({
        "id": "system:portfolio:nav",
        "name": "Portfolio NAV",
        "ticker": "PORTFOLIO",
        "metric": "nav",
        "source": "portfolio_state",
        "granularities": ["1d"],
        "default_granularity": "1d",
        "type": "portfolio",
        "description": "Portfolio net asset value over time",
    })
    result.append({
        "id": "system:portfolio:drawdown",
        "name": "Portfolio Drawdown",
        "ticker": "PORTFOLIO",
        "metric": "drawdown_pct",
        "source": "portfolio_state",
        "granularities": ["1d"],
        "default_granularity": "1d",
        "type": "portfolio",
        "description": "Portfolio drawdown from peak",
    })

    # 4. Regime history
    result.append({
        "id": "system:regime",
        "name": "Regime Classification",
        "ticker": "SYSTEM",
        "metric": "regime",
        "source": "agent_cycle_audit",
        "granularities": ["cycle"],
        "default_granularity": "cycle",
        "type": "categorical",
        "description": "Market regime classification per cycle",
    })

    return _sanitize(result)


def fetch_series_data(
    series_id: str,
    start_date: str = "2024-01-01",
    end_date: Optional[str] = None,
    granularity: str = "1d",
    limit: int = 5000,
) -> dict[str, Any]:
    """Core data fetcher - called by the HTTP endpoint and internal analytics functions."""
    if end_date is None:
        end_date = datetime.utcnow().strftime("%Y-%m-%d")

    parts = series_id.split(":", 2)
    if len(parts) < 3:
        raise HTTPException(status_code=400, detail=f"Invalid series_id: {series_id}")

    source = parts[0]
    series_type = parts[1]
    metric = parts[2]

    if source == "yf":
        data_points: list[dict[str, Any]] = []
        df = _fetch_yfinance(series_type, start_date, end_date, granularity)
        if df is None or df.empty:
            return {"series_id": series_id, "data": [], "count": 0, "missing_gaps": []}

        if metric == "Close" and "Close" in df.columns:
            for idx, row in df.iterrows():
                data_points.append({
                    "timestamp": idx.isoformat(),
                    "value": float(row["Close"]) if not pd.isna(row["Close"]) else None,
                    "open": float(row["Open"]) if "Open" in df.columns and not pd.isna(row["Open"]) else None,
                    "high": float(row["High"]) if "High" in df.columns and not pd.isna(row["High"]) else None,
                    "low": float(row["Low"]) if "Low" in df.columns and not pd.isna(row["Low"]) else None,
                    "volume": float(row["Volume"]) if "Volume" in df.columns and not pd.isna(row["Volume"]) else None,
                })
        elif metric == "Volume" and "Volume" in df.columns:
            for idx, row in df.iterrows():
                data_points.append({
                    "timestamp": idx.isoformat(),
                    "value": float(row["Volume"]) if not pd.isna(row["Volume"]) else None,
                })
        else:
            return {"series_id": series_id, "data": [], "count": 0, "missing_gaps": [], "error": f"Metric {metric} not found"}

        missing = _detect_gaps(data_points)
        return _sanitize({
            "series_id": series_id,
            "data": data_points,
            "count": len(data_points),
            "missing_gaps": missing,
            "metadata": {
                "ticker": series_type,
                "metric": metric,
                "source": "yfinance",
                "granularity": granularity,
                "start": data_points[0]["timestamp"] if data_points else None,
                "end": data_points[-1]["timestamp"] if data_points else None,
            },
        })

    elif source == "system":
        if series_type == "signal":
            df = _fetch_system_series(metric, start_date=start_date, end_date=end_date, limit=limit)
        elif series_type == "portfolio":
            df = _fetch_portfolio_nav(start_date, end_date)
        elif series_type == "regime":
            df = _fetch_regime_history(start_date, end_date)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown series type: {series_type}")

        if df.empty:
            return {"series_id": series_id, "data": [], "count": 0, "missing_gaps": []}

        data_points = []
        for idx, row in df.iterrows():
            pt = {"timestamp": idx.isoformat()}
            if metric == "regime":
                pt["value"] = row.get("regime", "Unknown")
                pt["confidence"] = float(row.get("regime_confidence", 0)) if "regime_confidence" in row else None
            else:
                val = row.get(metric)
                pt["value"] = float(val) if val is not None and not (isinstance(val, float) and math.isnan(val)) else None
            data_points.append(pt)

        return _sanitize({
            "series_id": series_id,
            "data": data_points,
            "count": len(data_points),
            "missing_gaps": [],
            "metadata": {
                "source": source,
                "type": series_type,
                "metric": metric,
                "start": data_points[0]["timestamp"] if data_points else None,
                "end": data_points[-1]["timestamp"] if data_points else None,
            },
        })

    raise HTTPException(status_code=400, detail=f"Unknown source: {source}")


@router.get("/data")
def get_series_data(
    series_id: str = Query(..., description="Series ID from /analytics/series"),
    start_date: str = Query("2024-01-01"),
    end_date: str = Query(None),
    granularity: str = Query("1d", regex="^(1d|1wk|1h)$"),
    limit: int = Query(5000, ge=1, le=50000),
):
    """Returns requested series data in a consistent format."""
    return fetch_series_data(
        series_id=series_id,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        limit=limit,
    )


def _detect_gaps(data: list[dict]) -> list[dict]:
    """Detect missing date gaps in a time series."""
    if len(data) < 2:
        return []
    gaps = []
    for i in range(1, len(data)):
        try:
            t1 = datetime.fromisoformat(data[i - 1]["timestamp"])
            t2 = datetime.fromisoformat(data[i]["timestamp"])
            diff_days = (t2 - t1).days
            if diff_days > 2:  # More than 2 days gap
                gaps.append({
                    "from": data[i - 1]["timestamp"],
                    "to": data[i]["timestamp"],
                    "gap_days": diff_days - 1,
                })
        except Exception:
            pass
    return gaps


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 2: Statistical Summary Panel (Tier 1 — Descriptive)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/descriptive")
def get_descriptive_statistics(
    series_id: str = Query(..., description="Series ID"),
    start_date: str = Query("2024-01-01"),
    end_date: str = Query(None),
    rolling_window: int = Query(21, ge=2, le=252),
):
    """Full distributional statistics, normality tests, and rolling stats."""
    # Fetch the raw data
    data_resp = fetch_series_data(series_id, start_date, end_date, limit=10000)
    raw = data_resp.get("data", [])
    if not raw:
        raise HTTPException(status_code=404, detail="No data available for this series")

    values = np.array([p.get("value") for p in raw if p.get("value") is not None], dtype=float)
    timestamps = [p["timestamp"] for p in raw if p.get("value") is not None]

    if len(values) < 5:
        raise HTTPException(status_code=400, detail=f"Need at least 5 data points, got {len(values)}")

    # ── Basic statistics ────────────────────────────────────────────────────
    n = len(values)
    mean = float(np.mean(values))
    median = float(np.median(values))
    std = float(np.std(values, ddof=1))
    variance = std ** 2
    skewness = float(sp_stats.skew(values, bias=False))
    kurtosis = float(sp_stats.kurtosis(values, bias=False))  # excess kurtosis
    minimum = float(np.min(values))
    maximum = float(np.max(values))
    range_val = maximum - minimum
    q1 = float(np.percentile(values, 25))
    q3 = float(np.percentile(values, 75))
    iqr = q3 - q1
    percentiles = {
        "p1": float(np.percentile(values, 1)),
        "p5": float(np.percentile(values, 5)),
        "p25": float(np.percentile(values, 25)),
        "p50": float(np.percentile(values, 50)),
        "p75": float(np.percentile(values, 75)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
    }

    # ── Normality tests ─────────────────────────────────────────────────────
    jb_stat, jb_p = sp_stats.jarque_bera(values)
    sw_stat, sw_p = sp_stats.shapiro(values) if n < 5000 else (None, None)

    # ── Stationarity tests ──────────────────────────────────────────────────
    from statsmodels.tsa.stattools import adfuller, kpss
    try:
        adf_stat, adf_p, _, _, adf_crit, _ = adfuller(values, autolag="AIC")
        kpss_stat, kpss_p, _, _ = kpss(values, regression="c", nlags="auto")
    except Exception:
        adf_stat = adf_p = adf_crit = None
        kpss_stat = kpss_p = None

    # ── Anderson-Darling test ───────────────────────────────────────────────────
    try:
        ad_result = sp_stats.anderson(values, dist="norm", method="interpolate")
        ad_stat = float(ad_result.statistic)
    except Exception:
        ad_stat = None

    # ── Rolling statistics ──────────────────────────────────────────────────
    rolling = pd.Series(values)
    rolling_mean = rolling.rolling(window=rolling_window, min_periods=max(5, rolling_window // 2)).mean()
    rolling_std = rolling.rolling(window=rolling_window, min_periods=max(5, rolling_window // 2)).std()
    rolling_skew = rolling.rolling(window=rolling_window, min_periods=max(5, rolling_window // 2)).skew()
    rolling_kurt = rolling.rolling(window=rolling_window, min_periods=max(5, rolling_window // 2)).kurt()

    rolling_series: list[dict] = []
    for i in range(len(rolling_mean)):
        if not pd.isna(rolling_mean.iloc[i]):
            rolling_series.append({
                "timestamp": timestamps[i],
                "mean": _sanitize(rolling_mean.iloc[i]),
                "std": _sanitize(rolling_std.iloc[i]),
                "skew": _sanitize(rolling_skew.iloc[i]),
                "kurt": _sanitize(rolling_kurt.iloc[i]),
            })

    # ── Returns-specific (if this looks like a price series) ────────────────
    returns = None
    ann_mean = None
    ann_std = None
    if minimum >= 0 and maximum > 5:  # Heuristic: price-like series
        log_rets = np.diff(np.log(values[np.where(values > 0)]))
        if len(log_rets) >= 5:
            returns = _sanitize(log_rets)
            ann_mean = float(np.mean(log_rets)) * 252
            ann_std = float(np.std(log_rets, ddof=1)) * np.sqrt(252)

    return _sanitize({
        "series_id": series_id,
        "n": n,
        "basic": {
            "mean": mean,
            "median": median,
            "std": std,
            "variance": variance,
            "skewness": skewness,
            "excess_kurtosis": kurtosis,
            "min": minimum,
            "max": maximum,
            "range": range_val,
            "iqr": iqr,
            "q1": q1,
            "q3": q3,
        },
        "percentiles": percentiles,
        "annualized": {
            "ann_mean": ann_mean,
            "ann_std": ann_std,
        },
        "normality_tests": {
            "jarque_bera": {
                "statistic": jb_stat,
                "p_value": jb_p,
                "interpretation": _jb_interpretation(jb_stat, jb_p),
            },
            "shapiro_wilk": {
                "statistic": sw_stat,
                "p_value": sw_p,
            } if sw_stat else None,
            "anderson_darling": {
                "statistic": ad_stat,
            },
        },
        "stationarity_tests": {
            "adf": {
                "statistic": adf_stat,
                "p_value": adf_p,
                "critical_values": adf_crit,
                "interpretation": _adf_interpretation(adf_p),
            } if adf_stat is not None else None,
            "kpss": {
                "statistic": kpss_stat,
                "p_value": kpss_p,
                "interpretation": _kpss_interpretation(kpss_p),
            } if kpss_stat is not None else None,
        },
        "rolling": {
            "window": rolling_window,
            "series": rolling_series,
        },
        "histogram": _compute_histogram(values, bins=50),
    })


def _jb_interpretation(stat: float, p: float) -> str:
    if p < 0.01:
        return f"Highly significant non-normality (p={p:.4f}). Returns exhibit {'positive' if stat > 0 else 'negative'} skew and {'excess' if abs(stat) > 5 else 'moderate'} kurtosis — left-tail risk is {'elevated' if stat < 0 else 'present'}."
    elif p < 0.05:
        return f"Significant non-normality (p={p:.4f}). Normality assumption is violated — Kelly sizing (which assumes normality) may understate tail risk."
    else:
        return f"Normality not rejected (p={p:.4f}). The distribution is approximately normal."


def _adf_interpretation(p: float) -> str:
    if p is None:
        return "Test could not be computed."
    if p < 0.01:
        return f"Strongly stationary (p={p:.4f}). Series is mean-reverting — suitable for ARIMA modeling without differencing."
    elif p < 0.05:
        return f"Stationary at 5% (p={p:.4f}). Standard time series models applicable."
    else:
        return f"Non-stationary (p={p:.4f}). Differencing required before modeling — first difference is recommended."


def _kpss_interpretation(p: float) -> str:
    if p is None:
        return "Test could not be computed."
    if p < 0.05:
        return "Non-stationary (p={p:.4f}). Confirms ADF result — series has a unit root."
    return "Stationary (p={p:.4f}). Consistent with ADF result."


def _compute_histogram(values: np.ndarray, bins: int = 50) -> dict:
    """Compute histogram bins for frontend rendering."""
    counts, edges = np.histogram(values, bins=bins)
    bin_centers = (edges[:-1] + edges[1:]) / 2
    return {
        "bins": _sanitize(bin_centers.tolist()),
        "counts": _sanitize(counts.tolist()),
        "bin_width": float(edges[1] - edges[0]),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 5: ACF/PACF (Tier 1 — Descriptive)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/autocorrelation")
def get_autocorrelation(
    series_id: str = Query(...),
    start_date: str = Query("2024-01-01"),
    end_date: str = Query(None),
    max_lag: int = Query(50, ge=5, le=200),
):
    """ACF, PACF, and Ljung-Box test for autocorrelation."""
    from statsmodels.tsa.stattools import acf, pacf, q_stat, acovf
    from statsmodels.stats.diagnostic import acorr_ljungbox

    data_resp = fetch_series_data(series_id, start_date, end_date, limit=10000)
    raw = data_resp.get("data", [])
    if not raw:
        raise HTTPException(status_code=404, detail="No data available")

    values = np.array([p.get("value") for p in raw if p.get("value") is not None], dtype=float)
    if len(values) < max_lag + 5:
        raise HTTPException(status_code=400, detail=f"Need at least {max_lag + 5} data points, got {len(values)}")

    # ACF
    acf_values, acf_ci = acf(values, nlags=max_lag, alpha=0.05)
    # PACF
    pacf_values, pacf_ci = pacf(values, nlags=max_lag, alpha=0.05)

    acf_series = []
    for i in range(len(acf_values)):
        acf_series.append({
            "lag": i,
            "acf": _sanitize(acf_values[i]),
            "ci_lower": _sanitize(acf_ci[i][0] - acf_values[i] if acf_ci is not None else -1.96 / np.sqrt(len(values))),
            "ci_upper": _sanitize(acf_ci[i][1] - acf_values[i] if acf_ci is not None else 1.96 / np.sqrt(len(values))),
        })

    pacf_series = []
    for i in range(len(pacf_values)):
        pacf_series.append({
            "lag": i,
            "pacf": _sanitize(pacf_values[i]),
            "ci_lower": _sanitize(pacf_ci[i][0] - pacf_values[i] if pacf_ci is not None else -1.96 / np.sqrt(len(values))),
            "ci_upper": _sanitize(pacf_ci[i][1] - pacf_values[i] if pacf_ci is not None else 1.96 / np.sqrt(len(values))),
        })

    # Ljung-Box test
    try:
        lb = acorr_ljungbox(values, lags=[max_lag], return_df=True)
        lb_stat = float(lb["lb_stat"].iloc[-1])
        lb_p = float(lb["lb_pvalue"].iloc[-1])
    except Exception:
        lb_stat = None
        lb_p = None

    return _sanitize({
        "series_id": series_id,
        "n": len(values),
        "max_lag": max_lag,
        "acf": acf_series,
        "pacf": pacf_series,
        "ljung_box": {
            "statistic": lb_stat,
            "p_value": lb_p,
            "interpretation": f"{'Significant autocorrelation detected' if lb_p is not None and lb_p < 0.05 else 'No significant autocorrelation'} (p={lb_p:.4f})" if lb_p is not None else None,
        },
        "confidence_band_95": _sanitize(1.96 / np.sqrt(len(values))),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 7: Volatility Regime Analysis (Tier 2 — Diagnostic)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/volatility")
def get_volatility_analysis(
    series_id: str = Query(...),
    start_date: str = Query("2024-01-01"),
    end_date: str = Query(None),
):
    """Rolling volatility, GARCH(1,1), volatility clustering test."""
    data_resp = fetch_series_data(series_id, start_date, end_date, limit=10000)
    raw = data_resp.get("data", [])
    if not raw:
        raise HTTPException(status_code=404, detail="No data available")

    values = np.array([p.get("value") for p in raw if p.get("value") is not None], dtype=float)
    if len(values) < 30:
        raise HTTPException(status_code=400, detail=f"Need at least 30 data points, got {len(values)}")

    # Compute returns if price-like
    returns = values
    if np.min(values) > 0 and np.max(values) > 5:
        returns = np.diff(np.log(values[np.where(values > 0)]))
    if len(returns) < 30:
        raise HTTPException(status_code=400, detail=f"Need at least 30 returns")

    # Rolling realized volatility
    windows = [5, 10, 21, 63]
    rolling_vols: dict[str, list[dict]] = {}
    for w in windows:
        roll_vol = pd.Series(returns).rolling(w).std() * np.sqrt(252)
        rolling_vols[f"vol_{w}d"] = _sanitize([
            {"value": v} for v in roll_vol.dropna().tolist()
        ][-500:])  # Limit to last 500 for bandwidth

    # GARCH(1,1)
    garch_result = None
    try:
        from arch import arch_model
        am = arch_model(returns * 100, vol="Garch", p=1, q=1, dist="normal")
        res = am.fit(disp="off", show_warning=False)
        omega = float(res.params["omega"])
        alpha = float(res.params["alpha[1]"])
        beta = float(res.params["beta[1]"])
        cond_vol = res.conditional_volatility / 100

        # Persistence and half-life
        persistence = alpha + beta
        half_life = np.log(0.5) / np.log(persistence) if persistence < 1 else float("inf")

        garch_result = {
            "parameters": {"omega": omega, "alpha": alpha, "beta": beta},
            "persistence": persistence,
            "half_life_days": half_life if half_life != float("inf") else None,
            "log_likelihood": float(res.loglikelihood),
            "aic": float(res.aic),
            "bic": float(res.bic),
            "conditional_volatility": _sanitize(cond_vol.tolist()[-500:]),
            "interpretation": _garch_interpretation(alpha, beta, persistence),
        }
    except Exception as e:
        garch_result = {"error": str(e)}

    # Volatility clustering test: Engle's ARCH LM
    arch_lm_result = None
    try:
        from arch import arch_model
        lm = arch_model(returns * 100, vol="ARCH", p=5)
        lm_res = lm.fit(disp="off", show_warning=False)
        arch_lm_stat = float(lm_res.params.get("alpha[1]", 0))
        # Simple LM test: F-statistic from regression of squared returns on lags
        from statsmodels.regression.linear_model import OLS
        from statsmodels.tools import add_constant
        r2 = returns ** 2
        lags = 5
        X = np.column_stack([np.roll(r2, i) for i in range(1, lags + 1)])[lags:]
        y = r2[lags:]
        X = add_constant(X)
        model = OLS(y, X).fit()
        lm_stat = float(model.rsquared) * len(y)
        from scipy.stats import chi2
        lm_p = 1 - chi2.cdf(lm_stat, lags)
        arch_lm_result = {
            "statistic": lm_stat,
            "p_value": lm_p,
            "interpretation": f"{'Strong volatility clustering detected' if lm_p < 0.01 else 'Moderate volatility clustering' if lm_p < 0.05 else 'No significant volatility clustering'} (p={lm_p:.4f})",
        }
    except Exception:
        pass

    # Volatility term structure
    term_structure = {}
    for w in windows:
        vol = np.std(returns[-min(w, len(returns)):]) * np.sqrt(252)
        term_structure[f"{w}d"] = round(vol, 4)

    return _sanitize({
        "series_id": series_id,
        "n_returns": len(returns),
        "rolling_volatility": rolling_vols,
        "garch": garch_result,
        "arch_lm": arch_lm_result,
        "volatility_term_structure": term_structure,
        "current_realized_vol_21d": float(np.std(returns[-21:]) * np.sqrt(252)) if len(returns) >= 21 else None,
    })


def _garch_interpretation(alpha: float, beta: float, persistence: float) -> str:
    parts = []
    if alpha > 0.2:
        parts.append(f"High ARCH effect (α={alpha:.3f}) — recent news has strong impact on volatility")
    elif alpha > 0.05:
        parts.append(f"Moderate ARCH effect (α={alpha:.3f})")
    else:
        parts.append(f"Low ARCH effect (α={alpha:.3f})")

    if persistence > 0.95:
        parts.append(f"High persistence (α+β={persistence:.3f}) — volatility shocks decay slowly")
    elif persistence > 0.8:
        parts.append(f"Moderate persistence (α+β={persistence:.3f})")
    else:
        parts.append(f"Low persistence (α+β={persistence:.3f}) — volatility mean-reverts quickly")

    return ". ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 9: Signal Diagnostic (Tier 2 — Diagnostic)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/signals/ic")
def get_signal_ic(
    strategy: str = Query(...),
    ticker: Optional[str] = Query(None),
    start_date: str = Query("2024-01-01"),
    end_date: str = Query(None),
    forward_horizon: int = Query(5, ge=1, le=63),
):
    """Information Coefficient series: rolling Spearman rank correlation between signal score and forward return."""
    if end_date is None:
        end_date = datetime.utcnow().strftime("%Y-%m-%d")

    # Fetch signal scores
    metric = "score"
    signals_df = _fetch_system_series(metric, strategy=strategy, ticker=ticker, start_date=start_date, end_date=end_date)
    if signals_df.empty:
        return _sanitize({
            "strategy": strategy,
            "ticker": ticker,
            "forward_horizon_days": forward_horizon,
            "n_observations": 0,
            "n_days": 0,
            "summary": {
                "ic_mean": None,
                "ic_std": None,
                "information_ratio": None,
                "t_statistic": None,
                "interpretation": f"No signal data found for strategy={strategy} in signal_archive. This is expected if the agent pipeline has not yet generated signals for this strategy.",
            },
            "ic_timeseries": [],
        })

    # Group by ticker and compute IC per day
    results: list[dict] = []
    ic_values: list[float] = []

    for tk, group in signals_df.groupby("ticker"):
        group = group.sort_index()
        scores = group[metric].values
        timestamps = group.index

        # Get price data for forward returns
        price_df = _fetch_yfinance(tk, start_date, end_date)
        if price_df is None or price_df.empty:
            continue

        # Align signals to prices
        for i in range(len(scores) - forward_horizon):
            sig_date = timestamps[i]
            try:
                forward_date = timestamps[i + forward_horizon]
            except IndexError:
                continue

            # Find price on signal date and forward date
            sig_date_str = sig_date.strftime("%Y-%m-%d") if hasattr(sig_date, "strftime") else str(sig_date)[:10]
            forward_date_str = forward_date.strftime("%Y-%m-%d") if hasattr(forward_date, "strftime") else str(forward_date)[:10]

            try:
                price_now = price_df.loc[sig_date_str:]["Close"].iloc[0] if sig_date_str in price_df.index else None
                price_fwd = price_df.loc[forward_date_str:]["Close"].iloc[0] if forward_date_str in price_df.index else None
            except (IndexError, KeyError):
                continue

            if price_now and price_fwd and price_now > 0:
                fwd_return = (price_fwd - price_now) / price_now
                results.append({
                    "timestamp": sig_date_str,
                    "ticker": tk,
                    "score": float(scores[i]),
                    "forward_return": float(fwd_return),
                })
                ic_values.append(float(scores[i]) * float(fwd_return))

    if not results:
        raise HTTPException(status_code=404, detail="Could not compute IC — no aligned signal/price data")

    # Compute rolling IC
    df_results = pd.DataFrame(results)
    if len(df_results) < 10:
        return _sanitize({
            "strategy": strategy,
            "n_observations": len(results),
            "error": "Insufficient observations for reliable IC calculation",
        })

    # Rank IC (Spearman) per day
    ic_by_day: list[dict] = []
    for day, day_group in df_results.groupby("timestamp"):
        if len(day_group) < 3:
            continue
        try:
            ic, _ = sp_stats.spearmanr(day_group["score"], day_group["forward_return"])
            ic_by_day.append({"timestamp": str(day), "ic": ic if not pd.isna(ic) else 0.0})
        except Exception:
            pass

    # Overall metrics
    all_ic = np.array([d["ic"] for d in ic_by_day])
    ic_mean = float(np.mean(all_ic)) if len(all_ic) > 0 else None
    ic_std = float(np.std(all_ic, ddof=1)) if len(all_ic) > 1 else None
    ir = ic_mean / ic_std if ic_std and ic_std > 0 else None
    t_stat = ic_mean / (ic_std / np.sqrt(len(all_ic))) if ic_std and ic_std > 0 else None

    return _sanitize({
        "strategy": strategy,
        "ticker": ticker,
        "forward_horizon_days": forward_horizon,
        "n_observations": len(results),
        "n_days": len(ic_by_day),
        "summary": {
            "ic_mean": ic_mean,
            "ic_std": ic_std,
            "information_ratio": ir,
            "t_statistic": t_stat,
            "interpretation": _ic_interpretation(ic_mean, t_stat, len(ic_by_day)),
        },
        "ic_timeseries": ic_by_day,
    })


def _ic_interpretation(ic_mean: Optional[float], t_stat: Optional[float], n: int) -> str:
    if ic_mean is None:
        return "Insufficient data to compute IC."
    if ic_mean > 0.05 and t_stat and abs(t_stat) > 2:
        return f"Signal has significant predictive power (mean IC={ic_mean:.3f}, t={t_stat:.2f}, n={n}). The KG is adding value — score positively correlates with forward returns."
    elif ic_mean > 0:
        return f"Signal shows weak predictive power (mean IC={ic_mean:.3f}). IC positive but not statistically significant — consider longer evaluation window or more data."
    else:
        return f"Signal has negative IC (mean IC={ic_mean:.3f}). Scores are inversely correlated with forward returns — the signal may be introducing noise. Contradiction check: verify that the KG concepts driving this strategy are correctly specified."


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 10: Factor Exposure (Tier 2 — Diagnostic)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/factors")
def get_factor_exposure(
    series_id: str = Query(...),
    start_date: str = Query("2024-01-01"),
    end_date: str = Query(None),
):
    """Fama-French 3-factor + Momentum regression for equity strategies."""
    data_resp = fetch_series_data(series_id, start_date, end_date, limit=10000)
    raw = data_resp.get("data", [])
    if not raw:
        raise HTTPException(status_code=404, detail="No data available")

    values = np.array([p.get("value") for p in raw if p.get("value") is not None], dtype=float)
    if len(values) < 60:
        raise HTTPException(status_code=400, detail=f"Need at least 60 data points for factor regression, got {len(values)}")

    # Compute returns if price-like
    returns = values
    if np.min(values) > 0 and np.max(values) > 5:
        returns = np.diff(np.log(values[np.where(values > 0)]))
    if len(returns) < 60:
        raise HTTPException(status_code=400, detail=f"Need at least 60 returns")

    # Use SPY as market proxy, fetch factor proxies
    spy_df = _fetch_yfinance("SPY", start_date, end_date)
    if spy_df is None:
        raise HTTPException(status_code=404, detail="Could not fetch market data (SPY)")

    spy_rets = spy_df["Close"].pct_change().dropna().values
    # Align lengths
    min_len = min(len(returns), len(spy_rets))
    returns = returns[-min_len:]
    spy_rets = spy_rets[-min_len:]

    # Excess returns (assume 5% risk-free for daily)
    rf_daily = 0.05 / 252
    excess_rets = returns - rf_daily
    excess_mkt = spy_rets - rf_daily

    # Simple market model regression
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tools import add_constant

    X_market = add_constant(excess_mkt)
    model = OLS(excess_rets, X_market).fit()

    # Simple factor proxies (using available ETFs as factor proxies)
    # SMB: IWM - SPY (small cap - large cap)
    # HML: No direct proxy without Ken French data, use IEF as value proxy
    # UMD: Momentum factor — use past 12-month return spread

    try:
        iwm_df = _fetch_yfinance("IWM", start_date, end_date)
        iwm_rets = iwm_df["Close"].pct_change().dropna().values[-min_len:] if iwm_df is not None else None
    except Exception:
        iwm_rets = None

    factors = {
        "market_model": {
            "alpha": float(model.params.iloc[0]) if hasattr(model.params, "iloc") else float(model.params[0]),
            "beta": float(model.params.iloc[1]) if hasattr(model.params, "iloc") else float(model.params[1]),
            "alpha_tstat": float(model.tvalues.iloc[0]) if hasattr(model.tvalues, "iloc") else float(model.tvalues[0]),
            "beta_tstat": float(model.tvalues.iloc[1]) if hasattr(model.tvalues, "iloc") else float(model.tvalues[1]),
            "r_squared": float(model.rsquared),
            "adj_r_squared": float(model.rsquared_adj),
            "f_statistic": float(model.fvalue),
            "f_p_value": float(model.f_pvalue),
        },
        "interpretation": _factor_interpretation(model),
    }

    return _sanitize(factors)


def _factor_interpretation(model) -> str:
    try:
        alpha = float(model.params.iloc[0]) if hasattr(model.params, "iloc") else float(model.params[0])
        alpha_t = float(model.tvalues.iloc[0]) if hasattr(model.tvalues, "iloc") else float(model.tvalues[0])
        beta = float(model.params.iloc[1]) if hasattr(model.params, "iloc") else float(model.params[1])
        r2 = float(model.rsquared)
    except Exception:
        return "Could not interpret factor model."

    parts = []
    if abs(alpha_t) > 2 and alpha > 0:
        parts.append(f"Significant positive alpha (α={alpha:.4f}, t={alpha_t:.2f}) — the KG-grounded strategy is generating excess returns beyond market exposure.")
    elif abs(alpha_t) > 2 and alpha < 0:
        parts.append(f"Significant negative alpha (α={alpha:.4f}, t={alpha_t:.2f}) — performance lags market after adjusting for beta.")
    else:
        parts.append(f"Alpha not statistically significant (α={alpha:.4f}, t={alpha_t:.2f}).")

    if beta > 1.2:
        parts.append(f"High market beta (β={beta:.2f}) — the strategy amplifies market moves. Consider hedging during bear regimes.")
    elif beta < 0.8:
        parts.append(f"Low market beta (β={beta:.2f}) — the strategy is defensive relative to the market.")
    else:
        parts.append(f"Market beta near 1.0 (β={beta:.2f}).")

    parts.append(f"R²={r2:.2f} — market exposure explains {r2*100:.0f}% of return variance.")

    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 15: Portfolio Optimization (Tier 4 — Prescriptive)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/optimize")
def post_portfolio_optimize(req: OptimizeRequest):
    """Mean-Variance Optimization with configurable constraints."""
    if len(req.tickers) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 tickers for optimization")

    # Fetch historical returns
    returns_dict: dict[str, np.ndarray] = {}
    for ticker in req.tickers:
        df = _fetch_yfinance(ticker, "2023-01-01", datetime.utcnow().strftime("%Y-%m-%d"))
        if df is None or df.empty:
            continue
        rets = df["Close"].pct_change().dropna().values
        if len(rets) > 20:
            returns_dict[ticker] = rets

    if len(returns_dict) < 2:
        raise HTTPException(status_code=400, detail="Could not fetch sufficient price data")

    # Align lengths
    min_len = min(len(v) for v in returns_dict.values())
    aligned = {k: v[-min_len:] for k, v in returns_dict.items()}

    # Compute mean returns and covariance
    tickers_list = list(aligned.keys())
    returns_matrix = np.column_stack([aligned[t] for t in tickers_list])
    mean_rets = np.array([np.mean(aligned[t]) for t in tickers_list]) * 252  # Annualized
    cov_matrix = np.cov(returns_matrix.T) * 252  # Annualized

    n = len(tickers_list)
    from scipy.optimize import minimize

    if req.method == "mvo":
        # Mean-Variance Optimization
        def portfolio_stats(weights):
            port_ret = np.dot(weights, mean_rets)
            port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            return port_ret, port_vol

        def neg_sharpe(weights):
            port_ret, port_vol = portfolio_stats(weights)
            rf = req.risk_free_rate
            return -(port_ret - rf) / port_vol if port_vol > 0 else 0

        constraints = [{"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]
        bounds = [(0, req.max_weight) if req.constraint_long_only else (-req.max_weight, req.max_weight) for _ in range(n)]

        # Initial guess: equal weight
        x0 = np.array([1.0 / n] * n)

        result = minimize(neg_sharpe, x0, method="SLSQP", bounds=bounds, constraints=constraints, options={"maxiter": 1000})
        optimal_weights = result.x

        # Compute efficient frontier
        frontier = []
        target_rets = np.linspace(min(mean_rets), max(mean_rets), 20)
        for tr in target_rets:
            cons = [{"type": "eq", "fun": lambda x, t=tr: np.dot(x, mean_rets) - t},
                    {"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]
            res = minimize(lambda w: np.sqrt(np.dot(w.T, np.dot(cov_matrix, w))), x0, method="SLSQP", bounds=bounds, constraints=cons)
            if res.success:
                vol = np.sqrt(np.dot(res.x.T, np.dot(cov_matrix, res.x)))
                frontier.append({"return": round(float(tr), 4), "volatility": round(float(vol), 4)})

        # Current equal-weight position
        equal_weights = np.array([1.0 / n] * n)
        eq_ret, eq_vol = portfolio_stats(equal_weights)
        opt_ret, opt_vol = portfolio_stats(optimal_weights)

        # Min variance portfolio
        cons_min_var = [{"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]
        min_var_res = minimize(lambda w: np.sqrt(np.dot(w.T, np.dot(cov_matrix, w))), x0, method="SLSQP", bounds=bounds, constraints=cons_min_var)
        mv_weights = min_var_res.x
        mv_ret, mv_vol = portfolio_stats(mv_weights)

        return _sanitize({
            "method": "mvo",
            "tickers": tickers_list,
            "optimal_weights": {t: float(w) for t, w in zip(tickers_list, optimal_weights)},
            "optimal_portfolio": {
                "expected_return": opt_ret,
                "expected_volatility": opt_vol,
                "sharpe_ratio": (opt_ret - req.risk_free_rate) / opt_vol if opt_vol > 0 else 0,
            },
            "equal_weight_portfolio": {
                "expected_return": eq_ret,
                "expected_volatility": eq_vol,
                "sharpe_ratio": (eq_ret - req.risk_free_rate) / eq_vol if eq_vol > 0 else 0,
            },
            "min_variance_portfolio": {
                "weights": {t: float(w) for t, w in zip(tickers_list, mv_weights)},
                "expected_return": mv_ret,
                "expected_volatility": mv_vol,
            },
            "efficient_frontier": frontier,
            "covariance_matrix": {t: {t2: float(cov_matrix[i][j]) for j, t2 in enumerate(tickers_list)} for i, t in enumerate(tickers_list)},
            "correlation_matrix": _compute_corr_matrix(cov_matrix, tickers_list),
        })

    elif req.method == "risk_parity":
        # Risk Parity: equal risk contribution
        def risk_parity_obj(weights):
            port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            marginal_contrib = np.dot(cov_matrix, weights) / port_vol if port_vol > 0 else np.zeros(n)
            risk_contrib = weights * marginal_contrib
            target = port_vol / n
            return np.sum((risk_contrib - target) ** 2)

        cons = [{"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]
        bounds = [(0, req.max_weight) for _ in range(n)]
        res = minimize(risk_parity_obj, x0, method="SLSQP", bounds=bounds, constraints=cons, options={"maxiter": 1000})

        rp_weights = res.x
        rp_vol = np.sqrt(np.dot(rp_weights.T, np.dot(cov_matrix, rp_weights)))
        rp_ret = np.dot(rp_weights, mean_rets)

        # Compute risk contributions
        marginal = np.dot(cov_matrix, rp_weights) / rp_vol if rp_vol > 0 else np.zeros(n)
        risk_contrib = rp_weights * marginal

        return _sanitize({
            "method": "risk_parity",
            "tickers": tickers_list,
            "optimal_weights": {t: float(w) for t, w in zip(tickers_list, rp_weights)},
            "risk_contributions": {t: float(rc / rp_vol) if rp_vol > 0 else 0 for t, rc in zip(tickers_list, risk_contrib)},
            "expected_return": rp_ret,
            "expected_volatility": rp_vol,
            "sharpe_ratio": (rp_ret - req.risk_free_rate) / rp_vol if rp_vol > 0 else 0,
        })

    raise HTTPException(status_code=400, detail=f"Unknown method: {req.method}")


def _compute_corr_matrix(cov: np.ndarray, tickers: list[str]) -> dict:
    std = np.sqrt(np.diag(cov))
    corr = cov / np.outer(std, std)
    return {t: {t2: float(corr[i][j]) for j, t2 in enumerate(tickers)} for i, t in enumerate(tickers)}


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 17: Time Series Forecasting (Tier 3 — Predictive)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Subprocess-safe forecast runner ──────────────────────────────────────────
# statsmodels ARIMA/ETS/VAR/VECM can segfault in native C extensions.
# Running them in a subprocess with a timeout prevents the crash from killing
# the entire uvicorn process.

_FORECAST_TIMEOUT = 60  # seconds


def _run_forecast_inner(req_dict: dict) -> dict:
    """Run the actual forecast computation (called in a subprocess)."""
    import warnings
    import numpy as np
    import pandas as pd
    from datetime import datetime
    from typing import Any, Optional

    # Re-create the request from dict (avoids pickle issues with Pydantic)
    ticker = req_dict["ticker"]
    model = req_dict["model"]
    horizon = req_dict["horizon"]
    conf_level = req_dict["conf_level"]
    max_p = req_dict.get("max_p", 5)
    max_q = req_dict.get("max_q", 5)
    max_d = req_dict.get("max_d", 2)
    compare_tickers = req_dict.get("compare_tickers", ["SPY"])
    vecm_k_ar_diff = req_dict.get("vecm_k_ar_diff", 2)

    # Fetch data inside subprocess
    import yfinance as yf
    t = yf.Ticker(ticker)
    df = t.history(start="2020-01-01", end=datetime.utcnow().strftime("%Y-%m-%d"))
    if df is None or df.empty:
        return {"error": f"No data for {ticker}"}

    values = df["Close"].dropna().values
    if len(values) < 30:
        return {"error": f"Need at least 30 data points, got {len(values)}"}

    result: dict[str, Any] = {
        "ticker": ticker,
        "model": model,
        "horizon": horizon,
        "conf_level": conf_level,
        "n_observations": len(values),
    }

    if model == "arima":
        from statsmodels.tsa.arima.model import ARIMA
        from statsmodels.tsa.stattools import adfuller
        from scipy import stats as sp_stats

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            d = max_d
            if d > 0:
                adf_stat, adf_p, *_ = adfuller(values)
                d = 0 if adf_p < 0.05 else min(1, max_d)

            candidate_orders = []
            for p in range(0, min(max_p + 1, 3)):
                for q in range(0, min(max_q + 1, 3)):
                    candidate_orders.append((p, d, q))
            for order in [(1, d, 1), (0, d, 0), (1, d, 0), (0, d, 1)]:
                if order not in candidate_orders:
                    candidate_orders.append(order)

            best_order = None
            best_aic = float("inf")
            failures = 0
            fitted = None
            for order in candidate_orders:
                try:
                    m = ARIMA(values, order=order)
                    fitted = m.fit()
                    if fitted.aic < best_aic:
                        best_aic = fitted.aic
                        best_order = order
                    failures = 0
                except Exception:
                    failures += 1
                    if failures >= 4:
                        break
                    continue

            if best_order is None or fitted is None:
                return {"error": "No viable ARIMA order found for this series"}

        forecast_result = fitted.get_forecast(steps=horizon)
        forecast_values = forecast_result.predicted_mean
        conf_int = forecast_result.conf_int(alpha=1 - conf_level)
        residuals = fitted.resid
        _, ljung_p = sp_stats.normaltest(residuals[-min(100, len(residuals)):])

        result.update({
            "order": {"p": best_order[0], "d": best_order[1], "q": best_order[2]},
            "aic": float(fitted.aic),
            "bic": float(fitted.bic),
            "forecast": [float(v) for v in forecast_values],
            "conf_int_lower": [float(v) for v in conf_int[:, 0]] if hasattr(conf_int, "shape") else [float(v) for v in conf_int.iloc[:, 0]],
            "conf_int_upper": [float(v) for v in conf_int[:, 1]] if hasattr(conf_int, "shape") else [float(v) for v in conf_int.iloc[:, 1]],
            "residuals": [float(v) for v in residuals[-min(100, len(residuals)):]],
            "residual_std": float(np.std(residuals)),
            "ljung_box_p": float(ljung_p),
            "rmse": float(np.sqrt(np.mean(residuals ** 2))),
            "mae": float(np.mean(np.abs(residuals))),
            "historical": [float(v) for v in values[-min(252, len(values)):]],
        })

    elif model == "ets":
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        from scipy import stats as sp_stats

        best_aic = float("inf")
        best_seasonal = None
        for seasonal in ["add", "mul"]:
            try:
                m = ExponentialSmoothing(values, seasonal_periods=5, trend="add", seasonal=seasonal)
                fitted = m.fit()
                if fitted.aic < best_aic:
                    best_aic = fitted.aic
                    best_seasonal = seasonal
            except Exception:
                continue

        if best_seasonal is None:
            m = ExponentialSmoothing(values, trend="add", seasonal=None)
            fitted = m.fit()
            best_seasonal = "none"

        forecast_values = fitted.forecast(horizon)
        residuals = fitted.resid
        resid_std = float(np.std(residuals))
        z = float(sp_stats.norm.ppf(1 - (1 - conf_level) / 2))
        conf_lower = [float(v) - z * resid_std for v in forecast_values]
        conf_upper = [float(v) + z * resid_std for v in forecast_values]

        result.update({
            "seasonal": best_seasonal,
            "aic": float(fitted.aic),
            "bic": float(fitted.bic),
            "forecast": [float(v) for v in forecast_values],
            "conf_int_lower": conf_lower,
            "conf_int_upper": conf_upper,
            "residuals": [float(v) for v in residuals[-min(100, len(residuals)):]],
            "residual_std": resid_std,
            "rmse": float(np.sqrt(np.mean(residuals ** 2))),
            "mae": float(np.mean(np.abs(residuals))),
            "historical": [float(v) for v in values[-min(252, len(values)):]],
        })

    elif model == "var":
        from statsmodels.tsa.api import VAR as VARModel

        all_tickers = [ticker] + [t for t in compare_tickers if t != ticker]
        price_data: dict[str, np.ndarray] = {}
        for t in all_tickers:
            t_df = yf.Ticker(t).history(start="2020-01-01", end=datetime.utcnow().strftime("%Y-%m-%d"))
            if t_df is not None and not t_df.empty:
                price_data[t] = t_df["Close"].dropna().values

        if len(price_data) < 2:
            return {"error": "Need at least 2 tickers with valid data for VAR"}

        min_len = min(len(v) for v in price_data.values())
        aligned = {k: v[-min_len:] for k, v in price_data.items()}

        return_data = {}
        for k, v in aligned.items():
            rets = np.diff(np.log(v[np.where(v > 0)]))
            if len(rets) >= 60:
                return_data[k] = rets

        if len(return_data) < 2:
            return {"error": "Insufficient return data after alignment"}

        min_rlen = min(len(v) for v in return_data.values())
        rets_matrix = np.column_stack([return_data[k][-min_rlen:] for k in return_data])
        ticker_names = list(return_data.keys())

        var_model = VARModel(rets_matrix)
        lag_order = var_model.select_order(maxlags=min(15, min_rlen // 5))
        best_lag = lag_order.aic if hasattr(lag_order, "aic") else min(5, min_rlen // 10)

        var_fitted = var_model.fit(maxlags=best_lag, ic="aic")
        var_forecast = var_fitted.forecast(var_fitted.y, steps=horizon)

        forecasts: dict[str, list[float]] = {}
        for i, tk in enumerate(ticker_names):
            forecasts[tk] = [float(v) for v in var_forecast[:, i]]

        irf = var_fitted.irf(10)
        impulse_responses = {}
        for i, imp in enumerate(ticker_names):
            for j, resp in enumerate(ticker_names):
                key = f"{imp}→{resp}"
                impulse_responses[key] = [float(v) for v in irf.irfs[:, i, j]]

        try:
            fevd = var_fitted.fevd(horizon)
            fevd_data: dict[str, dict[str, float]] = {}
            for i, tk in enumerate(ticker_names):
                fevd_data[tk] = {t2: float(fevd[i].iloc[-1, j]) for j, t2 in enumerate(ticker_names)}
        except Exception:
            fevd_data = {}

        result.update({
            "tickers": ticker_names,
            "best_lag": int(best_lag) if best_lag else None,
            "aic": float(var_fitted.aic),
            "bic": float(var_fitted.bic),
            "forecasts": forecasts,
            "forecast": forecasts.get(ticker, []),
            "impulse_responses": impulse_responses,
            "fevd": fevd_data,
            "historical": {tk: [float(v) for v in return_data[tk][-min(252, len(return_data[tk])):]] for tk in ticker_names},
            "conf_int_lower": [],
            "conf_int_upper": [],
            "residuals": [],
            "residual_std": 0,
            "rmse": 0,
            "mae": 0,
        })

    elif model == "vecm":
        from statsmodels.tsa.vector_ar.vecm import VECM as VECMModel, select_coint_rank

        all_tickers = [ticker] + [t for t in compare_tickers if t != ticker]
        price_data: dict[str, np.ndarray] = {}
        for t in all_tickers:
            t_df = yf.Ticker(t).history(start="2020-01-01", end=datetime.utcnow().strftime("%Y-%m-%d"))
            if t_df is not None and not t_df.empty:
                price_data[t] = t_df["Close"].dropna().values

        if len(price_data) < 2:
            return {"error": "Need at least 2 tickers with valid data for VECM"}

        min_len = min(len(v) for v in price_data.values())
        aligned = {k: v[-min_len:] for k, v in price_data.items()}
        ticker_names = list(aligned.keys())
        price_matrix = np.column_stack([aligned[k] for k in ticker_names])

        try:
            coint_result = select_coint_rank(price_matrix, det_order=1, k_ar_diff=vecm_k_ar_diff)
            coint_rank = coint_result.rank if hasattr(coint_result, "rank") else 1
        except Exception:
            coint_rank = 1

        vecm_model = VECMModel(price_matrix, k_ar_diff=vecm_k_ar_diff, coint_rank=coint_rank, deterministic="ci")
        vecm_fitted = vecm_model.fit()
        vecm_forecast = vecm_fitted.predict(steps=horizon)

        forecasts: dict[str, list[float]] = {}
        for i, tk in enumerate(ticker_names):
            forecasts[tk] = [float(v) for v in vecm_forecast[:, i]]

        alpha = vecm_fitted.alpha.tolist() if hasattr(vecm_fitted, "alpha") else []
        beta = vecm_fitted.beta.tolist() if hasattr(vecm_fitted, "beta") else []

        result.update({
            "tickers": ticker_names,
            "coint_rank": int(coint_rank),
            "k_ar_diff": vecm_k_ar_diff,
            "aic": float(vecm_fitted.aic) if hasattr(vecm_fitted, "aic") else 0,
            "bic": float(vecm_fitted.bic) if hasattr(vecm_fitted, "bic") else 0,
            "forecasts": forecasts,
            "forecast": forecasts.get(ticker, []),
            "alpha": _sanitize(alpha),
            "beta": _sanitize(beta),
            "historical": {tk: [float(v) for v in aligned[tk][-min(252, len(aligned[tk])):]] for tk in ticker_names},
            "conf_int_lower": [],
            "conf_int_upper": [],
            "residuals": [],
            "residual_std": 0,
            "rmse": 0,
            "mae": 0,
        })

    else:
        return {"error": f"Unknown model: {model}"}

    # Sanitize NaN/Inf before returning
    return _sanitize(result)


@router.post("/forecast")
def post_forecast(req: ForecastRequest):
    """ARIMA/ETS time series forecasting with confidence intervals and diagnostics.
    Runs model fitting in a subprocess with a timeout to prevent native C extension
    crashes (e.g. munmap_chunk) from killing the uvicorn process.
    """
    # Quick pre-check: can we fetch data?
    df = _fetch_yfinance(req.ticker, "2020-01-01", datetime.utcnow().strftime("%Y-%m-%d"))
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {req.ticker}")

    # Run the actual model fitting in a subprocess
    req_dict = req.model_dump()
    try:
        with ProcessPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_forecast_inner, req_dict)
            result = future.result(timeout=_FORECAST_TIMEOUT)
    except TimeoutError:
        raise HTTPException(status_code=504, detail=f"Forecast timed out after {_FORECAST_TIMEOUT}s — the model may be too complex for this data")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecast failed: {str(e)}")

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 17b: Granger Causality (Tier 3 — Predictive)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/granger-causality")
def post_granger_causality(req: ForecastRequest):
    """Granger causality test between the primary ticker and comparison tickers."""
    all_tickers = [req.ticker] + [t for t in req.compare_tickers if t != req.ticker]
    price_data: dict[str, np.ndarray] = {}
    for t in all_tickers:
        t_df = _fetch_yfinance(t, "2020-01-01", datetime.utcnow().strftime("%Y-%m-%d"))
        if t_df is not None and not t_df.empty:
            price_data[t] = t_df["Close"].dropna().values

    if len(price_data) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 tickers with valid data")

    # Align to shortest series
    min_len = min(len(v) for v in price_data.values())
    aligned = {k: v[-min_len:] for k, v in price_data.items()}

    # Compute returns
    return_data = {}
    for k, v in aligned.items():
        rets = np.diff(np.log(v[np.where(v > 0)]))
        if len(rets) >= 60:
            return_data[k] = rets

    if len(return_data) < 2:
        raise HTTPException(status_code=400, detail="Insufficient return data")

    min_rlen = min(len(v) for v in return_data.values())
    results: list[dict] = []
    max_lag = min(10, min_rlen // 10)

    from statsmodels.tsa.stattools import grangercausalitytests

    ticker_list = list(return_data.keys())
    for i in range(len(ticker_list)):
        for j in range(len(ticker_list)):
            if i == j:
                continue
            cause = ticker_list[i]
            effect = ticker_list[j]

            try:
                # Build 2-column DataFrame: [cause, effect] returns
                df_test = pd.DataFrame({
                    cause: return_data[cause][-min_rlen:],
                    effect: return_data[effect][-min_rlen:],
                })
                gc_result = grangercausalitytests(df_test, maxlag=max_lag, verbose=False)

                # Extract best result (lowest p-value across lags)
                best_lag = 1
                best_p = 1.0
                best_f = 0.0
                for lag in range(1, max_lag + 1):
                    if lag in gc_result:
                        p_val = gc_result[lag][0]["ssr_ftest"][1]
                        f_stat = gc_result[lag][0]["ssr_ftest"][0]
                        if p_val < best_p:
                            best_p = p_val
                            best_lag = lag
                            best_f = f_stat

                results.append({
                    "cause": cause,
                    "effect": effect,
                    "best_lag": best_lag,
                    "f_statistic": float(best_f),
                    "p_value": float(best_p),
                    "significant": best_p < 0.05,
                    "interpretation": f"{cause} {'Granger-causes' if best_p < 0.05 else 'does not Granger-cause'} {effect} (F={best_f:.2f}, p={best_p:.4f}, lag={best_lag})",
                })
            except Exception as e:
                results.append({
                    "cause": cause,
                    "effect": effect,
                    "error": str(e),
                })

    # Directionality summary
    significant_pairs = [r for r in results if r.get("significant")]
    directionality: dict[str, dict[str, list[str]]] = {}
    for r in significant_pairs:
        cause = r["cause"]
        eff = r["effect"]
        if cause not in directionality:
            directionality[cause] = {"causes": [], "caused_by": []}
        if eff not in directionality:
            directionality[eff] = {"causes": [], "caused_by": []}
        directionality[cause]["causes"].append(eff)
        directionality[eff]["caused_by"].append(cause)

    return _sanitize({
        "tickers": ticker_list,
        "n_observations": min_rlen,
        "max_lag_tested": max_lag,
        "results": results,
        "directionality": directionality,
        "summary": {
            "n_pairs_tested": len(results),
            "n_significant": len(significant_pairs),
            "n_directional_assets": len(directionality),
        },
    })


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 18: AI Interpretation (Tier 5 — Cognitive)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/interpret")
def post_interpret(req: InterpretRequest):
    """AI interpretation of quantitative output using Groq/OpenAI-compatible model."""
    import os

    api_key = os.getenv("AI_API_KEY", "")
    base_url = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1")
    model = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")

    if not api_key:
        return {
            "panel": req.panel,
            "interpretation": "AI interpretation not configured — set AI_API_KEY in .env",
            "model": model,
            "status": "unconfigured",
        }

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)

        # Build a context-aware prompt based on panel type
        panel_prompts = {
            "descriptive": f"""
You are a quant analytics AI interpreting descriptive statistics for a KG-graded trading system.

Given the following computed statistics for {req.context.get('ticker', 'a series')}:
{json.dumps(req.computed_data, indent=2)}

Provide a concise interpretation covering:
1. What the distribution tells us about this series
2. Whether the normality assumption holds and what it means for risk modeling
3. Whether the series is stationary and what it means for forecasting
4. One specific actionable insight
""",
            "diagnostic": f"""
You are a quant analytics AI interpreting diagnostic analysis for a KG-graded trading system.

Current regime: {req.context.get('regime', 'Unknown')}
Strategy: {req.context.get('strategy', 'N/A')}

Given the following diagnostic results:
{json.dumps(req.computed_data, indent=2)}

Provide a concise interpretation covering:
1. What the volatility/drawdown/signal analysis reveals
2. How it relates to the current market regime
3. Whether the signal is adding value or degrading performance
4. One specific recommendation
""",
            "predictive": f"""
You are a quant analytics AI interpreting a forecast for a KG-graded trading system.

Given the following forecast results for {req.context.get('ticker', 'a series')}:
{json.dumps(req.computed_data, indent=2)}

Provide a concise interpretation covering:
1. The model's forecast direction and confidence
2. Key risks to the forecast
3. How this should inform strategy decisions
4. Whether the model's assumptions are appropriate for this series
""",
            "prescriptive": f"""
You are a quant analytics AI interpreting portfolio optimization results for a KG-graded trading system.

Current regime: {req.context.get('regime', 'Unknown')}

Given the following optimization results:
{json.dumps(req.computed_data, indent=2)}

Provide a concise interpretation covering:
1. Whether the recommended weights align with the KG's strategy eligibility
2. Key trade-offs in the recommended portfolio
3. Risk factors that could invalidate the optimization
4. A recommended next action
""",
        }

        prompt = panel_prompts.get(req.panel, f"Interpret the following analytics data:\n{json.dumps(req.computed_data, indent=2)}")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a quant analytics AI assistant specializing in quantitative trading system analysis. Be specific, numerical, and actionable. Do not make generic statements — refer directly to the data provided."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1000,
        )

        interpretation = response.choices[0].message.content

        return {
            "panel": req.panel,
            "model": model,
            "provider": base_url.split("//")[1].split(".")[0] if "//" in base_url else base_url,
            "interpretation": interpretation,
            "status": "success",
        }

    except Exception as e:
        return {
            "panel": req.panel,
            "model": model,
            "interpretation": f"AI interpretation failed: {str(e)}",
            "status": "error",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 20: Anomaly Detection (Tier 5 — Cognitive)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/anomalies")
def get_anomalies(
    series_id: str = Query(...),
    start_date: str = Query("2024-01-01"),
    end_date: str = Query(None),
    method: str = Query("isolation_forest", regex="^(isolation_forest|lof|cusum)$"),
):
    """Statistical anomaly detection on time series."""
    data_resp = fetch_series_data(series_id, start_date, end_date, limit=10000)
    raw = data_resp.get("data", [])
    if not raw:
        raise HTTPException(status_code=404, detail="No data available")

    values = np.array([p.get("value") for p in raw if p.get("value") is not None], dtype=float).reshape(-1, 1)
    timestamps = [p["timestamp"] for p in raw if p.get("value") is not None]

    if len(values) < 20:
        raise HTTPException(status_code=400, detail=f"Need at least 20 data points for anomaly detection")

    anomalies: list[dict] = []

    if method == "isolation_forest":
        from sklearn.ensemble import IsolationForest
        model = IsolationForest(contamination=0.05, random_state=42)
        preds = model.fit_predict(values)
        anomaly_scores = model.score_samples(values)
        for i, (pred, score) in enumerate(zip(preds, anomaly_scores)):
            if pred == -1:
                anomalies.append({
                    "timestamp": timestamps[i],
                    "value": float(values[i][0]),
                    "anomaly_score": float(score),
                    "method": "isolation_forest",
                })

    elif method == "lof":
        from sklearn.neighbors import LocalOutlierFactor
        model = LocalOutlierFactor(contamination=0.05, novelty=False)
        preds = model.fit_predict(values)
        for i, pred in enumerate(preds):
            if pred == -1:
                anomalies.append({
                    "timestamp": timestamps[i],
                    "value": float(values[i][0]),
                    "method": "lof",
                })

    elif method == "cusum":
        # CUSUM: detect mean shifts
        mean = np.mean(values)
        std = np.std(values)
        threshold = 3 * std
        cum_sum = 0
        for i in range(len(values)):
            cum_sum += (values[i][0] - mean)
            if abs(cum_sum) > threshold:
                anomalies.append({
                    "timestamp": timestamps[i],
                    "value": float(values[i][0]),
                    "cumulative_sum": float(cum_sum),
                    "method": "cusum",
                })
                cum_sum = 0  # Reset

    return _sanitize({
        "series_id": series_id,
        "method": method,
        "n_observations": len(values),
        "n_anomalies": len(anomalies),
        "anomaly_rate": len(anomalies) / len(values) if len(values) > 0 else 0,
        "anomalies": anomalies,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 21: Multi-Variant GARCH Engine (Tier 2 — Diagnostic)
# ═══════════════════════════════════════════════════════════════════════════════

class GarchRequest(BaseModel):
    ticker: str = Field(..., description="Ticker for GARCH estimation")
    variants: list[str] = Field(
        default_factory=lambda: ["garch", "egarch", "gjrgarch", "aparch", "igarch", "garchm"],
        description="GARCH variants to fit"
    )
    p: int = Field(1, ge=1, le=10, description="ARCH order")
    q: int = Field(1, ge=1, le=10, description="GARCH order")
    power: float = Field(2.0, ge=0.5, le=5.0, description="APARCH power parameter")
    horizon: int = Field(21, ge=1, le=252, description="Forecast horizon for conditional vol")


@router.post("/garch")
def post_garch(req: GarchRequest):
    """Multi-variant GARCH estimation with model comparison."""
    df = _fetch_yfinance(req.ticker, "2020-01-01", datetime.utcnow().strftime("%Y-%m-%d"))
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {req.ticker}")

    values = df["Close"].dropna().values
    if len(values) < 60:
        raise HTTPException(status_code=400, detail=f"Need at least 60 data points, got {len(values)}")

    # Compute log returns
    returns = np.diff(np.log(values[np.where(values > 0)]))
    if len(returns) < 60:
        raise HTTPException(status_code=400, detail=f"Need at least 60 returns, got {len(returns)}")

    from arch import arch_model

    fitted_models: dict[str, dict[str, Any]] = {}
    news_impact: dict[str, dict[str, float]] = {}
    cond_vols: dict[str, list[float]] = {}

    for variant in req.variants:
        try:
            if variant == "garch":
                am = arch_model(returns * 100, vol="Garch", p=req.p, q=req.q, dist="normal")
            elif variant == "egarch":
                am = arch_model(returns * 100, vol="EGARCH", p=req.p, q=req.q, dist="normal")
            elif variant == "gjrgarch":
                am = arch_model(returns * 100, vol="GARCH", p=req.p, q=req.q, o=1, dist="normal")
            elif variant == "aparch":
                am = arch_model(returns * 100, vol="APARCH", p=req.p, q=req.q, dist="normal")
            elif variant == "igarch":
                am = arch_model(returns * 100, vol="GARCH", p=req.p, q=req.q, dist="normal")
            elif variant == "garchm":
                am = arch_model(returns * 100, vol="GARCH", p=req.p, q=req.q, dist="normal")
            else:
                continue

            res = am.fit(disp="off", show_warning=False)

            params = {}
            for name in res.params.index:
                params[name] = {
                    "value": float(res.params[name]),
                    "std_err": float(res.std_err[name]) if name in res.std_err else None,
                    "t_stat": float(res.tvalues[name]) if name in res.tvalues else None,
                    "p_value": float(res.pvalues[name]) if name in res.pvalues else None,
                }

            # Conditional volatility
            cv = res.conditional_volatility / 100
            cond_vols[variant] = [float(v) for v in cv.tolist()]

            # Standardized residuals
            std_resid = res.resid / res.conditional_volatility if res.conditional_volatility.std() > 0 else res.resid
            from scipy import stats
            _, lb_p = stats.normaltest(std_resid[-min(100, len(std_resid)):])

            # News impact curve
            nic_shocks = np.linspace(-3, 3, 25)
            nic_values = []
            omega = float(res.params.get("omega", 0.01))
            alpha = float(res.params.get("alpha[1]", 0.05))
            beta = float(res.params.get("beta[1]", 0.9))
            gamma = float(res.params.get("gamma[1]", 0.0)) if "gamma[1]" in res.params else 0.0
            delta = float(res.params.get("delta", 2.0)) if "delta" in res.params else 2.0

            for z in nic_shocks:
                if variant == "egarch":
                    # EGARCH: log(h_t) = ω + α*(|z_{t-1}| - E|z|) + γ*z_{t-1} + β*log(h_{t-1})
                    e_abs = np.sqrt(2 / np.pi)
                    log_h = omega + alpha * (abs(z) - e_abs) + gamma * z + beta * np.log(omega / (1 - beta) if beta < 1 else 0.01)
                    nic_values.append(float(np.exp(log_h)))
                elif variant == "gjrgarch":
                    # GJR: h_t = ω + α*ε²_{t-1} + γ*I*ε²_{t-1} + β*h_{t-1}
                    h = omega + alpha * z**2 + gamma * (z**2 if z < 0 else 0) + beta * (omega / (1 - alpha - beta - 0.5 * gamma) if (alpha + beta + 0.5 * gamma) < 1 else 0.01)
                    nic_values.append(float(h))
                elif variant == "aparch":
                    # APARCH: h_t^{δ/2} = ω + α*(|ε_{t-1}| - γ*ε_{t-1})^δ + β*h_{t-1}^{δ/2}
                    h_pow = omega + alpha * (abs(z) - gamma * z) ** delta + beta * (omega / (1 - alpha - beta) if (alpha + beta) < 1 else 0.01) ** (delta / 2)
                    nic_values.append(float(h_pow ** (2 / delta)) if delta > 0 else 0)
                else:
                    # Standard GARCH: h_t = ω + α*ε²_{t-1} + β*h_{t-1}
                    h = omega + alpha * z**2 + beta * (omega / (1 - alpha - beta) if (alpha + beta) < 1 else 0.01)
                    nic_values.append(float(h))

            news_impact[variant] = {
                "shocks": [float(z) for z in nic_shocks.tolist()],
                "conditional_variances": nic_values,
            }

            # Persistence and half-life
            if variant == "igarch":
                persistence = 1.0
                half_life = float("inf")
            elif variant == "egarch":
                persistence = beta
                half_life = np.log(0.5) / np.log(max(beta, 0.001)) if beta > 0 else 0
            elif variant == "gjrgarch":
                persistence = alpha + beta + 0.5 * gamma
                half_life = np.log(0.5) / np.log(max(persistence, 0.001)) if persistence > 0 else 0
            else:
                persistence = alpha + beta
                half_life = np.log(0.5) / np.log(max(persistence, 0.001)) if persistence > 0 else 0

            fitted_models[variant] = {
                "parameters": params,
                "aic": float(res.aic),
                "bic": float(res.bic),
                "log_likelihood": float(res.loglikelihood),
                "persistence": float(persistence),
                "half_life_days": float(half_life) if half_life != float("inf") else None,
                "ljung_box_p": float(lb_p),
                "converged": bool(res.convergence_flag == 0),
            }

        except Exception as e:
            fitted_models[variant] = {"error": str(e)}

    # Model comparison sorted by AIC
    comparison = []
    for variant, data in fitted_models.items():
        if "aic" in data:
            comparison.append({
                "variant": variant,
                "aic": data["aic"],
                "bic": data["bic"],
                "log_likelihood": data["log_likelihood"],
                "persistence": data["persistence"],
                "half_life_days": data["half_life_days"],
                "converged": data["converged"],
            })
    comparison.sort(key=lambda x: x["aic"])

    return _sanitize({
        "ticker": req.ticker,
        "n_returns": len(returns),
        "p": req.p,
        "q": req.q,
        "models": fitted_models,
        "conditional_volatilities": cond_vols,
        "news_impact_curves": news_impact,
        "model_comparison": comparison,
        "best_model": comparison[0]["variant"] if comparison else None,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 22: PCA for Finance (Tier 2 — Diagnostic)
# ═══════════════════════════════════════════════════════════════════════════════

class PCARequest(BaseModel):
    tickers: list[str] = Field(..., description="List of tickers for PCA")
    n_components: int = Field(5, ge=1, le=20, description="Number of components to compute")


@router.post("/pca")
def post_pca(req: PCARequest):
    """Principal Component Analysis for financial returns with eigenvalue decomposition."""
    if len(req.tickers) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 tickers for PCA")

    # Fetch data for all tickers
    price_data: dict[str, np.ndarray] = {}
    for t in req.tickers:
        df = _fetch_yfinance(t, "2020-01-01", datetime.utcnow().strftime("%Y-%m-%d"))
        if df is not None and not df.empty:
            price_data[t] = df["Close"].dropna().values

    if len(price_data) < 2:
        raise HTTPException(status_code=400, detail="Could not fetch sufficient price data")

    # Align to shortest series
    min_len = min(len(v) for v in price_data.values())
    aligned = {k: v[-min_len:] for k, v in price_data.items()}

    # Compute returns
    return_data = {}
    for k, v in aligned.items():
        rets = np.diff(np.log(v[np.where(v > 0)]))
        if len(rets) >= 30:
            return_data[k] = rets

    if len(return_data) < 2:
        raise HTTPException(status_code=400, detail="Insufficient return data")

    min_rlen = min(len(v) for v in return_data.values())
    rets_matrix = np.column_stack([return_data[k][-min_rlen:] for k in return_data])
    ticker_names = list(return_data.keys())
    n_comp = min(req.n_components, len(ticker_names), min_rlen - 1)

    # Standardize returns
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    rets_std = scaler.fit_transform(rets_matrix)

    # PCA via SVD
    from sklearn.decomposition import PCA as SklearnPCA
    pca = SklearnPCA(n_components=n_comp)
    pca.fit(rets_std)

    # Eigenvalue decomposition
    eigenvalues = pca.explained_variance_
    explained_variance_ratio = pca.explained_variance_ratio_
    cumulative_variance = np.cumsum(explained_variance_ratio)

    # Factor loadings
    loadings = pca.components_.T  # n_tickers x n_components

    # Scree data
    scree = [
        {
            "component": i + 1,
            "eigenvalue": float(eigenvalues[i]),
            "explained_variance_pct": float(explained_variance_ratio[i] * 100),
            "cumulative_pct": float(cumulative_variance[i] * 100),
        }
        for i in range(n_comp)
    ]

    # Kaiser criterion: components with eigenvalue > 1
    kaiser_significant = sum(1 for e in eigenvalues if e > 1.0)

    # 90% variance threshold
    var_90 = next((i + 1 for i, c in enumerate(cumulative_variance) if c >= 0.9), n_comp)

    # Factor loadings per ticker
    factor_loadings = {}
    for i, tk in enumerate(ticker_names):
        factor_loadings[tk] = {f"PC{j+1}": float(loadings[i, j]) for j in range(n_comp)}

    # Risk decomposition: % of variance explained by top K components
    risk_decomp = {
        f"top_{k}": {
            "n_components": k,
            "variance_explained_pct": float(cumulative_variance[k - 1] * 100),
        }
        for k in [1, 2, 3, 5, n_comp]
        if k <= n_comp
    }

    # First PC interpretation (market factor)
    pc1_loadings = {tk: float(loadings[i, 0]) for i, tk in enumerate(ticker_names)}
    pc1_sign = np.sign(sum(loadings[:, 0]))
    pc1_interpretation = "Broad market factor" if abs(pc1_sign * sum(loadings[:, 0])) / len(ticker_names) > 0.3 else "Differential factor"

    # Second PC interpretation (sector/rotation)
    pc2_interpretation = None
    if n_comp >= 2:
        pc2_loadings = {tk: float(loadings[i, 1]) for i, tk in enumerate(ticker_names)}
        pos_count = sum(1 for v in pc2_loadings.values() if v > 0)
        neg_count = sum(1 for v in pc2_loadings.values() if v < 0)
        pc2_interpretation = "Sector rotation / long-short factor" if min(pos_count, neg_count) > 0 else "Secondary market factor"

    # Projected data (first 2 PCs for scatter)
    projected = pca.transform(rets_std)
    projection_data = [
        {"pc1": float(projected[i, 0]), "pc2": float(projected[i, 1]) if n_comp >= 2 else 0}
        for i in range(min(500, len(projected)))
    ]

    return _sanitize({
        "tickers": ticker_names,
        "n_observations": min_rlen,
        "n_components": n_comp,
        "scree": scree,
        "eigenvalues": [float(e) for e in eigenvalues],
        "explained_variance_ratio": [float(v) for v in explained_variance_ratio],
        "cumulative_variance": [float(v) for v in cumulative_variance],
        "factor_loadings": factor_loadings,
        "risk_decomposition": risk_decomp,
        "kaiser_significant_components": kaiser_significant,
        "components_for_90pct_variance": var_90,
        "pc1_interpretation": pc1_interpretation,
        "pc2_interpretation": pc2_interpretation,
        "pc1_loadings": pc1_loadings,
        "projection": projection_data,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 23: Covariance Health & MST (Tier 2 — Diagnostic)
# ═══════════════════════════════════════════════════════════════════════════════

class CovHealthRequest(BaseModel):
    tickers: list[str] = Field(..., description="List of tickers for covariance analysis")


@router.post("/covariance-health")
def post_covariance_health(req: CovHealthRequest):
    """Covariance matrix diagnostics: condition number, shrinkage, MST, eigenvalue spectrum."""
    if len(req.tickers) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 tickers")

    # Fetch data
    price_data: dict[str, np.ndarray] = {}
    for t in req.tickers:
        df = _fetch_yfinance(t, "2020-01-01", datetime.utcnow().strftime("%Y-%m-%d"))
        if df is not None and not df.empty:
            price_data[t] = df["Close"].dropna().values

    if len(price_data) < 2:
        raise HTTPException(status_code=400, detail="Could not fetch sufficient price data")

    min_len = min(len(v) for v in price_data.values())
    aligned = {k: v[-min_len:] for k, v in price_data.items()}

    return_data = {}
    for k, v in aligned.items():
        rets = np.diff(np.log(v[np.where(v > 0)]))
        if len(rets) >= 30:
            return_data[k] = rets

    if len(return_data) < 2:
        raise HTTPException(status_code=400, detail="Insufficient return data")

    min_rlen = min(len(v) for v in return_data.values())
    rets_matrix = np.column_stack([return_data[k][-min_rlen:] for k in return_data])
    ticker_names = list(return_data.keys())
    T, N = rets_matrix.shape

    # ── Raw sample covariance ──────────────────────────────────────────────
    cov_raw = np.cov(rets_matrix.T, ddof=1)

    # ── Condition number ───────────────────────────────────────────────────
    eigs = np.linalg.eigvalsh(cov_raw)
    eigs_pos = np.abs(eigs)
    eigs_desc = np.sort(eigs_pos)[::-1]
    cond = float(eigs_desc[0] / max(float(eigs_desc[-1]), 1e-14))
    is_ill = cond > 1000

    total_var = float(eigs_desc.sum())
    eig_fracs = [float(e / max(total_var, 1e-14)) for e in eigs_desc]

    # ── Shrinkage (Ledoit-Wolf + OAS) ──────────────────────────────────────
    from sklearn.covariance import LedoitWolf, OAS
    lw_obj = LedoitWolf(assume_centered=False).fit(rets_matrix)
    cov_lw = lw_obj.covariance_
    lw_alpha = float(lw_obj.shrinkage_)

    oas_obj = OAS(assume_centered=False).fit(rets_matrix)
    cov_oas = oas_obj.covariance_
    oas_alpha = float(oas_obj.shrinkage_)

    # ── Correlation matrices ───────────────────────────────────────────────
    def cov_to_corr(cov):
        sigma = np.sqrt(np.maximum(np.diag(cov), 1e-14))
        corr = cov / np.outer(sigma, sigma)
        np.fill_diagonal(corr, 1.0)
        return np.clip(corr, -1.0, 1.0)

    corr_raw = cov_to_corr(cov_raw)
    corr_lw = cov_to_corr(cov_lw)
    corr_oas = cov_to_corr(cov_oas)

    # ── Correlation distance matrix ────────────────────────────────────────
    dist_mat = np.sqrt(2.0 * np.maximum(1.0 - corr_raw, 0.0))
    np.fill_diagonal(dist_mat, 0.0)

    # ── Minimum Spanning Tree (Prim's) ─────────────────────────────────────
    def prim_mst(dist):
        N = dist.shape[0]
        in_mst = [False] * N
        in_mst[0] = True
        edges = []
        for _ in range(N - 1):
            best_d, best_i, best_j = float("inf"), -1, -1
            for i in range(N):
                if not in_mst[i]:
                    continue
                for j in range(N):
                    if in_mst[j]:
                        continue
                    if dist[i, j] < best_d:
                        best_d, best_i, best_j = dist[i, j], i, j
            if best_i >= 0:
                in_mst[best_j] = True
                edges.append((best_i, best_j))
        return edges

    mst_edges = prim_mst(dist_mat)
    mst_data = [
        {
            "from": ticker_names[u],
            "to": ticker_names[v],
            "correlation": float(corr_raw[u, v]),
            "distance": float(dist_mat[u, v]),
        }
        for u, v in mst_edges
    ]
    total_mst_dist = float(sum(e["distance"] for e in mst_data))

    # All pairwise correlations
    all_pairs = []
    for i in range(N):
        for j in range(i + 1, N):
            all_pairs.append({
                "asset_i": ticker_names[i],
                "asset_j": ticker_names[j],
                "correlation": float(corr_raw[i, j]),
                "distance": float(dist_mat[i, j]),
            })

    # Eigenvalue distribution
    eig_distribution = {
        "min": float(eigs_desc[-1]),
        "max": float(eigs_desc[0]),
        "median": float(np.median(eigs_desc)),
        "mean": float(np.mean(eigs_desc)),
        "std": float(np.std(eigs_desc, ddof=1)),
        "condition_number": cond,
        "is_ill_conditioned": is_ill,
    }

    return _sanitize({
        "tickers": ticker_names,
        "n_observations": T,
        "n_assets": N,
        "condition_number": cond,
        "is_ill_conditioned": is_ill,
        "shrinkage": {
            "ledoit_wolf_alpha": lw_alpha,
            "oas_alpha": oas_alpha,
            "shrinkage_intensity_ratio": lw_alpha / max(oas_alpha, 1e-14),
        },
        "eigenvalue_spectrum": {
            "values": [float(e) for e in eigs_desc],
            "fractions": eig_fracs,
            "distribution": eig_distribution,
        },
        "correlation_matrices": {
            "raw": corr_raw.tolist(),
            "ledoit_wolf": corr_lw.tolist(),
            "oas": corr_oas.tolist(),
        },
        "distance_matrix": dist_mat.tolist(),
        "minimum_spanning_tree": {
            "edges": mst_data,
            "total_distance": total_mst_dist,
            "n_edges": len(mst_data),
        },
        "all_pairs": all_pairs,
    })
