"""
Tests for Alpaca integration.
Run with: pytest tests/test_alpaca.py -v
"""

import os
import pytest

from agent.alpaca_client import AlpacaClient, AlpacaOrderResult


@pytest.fixture
def client(monkeypatch):
    # Hermetic: ignore .env (real paper keys live there) so these tests
    # assert pure library defaults and never touch the Alpaca API.
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_BASE_URL", raising=False)
    monkeypatch.delenv("ALPACA_DATA_URL", raising=False)
    return AlpacaClient()


def test_alpaca_client_defaults(client):
    assert client.base_url == "https://paper-api.alpaca.markets"
    assert client.paper is True
    assert client.is_configured() is False


@pytest.mark.asyncio
async def test_alpaca_simulated_order(client):
    result = await client.place_order("SPY", "buy", 1.0)
    assert result.order_id == "simulated"
    assert result.symbol == "SPY"
    assert result.side == "buy"
    assert result.qty == 1.0
    assert result.status == "simulated"


@pytest.mark.asyncio
async def test_alpaca_get_positions_unconfigured(client):
    positions = await client.get_positions()
    assert positions == []


@pytest.mark.asyncio
async def test_alpaca_get_account_unconfigured(client):
    account = await client.get_account()
    assert account["status"] == "unconfigured"


@pytest.mark.asyncio
async def test_alpaca_get_bars_unconfigured(client):
    bars = await client.get_bars("SPY")
    assert bars == []


def test_alpaca_env_override(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test_key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    client = AlpacaClient()
    assert client.key_id == "test_key"
    assert client.secret_key == "test_secret"


def test_alpaca_live_url(monkeypatch):
    monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
    client = AlpacaClient()
    assert client.paper is False


def test_alpaca_order_result_dataclass():
    result = AlpacaOrderResult(
        order_id="123",
        symbol="SPY",
        side="buy",
        qty=1.0,
        filled_qty=1.0,
        filled_avg_price=500.0,
        status="filled",
        raw={},
    )
    assert result.order_id == "123"
    assert result.status == "filled"
