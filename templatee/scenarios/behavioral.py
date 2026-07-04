"""
Behavioral Scenarios — M4: Prospect Theory, herding, VaR under correlation stress
v(x) = x^α (gains), v(x) = -λ(-x)^β (losses), λ≈2.25, α≈β≈0.88
"""

import numpy as np
from typing import Optional
from dataclasses import dataclass


@dataclass
class ProspectTheoryResult:
    perceived_utility: float
    prospect_optimal_weights: np.ndarray
    perceived_utility_optimal: float


@dataclass
class HerdingResult:
    stressed_var_95: float
    stressed_var_99: float
    correlation_shift: float
    base_var_95: float
    base_var_99: float


def prospect_value(x: float, alpha: float = 0.88, lambda_: float = 2.25, beta: float = 0.88) -> float:
    """Kahneman-Tversky value function."""
    if x >= 0:
        return x ** alpha
    return -lambda_ * ((-x) ** beta)


def portfolio_perceived_utility(
    returns: np.ndarray,
    weights: np.ndarray,
    alpha: float = 0.88,
    lambda_: float = 2.25,
    beta: float = 0.88,
) -> float:
    """Average perceived utility over sample returns."""
    port_ret = returns @ weights
    return float(np.mean([prospect_value(r, alpha, lambda_, beta) for r in port_ret]))


def herding_stress_var(
    returns: np.ndarray,
    weights: np.ndarray,
    correlation_shift: float = 0.3,
    alpha: float = 0.05,
    portfolio_value: float = 1.0,
) -> HerdingResult:
    """Simulate herding: increase correlations by Δρ, recompute VaR."""
    cov = np.cov(returns.T, ddof=1)
    corr = np.corrcoef(returns.T) if returns.shape[0] > 1 else np.eye(len(weights))
    corr_stressed = np.clip(corr + correlation_shift, -0.99, 0.99)
    np.fill_diagonal(corr_stressed, 1.0)
    vol = np.sqrt(np.diag(cov))
    cov_stressed = np.diag(vol) @ corr_stressed @ np.diag(vol)

    w = np.asarray(weights).flatten()
    port_vol_base = np.sqrt(w @ cov @ w)
    port_vol_stressed = np.sqrt(w @ cov_stressed @ w)
    mu = np.mean(returns, axis=0) @ w

    from scipy.stats import norm
    # VaR: loss at percentile (95% VaR = 5th percentile, 99% VaR = 1st percentile)
    base_var_95 = -portfolio_value * (norm.ppf(alpha) * port_vol_base + mu)
    base_var_99 = -portfolio_value * (norm.ppf(0.01) * port_vol_base + mu)
    stressed_var_95 = -portfolio_value * (norm.ppf(alpha) * port_vol_stressed + mu)
    stressed_var_99 = -portfolio_value * (norm.ppf(0.01) * port_vol_stressed + mu)

    return HerdingResult(
        stressed_var_95=stressed_var_95,
        stressed_var_99=stressed_var_99,
        correlation_shift=correlation_shift,
        base_var_95=base_var_95,
        base_var_99=base_var_99,
    )
