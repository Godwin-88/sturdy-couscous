"""
VaR Engine — M1 L2: Parametric, Non-Parametric, Monte Carlo VaR + ES
Implements TRANSACT_APP_SPEC §3.3.1
"""

import numpy as np
from scipy import stats
from typing import Optional, Literal
from dataclasses import dataclass


@dataclass
class VaRResult:
    """VaR and ES for a given method."""
    var: float
    es: float
    method: str
    confidence: float
    horizon_days: int
    scaled: bool


def _scale_var(var_1d: float, horizon_days: int) -> float:
    """Square root of time: VaR(T) = VaR(1) × √T."""
    return var_1d * np.sqrt(horizon_days)


def var_historical(
    returns: np.ndarray,
    weights: Optional[np.ndarray] = None,
    alpha: float = 0.05,
    horizon_days: int = 1,
    portfolio_value: float = 1.0,
) -> VaRResult:
    """
    Non-parametric VaR: VaR̂_np(1-α) = M · q̂(α)
    ES_np = M · [Σ l_i · I(l_i > q̂(α))] / Σ I(l_i > q̂(α))
    """
    returns = np.asarray(returns)
    if weights is not None:
        portfolio_returns = returns @ np.asarray(weights).flatten()
    else:
        portfolio_returns = returns.flatten()

    losses = -portfolio_returns * portfolio_value
    q_alpha = np.percentile(losses, alpha * 100)
    var_1d = float(q_alpha)

    # ES: average of losses exceeding VaR
    tail = losses[losses >= q_alpha]
    es_1d = float(np.mean(tail)) if len(tail) > 0 else var_1d

    if horizon_days > 1:
        var_val = _scale_var(var_1d, horizon_days)
        es_val = _scale_var(es_1d, horizon_days)
        scaled = True
    else:
        var_val = var_1d
        es_val = es_1d
        scaled = False

    return VaRResult(
        var=var_val,
        es=es_val,
        method="historical",
        confidence=1 - alpha,
        horizon_days=horizon_days,
        scaled=scaled,
    )


def var_parametric_normal(
    returns: np.ndarray,
    weights: Optional[np.ndarray] = None,
    alpha: float = 0.05,
    horizon_days: int = 1,
    portfolio_value: float = 1.0,
) -> VaRResult:
    """
    Parametric VaR (Normal): VaR̂_p(1-α) = M · (μ̂ + σ̂ · q(α))
    ES_p = M · (μ̂ - σ̂ · φ(Φ⁻¹(α))/α)
    """
    returns = np.asarray(returns)
    if weights is not None:
        portfolio_returns = (returns @ np.asarray(weights).flatten()).flatten()
    else:
        portfolio_returns = returns.flatten()

    mu = np.mean(portfolio_returns)
    sigma = np.std(portfolio_returns, ddof=1)
    if sigma < 1e-12:
        sigma = 1e-12

    q_alpha = stats.norm.ppf(alpha)
    var_1d = portfolio_value * (-mu + sigma * (-q_alpha))  # loss = -return
    phi_inv = stats.norm.ppf(alpha)
    es_1d = portfolio_value * (-mu + sigma * stats.norm.pdf(phi_inv) / alpha)

    if horizon_days > 1:
        var_val = _scale_var(var_1d, horizon_days)
        es_val = _scale_var(es_1d, horizon_days)
        scaled = True
    else:
        var_val = var_1d
        es_val = es_1d
        scaled = False

    return VaRResult(
        var=float(var_val),
        es=float(es_val),
        method="parametric_normal",
        confidence=1 - alpha,
        horizon_days=horizon_days,
        scaled=scaled,
    )


def var_parametric_t(
    returns: np.ndarray,
    weights: Optional[np.ndarray] = None,
    alpha: float = 0.05,
    horizon_days: int = 1,
    portfolio_value: float = 1.0,
) -> VaRResult:
    """
    Parametric VaR (t-distribution): fit ν, μ, σ via MLE.
    VaR̂_p = M · (μ̂ + σ̂ · F_ν⁻¹(α))
    ES = M · (μ̂ - σ̂ · f_ν(F_ν⁻¹(α))/α · [ν + (F_ν⁻¹(α))²]/(ν-1))
    """
    returns = np.asarray(returns)
    if weights is not None:
        portfolio_returns = (returns @ np.asarray(weights).flatten()).flatten()
    else:
        portfolio_returns = returns.flatten()

    nu, mu, sigma = stats.t.fit(portfolio_returns)
    nu = max(nu, 2.01)  # ensure ν > 2 for finite variance

    t_inv = stats.t.ppf(alpha, nu)
    var_1d = portfolio_value * (-mu + sigma * (-t_inv))

    t_pdf = stats.t.pdf(t_inv, nu)
    es_factor = (nu + t_inv ** 2) / (nu - 1)
    es_1d = portfolio_value * (-mu + sigma * t_pdf / alpha * es_factor)

    if horizon_days > 1:
        var_val = _scale_var(var_1d, horizon_days)
        es_val = _scale_var(es_1d, horizon_days)
        scaled = True
    else:
        var_val = var_1d
        es_val = es_1d
        scaled = False

    return VaRResult(
        var=float(var_val),
        es=float(es_val),
        method="parametric_t",
        confidence=1 - alpha,
        horizon_days=horizon_days,
        scaled=scaled,
    )


def var_monte_carlo(
    returns: np.ndarray,
    weights: Optional[np.ndarray] = None,
    alpha: float = 0.05,
    horizon_days: int = 1,
    portfolio_value: float = 1.0,
    n_simulations: int = 100_000,
    use_multivariate: bool = False,
) -> VaRResult:
    """
    Monte Carlo VaR: simulate from fitted distribution.
    Supports multivariate normal for multi-asset portfolios.
    """
    returns = np.asarray(returns)
    n_obs, n_assets = returns.shape[0], returns.shape[1] if returns.ndim > 1 else 1

    if weights is not None:
        weights = np.asarray(weights).flatten()
        portfolio_returns = returns @ weights
    else:
        portfolio_returns = returns.flatten()
        weights = np.ones(1)

    if use_multivariate and returns.ndim > 1 and n_assets > 1 and weights is not None:
        mu = np.mean(returns, axis=0)
        cov = np.cov(returns.T, ddof=1)
        sim_returns = np.random.multivariate_normal(mu, cov, size=n_simulations)
        sim_portfolio = sim_returns @ weights
    else:
        mu = np.mean(portfolio_returns)
        sigma = np.std(portfolio_returns, ddof=1)
        if sigma < 1e-12:
            sigma = 1e-12
        sim_portfolio = np.random.normal(mu, sigma, size=n_simulations)

    losses = -sim_portfolio * portfolio_value
    var_1d = float(np.percentile(losses, alpha * 100))
    tail = losses[losses >= var_1d]
    es_1d = float(np.mean(tail)) if len(tail) > 0 else var_1d

    if horizon_days > 1:
        var_val = _scale_var(var_1d, horizon_days)
        es_val = _scale_var(es_1d, horizon_days)
        scaled = True
    else:
        var_val = var_1d
        es_val = es_1d
        scaled = False

    return VaRResult(
        var=var_val,
        es=es_val,
        method="monte_carlo",
        confidence=1 - alpha,
        horizon_days=horizon_days,
        scaled=scaled,
    )


def compute_var_all_methods(
    returns: np.ndarray,
    weights: Optional[np.ndarray] = None,
    alpha: float = 0.05,
    horizon_days: int = 1,
    portfolio_value: float = 1.0,
    include_monte_carlo: bool = True,
    mc_simulations: int = 100_000,
) -> dict:
    """Compute VaR and ES for all methods. Returns dict suitable for API."""
    results = {}
    results["historical"] = var_historical(
        returns, weights, alpha, horizon_days, portfolio_value
    )
    results["parametric_normal"] = var_parametric_normal(
        returns, weights, alpha, horizon_days, portfolio_value
    )
    results["parametric_t"] = var_parametric_t(
        returns, weights, alpha, horizon_days, portfolio_value
    )
    if include_monte_carlo:
        results["monte_carlo"] = var_monte_carlo(
            returns, weights, alpha, horizon_days, portfolio_value, mc_simulations
        )

    return {
        "var": {k: v.var for k, v in results.items()},
        "es": {k: v.es for k, v in results.items()},
        "confidence": 1 - alpha,
        "horizon_days": horizon_days,
        "portfolio_value": portfolio_value,
        "methods": list(results.keys()),
    }
