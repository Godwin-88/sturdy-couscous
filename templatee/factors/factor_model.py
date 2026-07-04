"""
Factor Model Estimation — M2 L4: R_it = α_i + β_i^T f_t + ε_it
Time series OLS, covariance Ω̂ = BΣ̂_f B^T + Σ̂_ε
"""

import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class FactorModelResult:
    """OLS factor model result."""
    alphas: np.ndarray
    betas: np.ndarray  # N × K
    residuals: np.ndarray
    factor_cov: np.ndarray
    residual_var: np.ndarray
    r_squared: np.ndarray


def estimate_factor_model_ols(
    returns: np.ndarray,
    factors: np.ndarray,
) -> FactorModelResult:
    """
    Time series OLS: R_i = α_i + Fβ_i + ε_i per asset.
    returns: T × N, factors: T × K (with constant column)
    """
    R = np.asarray(returns)
    F = np.asarray(factors)
    if F.shape[0] != R.shape[0]:
        raise ValueError("returns and factors must have same T")
    if F.ndim == 1:
        F = F.reshape(-1, 1)
    if F.shape[1] > 0 and not np.allclose(F[:, 0], 1.0):
        F = np.column_stack([np.ones(F.shape[0]), F])

    T, N = R.shape
    K = F.shape[1]
    betas = np.zeros((N, K))
    alphas = np.zeros(N)
    residuals = np.zeros((T, N))

    for i in range(N):
        y = R[:, i]
        b = np.linalg.lstsq(F, y, rcond=None)[0]
        betas[i, :] = b
        alphas[i] = b[0] if K > 0 else 0
        pred = F @ b
        residuals[:, i] = y - pred

    factor_returns = F[:, 1:] if K > 1 else F
    factor_cov = np.cov(factor_returns.T, ddof=1) if factor_returns.shape[1] > 0 else np.eye(1)
    residual_var = np.var(residuals, axis=0, ddof=1)
    r_sq = 1 - residual_var / np.var(R, axis=0, ddof=1)
    r_sq = np.clip(r_sq, 0, 1)

    return FactorModelResult(
        alphas=alphas,
        betas=betas,
        residuals=residuals,
        factor_cov=factor_cov,
        residual_var=residual_var,
        r_squared=r_sq,
    )


def factor_covariance(B: np.ndarray, Sigma_f: np.ndarray, D: np.ndarray) -> np.ndarray:
    """Ω̂ = B Σ_f B^T + D (D = diag of residual variances)."""
    if B.shape[1] != Sigma_f.shape[0]:
        B = B[:, 1:]  # drop alpha column if present
    return B @ Sigma_f @ B.T + np.diag(D)
