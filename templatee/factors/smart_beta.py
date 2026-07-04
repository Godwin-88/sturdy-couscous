"""
Smart Beta Construction — M6 L2: factor tilt strategies
"""

import numpy as np
from dataclasses import dataclass


@dataclass
class SmartBetaResult:
    weights: np.ndarray
    method: str
    factor_exposure: float
    expected_return: float
    volatility: float


def smart_beta_sort(factor_scores: np.ndarray, returns: np.ndarray, n_quantiles: int = 5) -> SmartBetaResult:
    scores = np.asarray(factor_scores).flatten()
    n = len(scores)
    q = np.percentile(scores, np.linspace(0, 100, n_quantiles + 1))
    top_idx = np.where(scores >= q[-2])[0]
    w = np.zeros(n)
    if len(top_idx) > 0:
        w[top_idx] = 1.0 / len(top_idx)
    ret = float(np.mean(returns, axis=0) @ w) if returns.shape[0] > 0 else 0.0
    cov = np.cov(returns.T, ddof=1) if returns.shape[0] > 1 and returns.shape[1] == n else np.eye(n) * 0.04
    vol = float(np.sqrt(w @ cov @ w))
    return SmartBetaResult(
        weights=w, method="quintile_sort",
        factor_exposure=float(np.mean(scores[top_idx])) if len(top_idx) > 0 else 0,
        expected_return=ret, volatility=vol,
    )


def smart_beta_signal_weighted(factor_scores: np.ndarray, returns: np.ndarray) -> SmartBetaResult:
    scores = np.asarray(factor_scores).flatten()
    scores = np.maximum(scores, 0)
    if scores.sum() < 1e-12:
        scores = np.ones_like(scores)
    w = scores / scores.sum()
    n = len(w)
    ret = float(np.mean(returns, axis=0) @ w) if returns.shape[0] > 0 else 0.0
    cov = np.cov(returns.T, ddof=1) if returns.shape[0] > 1 and returns.shape[1] == n else np.eye(n) * 0.04
    vol = float(np.sqrt(w @ cov @ w))
    return SmartBetaResult(weights=w, method="signal_weighted", factor_exposure=float(scores @ w / w.sum()), expected_return=ret, volatility=vol)
