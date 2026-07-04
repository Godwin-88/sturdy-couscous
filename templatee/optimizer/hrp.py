"""
Hierarchical Risk Parity — M7 L4: clustering → quasi-diagonalization → recursive bisection
"""

import numpy as np
from typing import List, Tuple
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import squareform


def correlation_distance(corr: np.ndarray) -> np.ndarray:
    """d(ρ_ij) = √(2(1-ρ_ij))"""
    return np.sqrt(np.maximum(2 * (1 - np.clip(corr, -1, 1)), 0))


def _cluster_var(cov: np.ndarray, start: int, end: int) -> float:
    """Variance of cluster (equal-weight)."""
    sub = cov[start:end, start:end]
    k = end - start
    w = np.ones(k) / k
    return float(w @ sub @ w)


def get_rec_bipart(cov: np.ndarray, n: int) -> np.ndarray:
    """
    Recursive bisection: alpha = 1 - cVar0/(cVar0+cVar1), weights by inverse cluster variance.
    cov is in quasi-diagonal order. Returns weights.
    """
    w = np.ones(n)

    def recurse(start: int, end: int) -> float:
        if end - start <= 1:
            return _cluster_var(cov, start, end) if start < end else 1e-12
        mid = (start + end) // 2
        cvar0 = recurse(start, mid)
        cvar1 = recurse(mid, end)
        tot = cvar0 + cvar1
        alpha = (1 - cvar0 / tot) if tot > 1e-12 else 0.5
        w[start:mid] *= alpha
        w[mid:end] *= 1 - alpha
        return tot

    recurse(0, n)
    return w / w.sum()


def hrp_weights(cov: np.ndarray) -> Tuple[np.ndarray, np.ndarray, List]:
    """
    Full HRP: correlation distance → linkage → quasi-diag → recursive bisection.
    Returns (weights, sort_order, dendrogram_linkage).
    """
    n = cov.shape[0]
    if n == 1:
        return np.array([1.0]), np.array([0]), []

    # Correlation matrix
    vol = np.sqrt(np.diag(cov))
    vol[vol < 1e-12] = 1e-12
    corr = cov / np.outer(vol, vol)
    dist = correlation_distance(corr)
    np.fill_diagonal(dist, 0)

    # Hierarchical clustering (single linkage)
    cond_dist = squareform(dist, checks=False)
    link = linkage(cond_dist, method="single")

    # Quasi-diagonal order (leaf order from dendrogram)
    sort_ix = leaves_list(link)
    if len(sort_ix) < n:
        sort_ix = np.concatenate([sort_ix, np.setdiff1d(np.arange(n), sort_ix)])

    # Reorder cov for recursive bisection
    cov_sorted = cov[np.ix_(sort_ix, sort_ix)]
    w_sorted = get_rec_bipart(cov_sorted, n)

    # Map back to original asset order
    w_orig = np.zeros(n)
    for i, idx in enumerate(sort_ix):
        w_orig[idx] = w_sorted[i]

    w_orig = w_orig / w_orig.sum()
    return w_orig, sort_ix, link.tolist()
