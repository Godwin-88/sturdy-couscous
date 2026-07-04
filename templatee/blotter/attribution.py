"""
Performance Attribution — M1 §4, M2: α, β·r_m, Σ λ_k·β_{p,k}, ε
r_p = α + β_p·r_m + Σ_k λ_k·β_{p,k} + ε_p
"""

import numpy as np
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class AttributionResult:
    alpha: float
    systematic_return: float  # β_p · r_m
    factor_returns: List[float]  # per-factor contribution
    residual: float
    total_return: float
    decomposition: dict


def performance_attribution(
    portfolio_returns: np.ndarray,
    market_returns: np.ndarray,
    risk_free_rate: float = 0.0,
    factor_betas: Optional[np.ndarray] = None,
    factor_returns: Optional[np.ndarray] = None,
) -> AttributionResult:
    """
    Decompose: r_p = α + β_p·r_m + Σ_k λ_k·β_{p,k} + ε
    If no factors: r_p = α + β·(r_m - r_f) + ε, α = r_p - r_f - β·(r_m - r_f)
    """
    r_p = np.asarray(portfolio_returns).flatten()
    r_m = np.asarray(market_returns).flatten()
    T = min(len(r_p), len(r_m))
    r_p, r_m = r_p[:T], r_m[:T]

    # CAPM: r_p - r_f = α + β·(r_m - r_f) + ε
    r_p_ex = r_p - risk_free_rate
    r_m_ex = r_m - risk_free_rate
    cov_pm = np.cov(r_p, r_m)[0, 1]
    var_m = np.var(r_m, ddof=1)
    beta_p = cov_pm / var_m if var_m > 0 else 0
    alpha = float(np.mean(r_p_ex) - beta_p * np.mean(r_m_ex))
    systematic = float(beta_p * np.mean(r_m_ex))

    factor_contrib = []
    if factor_betas is not None and factor_returns is not None:
        F = np.asarray(factor_returns)
        if F.ndim == 1:
            F = F.reshape(-1, 1)
        K = min(F.shape[1], len(factor_betas))
        for k in range(K):
            f_r = np.mean(F[:T, k]) if K <= F.shape[1] else 0
            b = factor_betas[k] if k < len(factor_betas) else 0
            factor_contrib.append(float(b * f_r))

    total_factor = sum(factor_contrib)
    residual = float(np.mean(r_p) - risk_free_rate - alpha - systematic - total_factor)
    total_return = float(np.mean(r_p))

    return AttributionResult(
        alpha=alpha,
        systematic_return=systematic,
        factor_returns=factor_contrib,
        residual=residual,
        total_return=total_return,
        decomposition={
            "alpha": alpha,
            "systematic": systematic,
            "factor_total": total_factor,
            "residual": residual,
            "total": total_return,
        },
    )
