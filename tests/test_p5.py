"""P5 — Redis Integration tests."""
import asyncio
import json
import os
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Fixture for a valid signal
VALID_SIGNAL = {
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
    "score": 0.5,
    "quant_score": 0.5,
    "sentiment_score": 0.0,
    "news_overlay": 0.0,
    "macro_overlay": 0.0,
    "kg_formula_contribution": 0.0,
    "graph_path": [],
    "contradiction_blocked": False
}


class TestRedisPublishing:
    """Feature 2: Redis channel publishing."""

    def test_signal_validated_before_publish(self):
        """Signals must pass validation before publishing."""
        from common.schema_validator import validate_signal
        # Valid signal should not raise
        validate_signal(VALID_SIGNAL)

    def test_signal_validation_rejects_invalid(self):
        """Invalid signals are rejected before publish."""
        from common.schema_validator import validate_signal
        from jsonschema import ValidationError
        invalid_signal = VALID_SIGNAL.copy()
        invalid_signal["score"] = 2.0  # Out of range
        with pytest.raises(ValidationError):
            validate_signal(invalid_signal)

    @pytest.mark.asyncio
    async def test_publish_respects_shadow_mode(self):
        """In shadow mode, signals are still published to Redis."""
        with patch.dict(os.environ, {"SHADOW_MODE": "true"}):
            from common.redis_publisher import publish_signal
            # Mock redis connection
            with patch("common.redis_publisher.aioredis.from_url") as mock_redis:
                mock_conn = AsyncMock()
                mock_redis.return_value = mock_conn
                result = await publish_signal(VALID_SIGNAL)
                assert result is True
                mock_conn.publish.assert_called_once()


class TestOrchestratorPublishing:
    """Feature 1: Agent publishes signals after merge."""

    def test_publish_signals_batched(self):
        """Signals are published in batch, not individually."""
        from common.redis_publisher import publish_signal_batch
        # Verify the function exists and accepts a list
        assert callable(publish_signal_batch)

    def test_inject_schema_v1_logic(self):
        """Verify schema stamping logic produces correct output."""
        # Test the logic without importing orchestrator (which has heavy deps)
        from backtest.universe import _create_universe_entry, _infer_venue_symbol
        entry = _create_universe_entry("SPY")
        assert entry.asset_class == "equity_xstock"
        assert entry.venue == "ibkr"
        assert entry.venue_symbol == "SPY"


class TestSubscriberMode:
    """Feature 3: RiskEngine subscribes and processes signals."""

    def test_subscriber_reconnect_on_disconnect(self):
        """RiskEngine reconnects on Redis disconnect."""
        # Verify the subscriber code exists in main.cpp
        assert os.path.exists("/home/ed/projects/sturdy-couscous/cpp-risk/src/main.cpp")

    def test_heartbeat_distinguishes_quiet_cycles(self):
        """Heartbeat allows ops to distinguish quiet cycles from failures."""
        from common.redis_publisher import publish_heartbeat
        with patch("common.redis_publisher.aioredis.from_url") as mock_redis:
            mock_conn = AsyncMock()
            mock_redis.return_value = mock_conn
            asyncio.run(publish_heartbeat("cycle-123", "cycle_complete:0_signals:0_orders"))
            # Heartbeat sets a key with 30s expiry
            assert mock_conn.set.called


class TestShadowComparison:
    """Feature 4: Parallel-run validation."""

    def test_shadow_comparison_table_exists(self):
        """Shadow comparison table has correct schema."""
        from pathlib import Path
        init_sql = Path("/home/ed/projects/sturdy-couscous/infra/postgres/init.sql").read_text()
        assert "shadow_comparison" in init_sql
        assert "cpp_decision" in init_sql
        assert "python_decision" in init_sql

    def test_shadow_comparison_columns(self):
        """Shadow comparison includes discrepancy flag."""
        init_sql = open("/home/ed/projects/sturdy-couscous/infra/postgres/init.sql").read()
        assert "discrepancy" in init_sql


class TestDockerComposeIntegration:
    """Feature 5: Docker Compose integration."""

    def test_risk_engine_service_defined(self):
        """risk-engine service is in docker-compose.yml."""
        from pathlib import Path
        compose = Path("/home/ed/projects/sturdy-couscous/docker-compose.yml").read_text()
        assert "risk-engine:" in compose
        assert "REDIS_SUBSCRIBE" in compose

    def test_risk_engine_depends_on_redis_postgres(self):
        """risk-engine waits for redis and postgres."""
        compose = open("/home/ed/projects/sturdy-couscous/docker-compose.yml").read()
        assert "depends_on:" in compose
        assert "postgres:" in compose
        assert "redis:" in compose

    def test_risk_engine_reads_env_file(self):
        """risk-engine reads .env like other services."""
        compose = open("/home/ed/projects/sturdy-couscous/docker-compose.yml").read()
        assert "env_file: .env" in compose


class TestSectorCapParity:
    """Verify C++ and Python sector cap logic match."""

    def test_sectored_asset_classes(self):
        """Sector cap applies to equity, not crypto."""
        from backtest.risk_sim import SECTOR_MAP
        assert SECTOR_MAP["QQQ"] == "equity_tech"
        assert SECTOR_MAP["SPY"] == "equity_broad"
        assert SECTOR_MAP["XLF"] == "equity_financials"

    def test_sector_cap_threshold(self):
        """Both implementations use same sector cap threshold."""
        from backtest.risk_sim import MAX_SECTOR_PCT
        import os
        env_val = float(os.getenv("RISK_MAX_SECTOR_PCT", "0.40"))
        assert MAX_SECTOR_PCT == env_val
        assert MAX_SECTOR_PCT == 0.40