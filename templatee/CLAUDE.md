# CLAUDE.md — Python/FastAPI Backend

## Overview

FastAPI application (`app/`) that exposes all financial computation endpoints.
The Rust core (`src/`) is compiled as a Python extension module (`pricing_engine`) via **maturin / PyO3**.

---

## Running the Server

```bash
# Activate venv first
source venv/Scripts/activate   # Windows Git Bash
# source venv/bin/activate     # Linux / macOS

# Build Rust bindings (must be done after any Rust code change)
maturin develop

# Start API (auto-reload on code changes)
uvicorn app.main:app --reload --port 8000

# Endpoints
# http://localhost:8000/docs        ← Swagger UI
# http://localhost:8000/redoc       ← ReDoc
# http://localhost:8000/health      ← basic health
# http://localhost:8000/health/detailed
```

---

## Module Responsibilities

### `app/main.py`
- FastAPI app creation, CORS, request-ID middleware.
- Imports `pricing_engine` (Rust) or falls back to `pricing_engine_mock`.
- Mounts three routers: pricing endpoints (inline), `market_data_router`, `transact_router`.

### `app/transact_routes.py`
- All **Transact** tab routes: `/portfolio/*`, `/risk/*`, `/optimize/*`, `/blotter/*`, `/scenarios/*`, `/factors/*`, `/heston/*`, `/vol/*`.
- Each route validates input, calls domain logic, returns JSON.

### Pricing Domain (`src/*.rs` compiled as `pricing_engine`)

| Function | Description |
|----------|-------------|
| `price_call(s, k, tau, r, sigma)` | BS call price |
| `price_put(s, k, tau, r, sigma)` | BS put price |
| `price_call_fft_optimized(s, k, tau, r, sigma)` | Carr-Madan FFT call (auto params) |
| `price_put_fft_optimized(s, k, tau, r, sigma)` | Carr-Madan FFT put (auto params) |
| `price_call_fft_enhanced(...)` | FFT call with manual params + stability |
| `price_heston_call(s, k, v0, r, kappa, theta, sigma_v, rho, tau)` | Heston call |
| `price_heston_put(...)` | Heston put |
| `validate_feller_condition_py(kappa, theta, sigma_v)` | Feller check |
| `calculate_bs_call_greeks(...)` | Analytical Greeks (Delta, Gamma, Theta, Vega, Rho) |
| `calculate_fft_call_greeks(...)` | Numerical Greeks via FFT |
| `calculate_heston_call_greeks(...)` | Numerical Greeks via Heston |

### `app/portfolio_engine.py`
Returns `PortfolioMoments` and `PerformanceMetrics` dataclasses.
- Moments: return, variance, vol, beta, systematic/non-systematic risk, skewness, kurtosis.
- Performance: Sharpe, Treynor, Sortino, M2, M2-Sortino, IR, Appraisal Ratio, CAPM alpha.

### `app/risk/var_engine.py`
```python
compute_var_all_methods(returns, weights, alpha, horizon_days, portfolio_value, include_mc, mc_simulations)
# Returns dict with historical, parametric, and Monte Carlo VaR + ES
```

### `app/optimizer/`

| Module | Function | Method |
|--------|----------|--------|
| `mvo.py` | `optimize_mvo`, `efficient_frontier`, `gmv_portfolio`, `tangency_portfolio` | cvxpy QP |
| `black_litterman.py` | `blm_optimize` | Idzorek / He-Litterman |
| `risk_parity.py` | `risk_parity_erc`, `risk_parity_rrp` | SciPy minimize |
| `hrp.py` | `hrp_weights` | Ward linkage + bisection |
| `kelly.py` | `kelly_single`, `kelly_multi_asset` | Analytical / cvxpy |

### `app/blotter/`
- `trade_store.py`: In-memory singleton `TradeStore` (reset on restart). Tracks trades, computes positions and P&L.
- `attribution.py`: Alpha / beta / factor / residual decomposition.

### `app/scenarios/`
- `scenario_engine.py`: Apply return/vol/correlation shocks; built-in crisis periods (GFC 2008, COVID 2020, Quant Melt 2007).
- `monte_carlo.py`: Multivariate normal (or t-distribution) path simulation.
- `behavioral.py`: Prospect theory perceived utility; herding-stressed VaR.

### `app/factors/`
- `factor_model.py`: OLS multi-factor regression (alphas, betas, R², residual var).
- `fama_macbeth.py`: Two-stage cross-sectional regression (λ, SE, t-stats, p-values).
- `smart_beta.py`: Quintile sort or signal-weighted long-short portfolios.
- `crowding.py`: Pairwise correlation-based crowding index.

### `app/vol/calibration.py`
- `implied_vol_bs`: Newton-Raphson IV solver.
- `heston_calibrate`: Differential evolution calibration to market option prices.

### `app/deriv_api_client.py`
- WebSocket client to Deriv API.
- L1 cache (30s) and L2 cache (5 min) with promotion.
- Exponential backoff + jitter for rate limiting.

---

## Adding a New Endpoint

1. Define a Pydantic `BaseModel` for the request body in the relevant route file.
2. Add a `@router.post("/your/endpoint")` function.
3. Call domain logic (imported from the appropriate module).
4. Return a typed dict; raise `HTTPException(status_code=400, detail=...)` on errors.
5. Add the endpoint to Swagger examples if it uses complex parameters.

```python
class MyRequest(BaseModel):
    returns: List[List[float]]
    weights: List[float]

@router.post("/portfolio/my-metric")
def post_my_metric(req: MyRequest):
    try:
        result = my_domain_function(np.array(req.returns), np.array(req.weights))
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

---

## Adding Rust Functions

1. Implement in `src/*.rs`.
2. Expose via `#[pyfunction]` and register in `src/lib.rs` `#[pymodule]`.
3. Rebuild: `maturin develop`.
4. Add corresponding Python wrapper/test.

```rust
// src/my_model.rs
#[pyfunction]
pub fn my_calculation(x: f64, y: f64) -> PyResult<f64> {
    Ok(x * y)
}

// src/lib.rs
m.add_function(wrap_pyfunction!(my_model::my_calculation, m)?)?;
```

---

## Testing

```bash
# All Python tests
pytest app/tests/ -v

# Single test file
pytest app/tests/test_pricing.py -v

# With coverage
pytest app/tests/ --cov=app --cov-report=html

# Rust tests
cargo test

# Property-based tests (Hypothesis + proptest)
pytest app/tests/test_mathematical_consistency_properties.py -v
pytest app/tests/test_deriv_api_properties.py -v
cargo test --test greeks_property_tests
```

---

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn[standard]` | ASGI server |
| `pydantic` v2 | Request/response validation |
| `maturin` | Rust-Python build system |
| `numpy` | Numerical arrays |
| `scipy` | Optimisation, stats distributions |
| `cvxpy` | Convex portfolio optimisation (MVO, Kelly) |
| `hypothesis` | Property-based testing |
| `structlog` | JSON structured logging |
| `httpx` | Async HTTP (for Deriv API) |

---

## Error Handling Pattern

Use `app/error_handling.py` for pricing endpoints:
```python
from .error_handling import handle_api_error, create_error_context, ValidationError, CalculationError

context = create_error_context(request_id=..., endpoint="/my/endpoint", parameters=req.dict())
try:
    ...
except ValidationError as e:
    raise handle_api_error(e, context)
```

For transact routes, plain `HTTPException` is sufficient.
