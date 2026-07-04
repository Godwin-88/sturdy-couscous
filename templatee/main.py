from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging
import uuid
import time

# Import enhanced error handling and health checks
from .error_handling import (
    handle_api_error, create_error_context, ValidationError, CalculationError,
    NumericalInstabilityError, configure_logging, error_handler
)
from .health_check import get_health_report, get_basic_health, health_checker

# Try to import the Rust pricing engine, fall back to mock if not available
try:
    import pricing_engine
    USING_MOCK = False
except ImportError:
    import pricing_engine_mock as pricing_engine
    USING_MOCK = True
    print("Warning: Using mock pricing engine for testing")

# Import Redis cache
try:
    from .cache.redis_cache import get_cache, close_cache
    REDIS_AVAILABLE = True
    print("Redis cache module loaded successfully")
except ImportError as e:
    print(f"Warning: Redis cache not available: {e}")
    REDIS_AVAILABLE = False

# Import market data endpoints
try:
    from .market_data_endpoints import router as market_data_router, cleanup_deriv_client
    MARKET_DATA_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Market data endpoints not available: {e}")
    MARKET_DATA_AVAILABLE = False

# Import Transact Phase 1 routes (Portfolio, Risk, Optimizer, Blotter)
try:
    from .transact_routes import router as transact_router
    TRANSACT_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Transact routes not available: {e}")
    TRANSACT_AVAILABLE = False

# Import Asset Universe (yfinance-backed symbol search)
try:
    from .asset_universe import router as asset_universe_router
    ASSET_UNIVERSE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Asset universe routes not available: {e}")
    ASSET_UNIVERSE_AVAILABLE = False

# Import Agent gateway (Neo4j + Ollama skills)
try:
    from .agents.routes import router as agents_router
    AGENTS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Agent routes not available: {e}")
    AGENTS_AVAILABLE = False

# Configure enhanced logging
configure_logging(log_level="INFO", log_format="json")

app = FastAPI(
    title="Derivatives Pricing Engine",
    version="1.0.0",
    description="High-performance derivatives pricing engine with comprehensive error handling and monitoring"
)

# Request ID middleware — defined first so CORS (added after) is outermost.
# In Starlette, add_middleware() inserts at position 0; reversed() at build time
# means the LAST add_middleware call becomes the outermost wrapper.
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    start_time = time.time()
    try:
        response = await call_next(request)
    except Exception:
        from fastapi.responses import JSONResponse
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    process_time = time.time() - start_time

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = str(process_time)

    return response

# CORS — added AFTER the @app.middleware decorator so it's inserted last
# and therefore becomes the TRUE outermost middleware after stack reversal.
_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include market data router if available
if MARKET_DATA_AVAILABLE:
    app.include_router(market_data_router)

# Include Transact Phase 1 router
if TRANSACT_AVAILABLE:
    app.include_router(transact_router)
    # Add cleanup handler
    @app.on_event("shutdown")
    async def shutdown_event():
        await cleanup_deriv_client()
        if REDIS_AVAILABLE:
            await close_cache()

# Include Asset Universe (yfinance) router
if ASSET_UNIVERSE_AVAILABLE:
    app.include_router(asset_universe_router)

# Include Agent router (Neo4j + Ollama)
if AGENTS_AVAILABLE:
    app.include_router(agents_router)

# Add Redis health check endpoint if available
if REDIS_AVAILABLE:
    @app.get("/cache/health")
    async def cache_health_check():
        """Health check for Redis cache"""
        try:
            cache = get_cache()
            is_connected = await cache.ping()
            stats = cache.stats()
            
            return {
                "status": "healthy" if is_connected else "degraded",
                "service": "redis-cache",
                "redis_connected": is_connected,
                "stats": stats,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "redis-cache",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @app.get("/cache/stats")
    async def get_cache_statistics():
        """Get detailed cache statistics"""
        try:
            cache = get_cache()
            stats = cache.stats()
            return {
                "status": "success",
                "cache_stats": stats,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/cache/clear")
    async def clear_all_cache():
        """Clear all cached data (L1 + L2)"""
        try:
            cache = get_cache()
            deleted = await cache.clear_pattern("*")
            return {
                "status": "success",
                "message": f"Cleared {deleted} keys from cache",
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


class OptionRequest(BaseModel):
    s: float  # Current stock price
    k: float  # Strike price
    tau: float  # Time to expiration
    r: float  # Risk-free rate
    sigma: float  # Volatility

class FFTRequest(BaseModel):
    s: float
    k_min: float
    delta_v: float
    delta_k: float
    n: int
    tau: float
    r: float
    sigma: float
    alpha: float

class FFTOptimizedRequest(BaseModel):
    s: float  # Current stock price
    k: float  # Strike price
    tau: float  # Time to expiration
    r: float  # Risk-free rate
    sigma: float  # Volatility

class HestonRequest(BaseModel):
    s: float  # Current stock price
    k: float  # Strike price
    tau: float  # Time to expiration
    r: float  # Risk-free rate
    v0: float  # Initial variance
    theta: float  # Long-term variance
    kappa: float  # Mean reversion speed
    sigma_v: float  # Volatility of volatility (xi)
    rho: float  # Correlation

class GreeksRequest(BaseModel):
    s: float  # Current stock price
    k: float  # Strike price
    tau: float  # Time to expiration
    r: float  # Risk-free rate
    sigma: float  # Volatility
    model: str  # "bs", "fft", or "numerical"

class HestonGreeksRequest(BaseModel):
    s: float  # Current stock price
    k: float  # Strike price
    tau: float  # Time to expiration
    r: float  # Risk-free rate
    v0: float  # Initial variance
    theta: float  # Long-term variance
    kappa: float  # Mean reversion speed
    sigma_v: float  # Volatility of volatility (xi)
    rho: float  # Correlation

@app.get("/")
def root():
    return {"message": "Derivatives Pricing Engine API"}

# ===== BLACK-SCHOLES ENDPOINTS =====
@app.post("/price/call/bs")
async def price_call_bs(request: OptionRequest, http_request: Request):
    """Price call option using Black-Scholes model with enhanced error handling"""
    try:
        # Validate input parameters
        if request.s <= 0:
            raise ValidationError("Spot price must be positive", field="s", value=request.s)
        if request.k <= 0:
            raise ValidationError("Strike price must be positive", field="k", value=request.k)
        if request.tau <= 0:
            raise ValidationError("Time to expiration must be positive", field="tau", value=request.tau)
        if request.sigma <= 0:
            raise ValidationError("Volatility must be positive", field="sigma", value=request.sigma)
        
        # Create error context for tracking
        context = create_error_context(
            request_id=getattr(http_request.state, 'request_id', None),
            endpoint="/price/call/bs",
            parameters=request.dict()
        )
        
        # Calculate price
        price = pricing_engine.price_call(request.s, request.k, request.tau, request.r, request.sigma)
        
        # Validate result
        if not isinstance(price, (int, float)) or price < 0:
            raise CalculationError(
                "Invalid pricing result",
                model="Black-Scholes",
                parameters=request.dict()
            )
        
        return {
            "price": price, 
            "model": "Black-Scholes",
            "request_id": context.request_id
        }
        
    except (ValidationError, CalculationError) as e:
        context = create_error_context(
            request_id=getattr(http_request.state, 'request_id', None),
            endpoint="/price/call/bs",
            parameters=request.dict()
        )
        raise handle_api_error(e, context)
    except Exception as e:
        context = create_error_context(
            request_id=getattr(http_request.state, 'request_id', None),
            endpoint="/price/call/bs",
            parameters=request.dict()
        )
        calculation_error = CalculationError(
            f"Black-Scholes call pricing failed: {str(e)}",
            model="Black-Scholes",
            parameters=request.dict()
        )
        raise handle_api_error(calculation_error, context)

@app.post("/price/put/bs")
async def price_put_bs(request: OptionRequest, http_request: Request):
    """Price put option using Black-Scholes model with enhanced error handling"""
    try:
        # Validate input parameters
        if request.s <= 0:
            raise ValidationError("Spot price must be positive", field="s", value=request.s)
        if request.k <= 0:
            raise ValidationError("Strike price must be positive", field="k", value=request.k)
        if request.tau <= 0:
            raise ValidationError("Time to expiration must be positive", field="tau", value=request.tau)
        if request.sigma <= 0:
            raise ValidationError("Volatility must be positive", field="sigma", value=request.sigma)
        
        # Create error context for tracking
        context = create_error_context(
            request_id=getattr(http_request.state, 'request_id', None),
            endpoint="/price/put/bs",
            parameters=request.dict()
        )
        
        # Calculate price
        price = pricing_engine.price_put(request.s, request.k, request.tau, request.r, request.sigma)
        
        # Validate result
        if not isinstance(price, (int, float)) or price < 0:
            raise CalculationError(
                "Invalid pricing result",
                model="Black-Scholes",
                parameters=request.dict()
            )
        
        return {
            "price": price, 
            "model": "Black-Scholes",
            "request_id": context.request_id
        }
        
    except (ValidationError, CalculationError) as e:
        context = create_error_context(
            request_id=getattr(http_request.state, 'request_id', None),
            endpoint="/price/put/bs",
            parameters=request.dict()
        )
        raise handle_api_error(e, context)
    except Exception as e:
        context = create_error_context(
            request_id=getattr(http_request.state, 'request_id', None),
            endpoint="/price/put/bs",
            parameters=request.dict()
        )
        calculation_error = CalculationError(
            f"Black-Scholes put pricing failed: {str(e)}",
            model="Black-Scholes",
            parameters=request.dict()
        )
        raise handle_api_error(calculation_error, context)

# ===== FFT PRICING ENDPOINTS (Original) =====
@app.post("/price/call/fft")
def price_call_fft(request: FFTRequest):
    try:
        prices = pricing_engine.price_call_fft(
            request.s, request.k_min, request.delta_v, request.delta_k, 
            request.n, request.tau, request.r, request.sigma, request.alpha
        )
        return {"prices": prices, "model": "FFT"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/price/put/fft")
def price_put_fft(request: FFTRequest):
    try:
        prices = pricing_engine.price_put_fft(
            request.s, request.k_min, request.delta_v, request.delta_k,
            request.n, request.tau, request.r, request.sigma, request.alpha
        )
        return {"prices": prices, "model": "FFT"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ===== ENHANCED FFT PRICING ENDPOINTS =====
@app.post("/price/call/fft-optimized")
def price_call_fft_optimized(request: FFTOptimizedRequest):
    """Enhanced FFT pricing with automatic parameter optimization"""
    try:
        price = pricing_engine.price_call_fft_optimized(
            request.s, request.k, request.tau, request.r, request.sigma
        )
        return {
            "price": price, 
            "model": "FFT-Optimized",
            "description": "FFT pricing with automatic parameter optimization for stability"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/price/put/fft-optimized")
def price_put_fft_optimized(request: FFTOptimizedRequest):
    """Enhanced FFT put pricing with automatic parameter optimization"""
    try:
        price = pricing_engine.price_put_fft_optimized(
            request.s, request.k, request.tau, request.r, request.sigma
        )
        return {
            "price": price, 
            "model": "FFT-Optimized",
            "description": "FFT put pricing with automatic parameter optimization for stability"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/price/call/fft-enhanced")
def price_call_fft_enhanced(request: FFTRequest):
    """Enhanced FFT pricing with stability checks and manual parameters"""
    try:
        price = pricing_engine.price_call_fft_enhanced(
            request.s, request.k, request.k_min, request.delta_v, request.delta_k,
            request.n, request.tau, request.r, request.sigma, request.alpha
        )
        return {
            "price": price, 
            "model": "FFT-Enhanced",
            "description": "FFT pricing with enhanced stability checks"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/price/put/fft-enhanced")
def price_put_fft_enhanced(request: FFTRequest):
    """Enhanced FFT put pricing with stability checks and manual parameters"""
    try:
        price = pricing_engine.price_put_fft_enhanced(
            request.s, request.k, request.k_min, request.delta_v, request.delta_k,
            request.n, request.tau, request.r, request.sigma, request.alpha
        )
        return {
            "price": price, 
            "model": "FFT-Enhanced",
            "description": "FFT put pricing with enhanced stability checks"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ===== HESTON MODEL ENDPOINTS =====
@app.post("/price/call/heston")
def price_call_heston(request: HestonRequest):
    """Heston model call pricing with stochastic volatility"""
    try:
        # Validate Feller condition first
        feller_valid = pricing_engine.validate_feller_condition_py(
            request.kappa, request.theta, request.sigma_v
        )
        if not feller_valid:
            raise HTTPException(
                status_code=400, 
                detail="Feller condition violated: 2*kappa*theta <= sigma_v^2"
            )
        
        price = pricing_engine.price_heston_call(
            request.s, request.k, request.v0, request.r, 
            request.kappa, request.theta, request.sigma_v, request.rho, request.tau
        )
        return {
            "price": price, 
            "model": "Heston",
            "description": "Stochastic volatility pricing using Heston model",
            "feller_condition_satisfied": True
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/price/put/heston")
def price_put_heston(request: HestonRequest):
    """Heston model put pricing with stochastic volatility"""
    try:
        # Validate Feller condition first
        feller_valid = pricing_engine.validate_feller_condition_py(
            request.kappa, request.theta, request.sigma_v
        )
        if not feller_valid:
            raise HTTPException(
                status_code=400, 
                detail="Feller condition violated: 2*kappa*theta <= sigma_v^2"
            )
        
        price = pricing_engine.price_heston_put(
            request.s, request.k, request.v0, request.r, 
            request.kappa, request.theta, request.sigma_v, request.rho, request.tau
        )
        return {
            "price": price, 
            "model": "Heston",
            "description": "Stochastic volatility put pricing using Heston model",
            "feller_condition_satisfied": True
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ===== GREEKS CALCULATION ENDPOINTS =====
@app.post("/greeks/call")
def calculate_call_greeks(request: GreeksRequest):
    """Calculate Greeks for call options using specified model"""
    try:
        if request.model.lower() == "bs":
            greeks = pricing_engine.calculate_bs_call_greeks(
                request.s, request.k, request.tau, request.r, request.sigma
            )
            method = "Analytical Black-Scholes"
        elif request.model.lower() == "fft":
            greeks = pricing_engine.calculate_fft_call_greeks(
                request.s, request.k, request.tau, request.r, request.sigma
            )
            method = "Numerical (FFT-based)"
        elif request.model.lower() == "numerical":
            greeks = pricing_engine.calculate_numerical_call_greeks(
                request.s, request.k, request.tau, request.r, request.sigma
            )
            method = "Numerical (Black-Scholes-based)"
        else:
            raise HTTPException(
                status_code=400, 
                detail="Invalid model. Use 'bs', 'fft', or 'numerical'"
            )
        
        return {
            "greeks": {
                "delta": greeks.delta,
                "gamma": greeks.gamma,
                "theta": greeks.theta,
                "vega": greeks.vega,
                "rho": greeks.rho
            },
            "option_type": "call",
            "model": request.model,
            "method": method
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/greeks/put")
def calculate_put_greeks(request: GreeksRequest):
    """Calculate Greeks for put options using specified model"""
    try:
        if request.model.lower() == "bs":
            greeks = pricing_engine.calculate_bs_put_greeks(
                request.s, request.k, request.tau, request.r, request.sigma
            )
            method = "Analytical Black-Scholes"
        elif request.model.lower() == "fft":
            greeks = pricing_engine.calculate_fft_put_greeks(
                request.s, request.k, request.tau, request.r, request.sigma
            )
            method = "Numerical (FFT-based)"
        elif request.model.lower() == "numerical":
            greeks = pricing_engine.calculate_numerical_put_greeks(
                request.s, request.k, request.tau, request.r, request.sigma
            )
            method = "Numerical (Black-Scholes-based)"
        else:
            raise HTTPException(
                status_code=400, 
                detail="Invalid model. Use 'bs', 'fft', or 'numerical'"
            )
        
        return {
            "greeks": {
                "delta": greeks.delta,
                "gamma": greeks.gamma,
                "theta": greeks.theta,
                "vega": greeks.vega,
                "rho": greeks.rho
            },
            "option_type": "put",
            "model": request.model,
            "method": method
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/greeks/call/heston")
def calculate_heston_call_greeks(request: HestonGreeksRequest):
    """Calculate Greeks for Heston model call options"""
    try:
        # Validate Feller condition first
        feller_valid = pricing_engine.validate_feller_condition_py(
            request.kappa, request.theta, request.sigma_v
        )
        if not feller_valid:
            raise HTTPException(
                status_code=400, 
                detail="Feller condition violated: 2*kappa*theta <= sigma_v^2"
            )
        
        greeks = pricing_engine.calculate_heston_call_greeks(
            request.s, request.k, request.tau, request.r, 
            request.v0, request.theta, request.kappa, request.sigma_v, request.rho
        )
        
        return {
            "greeks": {
                "delta": greeks.delta,
                "gamma": greeks.gamma,
                "theta": greeks.theta,
                "vega": greeks.vega,
                "rho": greeks.rho
            },
            "option_type": "call",
            "model": "Heston",
            "method": "Numerical (Heston-based)",
            "feller_condition_satisfied": True
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/greeks/put/heston")
def calculate_heston_put_greeks(request: HestonGreeksRequest):
    """Calculate Greeks for Heston model put options"""
    try:
        # Validate Feller condition first
        feller_valid = pricing_engine.validate_feller_condition_py(
            request.kappa, request.theta, request.sigma_v
        )
        if not feller_valid:
            raise HTTPException(
                status_code=400, 
                detail="Feller condition violated: 2*kappa*theta <= sigma_v^2"
            )
        
        greeks = pricing_engine.calculate_heston_put_greeks(
            request.s, request.k, request.tau, request.r, 
            request.v0, request.theta, request.kappa, request.sigma_v, request.rho
        )
        
        return {
            "greeks": {
                "delta": greeks.delta,
                "gamma": greeks.gamma,
                "theta": greeks.theta,
                "vega": greeks.vega,
                "rho": greeks.rho
            },
            "option_type": "put",
            "model": "Heston",
            "method": "Numerical (Heston-based)",
            "feller_condition_satisfied": True
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ===== UTILITY ENDPOINTS =====
@app.post("/validate/feller")
def validate_feller_condition(kappa: float, theta: float, sigma_v: float):
    """Validate Heston model Feller condition"""
    try:
        is_valid = pricing_engine.validate_feller_condition_py(kappa, theta, sigma_v)
        condition_value = 2.0 * kappa * theta
        threshold = sigma_v * sigma_v
        
        return {
            "feller_condition_satisfied": is_valid,
            "condition_value": condition_value,
            "threshold": threshold,
            "explanation": "Feller condition requires 2*kappa*theta > sigma_v^2 for mean reversion"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return await get_basic_health()

@app.get("/health/detailed")
async def detailed_health_check():
    """Comprehensive health check with full diagnostics"""
    try:
        report = await get_health_report(use_cache=False)
        return report.to_dict()
    except Exception as e:
        context = create_error_context(endpoint="/health/detailed")
        raise handle_api_error(e, context)

@app.get("/health/errors")
async def error_statistics():
    """Get error statistics for monitoring"""
    try:
        return error_handler.get_error_stats()
    except Exception as e:
        context = create_error_context(endpoint="/health/errors")
        raise handle_api_error(e, context)

# ===== MODEL COMPARISON ENDPOINT =====
@app.post("/compare/models")
def compare_pricing_models(request: OptionRequest):
    """Compare prices across multiple models for the same option"""
    try:
        results = {}
        
        # Black-Scholes
        try:
            bs_call = pricing_engine.price_call(request.s, request.k, request.tau, request.r, request.sigma)
            bs_put = pricing_engine.price_put(request.s, request.k, request.tau, request.r, request.sigma)
            results["black_scholes"] = {"call": bs_call, "put": bs_put}
        except Exception as e:
            results["black_scholes"] = {"error": str(e)}
        
        # FFT Optimized
        try:
            fft_call = pricing_engine.price_call_fft_optimized(request.s, request.k, request.tau, request.r, request.sigma)
            fft_put = pricing_engine.price_put_fft_optimized(request.s, request.k, request.tau, request.r, request.sigma)
            results["fft_optimized"] = {"call": fft_call, "put": fft_put}
        except Exception as e:
            results["fft_optimized"] = {"error": str(e)}
        
        return {
            "parameters": {
                "s": request.s,
                "k": request.k,
                "tau": request.tau,
                "r": request.r,
                "sigma": request.sigma
            },
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
