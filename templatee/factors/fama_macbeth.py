"""Fama-MacBeth Regression - M6 L1"""
import numpy as np
from dataclasses import dataclass


@dataclass
class FamaMacBethResult:
    lambdas: np.ndarray
    std_errors: np.ndarray
    t_stats: np.ndarray
    p_values: np.ndarray
    betas: np.ndarray


def fama_macbeth(returns: np.ndarray, factors: np.ndarray) -> FamaMacBethResult:
    R, F = np.asarray(returns), np.asarray(factors)
    T, N = R.shape
    if F.ndim == 1:
        F = F.reshape(-1, 1)
    K = F.shape[1]
    F1 = np.column_stack([np.ones(T), F])
    betas = np.array([np.linalg.lstsq(F1, R[:, i], rcond=None)[0] for i in range(N)])
    B = betas[:, 1:]
    lambda_t = np.array([np.linalg.lstsq(np.column_stack([np.ones(N), B]), R[t], rcond=None)[0] for t in range(T)])
    lambdas = np.mean(lambda_t, axis=0)
    se = np.std(lambda_t, axis=0) / np.sqrt(T)
    se = np.clip(se, 1e-12, None)
    t_stats = lambdas / se
    try:
        from scipy.stats import t as t_dist
        p_values = 2 * (1 - t_dist.cdf(np.abs(t_stats), T - 1))
    except ImportError:
        p_values = np.zeros_like(t_stats)
    return FamaMacBethResult(lambdas=lambdas, std_errors=se, t_stats=t_stats, p_values=p_values, betas=B)
