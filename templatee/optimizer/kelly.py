"""
Kelly Criterion — M5 L1: single-asset G(f)=p·ln(1+f)+q·ln(1-f), multi-asset continuous
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
class KellyResult:
    """Kelly optimization result."""
    optimal_fraction: float
    expected_growth: float
    weights: np.ndarray
    fractional_kelly: Optional[float] = None


def kelly_single(p: float, q: float, a: float = 1.0, b: float = 1.0) -> float:
    """
    Single-asset Kelly: f* = p - q (symmetric) or f* = p/a - q/b (asymmetric).
    p=win prob, q=1-p, a=loss per unit, b=win per unit.
    """
    return p / a - q / b


def kelly_growth_curve(p: float, q: float, f_max: float = 1.0, n_points: int = 100) -> list:
    """G(f) = p·ln(1+f) + q·ln(1-f) for plotting."""
    f_vals = np.linspace(0.01, min(f_max, 0.99), n_points)
    g_vals = []
    for f in f_vals:
        g = p * np.log(1 + f) + q * np.log(1 - f)
        g_vals.append({"f": float(f), "g": float(g)})
    return g_vals


def kelly_multi_asset(
    returns: np.ndarray,
    fractional: float = 1.0,
    long_only: bool = True,
) -> KellyResult:
    """
    Multi-asset Kelly: maximize E[ln(1 + w^T r)].
    fractional: κ ∈ (0,1] scales weights (half-Kelly etc).
    """
    if not CVXPY_AVAILABLE:
        raise ImportError("cvxpy required for multi-asset Kelly")

    returns = np.asarray(returns)
    n_obs, n_assets = returns.shape
    mean_r = np.mean(returns, axis=0)

    # Convex approximation: -E[ln(1+w'r)] ≈ -E[w'r] + ½E[(w'r)²] for small r
    # More stable: use log objective via geometric mean approximation
    w = cp.Variable(n_assets)

    # Maximize sum log(1 + r_t' w) — concave. Clip for numerical stability.
    log_terms = []
    for t in range(n_obs):
        r_t = returns[t, :]
        log_terms.append(cp.log(cp.maximum(1 + r_t @ w, 1e-6)))

    objective = cp.Maximize(cp.sum(log_terms) / n_obs)
    constraints = [cp.sum(w) == 1]
    if long_only:
        constraints.append(w >= 0)

    prob = cp.Problem(objective, constraints)
    prob.solve(verbose=False)

    if prob.status not in ["optimal", "optimal_inaccurate"]:
        raise ValueError(f"Kelly optimization failed: {prob.status}")

    w_val = np.array(w.value).flatten()
    w_val = np.maximum(w_val, 0)
    w_val = w_val / w_val.sum()

    if fractional < 1.0:
        w_val = w_val * fractional

    # Expected log growth
    gross = 1 + returns @ w_val
    gross = np.clip(gross, 1e-10, 1e10)
    g_mean = float(np.mean(np.log(gross)))

    return KellyResult(
        optimal_fraction=float(np.sum(np.abs(w_val))),
        expected_growth=g_mean,
        weights=w_val,
        fractional_kelly=fractional if fractional < 1.0 else None,
    )
