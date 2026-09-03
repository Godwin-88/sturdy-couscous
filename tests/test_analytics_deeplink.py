"""Contract tests for the chain-aware analytics deep-link feature (Part B follow-up).

Covers:
  * /analytics/series emits canonical px: ids labelled by market-data source.
  * /analytics/data resolves px: ids (and legacy yf: ids) to data points.
  * AlpacaDataProvider._fetch_yfinance_range flattens the yfinance MultiIndex
    columns (yf.download auto_adjust=True returns ("Close","SPY") tuples).
"""
import pandas as pd
import pytest

import routes.analytics as analytics_mod
from routes.analytics import fetch_series_data, _fetch_price_series


def _make_multindex_ohlcv():
    """What yf.download(..., auto_adjust=True) returns for a single ticker."""
    idx = pd.date_range("2026-08-03", periods=5, freq="D")  # Mon–Fri, 5 trading days
    cols = pd.MultiIndex.from_product([["Open", "High", "Low", "Close", "Volume"], ["SPY"]])
    data = {
        "Open": [750.0] * 5, "High": [760.0] * 5, "Low": [745.0] * 5,
        "Close": [755.0] * 5, "Volume": [1_000_000] * 5,
    }
    frame = pd.DataFrame(data, index=idx)
    frame.columns = cols
    return frame


@pytest.fixture(autouse=True)
def _no_network_yfinance(monkeypatch):
    """Make yf.download return a MultiIndex frame (deterministic, no network)."""
    monkeypatch.setattr("yfinance.download", lambda *a, **k: _make_multindex_ohlcv())


def test_provider_flattens_yfinance_multindex(monkeypatch):
    """The real production path: provider range-fetch flattens MultiIndex."""
    from agent.alpaca_data import AlpacaDataProvider, provider as _provider
    class _P:
        def is_enabled(self):
            return False  # force yfinance fallback
    monkeypatch.setattr(AlpacaDataProvider, "is_enabled", _P().is_enabled)
    monkeypatch.setattr(_provider, "_cache", {})  # clear in-memory cache
    df = _provider._fetch_yfinance_range("SPY", "2026-08-01", "2026-08-05")
    assert df is not None and not df.empty
    assert "Close" in df.columns
    assert not isinstance(df.columns, pd.MultiIndex)


def test_fetch_price_series_flattens_via_provider(monkeypatch):
    """_fetch_price_series delegates to the provider, which flattens."""
    from agent.alpaca_data import AlpacaDataProvider, provider as _provider
    class _P:
        def is_enabled(self):
            return False  # force yfinance fallback
    monkeypatch.setattr(AlpacaDataProvider, "is_enabled", _P().is_enabled)
    monkeypatch.setattr(_provider, "_cache", {})
    monkeypatch.setattr(analytics_mod, "_redis", lambda: _NullRedis())
    df = _fetch_price_series("SPY", "2026-08-01", "2026-08-05")
    assert df is not None and not df.empty
    assert "Close" in df.columns
    assert not isinstance(df.columns, pd.MultiIndex)


def test_series_catalog_emits_px():
    cats = analytics_mod.get_available_series()
    px = [c for c in cats if c["id"] == "px:SPY:Close"]
    assert px and px[0]["source"] in ("alpaca", "yfinance")
    assert any(c["id"] == "px:SPY:Volume" for c in cats)


def test_fetch_series_data_px(monkeypatch):
    monkeypatch.setattr(analytics_mod, "_fetch_price_series",
                        lambda *a, **k: _make_multindex_ohlcv().droplevel(1, axis=1))
    resp = fetch_series_data("px:SPY:Close", "2026-08-01", "2026-08-05")
    assert resp["count"] == 5
    assert resp["data"][0]["value"] == 755.0
    assert resp["metadata"]["source"] in ("alpaca", "yfinance")


def test_fetch_series_data_legacy_yf_alias(monkeypatch):
    monkeypatch.setattr(analytics_mod, "_fetch_price_series",
                        lambda *a, **k: _make_multindex_ohlcv().droplevel(1, axis=1))
    resp = fetch_series_data("yf:SPY:Close", "2026-08-01", "2026-08-05")
    assert resp["count"] == 5
    assert resp["data"][0]["value"] == 755.0


class _NullRedis:
    def __init__(self):
        self._d = {}

    def get(self, k):
        return self._d.get(k)

    def setex(self, k, ttl, v):
        self._d[k] = v