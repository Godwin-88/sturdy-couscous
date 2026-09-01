"""Tests for the Alpaca Market Data provider / perception layer.

Run with: pytest tests/test_alpaca_data.py -v
"""

import numpy as np
import pandas as pd
import pytest

from agent.alpaca_data import (
    AlpacaDataProvider,
    CRYPTO_MAP,
    EQUITY_SYMBOLS,
    realized_vix_proxy,
)


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_MARKET_DATA", raising=False)
    return AlpacaDataProvider()


def test_unconfigured_uses_yfinance(provider):
    assert provider.source_name() == "yfinance"
    assert provider.is_enabled() is False


def test_placeholder_keys_treated_unconfigured(provider, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "your_alpaca_paper_key_id")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "your_alpaca_paper_secret")
    monkeypatch.setenv("ALPACA_MARKET_DATA", "1")
    provider.key_id = "your_alpaca_paper_key_id"
    provider.secret_key = "your_alpaca_paper_secret"
    assert provider.is_configured() is False
    assert provider.source_name() == "yfinance"


def test_crypto_symbol_map():
    assert CRYPTO_MAP == {
        "BTC": "BTC/USD", "BTC-USD": "BTC/USD",
        "ETH": "ETH/USD", "ETH-USD": "ETH/USD",
    }


def test_equity_symbol_routing(provider):
    kind, sym = provider.resolve_symbol("SPY")
    assert kind == "stock" and sym == "SPY"


def test_crypto_symbol_routing(provider):
    kind, sym = provider.resolve_symbol("BTC-USD")
    assert kind == "crypto" and sym == "BTC/USD"


def test_realized_vix_proxy_warmup():
    # Too few observations -> empty (no IndexError).
    short = pd.Series(np.linspace(100, 110, 10))
    assert realized_vix_proxy(short).empty


def test_realized_vix_proxy_output():
    n = 60
    rng = np.random.default_rng(0)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))))
    proxy = realized_vix_proxy(close, mult=1.5)
    assert not proxy.empty
    assert (proxy > 0).all()
    # VIX proxy should be proportional to realized vol * multiplier.
    spy = close.pct_change().rolling(21).std().iloc[-1] * np.sqrt(252) * 100 * 1.5
    assert np.isclose(proxy.iloc[-1], spy, atol=1e-6)


def test_get_close_series_falls_back_gracefully(provider, monkeypatch):
    """Unconfigured provider falls back to yfinance; network errors -> empty frame."""
    monkeypatch.setenv("ALPACA_MARKET_DATA", "0")
    # _fetch_yfinance is an instance method — patch it to simulate a blocked network.
    monkeypatch.setattr(provider, "_fetch_yfinance", lambda symbol, days: pd.DataFrame())
    result = provider.get_ohlcv("SPY", days=30)
    assert isinstance(result, pd.DataFrame) and result.empty
