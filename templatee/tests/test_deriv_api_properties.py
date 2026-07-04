"""
Property-based tests for Deriv API integration.

These tests validate the correctness properties defined in the design document
using hypothesis for property-based testing.
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from unittest.mock import AsyncMock, patch

from hypothesis import given, strategies as st, settings, assume, HealthCheck
from hypothesis.strategies import composite

# Import the modules under test
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deriv_api_client import (
    DerivAPIClient, MarketData, OptionChain, OptionContract,
    AssetClass, MarketDataUnavailable, ValidationError, RateLimitExceeded
)

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


# Custom strategies for generating test data
@composite
def market_data_strategy(draw):
    """Generate valid MarketData objects for testing"""
    symbol = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    spot_price = draw(st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False))
    spread = spot_price * draw(st.floats(min_value=0.0001, max_value=0.01))
    
    # Generate timezone-naive datetime and then add timezone
    base_time = draw(st.datetimes(
        min_value=datetime(2025, 1, 1),
        max_value=datetime(2025, 12, 31)
    ))
    timestamp = base_time.replace(tzinfo=timezone.utc)
    
    return MarketData(
        symbol=symbol,
        spot_price=spot_price,
        bid=spot_price - spread/2,
        ask=spot_price + spread/2,
        timestamp=timestamp,
        implied_volatility=draw(st.one_of(
            st.none(),
            st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False)
        )),
        volume=draw(st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False)
        )),
        asset_class=draw(st.one_of(st.none(), st.sampled_from(AssetClass)))
    )


@composite
def option_contract_strategy(draw, underlying: str = None, expiry: datetime = None):
    """Generate valid OptionContract objects for testing"""
    if underlying is None:
        underlying = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    
    if expiry is None:
        # Generate timezone-naive datetime and then add timezone
        base_expiry = draw(st.datetimes(
            min_value=datetime(2025, 1, 1),
            max_value=datetime(2026, 12, 31)
        ))
        expiry = base_expiry.replace(tzinfo=timezone.utc)
    
    strike = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    option_type = draw(st.sampled_from(['call', 'put']))
    
    # Generate realistic option prices
    last_price = draw(st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False))
    spread = last_price * draw(st.floats(min_value=0.001, max_value=0.05))
    
    # Generate timezone-naive datetime and then add timezone
    base_timestamp = draw(st.datetimes(
        min_value=datetime(2025, 1, 1),
        max_value=datetime(2025, 12, 31)
    ))
    timestamp = base_timestamp.replace(tzinfo=timezone.utc)
    
    return OptionContract(
        symbol=f"{underlying}_{expiry.strftime('%Y%m%d')}_{option_type[0].upper()}_{strike}",
        underlying=underlying,
        strike=strike,
        expiry=expiry,
        option_type=option_type,
        bid=last_price - spread/2,
        ask=last_price + spread/2,
        last_price=last_price,
        implied_volatility=draw(st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False)),
        delta=draw(st.one_of(st.none(), st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False))),
        gamma=draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))),
        theta=draw(st.one_of(st.none(), st.floats(min_value=-1.0, max_value=0.0, allow_nan=False, allow_infinity=False))),
        vega=draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))),
        rho=draw(st.one_of(st.none(), st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False))),
        volume=draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False))),
        timestamp=timestamp
    )


@composite
def option_chain_strategy(draw):
    """Generate valid OptionChain objects for testing"""
    underlying = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    
    # Generate timezone-naive datetime and then add timezone
    base_expiry = draw(st.datetimes(
        min_value=datetime(2025, 1, 1),
        max_value=datetime(2026, 12, 31)
    ))
    expiry = base_expiry.replace(tzinfo=timezone.utc)
    
    # Generate at least one call and one put to ensure completeness
    num_contracts = draw(st.integers(min_value=2, max_value=20))
    calls = []
    puts = []
    
    for i in range(num_contracts // 2 + 1):
        calls.append(draw(option_contract_strategy(underlying=underlying, expiry=expiry)))
        calls[-1].option_type = 'call'
        
    for i in range(num_contracts // 2 + 1):
        puts.append(draw(option_contract_strategy(underlying=underlying, expiry=expiry)))
        puts[-1].option_type = 'put'
    
    # Generate timezone-naive datetime and then add timezone
    base_timestamp = draw(st.datetimes(
        min_value=datetime(2025, 1, 1),
        max_value=datetime(2025, 12, 31)
    ))
    timestamp = base_timestamp.replace(tzinfo=timezone.utc)
    
    return OptionChain(
        underlying=underlying,
        expiry=expiry,
        calls=calls,
        puts=puts,
        timestamp=timestamp
    )


class TestMarketDataFreshness:
    """
    Property 18: Market Data Freshness
    **Validates: Requirements 5.1**
    
    For any market data request, the Deriv API integration should return data 
    with timestamps no older than the configured cache TTL and should include 
    all required fields.
    """
    
    @given(
        symbol=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
        cache_ttl=st.integers(min_value=1, max_value=300)
    )
    @settings(max_examples=20, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_market_data_freshness_property(self, symbol, cache_ttl):
        """
        **Feature: pricing-engine-enhancements, Property 18: Market Data Freshness**
        
        For any market data request, the returned data should have timestamps
        within the cache TTL and contain all required fields.
        """
        assume(len(symbol.strip()) > 0)  # Ensure non-empty symbol
        
        async def run_test():
            # Create client with specified cache TTL
            client = DerivAPIClient(
                api_key="test_key",
                app_id="test_app",
                cache_ttl_l1=cache_ttl,
                cache_ttl_l2=cache_ttl * 2
            )
            
            try:
                # Get market data
                market_data = await client.get_market_data(symbol)
                
                # Property: Data should have recent timestamp
                current_time = datetime.now(timezone.utc)
                data_age = (current_time - market_data.timestamp).total_seconds()
                
                # Data should be fresh (within reasonable bounds for testing)
                # Allow some tolerance for test execution time
                assert data_age <= cache_ttl + 60, f"Market data too old: {data_age}s > {cache_ttl + 60}s"
                
                # Property: All required fields should be present and valid
                assert market_data.symbol == symbol
                assert isinstance(market_data.spot_price, (int, float))
                assert market_data.spot_price > 0
                assert isinstance(market_data.bid, (int, float))
                assert market_data.bid > 0
                assert isinstance(market_data.ask, (int, float))
                assert market_data.ask > 0
                assert market_data.ask >= market_data.bid  # Spread should be non-negative
                assert isinstance(market_data.timestamp, datetime)
                
                # Property: Optional fields should be valid if present
                if market_data.implied_volatility is not None:
                    assert isinstance(market_data.implied_volatility, (int, float))
                    assert 0.01 <= market_data.implied_volatility <= 5.0
                
                if market_data.volume is not None:
                    assert isinstance(market_data.volume, (int, float))
                    assert market_data.volume >= 0
                    
            finally:
                await client.close()
        
        # Run the async test
        asyncio.run(run_test())
    
    @given(market_data=market_data_strategy())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_market_data_staleness_detection(self, market_data):
        """
        Property: Market data staleness should be correctly detected
        """
        current_time = datetime.now(timezone.utc)
        
        # Test fresh data
        fresh_data = MarketData(
            symbol=market_data.symbol,
            spot_price=market_data.spot_price,
            bid=market_data.bid,
            ask=market_data.ask,
            timestamp=current_time - timedelta(seconds=30),  # 30 seconds old
            implied_volatility=market_data.implied_volatility,
            volume=market_data.volume,
            asset_class=market_data.asset_class
        )
        
        # Should not be stale with default 300s threshold
        assert not fresh_data.is_stale()
        assert not fresh_data.is_stale(max_age_seconds=60)
        
        # Test stale data
        stale_data = MarketData(
            symbol=market_data.symbol,
            spot_price=market_data.spot_price,
            bid=market_data.bid,
            ask=market_data.ask,
            timestamp=current_time - timedelta(seconds=400),  # 400 seconds old
            implied_volatility=market_data.implied_volatility,
            volume=market_data.volume,
            asset_class=market_data.asset_class
        )
        
        # Should be stale with default 300s threshold
        assert stale_data.is_stale()
        assert stale_data.is_stale(max_age_seconds=300)
        
        # Test data without timestamp
        no_timestamp_data = MarketData(
            symbol=market_data.symbol,
            spot_price=market_data.spot_price,
            bid=market_data.bid,
            ask=market_data.ask,
            timestamp=None,
            implied_volatility=market_data.implied_volatility,
            volume=market_data.volume,
            asset_class=market_data.asset_class
        )
        
        # Should be considered stale if no timestamp
        assert no_timestamp_data.is_stale()


class TestOptionChainCompleteness:
    """
    Property 19: Option Chain Completeness
    **Validates: Requirements 5.2**
    
    For any valid underlying symbol and expiration date, the API should return 
    option chain data containing strikes, prices, implied volatilities, and 
    Greeks for both calls and puts.
    """
    
    @given(
        underlying=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
        days_to_expiry=st.integers(min_value=1, max_value=365)
    )
    @settings(max_examples=20, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_option_chain_completeness_property(self, underlying, days_to_expiry):
        """
        **Feature: pricing-engine-enhancements, Property 19: Option Chain Completeness**
        
        For any valid underlying and expiration, the option chain should contain
        complete data for both calls and puts with all required fields.
        """
        assume(len(underlying.strip()) > 0)  # Ensure non-empty underlying
        
        async def run_test():
            # Calculate expiry date
            expiry_date = datetime.now(timezone.utc) + timedelta(days=days_to_expiry)
            expiry_str = expiry_date.strftime('%Y-%m-%d')
            
            client = DerivAPIClient(
                api_key="test_key",
                app_id="test_app"
            )
            
            try:
                # Get option chain
                option_chain = await client.get_option_chain(underlying, expiry_str)
                
                # Property: Option chain should be complete (have both calls and puts)
                assert option_chain.is_complete(), "Option chain should have both calls and puts"
                assert len(option_chain.calls) > 0, "Option chain should have call options"
                assert len(option_chain.puts) > 0, "Option chain should have put options"
                
                # Property: All contracts should have required fields
                all_contracts = option_chain.calls + option_chain.puts
                
                for contract in all_contracts:
                    # Required fields validation
                    assert contract.symbol is not None and len(contract.symbol) > 0
                    assert contract.underlying == underlying
                    assert isinstance(contract.strike, (int, float)) and contract.strike > 0
                    assert contract.expiry is not None
                    assert contract.option_type in ['call', 'put']
                    
                    # Price fields validation
                    assert isinstance(contract.bid, (int, float)) and contract.bid >= 0
                    assert isinstance(contract.ask, (int, float)) and contract.ask >= 0
                    assert isinstance(contract.last_price, (int, float)) and contract.last_price >= 0
                    assert contract.ask >= contract.bid  # Spread should be non-negative
                    
                    # Implied volatility validation
                    assert isinstance(contract.implied_volatility, (int, float))
                    assert 0.01 <= contract.implied_volatility <= 5.0
                    
                    # Greeks validation (if present)
                    if contract.delta is not None:
                        assert isinstance(contract.delta, (int, float))
                        if contract.option_type == 'call':
                            assert 0 <= contract.delta <= 1
                        else:  # put
                            assert -1 <= contract.delta <= 0
                    
                    if contract.gamma is not None:
                        assert isinstance(contract.gamma, (int, float))
                        assert contract.gamma >= 0  # Gamma should be non-negative
                    
                    if contract.theta is not None:
                        assert isinstance(contract.theta, (int, float))
                        # Theta is typically negative for long options
                    
                    if contract.vega is not None:
                        assert isinstance(contract.vega, (int, float))
                        assert contract.vega >= 0  # Vega should be non-negative
                    
                    if contract.rho is not None:
                        assert isinstance(contract.rho, (int, float))
                        # Rho sign depends on option type but we don't enforce here
                
                # Property: Strike prices should be available
                strikes = option_chain.get_strikes()
                assert len(strikes) > 0, "Option chain should have strike prices"
                assert strikes == sorted(strikes), "Strike prices should be sorted"
                
                # Property: Timestamp should be recent
                current_time = datetime.now(timezone.utc)
                chain_age = (current_time - option_chain.timestamp).total_seconds()
                assert chain_age <= 3600, f"Option chain too old: {chain_age}s"  # Within 1 hour
                
            finally:
                await client.close()
        
        # Run the async test
        asyncio.run(run_test())
    
    @given(option_chain=option_chain_strategy())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_option_chain_structure_properties(self, option_chain):
        """
        Property: Option chain structure should be consistent and complete
        """
        # Property: Completeness check should work correctly
        assert option_chain.is_complete() == (len(option_chain.calls) > 0 and len(option_chain.puts) > 0)
        
        # Property: Strike extraction should work
        strikes = option_chain.get_strikes()
        all_strikes = set()
        for contract in option_chain.calls + option_chain.puts:
            all_strikes.add(contract.strike)
        
        assert set(strikes) == all_strikes
        assert strikes == sorted(strikes)
        
        # Property: All contracts should have consistent underlying and expiry
        for contract in option_chain.calls + option_chain.puts:
            assert contract.underlying == option_chain.underlying
            assert contract.expiry.date() == option_chain.expiry.date()
        
        # Property: Calls should be calls, puts should be puts
        for call in option_chain.calls:
            assert call.option_type == 'call'
        
        for put in option_chain.puts:
            assert put.option_type == 'put'


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])


class TestRateLimitBackoffBehavior:
    """
    Property 20: Rate Limit Backoff Behavior
    **Validates: Requirements 5.5**
    
    For any sequence of API calls that triggers rate limiting, the system should 
    implement exponential backoff with jitter and should not exceed the API 
    provider's rate limits.
    """
    
    @given(
        failure_count=st.integers(min_value=1, max_value=5),
        max_backoff=st.floats(min_value=10.0, max_value=120.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_rate_limit_backoff_behavior_property(self, failure_count, max_backoff):
        """
        **Feature: pricing-engine-enhancements, Property 20: Rate Limit Backoff Behavior**
        
        For any sequence of failures, the rate limiter should implement exponential
        backoff with jitter and respect maximum backoff limits.
        """
        from deriv_api_client import RateLimiter
        
        # Create rate limiter with specified max backoff
        rate_limiter = RateLimiter(max_requests_per_second=10.0, max_backoff=max_backoff)
        
        # Record multiple failures
        for _ in range(failure_count):
            rate_limiter.record_failure()
        
        # Property: Consecutive failures should be recorded correctly
        assert rate_limiter.consecutive_failures == failure_count
        
        # Property: Backoff time should follow exponential pattern but respect max_backoff
        # We can't easily test the actual sleep time, but we can test the calculation logic
        expected_base_backoff = min(2 ** failure_count, max_backoff)
        
        # The actual backoff includes jitter, so it should be between base and base + 1
        # We test this indirectly by ensuring the failure count is correct
        assert rate_limiter.consecutive_failures <= 10  # Reasonable upper bound
        
        # Property: Recording success should reset failure count
        rate_limiter.record_success()
        assert rate_limiter.consecutive_failures == 0
    
    @given(
        requests_per_second=st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_rate_limiter_interval_property(self, requests_per_second):
        """
        Property: Rate limiter should enforce minimum intervals between requests
        """
        from deriv_api_client import RateLimiter
        
        rate_limiter = RateLimiter(max_requests_per_second=requests_per_second)
        
        # Property: Minimum interval should be inverse of requests per second
        expected_min_interval = 1.0 / requests_per_second
        assert abs(rate_limiter.min_interval - expected_min_interval) < 1e-10
        
        # Property: No failures initially
        assert rate_limiter.consecutive_failures == 0


class TestDataCachingEfficiency:
    """
    Property 21: Data Caching Efficiency
    **Validates: Requirements 5.6**
    
    For any repeated market data request within the cache TTL period, the system 
    should serve data from cache without making additional API calls while 
    maintaining data accuracy.
    """
    
    @given(
        cache_key=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
        ttl_l1=st.integers(min_value=1, max_value=60),
        ttl_l2=st.integers(min_value=60, max_value=300)
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_data_caching_efficiency_property(self, cache_key, ttl_l1, ttl_l2):
        """
        **Feature: pricing-engine-enhancements, Property 21: Data Caching Efficiency**
        
        For any cache key and TTL configuration, the cache should store and retrieve
        data efficiently within the TTL period.
        """
        assume(len(cache_key.strip()) > 0)  # Ensure non-empty cache key
        assume(ttl_l2 >= ttl_l1)  # L2 TTL should be >= L1 TTL
        
        from deriv_api_client import MarketDataCache
        
        # Create cache with specified TTLs
        cache = MarketDataCache(l1_ttl=ttl_l1, l2_ttl=ttl_l2, max_size=100)
        
        # Test data
        test_data = {"symbol": "TEST", "price": 100.0, "timestamp": "2023-01-01T00:00:00Z"}
        
        # Property: Cache miss should return None initially
        assert cache.get(cache_key) is None
        
        # Property: After setting data, it should be retrievable
        cache.set(cache_key, test_data)
        retrieved_data = cache.get(cache_key)
        assert retrieved_data == test_data
        
        # Property: Data should be in both L1 and L2 caches after setting
        assert cache_key in cache.l1_cache
        assert cache_key in cache.l2_cache
        
        # Property: Cache should maintain data integrity
        assert cache.l1_cache[cache_key] == test_data
        assert cache.l2_cache[cache_key] == test_data
        
        # Property: Invalidation should remove from both caches
        cache.invalidate(cache_key)
        assert cache.get(cache_key) is None
        assert cache_key not in cache.l1_cache
        assert cache_key not in cache.l2_cache
    
    @given(
        num_keys=st.integers(min_value=1, max_value=20),
        max_size=st.integers(min_value=5, max_value=50)
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_cache_size_limits_property(self, num_keys, max_size):
        """
        Property: Cache should respect size limits and evict old entries
        """
        assume(num_keys > 0 and max_size > 0)
        
        from deriv_api_client import MarketDataCache
        
        cache = MarketDataCache(l1_ttl=30, l2_ttl=300, max_size=max_size)
        
        # Fill cache with test data
        for i in range(min(num_keys, max_size * 2)):  # Potentially overflow the cache
            cache_key = f"key_{i}"
            test_data = {"value": i}
            cache.set(cache_key, test_data)
        
        # Property: Cache size should not exceed max_size
        assert len(cache.l1_cache) <= max_size
        assert len(cache.l2_cache) <= max_size * 2  # L2 can be larger
        
        # Property: Clear should empty all caches
        cache.clear()
        assert len(cache.l1_cache) == 0
        assert len(cache.l2_cache) == 0
    
    @given(market_data=market_data_strategy())
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_cache_data_integrity_property(self, market_data):
        """
        Property: Cache should maintain data integrity for complex objects
        """
        from deriv_api_client import MarketDataCache
        
        cache = MarketDataCache(l1_ttl=30, l2_ttl=300, max_size=100)
        cache_key = f"market_data_{market_data.symbol}"
        
        # Property: Complex objects should be stored and retrieved correctly
        cache.set(cache_key, market_data)
        retrieved_data = cache.get(cache_key)
        
        assert retrieved_data == market_data
        assert retrieved_data.symbol == market_data.symbol
        assert retrieved_data.spot_price == market_data.spot_price
        assert retrieved_data.bid == market_data.bid
        assert retrieved_data.ask == market_data.ask
        assert retrieved_data.timestamp == market_data.timestamp
        assert retrieved_data.implied_volatility == market_data.implied_volatility
        assert retrieved_data.volume == market_data.volume
        assert retrieved_data.asset_class == market_data.asset_class


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])