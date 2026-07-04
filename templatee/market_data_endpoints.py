"""
Market Data API Endpoints for Deriv API integration.

This module provides FastAPI endpoints for accessing real-time market data
through the Deriv API client with Redis-backed caching.

Cache hierarchy
───────────────
L1  in-process TTLCache   30 s    per-uvicorn-worker, zero-latency
L2  Redis                 5 min   shared across all workers, sub-ms
L3  Redis (long-TTL)      1 hr    historical / yfinance / OpenBB data
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import asyncio
import logging
import json

from .deriv_api_client import (
    DerivAPIClient, MarketData, OptionChain, OptionContract,
    AssetClass, MarketDataUnavailable, ValidationError, RateLimitExceeded
)
from .cache.redis_cache import get_cache

# Configure logging
logger = logging.getLogger(__name__)

# Create router for market data endpoints
router = APIRouter(prefix="/market-data", tags=["market-data"])

# Global client instance (in production, this should be managed properly)
_deriv_client: Optional[DerivAPIClient] = None


async def get_deriv_client() -> DerivAPIClient:
    """Dependency to get or create Deriv API client"""
    global _deriv_client
    
    if _deriv_client is None:
        # In production, these should come from environment variables
        _deriv_client = DerivAPIClient(
            api_key="production_api_key",  # Replace with actual API key
            app_id="production_app_id",    # Replace with actual app ID
            base_url="https://api.deriv.com",
            cache_ttl_l1=30,  # 30 second L1 cache
            cache_ttl_l2=300, # 5 minute L2 cache
            rate_limit=10.0   # 10 requests per second
        )
    
    return _deriv_client


# Request/Response Models
class MarketDataRequest(BaseModel):
    symbol: str = Field(..., description="Asset symbol (e.g., 'AAPL', 'SPY', 'EURUSD')")
    asset_class: Optional[str] = Field(None, description="Asset class: stocks, indices, currencies, commodities")


class MarketDataResponse(BaseModel):
    symbol: str
    spot_price: float
    bid: float
    ask: float
    timestamp: datetime
    implied_volatility: Optional[float] = None
    volume: Optional[float] = None
    asset_class: Optional[str] = None
    data_age_seconds: float


class OptionChainRequest(BaseModel):
    underlying: str = Field(..., description="Underlying asset symbol")
    expiry: date = Field(..., description="Option expiration date")


class OptionContractResponse(BaseModel):
    symbol: str
    underlying: str
    strike: float
    expiry: datetime
    option_type: str
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
    timestamp: datetime


class OptionChainResponse(BaseModel):
    underlying: str
    expiry: datetime
    calls: List[OptionContractResponse]
    puts: List[OptionContractResponse]
    timestamp: datetime
    total_strikes: int


class CacheStatsResponse(BaseModel):
    l1_cache_size: int
    l2_cache_size: int
    l1_cache_info: int
    l2_cache_info: int
    rate_limiter_failures: int


# API Endpoints
@router.get("/health")
async def market_data_health_check():
    """Health check for market data service"""
    try:
        client = await get_deriv_client()
        is_connected = await client.validate_connection()
        
        return {
            "status": "healthy" if is_connected else "degraded",
            "service": "market-data",
            "api_connection": is_connected,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Market data health check failed: {e}")
        raise HTTPException(status_code=503, detail="Market data service unavailable")


@router.post("/spot", response_model=MarketDataResponse)
async def get_spot_price(
    request: MarketDataRequest,
    client: DerivAPIClient = Depends(get_deriv_client)
):
    """
    Get current spot price and market data for an asset.

    Returns real-time market data including bid/ask prices, volume,
    and implied volatility when available.
    
    Caching: L1 (30s) + L2 Redis (5min)
    """
    try:
        # Try cache first
        cache = get_cache()
        cache_key = f"spot:{request.symbol}:{request.asset_class or 'all'}"
        
        cached_data = await cache.get(cache_key)
        if cached_data is not None:
            logger.info(f"Cache hit for spot price: {request.symbol}")
            # Convert cached dict back to MarketDataResponse
            return MarketDataResponse(**cached_data)
        
        # Cache miss - fetch from API
        logger.info(f"Cache miss for spot price: {request.symbol}, fetching from API")
        
        # Parse asset class if provided
        asset_class = None
        if request.asset_class:
            try:
                asset_class = AssetClass(request.asset_class.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid asset class: {request.asset_class}"
                )

        # Fetch market data
        market_data = await client.get_market_data(request.symbol, asset_class)

        # Calculate data age
        current_time = datetime.utcnow().replace(tzinfo=market_data.timestamp.tzinfo)
        data_age = (current_time - market_data.timestamp).total_seconds()

        response = MarketDataResponse(
            symbol=market_data.symbol,
            spot_price=market_data.spot_price,
            bid=market_data.bid,
            ask=market_data.ask,
            timestamp=market_data.timestamp,
            implied_volatility=market_data.implied_volatility,
            volume=market_data.volume,
            asset_class=market_data.asset_class.value if market_data.asset_class else None,
            data_age_seconds=data_age
        )
        
        # Cache the response (L2 Redis, 5 min TTL)
        await cache.set(cache_key, response.dict(), ttl=300)
        logger.info(f"Cached spot price for {request.symbol}")
        
        return response

    except MarketDataUnavailable as e:
        logger.warning(f"Market data unavailable for {request.symbol}: {e}")
        raise HTTPException(status_code=404, detail=str(e))

    except ValidationError as e:
        logger.error(f"Market data validation error for {request.symbol}: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    except RateLimitExceeded as e:
        logger.warning(f"Rate limit exceeded: {e}")
        raise HTTPException(status_code=429, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error fetching market data for {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/option-chain", response_model=OptionChainResponse)
async def get_option_chain(
    request: OptionChainRequest,
    client: DerivAPIClient = Depends(get_deriv_client)
):
    """
    Get complete option chain for an underlying asset and expiration date.

    Returns all available call and put options with strikes, prices,
    implied volatilities, and Greeks.
    
    Caching: L1 (30s) + L2 Redis (5min)
    """
    try:
        # Try cache first
        cache = get_cache()
        cache_key = f"option-chain:{request.underlying}:{request.expiry}"
        
        cached_data = await cache.get(cache_key)
        if cached_data is not None:
            logger.info(f"Cache hit for option chain: {request.underlying} {request.expiry}")
            return OptionChainResponse(**cached_data)
        
        # Cache miss - fetch from API
        logger.info(f"Cache miss for option chain: {request.underlying} {request.expiry}, fetching from API")
        
        # Convert date to string format expected by API
        expiry_str = request.expiry.strftime('%Y-%m-%d')

        # Fetch option chain
        option_chain = await client.get_option_chain(request.underlying, expiry_str)

        # Convert contracts to response format
        def convert_contract(contract: OptionContract) -> OptionContractResponse:
            return OptionContractResponse(
                symbol=contract.symbol,
                underlying=contract.underlying,
                strike=contract.strike,
                expiry=contract.expiry,
                option_type=contract.option_type,
                bid=contract.bid,
                ask=contract.ask,
                last_price=contract.last_price,
                implied_volatility=contract.implied_volatility,
                delta=contract.delta,
                gamma=contract.gamma,
                theta=contract.theta,
                vega=contract.vega,
                rho=contract.rho,
                volume=contract.volume,
                timestamp=contract.timestamp
            )

        calls = [convert_contract(call) for call in option_chain.calls]
        puts = [convert_contract(put) for put in option_chain.puts]

        response = OptionChainResponse(
            underlying=option_chain.underlying,
            expiry=option_chain.expiry,
            calls=calls,
            puts=puts,
            timestamp=option_chain.timestamp,
            total_strikes=len(option_chain.get_strikes())
        )
        
        # Cache the response (L2 Redis, 5 min TTL)
        await cache.set(cache_key, response.dict(), ttl=300)
        logger.info(f"Cached option chain for {request.underlying} {request.expiry}")
        
        return response

    except MarketDataUnavailable as e:
        logger.warning(f"Option chain unavailable for {request.underlying}: {e}")
        raise HTTPException(status_code=404, detail=str(e))

    except ValidationError as e:
        logger.error(f"Option chain validation error for {request.underlying}: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    except RateLimitExceeded as e:
        logger.warning(f"Rate limit exceeded: {e}")
        raise HTTPException(status_code=429, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error fetching option chain for {request.underlying}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats(client: DerivAPIClient = Depends(get_deriv_client)):
    """
    Get cache statistics for monitoring and debugging.
    
    Returns information about cache usage, hit rates, and rate limiter status.
    """
    try:
        stats = client.get_cache_stats()
        
        return CacheStatsResponse(
            l1_cache_size=stats['l1_cache_size'],
            l2_cache_size=stats['l2_cache_size'],
            l1_cache_info=stats['l1_cache_info'],
            l2_cache_info=stats['l2_cache_info'],
            rate_limiter_failures=stats['rate_limiter_failures']
        )
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/cache/clear")
async def clear_cache(client: DerivAPIClient = Depends(get_deriv_client)):
    """
    Clear all cached market data.
    
    Use this endpoint to force refresh of all cached data.
    """
    try:
        await client.clear_cache()
        
        return {
            "status": "success",
            "message": "Cache cleared successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/symbols")
async def get_supported_symbols():
    """
    Get list of supported symbols and asset classes.
    
    This is a mock implementation - in production this would
    query the actual Deriv API for available symbols.
    """
    return {
        "symbols": {
            "stocks": ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN", "META", "NVDA"],
            "indices": ["SPY", "QQQ", "IWM", "VIX", "DIA"],
            "currencies": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"],
            "commodities": ["GLD", "SLV", "USO", "UNG"]
        },
        "asset_classes": ["stocks", "indices", "currencies", "commodities"],
        "note": "This is a sample list. Actual symbols depend on Deriv API availability."
    }


# Cleanup function for application shutdown
async def cleanup_deriv_client():
    """Clean up Deriv API client on application shutdown"""
    global _deriv_client
    
    if _deriv_client is not None:
        await _deriv_client.close()
        _deriv_client = None
        logger.info("Deriv API client closed")