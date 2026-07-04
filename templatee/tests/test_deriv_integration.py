"""
Integration tests for Deriv API client and endpoints.

These tests verify that the Deriv API integration works correctly
with the FastAPI application.
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

# Import the modules under test
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deriv_api_client import DerivAPIClient, MarketData, AssetClass
from market_data_endpoints import get_deriv_client


class TestDerivAPIIntegration:
    """Integration tests for Deriv API client"""
    
    @pytest.mark.asyncio
    async def test_client_creation_and_cleanup(self):
        """Test that client can be created and cleaned up properly"""
        client = DerivAPIClient(
            api_key="test_key",
            app_id="test_app",
            rate_limit=5.0
        )
        
        try:
            # Test basic client functionality
            assert client.api_key == "test_key"
            assert client.app_id == "test_app"
            assert client.rate_limiter.max_requests_per_second == 5.0
            
            # Test cache functionality
            stats = client.get_cache_stats()
            assert 'l1_cache_size' in stats
            assert 'l2_cache_size' in stats
            
        finally:
            await client.close()
    
    @pytest.mark.asyncio
    async def test_market_data_retrieval(self):
        """Test market data retrieval with mock data"""
        client = DerivAPIClient(
            api_key="test_key",
            app_id="test_app"
        )
        
        try:
            # Get market data (uses mock implementation)
            market_data = await client.get_market_data("AAPL", AssetClass.STOCKS)
            
            # Verify data structure
            assert isinstance(market_data, MarketData)
            assert market_data.symbol == "AAPL"
            assert market_data.spot_price > 0
            assert market_data.bid > 0
            assert market_data.ask > 0
            assert market_data.ask >= market_data.bid
            assert isinstance(market_data.timestamp, datetime)
            assert market_data.asset_class == AssetClass.STOCKS
            
            # Test data freshness
            assert not market_data.is_stale()
            
        finally:
            await client.close()
    
    @pytest.mark.asyncio
    async def test_option_chain_retrieval(self):
        """Test option chain retrieval with mock data"""
        client = DerivAPIClient(
            api_key="test_key",
            app_id="test_app"
        )
        
        try:
            # Get option chain (uses mock implementation)
            expiry_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime('%Y-%m-%d')
            option_chain = await client.get_option_chain("AAPL", expiry_date)
            
            # Verify option chain structure
            assert option_chain.underlying == "AAPL"
            assert option_chain.is_complete()
            assert len(option_chain.calls) > 0
            assert len(option_chain.puts) > 0
            
            # Verify strikes are available and sorted
            strikes = option_chain.get_strikes()
            assert len(strikes) > 0
            assert strikes == sorted(strikes)
            
            # Verify contract data
            for contract in option_chain.calls + option_chain.puts:
                assert contract.underlying == "AAPL"
                assert contract.strike > 0
                assert contract.bid >= 0
                assert contract.ask >= contract.bid
                assert contract.last_price >= 0
                assert 0.01 <= contract.implied_volatility <= 5.0
                
        finally:
            await client.close()
    
    @pytest.mark.asyncio
    async def test_rate_limiting_behavior(self):
        """Test rate limiting functionality"""
        client = DerivAPIClient(
            api_key="test_key",
            app_id="test_app",
            rate_limit=100.0  # High rate limit for testing
        )
        
        try:
            # Test that rate limiter works
            rate_limiter = client.rate_limiter
            
            # Initially no failures
            assert rate_limiter.consecutive_failures == 0
            
            # Record some failures
            rate_limiter.record_failure()
            rate_limiter.record_failure()
            assert rate_limiter.consecutive_failures == 2
            
            # Record success should reset
            rate_limiter.record_success()
            assert rate_limiter.consecutive_failures == 0
            
        finally:
            await client.close()
    
    @pytest.mark.asyncio
    async def test_cache_functionality(self):
        """Test caching behavior"""
        client = DerivAPIClient(
            api_key="test_key",
            app_id="test_app",
            cache_ttl_l1=10,
            cache_ttl_l2=60
        )
        
        try:
            # Test cache operations
            cache = client.cache
            
            # Initially empty
            assert cache.get("test_key") is None
            
            # Set and retrieve
            test_data = {"test": "value"}
            cache.set("test_key", test_data)
            assert cache.get("test_key") == test_data
            
            # Test invalidation
            cache.invalidate("test_key")
            assert cache.get("test_key") is None
            
            # Test clear
            cache.set("key1", "value1")
            cache.set("key2", "value2")
            cache.clear()
            assert cache.get("key1") is None
            assert cache.get("key2") is None
            
        finally:
            await client.close()


class TestMarketDataEndpoints:
    """Integration tests for market data API endpoints"""
    
    def test_endpoint_availability(self):
        """Test that market data endpoints are available"""
        # This test verifies that the endpoints can be imported
        from market_data_endpoints import router
        
        # Check that router has the expected endpoints
        routes = [route.path for route in router.routes]
        
        expected_routes = [
            "/market-data/health",
            "/market-data/spot",
            "/market-data/option-chain",
            "/market-data/cache/stats",
            "/market-data/cache/clear",
            "/market-data/symbols"
        ]
        
        for expected_route in expected_routes:
            # Remove prefix for comparison
            route_path = expected_route.replace("/market-data", "")
            assert any(route_path in route for route in routes), f"Route {expected_route} not found"
    
    @pytest.mark.asyncio
    async def test_dependency_injection(self):
        """Test that the dependency injection works for getting client"""
        client = await get_deriv_client()
        
        assert isinstance(client, DerivAPIClient)
        assert client.api_key is not None
        assert client.app_id is not None
        
        # Clean up
        await client.close()


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])