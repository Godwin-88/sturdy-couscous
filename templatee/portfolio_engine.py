"""
Portfolio Engine — M1 L1: Sample moments, Beta, Sharpe/Treynor/Sortino/M²/IR
Implements vector/matrix formulas from TRANSACT_APP_SPEC §3.2
"""

import numpy as np
from typing import Optional
from dataclasses import dataclass


@dataclass
class PortfolioMoments:
    """Sample moments for a portfolio (M1 §2–5)."""
    portfolio_return: float
    portfolio_variance: float
    portfolio_volatility: float
    portfolio_beta: float
    systematic_risk: float
    non_systematic_risk: float
    skewness: float
    kurtosis_excess: float
    asset_returns: np.ndarray
    asset_volatilities: np.ndarray


@dataclass
class PerformanceMetrics:
    """Performance appraisal ratios (M1 Part II §4–7)."""
    sharpe_ratio: float
    treynor_ratio: float
    sortino_ratio: float
    m2_modigliani: float
    m2_sortino: float
    information_ratio: float
    appraisal_ratio: float
    alpha: float


def compute_portfolio_moments(
    returns: np.ndarray,
    weights: np.ndarray,
    market_returns: Optional[np.ndarray] = None,
) -> PortfolioMoments:
    """
    Compute all sample moments for a portfolio.
    R_p = w^T r, σ²_p = w^T Σ w, β_p = w^T β
    Skewness: γ̂ = [N/((N-1)(N-2))] · Σ(r_i - r̄)³/s³
    Kurtosis: excess over normal (= 3)
    """
    returns = np.asarray(returns)
    weights = np.asarray(weights).flatten()
    n_assets = returns.shape[1]
    n_obs = returns.shape[0]

    if weights.shape[0] != n_assets:
        raise ValueError(f"Weights length {weights.shape[0]} != assets {n_assets}")

    # Portfolio return: R_p = w^T r (per-period, then mean)
    portfolio_returns = returns @ weights
    r_p = float(np.mean(portfolio_returns))

    # Covariance matrix (sample)
    cov = np.cov(returns.T, ddof=1)
    # Portfolio variance: σ²_p = w^T Σ w
    var_p = float(weights @ cov @ weights)
    vol_p = float(np.sqrt(max(var_p, 0)))

    # Asset betas vs portfolio (or vs market if provided)
    if market_returns is not None:
        market_returns = np.asarray(market_returns).flatten()
        if len(market_returns) != n_obs:
            market_returns = market_returns[:n_obs] if len(market_returns) > n_obs else np.pad(
                market_returns, (0, n_obs - len(market_returns)), mode="edge"
            )
        cov_im = np.cov(returns.T, market_returns, ddof=1)[:n_assets, n_assets]
        var_m = np.var(market_returns, ddof=1)
        betas = cov_im / var_m if var_m > 0 else np.zeros(n_assets)
    else:
        # Use portfolio itself as "market" for beta decomposition
        cov_im = cov @ weights
        var_m = var_p
        betas = cov_im / var_m if var_m > 0 else weights

    beta_p = float(weights @ betas)

    # Total risk decomposition: σ²_p = β²_p · σ²_m + σ²_u
    var_m = float(np.var(market_returns, ddof=1)) if market_returns is not None and len(market_returns) > 1 else var_p
    systematic = beta_p ** 2 * var_m
    non_systematic = max(var_p - systematic, 0)

    # Skewness: γ̂ = [N/((N-1)(N-2))] · Σ(r_i - r̄)³/s³
    r_centered = portfolio_returns - r_p
    s3 = vol_p ** 3
    if s3 > 1e-12:
        skew = (n_obs / ((n_obs - 1) * (n_obs - 2))) * np.sum(r_centered ** 3) / s3
    else:
        skew = 0.0

    # Kurtosis (excess over 3)
    s4 = vol_p ** 4
    if s4 > 1e-12:
        kurt = (n_obs * (n_obs + 1) / ((n_obs - 1) * (n_obs - 2) * (n_obs - 3))) * np.sum(r_centered ** 4) / s4 - 3
    else:
        kurt = 0.0

    asset_vols = np.sqrt(np.diag(cov))

    return PortfolioMoments(
        portfolio_return=r_p,
        portfolio_variance=var_p,
        portfolio_volatility=vol_p,
        portfolio_beta=float(beta_p),
        systematic_risk=float(systematic),
        non_systematic_risk=float(non_systematic),
        skewness=float(skew),
        kurtosis_excess=float(kurt),
        asset_returns=np.mean(returns, axis=0),
        asset_volatilities=asset_vols,
    )


def compute_performance_metrics(
    portfolio_returns: np.ndarray,
    risk_free_rate: float,
    portfolio_beta: float,
    benchmark_returns: Optional[np.ndarray] = None,
    mar: Optional[float] = None,
) -> PerformanceMetrics:
    """
    Compute performance appraisal ratios (M1 Part II §4–7).
    SR, TR, Sortino, M², M²-Sortino, IR, Appraisal Ratio.
    """
    r_p = np.mean(portfolio_returns)
    sigma_p = np.std(portfolio_returns, ddof=1)
    if sigma_p < 1e-12:
        sigma_p = 1e-12

    # Sharpe: (r̄_p - r̄_f) / σ_p
    sharpe = (r_p - risk_free_rate) / sigma_p if sigma_p > 0 else 0.0

    # Treynor: (r̄_p - r̄_f) / β_p
    treynor = (r_p - risk_free_rate) / portfolio_beta if abs(portfolio_beta) > 1e-12 else 0.0

    # Sortino: (r̄_p - r_MAR) / σ_downside
    mar_val = mar if mar is not None else risk_free_rate
    downside_returns = portfolio_returns[portfolio_returns < mar_val]
    sigma_down = np.std(downside_returns, ddof=1) if len(downside_returns) > 1 else sigma_p
    if sigma_down < 1e-12:
        sigma_down = 1e-12
    sortino = (r_p - mar_val) / sigma_down

    # M² (Modigliani): r_f + SR · σ_benchmark
    sigma_bench = np.std(benchmark_returns, ddof=1) if benchmark_returns is not None and len(benchmark_returns) > 1 else sigma_p
    m2 = risk_free_rate + sharpe * sigma_bench

    # M²-Sortino
    sigma_d_bench = np.std(benchmark_returns[benchmark_returns < mar_val], ddof=1) if benchmark_returns is not None else sigma_down
    if np.isnan(sigma_d_bench) or sigma_d_bench < 1e-12:
        sigma_d_bench = sigma_down
    m2_sortino = r_p + sortino * (sigma_d_bench - sigma_down)

    # Information Ratio: (r̄_p - r̄_b) / σ(r_p - r_b)
    if benchmark_returns is not None and len(benchmark_returns) == len(portfolio_returns):
        excess = portfolio_returns - benchmark_returns
        ir = (np.mean(excess) / np.std(excess, ddof=1)) if np.std(excess, ddof=1) > 1e-12 else 0.0
    else:
        ir = 0.0

    # Alpha: r_p - (r_RF + β_p(r_m - r_RF))
    r_m = np.mean(benchmark_returns) if benchmark_returns is not None else r_p
    alpha = r_p - (risk_free_rate + portfolio_beta * (r_m - risk_free_rate))

    # Appraisal Ratio: α / σ_u (idiosyncratic vol)
    sigma_u = sigma_p * np.sqrt(max(1 - portfolio_beta ** 2 * (np.var(benchmark_returns, ddof=1) if benchmark_returns is not None else 0) / (sigma_p ** 2 if sigma_p > 0 else 1), 0))
    if sigma_u < 1e-12:
        sigma_u = 1e-12
    ar = alpha / sigma_u

    return PerformanceMetrics(
        sharpe_ratio=float(sharpe),
        treynor_ratio=float(treynor),
        sortino_ratio=float(sortino),
        m2_modigliani=float(m2),
        m2_sortino=float(m2_sortino),
        information_ratio=float(ir),
        appraisal_ratio=float(ar),
        alpha=float(alpha),
    )
