"""
Higher-Order Statistics — M2 L2: Coskewness M3, Cokurtosis M4
skewness_p = w^T M3 (w⊗w), kurtosis_p = w^T M4 (w⊗w⊗w)
"""

import numpy as np
from typing import Optional
from dataclasses import dataclass


@dataclass
class CoskewnessResult:
    portfolio_skewness: float
    coskewness_matrix: np.ndarray  # N x N heatmap
    excess_kurtosis_warning: bool


def compute_coskewness(returns: np.ndarray, weights: np.ndarray) -> CoskewnessResult:
    """
    M3 coskewness: gamma_XYZ = E[(X-mu)(Y-mu)(Z-mu)] / (sig_X sig_Y sig_Z)
    Portfolio skewness = w^T M3 (w⊗w) via Kronecker.
    Simplified: sample coskewness matrix (N x N^2) and portfolio skewness.
    """
    R = np.asarray(returns)
    w = np.asarray(weights).flatten()
    n = R.shape[1]
    T = R.shape[0]
    if w.shape[0] != n:
        raise ValueError("weights length must match assets")

    mu = np.mean(R, axis=0)
    sigma = np.std(R, axis=0, ddof=1)
    sigma[sigma < 1e-12] = 1e-12
    R_centered = (R - mu) / sigma

    # Portfolio skewness via direct computation (more stable than full M3)
    port_ret = R @ w
    port_mu = np.mean(port_ret)
    port_sigma = np.std(port_ret, ddof=1)
    if port_sigma < 1e-12:
        port_skew = 0.0
    else:
        port_skew = np.mean((port_ret - port_mu) ** 3) / (port_sigma ** 3)

    # Coskewness heatmap: E[(r_i-mu_i)(r_j-mu_j)(r_k-mu_k)]/(sig_i sig_j sig_k) for i,j,k
    # Use (i,j) = co-skew of asset i,j with portfolio
    port_std = (R @ w - port_mu) / port_sigma if port_sigma > 1e-12 else np.zeros(T)
    M3_heatmap = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            m3 = np.mean(R_centered[:, i] * R_centered[:, j] * port_std)
            M3_heatmap[i, j] = m3

    # Kurtosis check
    port_kurt = np.mean((port_ret - port_mu) ** 4) / (port_sigma ** 4) - 3 if port_sigma > 1e-12 else 0
    kurtosis_warning = port_kurt > 1.0

    return CoskewnessResult(
        portfolio_skewness=float(port_skew),
        coskewness_matrix=M3_heatmap,
        excess_kurtosis_warning=bool(kurtosis_warning),  # numpy.bool_ → Python bool (numpy 2.x compat)
    )
