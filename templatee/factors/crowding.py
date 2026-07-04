"""
Herding/Crowding Risk Monitor — M6 L2: Khandani-Lo style crowding index
Cross-portfolio correlation of factor loadings
"""

import numpy as np
from typing import Optional
from dataclasses import dataclass


@dataclass
class CrowdingResult:
    """Crowding risk result."""
    crowding_index: float
    level: str  # "low" | "mild" | "elevated" | "extreme"
    pair_correlations: np.ndarray
    avg_correlation: float


def crowding_index(
    factor_loadings: np.ndarray,
    thresholds: Optional[dict] = None,
) -> CrowdingResult:
    """
    Crowding index = avg pairwise correlation of factor loadings across assets.
    factor_loadings: N × K (N assets, K factors)
    """
    B = np.asarray(factor_loadings)
    if B.ndim == 1:
        B = B.reshape(-1, 1)
    N, K = B.shape
    if N < 2:
        return CrowdingResult(
            crowding_index=0.0,
            level="low",
            pair_correlations=np.array([]),
            avg_correlation=0.0,
        )

    # Correlation matrix of loadings (across assets)
    corr = np.corrcoef(B.T)  # K × K if we want factor-factor, or
    # Pairwise correlation of asset loading vectors
    corr_flat = []
    for i in range(N):
        for j in range(i + 1, N):
            c = np.corrcoef(B[i, :], B[j, :])[0, 1]
            if not np.isnan(c):
                corr_flat.append(c)
    corr_flat = np.array(corr_flat) if corr_flat else np.array([0.0])
    avg_corr = float(np.mean(np.abs(corr_flat)))
    crowding_idx = avg_corr

    thresh = thresholds or {"mild": 0.3, "elevated": 0.5, "extreme": 0.7}
    if crowding_idx >= thresh.get("extreme", 0.7):
        level = "extreme"
    elif crowding_idx >= thresh.get("elevated", 0.5):
        level = "elevated"
    elif crowding_idx >= thresh.get("mild", 0.3):
        level = "mild"
    else:
        level = "low"

    return CrowdingResult(
        crowding_index=crowding_idx,
        level=level,
        pair_correlations=corr_flat,
        avg_correlation=avg_corr,
    )
