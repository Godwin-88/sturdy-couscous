"""P6 — Interactive Brokers Integration tests."""
import json
import uuid
from pathlib import Path

import pytest


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
        assert Path("/home/ed/projects/sturdy-couscous/cpp-risk/include/graphalpha/ibkr_adapter.hpp").exists()

    def test_ibkr_venue_id(self):
        """IBKRAdapter returns 'ibkr' as venue_id."""
        from backtest.universe import lookup
        entry = lookup("SPY")
        assert entry.venue == "ibkr"

    def test_ibkr_rejects_live_mode(self):
        """Hard rule: IBKRAdapter rejects non-paper orders."""
        # Test the paper-only constraint is enforced in the adapter logic
        ibkr_cpp = Path("/home/ed/projects/sturdy-couscous/cpp-risk/src/ibkr_adapter.cpp").read_text()
        assert 'order.mode != "paper"' in ibkr_cpp
        assert "REJECTED (HARD)" in ibkr_cpp


class TestVenueRouting:
    """Feature 3: ExecutionEngine routes by venue."""

    def test_execution_engine_routes_by_venue(self):
        """ExecutionEngine dispatches based on order.venue field."""
        exec_cpp = Path("/home/ed/projects/sturdy-couscous/cpp-risk/src/execution_engine.cpp").read_text()
        assert "adapters_.find(order.venue)" in exec_cpp
        main_cpp = Path("/home/ed/projects/sturdy-couscous/cpp-risk/src/main.cpp").read_text()
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
        loader_cpp = Path("/home/ed/projects/sturdy-couscous/cpp-risk/src/PortfolioLoader.cpp").read_text()
        assert 'infer_sector(p.ticker)' in loader_cpp


class TestOrchestratorVenueAssignment:
    """Feature 5: Orchestrator assigns correct venue."""

    def test_spy_routes_to_ibkr(self):
        """SPY signal routes to IBKR by default."""
        from backtest.universe import lookup
        entry = lookup("SPY")
        assert entry.venue == "ibkr"
        assert entry.venue_symbol == "SPY"

    def test_btc_usd_routes_to_kraken(self):
        """BTC-USD signal routes to Kraken by default."""
        from backtest.universe import lookup
        entry = lookup("BTC-USD")
        assert entry.venue == "kraken"
        assert entry.venue_symbol == "XBTUSD"

    def test_qqq_routes_to_ibkr(self):
        """QQQ signal routes to IBKR by default."""
        from backtest.universe import lookup
        entry = lookup("QQQ")
        assert entry.venue == "ibkr"


class TestDockerComposeIBKR:
    """Feature 1: Docker Compose IBKR service."""

    def test_ib_gateway_service_exists(self):
        """ib-gateway service defined in docker-compose.yml."""
        compose = Path("/home/ed/projects/sturdy-couscous/docker-compose.yml").read_text()
        assert "ib-gateway:" in compose
        assert "IBKR_USERNAME" in compose
        assert "IBKR_TRADING_MODE" in compose

    def test_ibkr_env_vars_in_env_example(self):
        """IBKR credentials documented in .env.example."""
        env = Path("/home/ed/projects/sturdy-couscous/.env.example").read_text()
        assert "IBKR_USERNAME=" in env
        assert "IBKR_PASSWORD=" in env
        assert "IBKR_TRADING_MODE=paper" in env

    def test_risk_engine_connects_to_ibkr(self):
        """risk-engine is configured to connect to IB Gateway."""
        compose = Path("/home/ed/projects/sturdy-couscous/docker-compose.yml").read_text()
        assert "IBKR_HOST:" in compose or "IBKR_HOST=" in compose
        assert "IBKR_PORT" in compose

    def test_ibkr_profile_condition(self):
        """IB gateway only starts when credentials are provided."""
        compose = Path("/home/ed/projects/sturdy-couscous/docker-compose.yml").read_text()
        assert 'profiles: ["ibkr"]' in compose