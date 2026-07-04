"""
Risk Parity / Equal Risk Contribution — M5 L3: ERC + Relaxed RRP
RC_i = w_i · (Σw)_i / σ_p = 1/N · σ_p for all i
"""

import numpy as np
from typing import Optional
from dataclasses import dataclass

try:
    import cvxpy as cp
    CVXPY_AVAILABLE = True
except ImportError:
    CVXPY_AVAILABLE = False


@dataclass
class RiskParityResult:
    """Risk parity result."""
    weights: np.ndarray
    risk_contributions: np.ndarray
    volatility: float
    method: str  # "erc" or "rrp"


def _risk_contributions(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """RC_i = w_i * (Σw)_i / σ_p"""
    sigma_p = np.sqrt(w @ cov @ w)
    if sigma_p < 1e-12:
        return np.zeros_like(w)
    marginal = cov @ w
    return w * marginal / sigma_p


def risk_parity_erc(cov: np.ndarray, max_iter: int = 100) -> RiskParityResult:
    """
    Equal Risk Contribution: minimize Σ_i Σ_j (RC_i - RC_j)²
    Uses iterative optimization (CCD or scipy).
    """
    n = cov.shape[0]
    w = np.ones(n) / n  # start equal-weight

    for _ in range(max_iter):
        sigma_p = np.sqrt(w @ cov @ w)
        if sigma_p < 1e-12:
            break
        marginal = cov @ w
        # CCD: w_i = (1/n * σ_p) / (Σw)_i * w_i
        target_rc = sigma_p / n
        w_new = target_rc * w / marginal
        w_new = np.clip(w_new, 1e-8, 1.0)
        w_new = w_new / w_new.sum()
        if np.allclose(w, w_new, atol=1e-8):
            break
        w = w_new

    rc = _risk_contributions(w, cov)
    vol = np.sqrt(w @ cov @ w)
    return RiskParityResult(weights=w, risk_contributions=rc, volatility=vol, method="erc")


def risk_parity_rrp(
    cov: np.ndarray,
    mu: np.ndarray,
    rho: float = 0.0,
    long_only: bool = True,
) -> RiskParityResult:
    """
    Relaxed Risk Parity: blend ERC with return tilt via ρ.
    ρ=0 → ERC, ρ=1 → MVO. Solved via SOCP approximation.
    """
    if not CVXPY_AVAILABLE:
        return risk_parity_erc(cov)

    n = cov.shape[0]
    w = cp.Variable(n)

    # Objective: balance risk contributions + return tilt
    sigma_p_sq = cp.quad_form(w, cov)
    sigma_p = cp.sqrt(sigma_p_sq)
    marginal = cov @ w
    # Relaxed: minimize variance of risk contributions
    rc_var = cp.sum_squares(cp.multiply(w, marginal) - sigma_p / n)
    ret_objective = -mu @ w * rho
    objective = cp.Minimize(rc_var + 1e6 * ret_objective if rho > 0 else rc_var)

    constraints = [cp.sum(w) == 1, w >= 0] if long_only else [cp.sum(w) == 1]

    prob = cp.Problem(objective, constraints)
    prob.solve(verbose=False)

    if prob.status not in ["optimal", "optimal_inaccurate"]:
        return risk_parity_erc(cov)

    w_val = np.array(w.value).flatten()
    w_val = np.maximum(w_val, 0)
    w_val = w_val / w_val.sum()
    rc = _risk_contributions(w_val, cov)
    vol = float(np.sqrt(w_val @ cov @ w_val))
    return RiskParityResult(weights=w_val, risk_contributions=rc, volatility=vol, method="rrp")
