"""
Covariance Matrix Health — M7 L1–3: Ledoit-Wolf, OAS shrinkage, MST, condition number.

TRANSACT_APP_SPEC §3.3.3
  - Condition number of Σ: flag ill-conditioned matrices (cond > 1000)
  - Shrinkage intensity comparison: Ledoit-Wolf α_LW vs OAS shrinkage
  - Correlation distance matrix: d(ρ_ij) = √(2(1-ρ_ij))
  - Minimum Spanning Tree (MST) visualization of asset correlations
  - Heat map: raw Σ vs shrunk Σ side-by-side
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List

try:
    from sklearn.covariance import LedoitWolf, OAS
    _SKLEARN = True
except ImportError:
    _SKLEARN = False

try:
    import networkx as nx
    _NX = True
except ImportError:
    _NX = False


@dataclass
class CovarianceHealthResult:
    condition_number: float
    is_ill_conditioned: bool        # cond > 1000
    lw_shrinkage: float             # Ledoit-Wolf α
    oas_shrinkage: float            # OAS α
    eigenvalues: List[float]        # descending order (raw covariance)
    eigenvalue_fractions: List[float]  # fraction of total variance explained
    raw_correlation: List[List[float]]
    lw_correlation: List[List[float]]
    oas_correlation: List[List[float]]
    distance_matrix: List[List[float]]   # d(ρ_ij) = √(2(1-ρ_ij))
    n_assets: int
    n_obs: int


@dataclass
class MSTResult:
    nodes: List[dict]           # [{"id": i, "label": "AAPL"}, ...]
    mst_edges: List[dict]       # MST edges: [{"from": i, "to": j, "correlation": ρ, "distance": d}]
    all_edges: List[dict]       # all N*(N-1)/2 pairs
    total_mst_distance: float


def _cov_to_corr(cov: np.ndarray) -> np.ndarray:
    """Convert covariance matrix to correlation matrix."""
    sigma = np.sqrt(np.maximum(np.diag(cov), 1e-14))
    corr = cov / np.outer(sigma, sigma)
    np.fill_diagonal(corr, 1.0)
    return np.clip(corr, -1.0, 1.0)


def _corr_distance(corr: np.ndarray) -> np.ndarray:
    """d(ρ_ij) = √(2(1 − ρ_ij))  — M7 §1."""
    dist = np.sqrt(2.0 * np.maximum(1.0 - corr, 0.0))
    np.fill_diagonal(dist, 0.0)
    return dist


def compute_covariance_health(returns: np.ndarray) -> CovarianceHealthResult:
    """
    Full covariance matrix diagnostics:
    - Condition number (spectral: λ_max / λ_min)
    - Ledoit-Wolf and OAS shrinkage intensities
    - Eigenvalue spectrum
    - Raw, LW-shrunk, OAS-shrunk correlation matrices
    - Correlation distance matrix for MST
    """
    R = np.asarray(returns, dtype=float)
    T, N = R.shape

    if N < 2:
        raise ValueError("Need at least 2 assets.")
    if T < N + 2:
        raise ValueError(
            f"Too few observations: T={T} must exceed N+2={N+2}. "
            "Use a longer data period or fewer assets."
        )

    # ── Raw sample covariance ──────────────────────────────────────────────
    cov_raw = np.cov(R.T, ddof=1)

    # ── Condition number ───────────────────────────────────────────────────
    eigs = np.linalg.eigvalsh(cov_raw)           # ascending
    eigs_pos = np.abs(eigs)
    eigs_desc = np.sort(eigs_pos)[::-1]
    cond = float(eigs_desc[0] / max(float(eigs_desc[-1]), 1e-14))

    total_var = float(eigs_desc.sum())
    eig_fracs = [float(e / max(total_var, 1e-14)) for e in eigs_desc]

    # ── Shrinkage ──────────────────────────────────────────────────────────
    if _SKLEARN:
        lw_obj = LedoitWolf(assume_centered=False).fit(R)
        cov_lw = lw_obj.covariance_
        lw_alpha = float(lw_obj.shrinkage_)

        oas_obj = OAS(assume_centered=False).fit(R)
        cov_oas = oas_obj.covariance_
        oas_alpha = float(oas_obj.shrinkage_)
    else:
        # Ledoit-Wolf analytical estimator (Oracle Approximating Shrinkage)
        S = cov_raw
        mu_tgt = np.trace(S) / N
        # α_LW = min(1, (||S||_F² + Tr(S)²) / ((T+1-2/N)(||S||_F² - Tr(S)²/N)))
        trS2 = float(np.trace(S @ S))
        trS = float(np.trace(S))
        num = trS2 + trS**2
        denom = (T + 1 - 2.0 / N) * (trS2 - trS**2 / N)
        lw_alpha = float(min(1.0, num / max(denom, 1e-14)))
        cov_lw = (1 - lw_alpha) * S + lw_alpha * mu_tgt * np.eye(N)
        oas_alpha = lw_alpha         # best fallback without sklearn
        cov_oas = cov_lw

    corr_raw = _cov_to_corr(cov_raw)
    corr_lw  = _cov_to_corr(cov_lw)
    corr_oas = _cov_to_corr(cov_oas)
    dist_mat = _corr_distance(corr_raw)

    return CovarianceHealthResult(
        condition_number=cond,
        is_ill_conditioned=bool(cond > 1000),
        lw_shrinkage=lw_alpha,
        oas_shrinkage=oas_alpha,
        eigenvalues=[float(e) for e in eigs_desc],
        eigenvalue_fractions=eig_fracs,
        raw_correlation=corr_raw.tolist(),
        lw_correlation=corr_lw.tolist(),
        oas_correlation=corr_oas.tolist(),
        distance_matrix=dist_mat.tolist(),
        n_assets=N,
        n_obs=T,
    )


def _prim_mst(dist: np.ndarray) -> List[tuple]:
    """Prim's MST without networkx. Returns list of (i, j) edges."""
    N = dist.shape[0]
    in_mst = [False] * N
    in_mst[0] = True
    edges = []
    for _ in range(N - 1):
        best_d, best_i, best_j = float("inf"), -1, -1
        for i in range(N):
            if not in_mst[i]:
                continue
            for j in range(N):
                if in_mst[j]:
                    continue
                if dist[i, j] < best_d:
                    best_d, best_i, best_j = dist[i, j], i, j
        if best_i >= 0:
            in_mst[best_j] = True
            edges.append((best_i, best_j))
    return edges


def compute_mst(
    returns: np.ndarray,
    labels: Optional[List[str]] = None,
) -> MSTResult:
    """
    Minimum Spanning Tree of the correlation graph.
    Weights = distance d(ρ_ij) = √(2(1-ρ_ij))  (M7 L3).
    """
    R = np.asarray(returns, dtype=float)
    T, N = R.shape

    if labels is None:
        labels = [str(i) for i in range(N)]

    cov_raw = np.cov(R.T, ddof=1)
    corr    = _cov_to_corr(cov_raw)
    dist    = _corr_distance(corr)

    nodes = [{"id": i, "label": labels[i]} for i in range(N)]

    all_edges = [
        {
            "from": int(i),
            "to": int(j),
            "correlation": float(corr[i, j]),
            "distance": float(dist[i, j]),
        }
        for i in range(N)
        for j in range(i + 1, N)
    ]

    # ── Compute MST ────────────────────────────────────────────────────────
    if _NX and N > 1:
        G = nx.Graph()
        for i in range(N):
            G.add_node(i)
        for e in all_edges:
            G.add_edge(e["from"], e["to"], weight=e["distance"])
        mst_g = nx.minimum_spanning_tree(G, weight="weight")
        mst_edge_pairs = list(mst_g.edges())
    elif N > 1:
        mst_edge_pairs = _prim_mst(dist)
    else:
        mst_edge_pairs = []

    mst_edges = [
        {
            "from": int(u),
            "to": int(v),
            "correlation": float(corr[u, v]),
            "distance": float(dist[u, v]),
        }
        for u, v in mst_edge_pairs
    ]

    total_dist = float(sum(e["distance"] for e in mst_edges))

    return MSTResult(
        nodes=nodes,
        mst_edges=mst_edges,
        all_edges=all_edges,
        total_mst_distance=total_dist,
    )
