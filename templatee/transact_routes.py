"""
Transact Phase 1 Routes — Portfolio, Risk, Optimizer, Blotter
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import numpy as np

from .portfolio_engine import compute_portfolio_moments, compute_performance_metrics
from .risk.var_engine import compute_var_all_methods
from .optimizer.mvo import efficient_frontier, gmv_portfolio, tangency_portfolio, optimize_mvo
from .optimizer.black_litterman import blm_optimize
from .optimizer.risk_parity import risk_parity_erc, risk_parity_rrp
from .optimizer.hrp import hrp_weights
from .optimizer.kelly import kelly_single, kelly_growth_curve, kelly_multi_asset
from .blotter.trade_store import get_trade_store
from .blotter.attribution import performance_attribution
from .blotter.chart_data import get_chart_bars, list_instruments
from .blotter.db_blotter import (
    use_db_blotter,
    ensure_db_init,
    add_trade as db_add_trade,
    get_trades_from_db,
    get_positions_from_db,
)
from .scenarios.scenario_engine import apply_custom_scenario, probabilistic_scenario_optimization, CRISIS_PERIODS
from .scenarios.monte_carlo import monte_carlo_portfolio
from .scenarios.behavioral import portfolio_perceived_utility, herding_stress_var
from .factors.factor_model import estimate_factor_model_ols
from .factors.fama_macbeth import fama_macbeth
from .factors.smart_beta import smart_beta_sort, smart_beta_signal_weighted
from .factors.crowding import crowding_index
from .higher_moments import compute_coskewness
from .vol.calibration import heston_calibrate, implied_vol_bs
from .risk.covariance import compute_covariance_health, compute_mst

try:
    import pricing_engine
    HAS_PRICING = True
except ImportError:
    try:
        import pricing_engine_mock as pricing_engine  # type: ignore
        HAS_PRICING = True
    except ImportError:
        HAS_PRICING = False

router = APIRouter(prefix="", tags=["transact"])

# In-memory registration store (persists for session lifetime)
_registrations: list[dict] = []


# --- Marketplace Registration ---

class MarketplaceRegistrationRequest(BaseModel):
    menu_id: str
    name: str
    email: str
    phone: Optional[str] = None
    role: str
    organization: Optional[str] = None


@router.post("/marketplace/register")
def marketplace_register(req: MarketplaceRegistrationRequest):
    """Store a marketplace interest registration."""
    import time
    record = {
        "menu_id": req.menu_id,
        "name": req.name,
        "email": req.email,
        "phone": req.phone or "",
        "role": req.role,
        "organization": req.organization or "",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _registrations.append(record)
    return {"status": "ok", "message": f"Registration received for {req.menu_id}.", "count": len(_registrations)}


@router.get("/marketplace/registrations")
def marketplace_registrations():
    """Return all registrations (admin view)."""
    return {"registrations": _registrations, "count": len(_registrations)}


# --- Portfolio ---
class PortfolioMomentsRequest(BaseModel):
    returns: List[List[float]]  # T x N matrix
    weights: List[float]
    market_returns: Optional[List[float]] = None


class PortfolioPerformanceRequest(BaseModel):
    portfolio_returns: List[float]
    risk_free_rate: float = 0.0
    portfolio_beta: float = 1.0
    benchmark_returns: Optional[List[float]] = None
    mar: Optional[float] = None


@router.post("/portfolio/moments")
def post_portfolio_moments(req: PortfolioMomentsRequest):
    """Compute all sample moments (M1 L1)."""
    try:
        returns = np.array(req.returns)
        weights = np.array(req.weights)
        market = np.array(req.market_returns) if req.market_returns else None
        m = compute_portfolio_moments(returns, weights, market)
        return {
            "portfolio_return": m.portfolio_return,
            "portfolio_variance": m.portfolio_variance,
            "portfolio_volatility": m.portfolio_volatility,
            "portfolio_beta": m.portfolio_beta,
            "systematic_risk": m.systematic_risk,
            "non_systematic_risk": m.non_systematic_risk,
            "skewness": m.skewness,
            "kurtosis_excess": m.kurtosis_excess,
            "asset_returns": m.asset_returns.tolist(),
            "asset_volatilities": m.asset_volatilities.tolist(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/portfolio/performance")
def post_portfolio_performance(req: PortfolioPerformanceRequest):
    """Compute performance appraisal ratios (M1 Part II §4–7)."""
    try:
        pr = np.array(req.portfolio_returns)
        bench = np.array(req.benchmark_returns) if req.benchmark_returns else None
        pm = compute_performance_metrics(
            pr, req.risk_free_rate, req.portfolio_beta, bench, req.mar
        )
        return {
            "sharpe_ratio": pm.sharpe_ratio,
            "treynor_ratio": pm.treynor_ratio,
            "sortino_ratio": pm.sortino_ratio,
            "m2_modigliani": pm.m2_modigliani,
            "m2_sortino": pm.m2_sortino,
            "information_ratio": pm.information_ratio,
            "appraisal_ratio": pm.appraisal_ratio,
            "alpha": pm.alpha,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Risk ---
class VaRRequest(BaseModel):
    returns: List[List[float]]  # T x N matrix
    weights: Optional[List[float]] = None
    alpha: float = 0.05
    horizon_days: int = 1
    portfolio_value: float = 1.0
    include_monte_carlo: bool = True
    mc_simulations: int = 100_000


@router.post("/risk/var")
def post_risk_var(req: VaRRequest):
    """Compute VaR and ES for all methods (M1 L2)."""
    try:
        returns = np.array(req.returns)
        weights = np.array(req.weights) if req.weights else None
        result = compute_var_all_methods(
            returns,
            weights,
            req.alpha,
            req.horizon_days,
            req.portfolio_value,
            req.include_monte_carlo,
            req.mc_simulations,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/risk/es")
def post_risk_es(req: VaRRequest):
    """Compute Expected Shortfall (CVaR) — same as /risk/var, returns ES focus."""
    try:
        returns = np.array(req.returns)
        weights = np.array(req.weights) if req.weights else None
        result = compute_var_all_methods(
            returns,
            weights,
            req.alpha,
            req.horizon_days,
            req.portfolio_value,
            req.include_monte_carlo,
            req.mc_simulations,
        )
        return {"es": result["es"], "confidence": result["confidence"], "methods": result["methods"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Risk: Covariance Health, MST, Greeks Aggregate ---

class CovarianceHealthRequest(BaseModel):
    returns: List[List[float]]  # T × N matrix


class MSTRequest(BaseModel):
    returns: List[List[float]]
    labels: Optional[List[str]] = None


class GreeksAggregateRequest(BaseModel):
    positions: List[dict]       # [{asset, delta, gamma, vega, theta, quantity, spot_price}, ...]
    alpha: float = 0.05         # tail probability (e.g. 0.05 → 95% VaR)
    sigma_spot: float = 0.01    # daily spot vol as fraction (e.g. 0.01 = 1%)


@router.post("/risk/covariance-health")
def post_risk_covariance_health(req: CovarianceHealthRequest):
    """Shrinkage, condition number, eigenspectrum, correlation heatmaps (M7 L1–3)."""
    try:
        res = compute_covariance_health(np.array(req.returns))
        return {
            "condition_number": res.condition_number,
            "is_ill_conditioned": res.is_ill_conditioned,
            "lw_shrinkage": res.lw_shrinkage,
            "oas_shrinkage": res.oas_shrinkage,
            "eigenvalues": res.eigenvalues,
            "eigenvalue_fractions": res.eigenvalue_fractions,
            "raw_correlation": res.raw_correlation,
            "lw_correlation": res.lw_correlation,
            "oas_correlation": res.oas_correlation,
            "distance_matrix": res.distance_matrix,
            "n_assets": res.n_assets,
            "n_obs": res.n_obs,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/risk/mst")
def post_risk_mst(req: MSTRequest):
    """Minimum Spanning Tree of correlation-distance graph (M7 L3)."""
    try:
        res = compute_mst(np.array(req.returns), req.labels)
        return {
            "nodes": res.nodes,
            "mst_edges": res.mst_edges,
            "all_edges": res.all_edges,
            "total_mst_distance": res.total_mst_distance,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/risk/greeks-aggregate")
def post_risk_greeks_aggregate(req: GreeksAggregateRequest):
    """
    Portfolio-level Greeks aggregation + Delta-VaR and Gamma-adjusted VaR.
    Delta-VaR: ΔW ≈ Δ_net · ΔS, ΔS ~ N(0, σ_spot · S)
    Gamma-VaR: ΔW ≈ Δ_net · ΔS + ½ Γ_net · (ΔS)²  (M1 L2 §8)
    """
    try:
        from scipy import stats as scipy_stats

        q_alpha = float(scipy_stats.norm.ppf(req.alpha))   # negative quantile

        net_delta = 0.0
        net_gamma = 0.0
        net_vega  = 0.0
        net_theta = 0.0
        positions_out = []

        for pos in req.positions:
            qty   = float(pos.get("quantity", 1))
            delta = float(pos.get("delta", 0))
            gamma = float(pos.get("gamma", 0))
            vega  = float(pos.get("vega",  0))
            theta = float(pos.get("theta", 0))
            spot  = float(pos.get("spot_price", 1.0))

            net_delta += delta * qty
            net_gamma += gamma * qty
            net_vega  += vega  * qty
            net_theta += theta * qty

            # Per-position delta-VaR (1-day): |δ · qty · σ_S · S · z_α|
            dS_std   = req.sigma_spot * spot
            pos_dvar = float(abs(delta * qty * dS_std * (-q_alpha)))

            positions_out.append({
                "asset": pos.get("asset", "?"),
                "quantity": qty,
                "delta": delta,
                "gamma": gamma,
                "vega":  vega,
                "theta": theta,
                "spot_price": spot,
                "delta_var": pos_dvar,
            })

        # Portfolio delta-VaR (fractional spot move, no position size)
        dS_frac = req.sigma_spot
        delta_var_port = float(abs(net_delta * dS_frac * (-q_alpha)))

        # Gamma-adjusted VaR via Monte Carlo (50 k paths)
        n_sim = 50_000
        delta_S_sim = np.random.normal(0.0, dS_frac, n_sim)
        pnl_sim     = net_delta * delta_S_sim + 0.5 * net_gamma * delta_S_sim ** 2
        losses_sim  = -pnl_sim
        gamma_var   = float(np.percentile(losses_sim, req.alpha * 100))
        gamma_es    = float(np.mean(losses_sim[losses_sim >= gamma_var]))

        return {
            "net_delta": float(net_delta),
            "net_gamma": float(net_gamma),
            "net_vega":  float(net_vega),
            "net_theta": float(net_theta),
            "delta_var":         float(delta_var_port),
            "gamma_adjusted_var": float(gamma_var),
            "gamma_adjusted_es":  float(gamma_es),
            "confidence":  float(1 - req.alpha),
            "sigma_spot":  float(req.sigma_spot),
            "positions":   positions_out,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Optimizer ---
class MVORequest(BaseModel):
    covariance: List[List[float]]
    expected_returns: List[float]
    target_return: Optional[float] = None
    risk_free_rate: float = 0.0
    long_only: bool = True


class MVOFrontierRequest(BaseModel):
    covariance: List[List[float]]
    expected_returns: List[float]
    risk_free_rate: float = 0.0
    n_points: int = 50
    long_only: bool = True


@router.post("/optimize/mvo")
def post_optimize_mvo(req: MVORequest):
    """Mean-variance optimization (M1 L4)."""
    try:
        cov = np.array(req.covariance)
        mu = np.array(req.expected_returns)
        res = optimize_mvo(
            cov, mu, req.target_return, req.risk_free_rate, req.long_only
        )
        return {
            "weights": res.weights.tolist(),
            "expected_return": res.expected_return,
            "volatility": res.volatility,
            "sharpe_ratio": res.sharpe_ratio,
            "is_gmv": res.is_gmv,
            "is_tangency": res.is_tangency,
        }
    except ImportError as e:
        raise HTTPException(status_code=503, detail="cvxpy not installed. pip install cvxpy")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/optimize/mvo/frontier")
def post_optimize_mvo_frontier(req: MVOFrontierRequest):
    """Efficient frontier (M1 L4)."""
    try:
        cov = np.array(req.covariance)
        mu = np.array(req.expected_returns)
        points = efficient_frontier(
            cov, mu, req.risk_free_rate, req.n_points, req.long_only
        )
        return {
            "frontier": [
                {
                    "weights": p.weights.tolist(),
                    "expected_return": p.expected_return,
                    "volatility": p.volatility,
                    "sharpe_ratio": p.sharpe_ratio,
                }
                for p in points
            ],
            "gmv": _gmv_dict(cov, mu, req.long_only),
            "tangency": _tangency_dict(cov, mu, req.risk_free_rate, req.long_only),
        }
    except ImportError as e:
        raise HTTPException(status_code=503, detail="cvxpy not installed. pip install cvxpy")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _gmv_dict(cov, mu, long_only):
    r = gmv_portfolio(cov, mu, long_only)
    return {"weights": r.weights.tolist(), "expected_return": r.expected_return, "volatility": r.volatility}


def _tangency_dict(cov, mu, rf, long_only):
    r = tangency_portfolio(cov, mu, rf, long_only)
    return {"weights": r.weights.tolist(), "expected_return": r.expected_return, "volatility": r.volatility}


# --- Phase 2: BLM, Risk Parity, HRP, Kelly ---
class BLMRequest(BaseModel):
    covariance: List[List[float]]
    market_weights: List[float]
    P: List[List[float]]  # K×N pick matrix
    Q: List[float]       # K×1 view returns
    tau: float = 0.05
    risk_aversion: float = 2.5
    risk_free_rate: float = 0.0
    long_only: bool = True


class RiskParityRequest(BaseModel):
    covariance: List[List[float]]
    expected_returns: Optional[List[float]] = None
    rho: float = 0.0  # 0=ERC, 1=MVO tilt
    long_only: bool = True


class HRPRequest(BaseModel):
    covariance: List[List[float]]


class KellySingleRequest(BaseModel):
    p: float  # win probability
    q: float  # lose probability (1-p)
    a: float = 1.0  # loss per unit
    b: float = 1.0  # win per unit


class KellyMultiRequest(BaseModel):
    returns: List[List[float]]  # T×N
    fractional: float = 1.0
    long_only: bool = True


@router.post("/optimize/blm")
def post_optimize_blm(req: BLMRequest):
    """Black-Litterman model (M3 L1)."""
    try:
        cov = np.array(req.covariance)
        w_m = np.array(req.market_weights)
        P = np.array(req.P)
        Q = np.array(req.Q)
        res = blm_optimize(
            cov, w_m, P, Q,
            tau=req.tau, risk_aversion=req.risk_aversion,
            risk_free=req.risk_free_rate, long_only=req.long_only,
        )
        return {
            "implied_returns": res.implied_returns.tolist(),
            "blm_returns": res.blm_returns.tolist(),
            "weights": res.optimal_weights.tolist(),
            "expected_return": res.expected_return,
            "volatility": res.volatility,
            "sharpe_ratio": res.sharpe_ratio,
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="cvxpy required")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/optimize/risk-parity")
def post_optimize_risk_parity(req: RiskParityRequest):
    """Equal Risk Contribution + Relaxed RRP (M5 L3)."""
    try:
        cov = np.array(req.covariance)
        if req.rho > 0 and req.expected_returns:
            res = risk_parity_rrp(
                cov, np.array(req.expected_returns),
                rho=req.rho, long_only=req.long_only,
            )
        else:
            res = risk_parity_erc(cov)
        return {
            "weights": res.weights.tolist(),
            "risk_contributions": res.risk_contributions.tolist(),
            "volatility": res.volatility,
            "method": res.method,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/optimize/hrp")
def post_optimize_hrp(req: HRPRequest):
    """Hierarchical Risk Parity (M7 L4)."""
    try:
        cov = np.array(req.covariance)
        w, sort_ix, link = hrp_weights(cov)
        return {
            "weights": w.tolist(),
            "sort_order": sort_ix.tolist(),
            "linkage": link,
            "volatility": float(np.sqrt(w @ cov @ w)),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/optimize/kelly/single")
def post_optimize_kelly_single(req: KellySingleRequest):
    """Single-asset Kelly (M5 L1)."""
    try:
        f_star = kelly_single(req.p, req.q, req.a, req.b)
        curve = kelly_growth_curve(req.p, req.q)
        return {"optimal_fraction": f_star, "growth_curve": curve}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/optimize/kelly")
def post_optimize_kelly(req: KellyMultiRequest):
    """Multi-asset Kelly (M5 L1)."""
    try:
        returns = np.array(req.returns)
        res = kelly_multi_asset(
            returns,
            fractional=req.fractional,
            long_only=req.long_only,
        )
        return {
            "weights": res.weights.tolist(),
            "expected_growth": res.expected_growth,
            "optimal_fraction": res.optimal_fraction,
            "fractional_kelly": res.fractional_kelly,
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="cvxpy required")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Phase 3: Factors, Coskewness, Heston, Smart Beta, Crowding ---
class FactorEstimateRequest(BaseModel):
    returns: List[List[float]]
    factors: List[List[float]]  # T x K, add constant automatically


class FamaMacBethRequest(BaseModel):
    returns: List[List[float]]
    factors: List[List[float]]


class CoskewnessRequest(BaseModel):
    returns: List[List[float]]
    weights: List[float]


class HestonCalibrateRequest(BaseModel):
    s: float
    r: float
    strikes: List[float]
    expiries: List[float]
    market_prices: List[float]


class SmartBetaRequest(BaseModel):
    factor_scores: List[float]
    returns: List[List[float]]
    method: str = "quintile"


class CrowdingRequest(BaseModel):
    factor_loadings: List[List[float]]


@router.post("/factors/estimate")
def post_factors_estimate(req: FactorEstimateRequest):
    """OLS factor model (M2 L4)."""
    try:
        R = np.array(req.returns)
        F = np.array(req.factors)
        res = estimate_factor_model_ols(R, F)
        return {
            "alphas": res.alphas.tolist(),
            "betas": res.betas.tolist(),
            "r_squared": res.r_squared.tolist(),
            "residual_var": res.residual_var.tolist(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/factors/fama-macbeth")
def post_factors_fama_macbeth(req: FamaMacBethRequest):
    """Fama-MacBeth two-stage regression (M6 L1)."""
    try:
        res = fama_macbeth(np.array(req.returns), np.array(req.factors))
        return {
            "lambdas": res.lambdas.tolist(),
            "std_errors": res.std_errors.tolist(),
            "t_stats": res.t_stats.tolist(),
            "p_values": res.p_values.tolist(),
            "betas": res.betas.tolist(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/portfolio/coskewness")
def post_portfolio_coskewness(req: CoskewnessRequest):
    """Coskewness M3 and portfolio skewness (M2 L2)."""
    try:
        res = compute_coskewness(np.array(req.returns), np.array(req.weights))
        return {
            "portfolio_skewness": float(res.portfolio_skewness),
            "excess_kurtosis_warning": bool(res.excess_kurtosis_warning),
            "coskewness_matrix": res.coskewness_matrix.tolist(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class PortfolioAttributionRequest(BaseModel):
    portfolio_returns: List[float]
    market_returns: List[float]
    risk_free_rate: float = 0.0
    factor_betas: Optional[List[float]] = None
    factor_returns: Optional[List[List[float]]] = None
    factor_names: Optional[List[str]] = None


@router.post("/portfolio/attribution")
def post_portfolio_attribution(req: PortfolioAttributionRequest):
    """Factor-based return attribution: r_p = α + β·r_m + Σ λ_k·β_k + ε (M1 §4, M2 §5)."""
    try:
        factor_b = np.array(req.factor_betas) if req.factor_betas else None
        factor_r = np.array(req.factor_returns).T if req.factor_returns else None
        res = performance_attribution(
            np.array(req.portfolio_returns),
            np.array(req.market_returns),
            req.risk_free_rate,
            factor_b,
            factor_r,
        )
        factor_names = req.factor_names or [f"Factor {i+1}" for i in range(len(res.factor_returns))]
        return {
            "alpha": res.alpha,
            "systematic_return": res.systematic_return,
            "factor_contributions": [
                {"name": factor_names[i] if i < len(factor_names) else f"Factor {i+1}", "contribution": v}
                for i, v in enumerate(res.factor_returns)
            ],
            "residual": res.residual,
            "total_return": res.total_return,
            "decomposition": res.decomposition,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/heston/calibrate")
def post_heston_calibrate(req: HestonCalibrateRequest):
    """Calibrate Heston to market option prices."""
    try:
        res = heston_calibrate(
            req.s, req.r,
            np.array(req.strikes), np.array(req.expiries), np.array(req.market_prices),
        )
        return {
            "v0": float(res.v0),
            "kappa": float(res.kappa),
            "theta": float(res.theta),
            "xi": float(res.xi),
            "rho": float(res.rho),
            "rmse": float(res.rmse),
            "feller_condition_ok": bool(res.feller_ok),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ImpliedSurfaceRequest(BaseModel):
    s: float
    r: float
    strikes: List[float]
    expiries: List[float]
    market_prices: List[float]


@router.post("/vol/implied-surface")
def post_vol_implied_surface(req: ImpliedSurfaceRequest):
    """Compute IV for each (K,tau) from market prices (calls)."""
    try:
        ivs = []
        for i in range(len(req.strikes)):
            iv = implied_vol_bs(req.market_prices[i], req.s, req.strikes[i], req.r, req.expiries[i], "call")
            ivs.append({"strike": float(req.strikes[i]), "expiry": float(req.expiries[i]), "iv": float(iv)})
        return {"surface": ivs}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class HestonSurfaceRequest(BaseModel):
    v0: float = 0.04
    kappa: float = 2.0
    theta: float = 0.04
    xi: float = 0.3
    rho: float = -0.5
    s: float = 100.0
    r: float = 0.02
    n_moneyness: int = 10
    n_expiry: int = 8


@router.post("/vol/heston-surface")
def post_vol_heston_surface(req: HestonSurfaceRequest):
    """Generate Heston-implied vol surface grid (moneyness × expiry)."""
    try:
        moneyness = np.linspace(0.7, 1.3, req.n_moneyness)  # K/S
        expiries = np.linspace(0.1, 2.0, req.n_expiry)
        iv_grid = []
        for tau in expiries:
            row = []
            for m in moneyness:
                k = m * req.s
                price = 0.0
                if HAS_PRICING:
                    try:
                        price = float(pricing_engine.price_heston_call(
                            req.s, k, req.v0, req.r,
                            req.kappa, req.theta, req.xi, req.rho, tau
                        ))
                    except Exception:
                        price = 0.0
                iv = implied_vol_bs(price, req.s, k, req.r, tau, "call") if price > 1e-6 else float(np.sqrt(req.v0))
                row.append(round(iv, 5))
            iv_grid.append(row)
        # smile at mid expiry
        mid = req.n_expiry // 2
        smile = [{"moneyness": float(m), "iv": iv_grid[mid][i]} for i, m in enumerate(moneyness)]
        # term structure at ATM
        atm = req.n_moneyness // 2
        term_structure = [{"expiry": float(tau), "iv": iv_grid[j][atm]} for j, tau in enumerate(expiries)]
        return {
            "moneyness": moneyness.tolist(),
            "expiries": expiries.tolist(),
            "iv_grid": iv_grid,
            "smile": smile,
            "term_structure": term_structure,
            "feller_ok": bool(2 * req.kappa * req.theta > req.xi ** 2),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class HistVolRequest(BaseModel):
    returns: List[float]          # daily log-returns for one asset
    window: int = 21              # rolling window (trading days)
    annualise: bool = True


@router.post("/vol/historical")
def post_vol_historical(req: HistVolRequest):
    """Rolling realised vol σ_r = √(252/w · Σr²) and optional implied-vol proxy."""
    try:
        r = np.array(req.returns)
        T = len(r)
        if T < req.window:
            raise ValueError(f"Need ≥{req.window} observations, got {T}")
        factor = 252 if req.annualise else 1
        realized = []
        for i in range(req.window, T + 1):
            window_r = r[i - req.window:i]
            rv = float(np.sqrt(factor / req.window * np.sum(window_r ** 2)))
            realized.append(rv)
        full_std = float(np.std(r) * np.sqrt(factor))
        return {
            "realized_vol": realized,
            "full_period_vol": full_std,
            "window": req.window,
            "n_obs": T,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class VolDecompRequest(BaseModel):
    returns: List[List[float]]    # T × N
    weights: List[float]          # N
    market_returns: Optional[List[float]] = None  # T — if None use equal-weighted pf as proxy


@router.post("/vol/factor-decompose")
def post_vol_factor_decompose(req: VolDecompRequest):
    """Decompose σ²_p into systematic (β²σ²_m) and idiosyncratic (w^TΣ_εw)."""
    try:
        R = np.array(req.returns)      # T×N
        w = np.array(req.weights)
        w = w / w.sum()
        T, N = R.shape
        if req.market_returns:
            mkt = np.array(req.market_returns)
        else:
            mkt = R @ w  # portfolio itself as proxy
        mkt_var = float(np.var(mkt, ddof=1))
        # Per-asset betas and residual variances
        betas, resid_vars, r2s = [], [], []
        for i in range(N):
            cov_im = float(np.cov(R[:, i], mkt, ddof=1)[0, 1])
            beta_i = cov_im / mkt_var if mkt_var > 1e-12 else 0.0
            resid = R[:, i] - beta_i * mkt
            resid_vars.append(float(np.var(resid, ddof=1)))
            betas.append(beta_i)
            r2 = 1 - float(np.var(resid, ddof=1)) / max(float(np.var(R[:, i], ddof=1)), 1e-12)
            r2s.append(max(r2, 0.0))
        beta_p = float(w @ np.array(betas))
        systematic_var = beta_p ** 2 * mkt_var * 252
        idio_var = float(w @ np.diag(np.array(resid_vars)) @ w) * 252
        total_var = systematic_var + idio_var
        total_vol = float(np.sqrt(total_var)) if total_var > 0 else 0.0
        return {
            "systematic_vol": float(np.sqrt(systematic_var)) if systematic_var > 0 else 0.0,
            "idiosyncratic_vol": float(np.sqrt(idio_var)) if idio_var > 0 else 0.0,
            "total_vol": total_vol,
            "systematic_pct": systematic_var / total_var if total_var > 0 else 0.0,
            "idiosyncratic_pct": idio_var / total_var if total_var > 0 else 0.0,
            "asset_betas": betas,
            "asset_r_squared": r2s,
            "portfolio_beta": beta_p,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/factors/smart-beta")
def post_factors_smart_beta(req: SmartBetaRequest):
    """Smart beta portfolio (M6 L2)."""
    try:
        scores = np.array(req.factor_scores)
        returns = np.array(req.returns)
        if req.method == "signal_weighted":
            res = smart_beta_signal_weighted(scores, returns)
        else:
            res = smart_beta_sort(scores, returns)
        return {
            "weights": res.weights.tolist(),
            "method": res.method,
            "expected_return": res.expected_return,
            "volatility": res.volatility,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/factors/crowding")
def post_factors_crowding(req: CrowdingRequest):
    """Herding/crowding risk index (M6 L2)."""
    try:
        res = crowding_index(np.array(req.factor_loadings))
        return {
            "crowding_index": res.crowding_index,
            "level": res.level,
            "avg_correlation": res.avg_correlation,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class PCARequest(BaseModel):
    returns: List[List[float]]  # T × N
    n_components: int = 5


@router.post("/factors/pca")
def post_factors_pca(req: PCARequest):
    """PCA latent factor extraction (M6 L2 / ML Factor Discovery)."""
    try:
        R = np.array(req.returns)  # T × N
        if R.ndim != 2 or R.shape[0] < 3:
            raise ValueError("Need at least 3 time periods and 2 assets for PCA")
        T, N = R.shape
        # Standardise each column
        mu = R.mean(axis=0)
        sigma = R.std(axis=0, ddof=1)
        sigma = np.where(sigma < 1e-12, 1.0, sigma)
        R_std = (R - mu) / sigma

        # Covariance of standardised returns = correlation matrix
        C = np.cov(R_std.T, ddof=1)
        if C.ndim == 0:
            C = C.reshape(1, 1)
        eigenvalues, eigenvectors = np.linalg.eigh(C)
        # Sort descending
        idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        total_var = float(eigenvalues.sum())
        if total_var < 1e-12:
            total_var = 1.0
        explained_ratio = (eigenvalues / total_var).tolist()
        cumulative = np.cumsum(eigenvalues / total_var).tolist()

        K = min(max(req.n_components, 1), N)
        loadings = eigenvectors[:, :K].tolist()  # N × K

        # How many components to explain >= 80% variance
        comp_80 = int(np.searchsorted(cumulative, 0.80) + 1)

        return {
            "eigenvalues": eigenvalues[:K].tolist(),
            "explained_variance_ratio": explained_ratio[:K],
            "cumulative_variance": cumulative[:K],
            "loadings": loadings,  # N × K
            "n_components": K,
            "components_for_80pct": min(comp_80, N),
            "total_n_assets": N,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Blotter (Menu 8: Chart Area data from Nautilus; fallback yfinance) ---
@router.get("/blotter/chart/bars")
def get_blotter_chart_bars(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = "1d",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    """OHLCV bars for Chart Area. Source: Nautilus when configured, else yfinance (same as /assets/history)."""
    try:
        sym = (symbol or "").strip()
        bars = get_chart_bars(symbol=sym, timeframe=timeframe or "1d", from_date=from_date, to_date=to_date)
        return {"symbol": sym, "timeframe": timeframe or "1d", "bars": bars}
    except Exception as e:
        return {"symbol": symbol or "", "timeframe": timeframe or "1d", "bars": [], "error": str(e)}


@router.get("/blotter/instruments")
def get_blotter_instruments(asset_type: Optional[str] = "equity"):
    """Instruments by asset type for Chart Area selector. Source: Nautilus when configured."""
    try:
        instruments = list_instruments(asset_type or "equity")
        return {"asset_type": asset_type or "equity", "instruments": instruments}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Blotter: Trade Entry, Positions, History ---
class TradeEntryRequest(BaseModel):
    asset: str
    direction: str  # "long" | "short"
    quantity: float
    entry_price: float
    entry_date: Optional[str] = None
    model_used: Optional[str] = None
    theoretical_price: Optional[float] = None
    strategy_tag: Optional[str] = None
    asset_class: Optional[str] = None


class PositionsRequest(BaseModel):
    current_prices: dict  # {"AAPL": 150.0, ...}


@router.post("/blotter/trade")
def post_blotter_trade(req: TradeEntryRequest):
    """Add a new trade. Persists to Postgres + double-entry ledger when DATABASE_URL is set."""
    try:
        if req.direction.lower() not in ("long", "short"):
            raise HTTPException(status_code=400, detail="direction must be 'long' or 'short'")
        if use_db_blotter():
            result = db_add_trade(
                asset=req.asset,
                direction=req.direction,
                quantity=req.quantity,
                entry_price=req.entry_price,
                entry_date=req.entry_date,
                model_used=req.model_used,
                theoretical_price=req.theoretical_price,
                strategy_tag=req.strategy_tag,
                asset_class=req.asset_class,
            )
            if result:
                return result
        store = get_trade_store()
        trade = store.add_trade(
            asset=req.asset,
            direction=req.direction,
            quantity=req.quantity,
            entry_price=req.entry_price,
            entry_date=req.entry_date,
            model_used=req.model_used,
            theoretical_price=req.theoretical_price,
            strategy_tag=req.strategy_tag,
            asset_class=req.asset_class,
        )
        return {
            "id": trade.id,
            "asset": trade.asset,
            "direction": trade.direction,
            "quantity": trade.quantity,
            "entry_price": trade.entry_price,
            "entry_date": trade.entry_date,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/blotter/positions")
def get_blotter_positions(current_prices: Optional[str] = None):
    """Get open positions with P&L. Uses DB when DATABASE_URL is set."""
    try:
        import json
        prices = json.loads(current_prices) if current_prices else {}
        prices_dict = prices if isinstance(prices, dict) else {}
        if use_db_blotter():
            positions = get_positions_from_db(prices_dict)
            return {"positions": positions}
        store = get_trade_store()
        positions = store.get_positions(prices_dict)
        return {
            "positions": [
                {
                    "asset": p.asset,
                    "quantity": p.quantity,
                    "direction": p.direction,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                }
                for p in positions
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/blotter/positions")
def post_blotter_positions(req: PositionsRequest):
    """Get positions with P&L given current prices. Uses DB when DATABASE_URL is set."""
    try:
        if use_db_blotter():
            positions = get_positions_from_db(req.current_prices)
            return {"positions": positions}
        store = get_trade_store()
        positions = store.get_positions(req.current_prices)
        return {
            "positions": [
                {
                    "asset": p.asset,
                    "quantity": p.quantity,
                    "direction": p.direction,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                }
                for p in positions
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/blotter/journal")
def get_blotter_journal(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: Optional[int] = 500,
):
    """List journal entries with lines (double-entry ledger). Requires DATABASE_URL."""
    try:
        entries = get_journal(from_date=from_date, to_date=to_date, limit=limit or 500)
        return {"entries": entries}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/blotter/accounts")
def get_blotter_accounts(as_of_date: Optional[str] = None):
    """List accounts with balances (trial balance). Requires DATABASE_URL."""
    try:
        balances = get_accounts_balances(as_of_date=as_of_date)
        return {"accounts": balances}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/blotter/history")
def get_blotter_history(
    asset: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    """Full transaction history. Uses DB when DATABASE_URL is set."""
    try:
        if use_db_blotter():
            trades = get_trades_from_db(asset=asset, from_date=from_date, to_date=to_date)
            return {"trades": trades}
        store = get_trade_store()
        if asset or from_date or to_date:
            trade_list = store.get_trades(asset=asset, from_date=from_date, to_date=to_date)
            return {"trades": [{"id": t.id, "asset": t.asset, "direction": t.direction, "quantity": t.quantity, "entry_price": t.entry_price, "entry_date": t.entry_date, "model_used": t.model_used, "theoretical_price_at_entry": t.theoretical_price_at_entry, "strategy_tag": t.strategy_tag} for t in trade_list]}
        return {"trades": store.get_history()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Phase 4: Scenarios & Behavioral ---
class ScenarioDefineRequest(BaseModel):
    name: str
    return_shocks: Optional[List[float]] = None
    vol_shocks: Optional[List[float]] = None
    corr_shift: float = 0.0


class ScenarioRunRequest(BaseModel):
    returns: List[List[float]]
    weights: List[float]
    return_shocks: Optional[List[float]] = None
    vol_shocks: Optional[List[float]] = None
    corr_shift: float = 0.0
    historical: Optional[str] = None  # e.g. "GFC_2008", "COVID_2020", "Quant_Melt_2007"


class ProbabilisticScenarioRequest(BaseModel):
    scenario_returns: List[List[float]]  # K x N
    scenario_probs: List[float]
    target_return: float
    long_only: bool = True


class MonteCarloRequest(BaseModel):
    returns: List[List[float]]
    weights: List[float]
    portfolio_value: float = 1.0
    horizon_days: int = 1
    n_paths: int = 100_000
    use_t_dist: bool = False
    df: float = 5.0


class BehavioralRequest(BaseModel):
    returns: List[List[float]]
    weights: List[float]
    mode: str = "prospect"  # "prospect" | "herding"
    correlation_shift: float = 0.3
    alpha: float = 0.05
    portfolio_value: float = 1.0


class AttributionRequest(BaseModel):
    portfolio_returns: List[float]
    market_returns: List[float]
    risk_free_rate: float = 0.0
    factor_betas: Optional[List[float]] = None
    factor_returns: Optional[List[List[float]]] = None  # T x K matrix


class PnLRequest(BaseModel):
    price_history: Optional[List[dict]] = None  # [{"date": "YYYY-MM-DD", "prices": {...}}, ...]
    current_prices: Optional[dict] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None


_scenarios_store: dict = {}


@router.post("/scenarios/define")
def post_scenarios_define(req: ScenarioDefineRequest):
    """Save custom scenario by name (M3 L4)."""
    _scenarios_store[req.name] = {
        "return_shocks": req.return_shocks,
        "vol_shocks": req.vol_shocks,
        "corr_shift": req.corr_shift,
    }
    return {"name": req.name, "saved": True}


@router.post("/scenarios/run")
def post_scenarios_run(req: ScenarioRunRequest):
    """Apply scenario to portfolio, return stressed metrics (M3 L4)."""
    try:
        returns = np.array(req.returns)
        weights = np.array(req.weights)
        return_shocks = req.return_shocks
        vol_shocks = req.vol_shocks
        corr_shift = req.corr_shift

        if req.historical:
            crisis = CRISIS_PERIODS.get(req.historical)
            if crisis:
                n = returns.shape[1]
                return_shocks = [crisis["return_shift"]] * n  # uniform market crash
                corr_shift = crisis["corr_shift"]

        res = apply_custom_scenario(returns, weights, return_shocks, vol_shocks, corr_shift)
        return {
            "stressed_portfolio_return": res.portfolio_return,
            "stressed_portfolio_variance": res.portfolio_var,
            "stressed_portfolio_volatility": np.sqrt(res.portfolio_var),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scenarios/probabilistic")
def post_scenarios_probabilistic(req: ProbabilisticScenarioRequest):
    """Probabilistic scenario optimization (M3 L4)."""
    try:
        R = [np.array(r) for r in req.scenario_returns]
        w = probabilistic_scenario_optimization(
            R, req.scenario_probs, req.target_return, req.long_only
        )
        return {"weights": w.tolist()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scenarios/monte-carlo")
def post_scenarios_monte_carlo(req: MonteCarloRequest):
    """Monte Carlo portfolio simulation (M1 L2)."""
    try:
        res = monte_carlo_portfolio(
            np.array(req.returns),
            np.array(req.weights),
            req.portfolio_value,
            req.horizon_days,
            req.n_paths,
            req.use_t_dist,
            req.df,
        )
        return {
            "terminal_wealth_mean": res.terminal_wealth_mean,
            "terminal_wealth_std": res.terminal_wealth_std,
            "var_95": res.var_95,
            "var_99": res.var_99,
            "cvar_95": res.cvar_95,
            "cvar_99": res.cvar_99,
            "percentiles": res.percentiles,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scenarios/behavioral")
def post_scenarios_behavioral(req: BehavioralRequest):
    """Prospect Theory / herding simulation (M4)."""
    try:
        returns = np.array(req.returns)
        weights = np.array(req.weights)
        if req.mode == "herding":
            res = herding_stress_var(
                returns, weights, req.correlation_shift, req.alpha, req.portfolio_value
            )
            return {
                "base_var_95": res.base_var_95,
                "base_var_99": res.base_var_99,
                "stressed_var_95": res.stressed_var_95,
                "stressed_var_99": res.stressed_var_99,
                "correlation_shift": res.correlation_shift,
            }
        else:
            util = portfolio_perceived_utility(returns, weights)
            return {"perceived_utility": util}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/blotter/context")
def get_blotter_context():
    """
    Aggregated blotter context for the AI agent.
    Returns positions, trade summary, P&L stats, available instruments,
    and attribution metadata in a single lightweight payload.
    """
    try:
        store = get_trade_store()
        positions_raw = store.get_positions({})
        trades_raw = store.get_history() if hasattr(store, 'get_history') else []

        positions = []
        total_pnl = 0.0
        total_value = 0.0
        for p in positions_raw:
            pnl = float(getattr(p, 'unrealized_pnl', 0) or 0)
            mv = float(getattr(p, 'market_value', 0) or (
                float(getattr(p, 'quantity', 0)) * float(getattr(p, 'current_price', 0))
            ))
            total_pnl += pnl
            total_value += mv
            positions.append({
                "symbol": getattr(p, 'asset', ''),
                "quantity": getattr(p, 'quantity', 0),
                "direction": getattr(p, 'direction', 'long'),
                "entry_price": getattr(p, 'entry_price', 0),
                "current_price": getattr(p, 'current_price', 0),
                "unrealized_pnl": pnl,
                "unrealized_pnl_pct": float(getattr(p, 'unrealized_pnl_pct', 0) or 0),
                "market_value": mv,
            })

        # P&L breakdown by direction
        long_positions = [p for p in positions if p['direction'] == 'long']
        short_positions = [p for p in positions if p['direction'] == 'short']
        winners = [p for p in positions if p['unrealized_pnl'] > 0]
        losers  = [p for p in positions if p['unrealized_pnl'] < 0]

        # Available instruments from chart data
        try:
            instruments = list_instruments()
        except Exception:
            instruments = []

        return {
            "positions": positions,
            "position_count": len(positions),
            "long_count": len(long_positions),
            "short_count": len(short_positions),
            "total_unrealized_pnl": round(total_pnl, 2),
            "total_market_value": round(total_value, 2),
            "winner_count": len(winners),
            "loser_count": len(losers),
            "win_rate_pct": round(len(winners) / len(positions) * 100, 1) if positions else 0.0,
            "trade_count": len(trades_raw) if isinstance(trades_raw, list) else 0,
            "available_instruments": instruments[:20],
            "attribution_available": len(positions) >= 2,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/blotter/attribution")
def post_blotter_attribution(req: AttributionRequest):
    """Performance attribution: α, β·r_m, factor contributions, residual (M1 §4)."""
    try:
        factor_b = np.array(req.factor_betas) if req.factor_betas else None
        factor_r = np.array(req.factor_returns) if req.factor_returns else None
        res = performance_attribution(
            np.array(req.portfolio_returns),
            np.array(req.market_returns),
            req.risk_free_rate,
            factor_b,
            factor_r,
        )
        return {
            "alpha": res.alpha,
            "systematic_return": res.systematic_return,
            "factor_returns": res.factor_returns,
            "residual": res.residual,
            "total_return": res.total_return,
            "decomposition": res.decomposition,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/blotter/pnl")
def post_blotter_pnl(req: PnLRequest):
    """Cumulative P&L time series or current snapshot (Menu 8)."""
    try:
        store = get_trade_store()
        if req.price_history:
            series = store.get_pnl_timeseries(
                req.price_history, req.from_date, req.to_date
            )
            return {"timeseries": series}
        if req.current_prices:
            cum = store.get_cumulative_pnl(req.current_prices)
            positions = store.get_positions(req.current_prices)
            return {
                "cumulative_pnl": cum,
                "positions": [
                    {
                        "asset": p.asset,
                        "unrealized_pnl": p.unrealized_pnl,
                    }
                    for p in positions
                ],
            }
        raise HTTPException(status_code=400, detail="Provide price_history or current_prices")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
