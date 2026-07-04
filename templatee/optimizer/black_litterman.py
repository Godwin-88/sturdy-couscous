"""
Black-Litterman Model — M3 L1: Reverse optimization, Bayesian views, BLM posterior
μ_BL = [(τΣ)⁻¹ + P^T Ω⁻¹ P]⁻¹ [(τΣ)⁻¹π + P^T Ω⁻¹Q]
"""

import numpy as np
from typing import Optional, List
from dataclasses import dataclass

try:
    import cvxpy as cp
    CVXPY_AVAILABLE = True
except ImportError:
    CVXPY_AVAILABLE = False


@dataclass
class BLMResult:
    """Black-Litterman result."""
    implied_returns: np.ndarray
    blm_returns: np.ndarray
    optimal_weights: np.ndarray
    expected_return: float
    volatility: float
    sharpe_ratio: float


def reverse_optimization(
    cov: np.ndarray,
    market_weights: np.ndarray,
    risk_aversion: Optional[float] = None,
) -> np.ndarray:
    """
    Implied equilibrium returns: π = δ · Σ · w_m
    δ = Sharpe_market / σ_m (risk-aversion)
    """
    w_m = np.asarray(market_weights).flatten()
    cov = np.asarray(cov)
    sigma_m = np.sqrt(w_m @ cov @ w_m)
    if risk_aversion is None:
        risk_aversion = 2.5  # typical value
    pi = risk_aversion * (cov @ w_m)
    return pi


def blm_posterior(
    cov: np.ndarray,
    implied_returns: np.ndarray,
    P: np.ndarray,
    Q: np.ndarray,
    tau: float = 0.05,
    omega: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    BLM posterior: μ_BL = [(τΣ)⁻¹ + P^T Ω⁻¹ P]⁻¹ [(τΣ)⁻¹π + P^T Ω⁻¹Q]
    P: K×N pick matrix, Q: K×1 view returns, Ω: K×K view uncertainty (diag)
    """
    cov = np.asarray(cov)
    pi = np.asarray(implied_returns).flatten()
    P = np.asarray(P)
    Q = np.asarray(Q).flatten()
    n = cov.shape[0]
    k = P.shape[0]

    tau_sigma_inv = np.linalg.inv(tau * cov)
    if omega is None:
        omega = np.diag(np.diag(tau * P @ cov @ P.T))  # idzorek-style
    omega_inv = np.linalg.inv(omega)

    A = tau_sigma_inv + P.T @ omega_inv @ P
    b = tau_sigma_inv @ pi + P.T @ omega_inv @ Q
    mu_bl = np.linalg.solve(A, b)
    return mu_bl


def blm_optimize(
    cov: np.ndarray,
    market_weights: np.ndarray,
    P: np.ndarray,
    Q: np.ndarray,
    tau: float = 0.05,
    risk_aversion: float = 2.5,
    risk_free: float = 0.0,
    long_only: bool = True,
) -> BLMResult:
    """
    Full BLM pipeline: reverse opt → posterior → MVO on μ_BL.
    """
    pi = reverse_optimization(cov, market_weights, risk_aversion)
    mu_bl = blm_posterior(cov, pi, P, Q, tau)

    if not CVXPY_AVAILABLE:
        raise ImportError("cvxpy required for BLM optimization")

    n = cov.shape[0]
    w = cp.Variable(n)
    objective = cp.Minimize(0.5 * cp.quad_form(w, cov) - (mu_bl @ w) / risk_aversion)
    constraints = [cp.sum(w) == 1]
    if long_only:
        constraints.append(w >= 0)

    prob = cp.Problem(objective, constraints)
    prob.solve(verbose=False)

    if prob.status not in ["optimal", "optimal_inaccurate"]:
        raise ValueError(f"BLM QP failed: {prob.status}")

    w_val = np.array(w.value).flatten()
    ret = float(mu_bl @ w_val)
    vol = float(np.sqrt(w_val @ cov @ w_val))
    sharpe = (ret - risk_free) / vol if vol > 1e-12 else 0.0

    return BLMResult(
        implied_returns=pi,
        blm_returns=mu_bl,
        optimal_weights=w_val,
        expected_return=ret,
        volatility=vol,
        sharpe_ratio=sharpe,
    )
