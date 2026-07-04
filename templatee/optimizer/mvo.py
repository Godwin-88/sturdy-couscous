"""
Mean-Variance Optimization — M1 L4: QP, GMV, Tangency, Efficient Frontier
Uses CVXPY for quadratic programming.
"""

import numpy as np
from typing import Optional, List, Tuple
from dataclasses import dataclass

try:
    import cvxpy as cp
    CVXPY_AVAILABLE = True
except ImportError:
    CVXPY_AVAILABLE = False


@dataclass
class MVOResult:
    """Result of MVO optimization."""
    weights: np.ndarray
    expected_return: float
    volatility: float
    sharpe_ratio: float
    is_gmv: bool
    is_tangency: bool


@dataclass
class FrontierPoint:
    """Single point on efficient frontier."""
    weights: np.ndarray
    expected_return: float
    volatility: float
    sharpe_ratio: float


def _solve_qp(
    cov: np.ndarray,
    mu: np.ndarray,
    target_return: Optional[float] = None,
    risk_free: float = 0.0,
    long_only: bool = True,
    sum_to_one: bool = True,
) -> Tuple[np.ndarray, float, float]:
    """
    Solve min ½ w^T Σ w  s.t.  w^T r = target (if given), w^T ι = 1, w ≥ 0.
    """
    n = cov.shape[0]
    w = cp.Variable(n)

    objective = cp.Minimize(0.5 * cp.quad_form(w, cov))
    constraints = []
    if sum_to_one:
        constraints.append(cp.sum(w) == 1)
    if long_only:
        constraints.append(w >= 0)
    if target_return is not None:
        constraints.append(mu @ w >= target_return)

    prob = cp.Problem(objective, constraints)
    prob.solve(verbose=False)

    if prob.status not in ["optimal", "optimal_inaccurate"]:
        raise ValueError(f"QP failed: {prob.status}")

    w_val = np.array(w.value).flatten()
    ret = float(mu @ w_val)
    vol = float(np.sqrt(w_val @ cov @ w_val))
    return w_val, ret, vol


def gmv_portfolio(
    cov: np.ndarray,
    mu: Optional[np.ndarray] = None,
    long_only: bool = True,
) -> MVOResult:
    """
    Global Minimum Variance: w_GMV = Σ⁻¹ι / (ι^T Σ⁻¹ι)
    """
    n = cov.shape[0]
    ones = np.ones(n)
    try:
        cov_inv = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        cov_inv = np.linalg.pinv(cov)
    denom = ones @ cov_inv @ ones
    w = (cov_inv @ ones) / denom
    if long_only:
        w = np.maximum(w, 0)
        w = w / w.sum()
    ret = float(mu @ w) if mu is not None else 0.0
    vol = float(np.sqrt(w @ cov @ w))
    sharpe = (ret - 0) / vol if vol > 1e-12 else 0.0
    return MVOResult(
        weights=w,
        expected_return=ret,
        volatility=vol,
        sharpe_ratio=sharpe,
        is_gmv=True,
        is_tangency=False,
    )


def tangency_portfolio(
    cov: np.ndarray,
    mu: np.ndarray,
    risk_free: float = 0.0,
    long_only: bool = True,
) -> MVOResult:
    """
    Tangency portfolio: w_TANG = Σ⁻¹(r - r_f ι) / (B - r_f A)
    Maximizes Sharpe ratio.
    """
    n = cov.shape[0]
    r = mu - risk_free
    try:
        cov_inv = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        cov_inv = np.linalg.pinv(cov)
    v = cov_inv @ r
    w = v / v.sum()
    if long_only:
        w = np.maximum(w, 0)
        w = w / w.sum()
    ret = float(mu @ w)
    vol = float(np.sqrt(w @ cov @ w))
    sharpe = (ret - risk_free) / vol if vol > 1e-12 else 0.0
    return MVOResult(
        weights=w,
        expected_return=ret,
        volatility=vol,
        sharpe_ratio=sharpe,
        is_gmv=False,
        is_tangency=True,
    )


def efficient_frontier(
    cov: np.ndarray,
    mu: np.ndarray,
    risk_free: float = 0.0,
    n_points: int = 50,
    long_only: bool = True,
) -> List[FrontierPoint]:
    """
    Compute efficient frontier by varying target return.
    """
    if not CVXPY_AVAILABLE:
        raise ImportError("cvxpy is required for efficient frontier. pip install cvxpy")

    gmv = gmv_portfolio(cov, mu, long_only)
    tang = tangency_portfolio(cov, mu, risk_free, long_only)

    ret_min = gmv.expected_return
    ret_max = tang.expected_return
    if ret_max <= ret_min:
        ret_max = float(np.max(mu))

    targets = np.linspace(ret_min, ret_max, n_points)
    points = []
    for tr in targets:
        try:
            w, r, v = _solve_qp(cov, mu, target_return=tr, risk_free=risk_free, long_only=long_only)
            sr = (r - risk_free) / v if v > 1e-12 else 0.0
            points.append(FrontierPoint(weights=w, expected_return=r, volatility=v, sharpe_ratio=sr))
        except Exception:
            continue

    return points


def optimize_mvo(
    cov: np.ndarray,
    mu: np.ndarray,
    target_return: Optional[float] = None,
    risk_free: float = 0.0,
    long_only: bool = True,
) -> MVOResult:
    """
    Single MVO optimization. If target_return is None, returns tangency portfolio.
    """
    if not CVXPY_AVAILABLE:
        raise ImportError("cvxpy is required. pip install cvxpy")

    if target_return is None:
        return tangency_portfolio(cov, mu, risk_free, long_only)

    w, r, v = _solve_qp(cov, mu, target_return=target_return, risk_free=risk_free, long_only=long_only)
    sr = (r - risk_free) / v if v > 1e-12 else 0.0
    return MVOResult(
        weights=w,
        expected_return=r,
        volatility=v,
        sharpe_ratio=sr,
        is_gmv=False,
        is_tangency=False,
    )
