"""
Deriv API Client for real-time market data integration.

This module provides a comprehensive API client for integrating with Deriv's
market data services, including caching, rate limiting, and error handling.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import hashlib
import random

import httpx
from cachetools import TTLCache
import structlog

# Configure structured logging
logger = structlog.get_logger(__name__)


class AssetClass(Enum):
    """Supported asset classes for market data"""
    STOCKS = "stocks"
    INDICES = "indices"
    CURRENCIES = "currencies"
    COMMODITIES = "commodities"


@dataclass
class MarketData:
    """Market data structure for underlying assets"""
    symbol: str
    spot_price: float
    bid: float
    ask: float
    timestamp: datetime
    implied_volatility: Optional[float] = None
    volume: Optional[float] = None
    asset_class: Optional[AssetClass] = None
    
    def is_stale(self, max_age_seconds: int = 300) -> bool:
        """Check if market data is stale based on timestamp"""
        if not self.timestamp:
            return True
        age = datetime.now(timezone.utc) - self.timestamp
        return age.total_seconds() > max_age_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat() if self.timestamp else None
        data['asset_class'] = self.asset_class.value if self.asset_class else None
        return data


@dataclass
class OptionContract:
    """Option contract data structure"""
    symbol: str
    underlying: str
    strike: float
    expiry: datetime
    option_type: str  # "call" or "put"
    bid: float
    ask: float
    last_price: float
    implied_volatility: float
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    volume: Optional[float] = None
    open_interest: Optional[float] = None
    timestamp: datetime = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['expiry'] = self.expiry.isoformat() if self.expiry else None
        data['timestamp'] = self.timestamp.isoformat() if self.timestamp else None
        return data


@dataclass
class OptionChain:
    """Complete option chain for an underlying asset"""
    underlying: str
    expiry: datetime
    calls: List[OptionContract]
    puts: List[OptionContract]
    timestamp: datetime
    
    def is_complete(self) -> bool:
        """Check if option chain has both calls and puts"""
        return len(self.calls) > 0 and len(self.puts) > 0
    
    def get_strikes(self) -> List[float]:
        """Get all unique strike prices in the chain"""
        strikes = set()
        for contract in self.calls + self.puts:
            strikes.add(contract.strike)
        return sorted(list(strikes))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'underlying': self.underlying,
            'expiry': self.expiry.isoformat(),
            'calls': [call.to_dict() for call in self.calls],
            'puts': [put.to_dict() for put in self.puts],
            'timestamp': self.timestamp.isoformat()
        }


class DerivAPIError(Exception):
    """Base exception for Deriv API errors"""
    pass


class RateLimitExceeded(DerivAPIError):
    """Exception raised when API rate limits are exceeded"""
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after} seconds")


class MarketDataUnavailable(DerivAPIError):
    """Exception raised when market data is unavailable"""
    pass


class ValidationError(DerivAPIError):
    """Exception raised when data validation fails"""
    pass


class MarketDataCache:
    """Multi-level caching system for market data"""
    
    def __init__(self, l1_ttl: int = 30, l2_ttl: int = 300, max_size: int = 1000):
        self.l1_cache = TTLCache(maxsize=max_size, ttl=l1_ttl)  # 30 second TTL
        self.l2_cache = TTLCache(maxsize=max_size * 2, ttl=l2_ttl)  # 5 minute TTL
        self.l1_ttl = l1_ttl
        self.l2_ttl = l2_ttl
        
    def get(self, key: str) -> Optional[Any]:
        """Get data from cache, checking L1 first, then L2"""
        # Check L1 cache first
        data = self.l1_cache.get(key)
        if data is not None:
            logger.debug("Cache hit L1", key=key)
            return data
            
        # Check L2 cache
        data = self.l2_cache.get(key)
        if data is not None:
            logger.debug("Cache hit L2", key=key)
            # Promote to L1 cache
            self.l1_cache[key] = data
            return data
            
        logger.debug("Cache miss", key=key)
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Set data in both cache levels"""
        self.l1_cache[key] = value
        self.l2_cache[key] = value
        logger.debug("Cache set", key=key)
    
    def invalidate(self, key: str) -> None:
        """Remove key from all cache levels"""
        self.l1_cache.pop(key, None)
        self.l2_cache.pop(key, None)
        logger.debug("Cache invalidated", key=key)
    
    def clear(self) -> None:
        """Clear all caches"""
        self.l1_cache.clear()
        self.l2_cache.clear()
        logger.info("All caches cleared")


class RateLimiter:
    """Rate limiter with exponential backoff and jitter"""
    
    def __init__(self, max_requests_per_second: float = 10.0, max_backoff: float = 60.0):
        self.max_requests_per_second = max_requests_per_second
        self.min_interval = 1.0 / max_requests_per_second
        self.last_request_time = 0.0
        self.consecutive_failures = 0
        self.max_backoff = max_backoff
        
    async def acquire(self) -> None:
        """Acquire permission to make a request with rate limiting"""
        current_time = time.time()
        
        # Calculate required wait time based on rate limit
        time_since_last = current_time - self.last_request_time
        required_wait = self.min_interval - time_since_last
        
        # Add exponential backoff if there have been failures
        if self.consecutive_failures > 0:
            backoff_time = min(
                (2 ** self.consecutive_failures) + random.uniform(0, 1),
                self.max_backoff
            )
            required_wait = max(required_wait, backoff_time)
            logger.info("Rate limiter backoff", 
                       failures=self.consecutive_failures, 
                       backoff_time=backoff_time)
        
        if required_wait > 0:
            logger.debug("Rate limiter wait", wait_time=required_wait)
            await asyncio.sleep(required_wait)
        
        self.last_request_time = time.time()
    
    def record_success(self) -> None:
        """Record a successful request"""
        self.consecutive_failures = 0
    
    def record_failure(self) -> None:
        """Record a failed request for backoff calculation"""
        self.consecutive_failures += 1
        logger.warning("Rate limiter failure recorded", 
                      failures=self.consecutive_failures)


class DerivAPIClient:
    """
    Comprehensive Deriv API client with caching, rate limiting, and error handling.
    
    This client provides real-time market data integration for the pricing engine,
    supporting multiple asset classes and comprehensive error handling.
    """
    
    def __init__(
        self,
        api_key: str,
        app_id: str,
        base_url: str = "https://api.deriv.com",
        cache_ttl_l1: int = 30,
        cache_ttl_l2: int = 300,
        rate_limit: float = 10.0,
        timeout: float = 30.0
    ):
        self.api_key = api_key
        self.app_id = app_id
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        
        # Initialize caching and rate limiting
        self.cache = MarketDataCache(l1_ttl=cache_ttl_l1, l2_ttl=cache_ttl_l2)
        self.rate_limiter = RateLimiter(max_requests_per_second=rate_limit)
        
        # HTTP client configuration
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-App-ID": app_id,
                "Content-Type": "application/json",
                "User-Agent": "PricingEngine/1.0.0"
            }
        )
        
        logger.info("Deriv API client initialized", 
                   base_url=base_url, 
                   rate_limit=rate_limit)
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def close(self) -> None:
        """Close the HTTP client"""
        await self.client.aclose()
        logger.info("Deriv API client closed")
    
    def _generate_cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """Generate a cache key for the request"""
        # Create a deterministic hash of the endpoint and parameters
        param_str = json.dumps(params, sort_keys=True)
        key_data = f"{endpoint}:{param_str}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _validate_market_data(self, data: Dict[str, Any]) -> None:
        """Validate incoming market data"""
        required_fields = ['symbol', 'price', 'timestamp']
        
        for field in required_fields:
            if field not in data:
                raise ValidationError(f"Missing required field: {field}")
        
        # Validate price is positive
        price = data.get('price', 0)
        if not isinstance(price, (int, float)) or price <= 0:
            raise ValidationError(f"Invalid price: {price}")
        
        # Validate volatility if present
        if 'implied_volatility' in data:
            vol = data['implied_volatility']
            if vol is not None and (not isinstance(vol, (int, float)) or vol < 0.01 or vol > 5.0):
                raise ValidationError(f"Invalid implied volatility: {vol}")
        
        # Validate timestamp
        timestamp = data.get('timestamp')
        if timestamp:
            try:
                parsed_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                # Check if timestamp is too old (more than 1 hour)
                age = datetime.now(timezone.utc) - parsed_time
                if age.total_seconds() > 3600:
                    logger.warning("Stale market data", symbol=data['symbol'], age_hours=age.total_seconds()/3600)
            except (ValueError, TypeError) as e:
                raise ValidationError(f"Invalid timestamp format: {timestamp}") from e
    
    async def _make_request(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Make an HTTP request with rate limiting and error handling"""
        if params is None:
            params = {}
        
        # Check cache first
        cache_key = self._generate_cache_key(endpoint, params)
        if use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        # Apply rate limiting
        await self.rate_limiter.acquire()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            logger.debug("Making API request", url=url, params=params)
            
            response = await self.client.get(url, params=params)
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                self.rate_limiter.record_failure()
                raise RateLimitExceeded(retry_after)
            
            # Handle other HTTP errors
            if response.status_code >= 400:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error("API request failed", 
                           status_code=response.status_code, 
                           error=error_msg)
                self.rate_limiter.record_failure()
                raise DerivAPIError(error_msg)
            
            # Parse response
            data = response.json()
            
            # Validate response structure
            if 'error' in data:
                error_msg = data['error'].get('message', 'Unknown API error')
                logger.error("API returned error", error=error_msg)
                self.rate_limiter.record_failure()
                raise DerivAPIError(error_msg)
            
            # Cache successful response
            if use_cache:
                self.cache.set(cache_key, data)
            
            self.rate_limiter.record_success()
            logger.debug("API request successful", endpoint=endpoint)
            
            return data
            
        except httpx.TimeoutException as e:
            self.rate_limiter.record_failure()
            logger.error("API request timeout", endpoint=endpoint, timeout=self.timeout)
            raise DerivAPIError(f"Request timeout: {endpoint}") from e
        
        except httpx.RequestError as e:
            self.rate_limiter.record_failure()
            logger.error("API request error", endpoint=endpoint, error=str(e))
            raise DerivAPIError(f"Request failed: {endpoint}") from e
    
    async def get_market_data(self, symbol: str, asset_class: Optional[AssetClass] = None) -> MarketData:
        """
        Fetch current market data for an underlying asset.
        
        Args:
            symbol: Asset symbol (e.g., 'AAPL', 'SPY', 'EURUSD')
            asset_class: Optional asset class for validation
            
        Returns:
            MarketData object with current prices and metadata
            
        Raises:
            MarketDataUnavailable: When data is not available
            ValidationError: When data validation fails
        """
        try:
            # Mock implementation for demonstration - replace with actual Deriv API calls
            params = {
                'symbol': symbol,
                'fields': 'price,bid,ask,volume,implied_volatility'
            }
            
            # For now, return mock data that passes validation
            # In production, this would call the actual Deriv API
            current_time = datetime.now(timezone.utc)
            
            # Generate realistic mock data
            base_price = 100.0 + hash(symbol) % 200  # Deterministic but varied prices
            spread = base_price * 0.001  # 0.1% spread
            
            mock_data = {
                'symbol': symbol,
                'price': base_price,
                'bid': base_price - spread/2,
                'ask': base_price + spread/2,
                'timestamp': current_time.isoformat(),
                'implied_volatility': 0.2 + (hash(symbol) % 100) / 1000,  # 0.2-0.3 range
                'volume': 1000000 + hash(symbol) % 5000000
            }
            
            # Validate the data
            self._validate_market_data(mock_data)
            
            return MarketData(
                symbol=symbol,
                spot_price=mock_data['price'],
                bid=mock_data['bid'],
                ask=mock_data['ask'],
                timestamp=current_time,
                implied_volatility=mock_data.get('implied_volatility'),
                volume=mock_data.get('volume'),
                asset_class=asset_class
            )
            
        except Exception as e:
            logger.error("Failed to fetch market data", symbol=symbol, error=str(e))
            if isinstance(e, (DerivAPIError, ValidationError)):
                raise
            raise MarketDataUnavailable(f"Market data unavailable for {symbol}") from e
    
    async def get_option_chain(self, underlying: str, expiry: str) -> OptionChain:
        """
        Retrieve complete option chain data for an underlying asset.
        
        Args:
            underlying: Underlying asset symbol
            expiry: Expiration date in YYYY-MM-DD format
            
        Returns:
            OptionChain object with calls and puts data
            
        Raises:
            MarketDataUnavailable: When option chain is not available
            ValidationError: When data validation fails
        """
        try:
            expiry_date = datetime.fromisoformat(expiry).replace(tzinfo=timezone.utc)
            current_time = datetime.now(timezone.utc)
            
            # Mock option chain data - replace with actual API calls
            calls = []
            puts = []
            
            # Generate mock option contracts
            base_price = 100.0 + hash(underlying) % 200
            strikes = [base_price * (0.8 + i * 0.05) for i in range(9)]  # 9 strikes around ATM
            
            for i, strike in enumerate(strikes):
                # Mock call option
                call_price = max(base_price - strike, 0) + 5.0 - i * 0.5  # Intrinsic + time value
                call = OptionContract(
                    symbol=f"{underlying}_{expiry}_C_{strike}",
                    underlying=underlying,
                    strike=strike,
                    expiry=expiry_date,
                    option_type="call",
                    bid=call_price * 0.99,
                    ask=call_price * 1.01,
                    last_price=call_price,
                    implied_volatility=0.2 + i * 0.01,
                    delta=0.1 + i * 0.1,
                    gamma=0.05,
                    theta=-0.02,
                    vega=0.15,
                    rho=0.05,
                    volume=1000 + i * 100,
                    timestamp=current_time
                )
                calls.append(call)
                
                # Mock put option
                put_price = max(strike - base_price, 0) + 5.0 - i * 0.5  # Intrinsic + time value
                put = OptionContract(
                    symbol=f"{underlying}_{expiry}_P_{strike}",
                    underlying=underlying,
                    strike=strike,
                    expiry=expiry_date,
                    option_type="put",
                    bid=put_price * 0.99,
                    ask=put_price * 1.01,
                    last_price=put_price,
                    implied_volatility=0.2 + i * 0.01,
                    delta=-(0.9 - i * 0.1),
                    gamma=0.05,
                    theta=-0.02,
                    vega=0.15,
                    rho=-0.05,
                    volume=800 + i * 80,
                    timestamp=current_time
                )
                puts.append(put)
            
            option_chain = OptionChain(
                underlying=underlying,
                expiry=expiry_date,
                calls=calls,
                puts=puts,
                timestamp=current_time
            )
            
            if not option_chain.is_complete():
                raise MarketDataUnavailable(f"Incomplete option chain for {underlying}")
            
            logger.info("Option chain retrieved", 
                       underlying=underlying, 
                       expiry=expiry,
                       calls_count=len(calls),
                       puts_count=len(puts))
            
            return option_chain
            
        except Exception as e:
            logger.error("Failed to fetch option chain", 
                        underlying=underlying, 
                        expiry=expiry, 
                        error=str(e))
            if isinstance(e, (DerivAPIError, ValidationError, MarketDataUnavailable)):
                raise
            raise MarketDataUnavailable(f"Option chain unavailable for {underlying}") from e
    
    async def validate_connection(self) -> bool:
        """
        Validate API connection and credentials.
        
        Returns:
            True if connection is valid, False otherwise
        """
        try:
            # Simple health check endpoint
            await self._make_request('/health', use_cache=False)
            logger.info("API connection validated")
            return True
        except Exception as e:
            logger.error("API connection validation failed", error=str(e))
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        return {
            'l1_cache_size': len(self.cache.l1_cache),
            'l2_cache_size': len(self.cache.l2_cache),
            'l1_cache_info': self.cache.l1_cache.currsize,
            'l2_cache_info': self.cache.l2_cache.currsize,
            'rate_limiter_failures': self.rate_limiter.consecutive_failures
        }
    
    async def clear_cache(self) -> None:
        """Clear all cached data"""
        self.cache.clear()
        logger.info("Cache cleared")


# Utility functions for testing and development
async def create_test_client() -> DerivAPIClient:
    """Create a test client with mock credentials"""
    return DerivAPIClient(
        api_key="test_api_key",
        app_id="test_app_id",
        base_url="https://api.deriv.com",
        rate_limit=5.0  # Lower rate limit for testing
    )


async def with_retry(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0
) -> Any:
    """
    Retry wrapper for API calls with exponential backoff.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries
        max_delay: Maximum delay between retries
        
    Returns:
        Result of the function call
        
    Raises:
        The last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except RateLimitExceeded as e:
            if attempt == max_retries:
                raise
            delay = min(e.retry_after + random.uniform(0, 1), max_delay)
            logger.info("Retrying after rate limit", attempt=attempt, delay=delay)
            await asyncio.sleep(delay)
            last_exception = e
        except (DerivAPIError, MarketDataUnavailable) as e:
            if attempt == max_retries:
                raise
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
            logger.info("Retrying after error", attempt=attempt, delay=delay, error=str(e))
            await asyncio.sleep(delay)
            last_exception = e
    
    # This should never be reached, but just in case
    if last_exception:
        raise last_exception