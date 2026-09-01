"""P6 — Interactive Brokers Integration tests."""
import json
import uuid
from pathlib import Path

import pytest

from pathlib import Path

# Repo root, works on host AND inside the API container (/app).
REPO_ROOT = Path(__file__).resolve().parents[1]


VALID_IBKR_SIGNAL = {
    "schema_version": 1,
    "cycle_id": str(uuid.uuid4()),
    "timestamp": "2023-01-15T00:00:00Z",
    "regime": "Trending",
    "strategy": "MomentumOverlay",
    "ticker": "SPY",
    "venue": "ibkr",
    "venue_symbol": "SPY",
    "asset_class": "equity_xstock",
    "direction": "buy",
    "score": 0.6,
    "quant_score": 0.6,
    "sentiment_score": 0.0,
    "news_overlay": 0.0,
    "macro_overlay": 0.0,
    "kg_formula_contribution": 0.0,
    "contradiction_blocked": False
}


class TestIBKRAdapterInterface:
    """Feature 2: IBKRAdapter implements venue adapter interface."""

    def test_ibkr_adapter_exists(self):
        """IBKRAdapter header exists."""
        assert (REPO_ROOT / "cpp-risk/include/graphalpha/ibkr_adapter.hpp").exists()

    def test_default_venue_alpaca(self):
        """Default universe routes equities via Alpaca (IBKR stays dormant/profile)."""
        from backtest.universe import lookup
        entry = lookup("SPY")
        assert entry.venue == "alpaca"

    def test_ibkr_rejects_live_mode(self):
        """Hard rule: IBKRAdapter rejects non-paper orders."""
        # Test the paper-only constraint is enforced in the adapter logic
        ibkr_cpp = (REPO_ROOT / "cpp-risk/src/ibkr_adapter.cpp").read_text()
        assert 'order.mode != "paper"' in ibkr_cpp
        assert "REJECTED (HARD)" in ibkr_cpp


class TestVenueRouting:
    """Feature 3: ExecutionEngine routes by venue."""

    def test_execution_engine_routes_by_venue(self):
        """ExecutionEngine dispatches based on order.venue field."""
        exec_cpp = (REPO_ROOT / "cpp-risk/src/execution_engine.cpp").read_text()
        assert "adapters_.find(order.venue)" in exec_cpp
        main_cpp = (REPO_ROOT / "cpp-risk/src/main.cpp").read_text()
        assert "IBKRAdapter" in main_cpp
        assert "KrakenAdapter" in main_cpp


class TestCrossVenuePortfolio:
    """Feature 4: Cross-venue portfolio aggregation."""

    def test_sector_map_complete(self):
        """Sector map covers all instrument types."""
        from backtest.risk_sim import SECTOR_MAP, MAX_SECTOR_PCT
        # Equity sectors
        assert SECTOR_MAP["QQQ"] == "equity_tech"
        assert SECTOR_MAP["SPY"] == "equity_broad"
        assert SECTOR_MAP["XLF"] == "equity_financials"
        assert SECTOR_MAP["XLE"] == "equity_energy"
        # Macro sectors
        assert SECTOR_MAP["TLT"] == "macro_rates"
        assert SECTOR_MAP["GLD"] == "commodities"
        # Crypto has no sector
        assert SECTOR_MAP["BTC"] == "crypto"
        assert MAX_SECTOR_PCT == 0.40

    def test_portfolio_loader_infers_sector(self):
        """PortfolioLoader correctly infers sector for positions."""
        loader_cpp = (REPO_ROOT / "cpp-risk/src/PortfolioLoader.cpp").read_text()
        assert 'infer_sector(p.ticker)' in loader_cpp


class TestOrchestratorVenueAssignment:
    """Feature 5: Orchestrator assigns correct venue."""

    def test_spy_routes_to_alpaca(self):
        """SPY signal routes to Alpaca by default."""
        from backtest.universe import lookup
        entry = lookup("SPY")
        assert entry.venue == "alpaca"
        assert entry.venue_symbol == "SPY"

    def test_btc_usd_routes_to_alpaca(self):
        """BTC-USD signal routes to Alpaca when in universe."""
        from backtest.universe import lookup
        entry = lookup("BTC-USD")
        assert entry.venue == "alpaca"
        assert entry.venue_symbol == "BTC/USD"

    def test_qqq_routes_to_alpaca(self):
        """QQQ signal routes to Alpaca by default."""
        from backtest.universe import lookup
        entry = lookup("QQQ")
        assert entry.venue == "alpaca"


class TestDockerComposeIBKR:
    """Feature 1: Docker Compose IBKR service."""

    def test_ib_gateway_service_exists(self):
        """ib-gateway service defined in docker-compose.yml."""
        compose = (REPO_ROOT / "docker-compose.yml").read_text()
        assert "ib-gateway:" in compose
        assert "IBKR_USERNAME" in compose
        assert "IBKR_TRADING_MODE" in compose

    def test_ibkr_env_vars_in_env_example(self):
        """IBKR credentials documented in .env.example."""
        env = (REPO_ROOT / ".env.example").read_text()
        assert "IBKR_USERNAME=" in env
        assert "IBKR_PASSWORD=" in env
        assert "IBKR_TRADING_MODE=paper" in env

    def test_risk_engine_connects_to_ibkr(self):
        """risk-engine is configured to connect to IB Gateway."""
        compose = (REPO_ROOT / "docker-compose.yml").read_text()
        assert "IBKR_HOST:" in compose or "IBKR_HOST=" in compose
        assert "IBKR_PORT" in compose

    def test_ibkr_profile_condition(self):
        """IB gateway only starts when credentials are provided."""
        compose = (REPO_ROOT / "docker-compose.yml").read_text()
        assert 'profiles: ["ibkr"]' in compose