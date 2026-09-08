"""Correlation & hidden-concentration endpoints (E6 / F6.4).

POST /risk/correlation/matrix                    -> pairwise correlation matrix
GET  /risk/borrowers/{borrower_id}/correlation   -> portfolio correlation exposure
GET  /risk/correlation/groups                    -> correlated groups above threshold
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from creditgraph.services import correlation

correlation_router = APIRouter(prefix="/risk", tags=["correlation"])


class CorrelationMatrixRequest(BaseModel):
    asset_symbols: list[str] = Field(
        ...,
        min_length=1,
        max_length=correlation.MAX_MATRIX_SYMBOLS,
        description="Asset symbols to correlate, e.g. ['ETH', 'USDC', 'ARB']",
    )
    threshold: float = Field(
        correlation.DEFAULT_CORRELATION_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="Correlation threshold used to flag highly correlated pairs",
    )


@correlation_router.post("/correlation/matrix")
async def correlation_matrix(body: CorrelationMatrixRequest) -> dict:
    """Compute the deterministic pairwise correlation matrix for a symbol set."""
    try:
        return correlation.compute_correlation_matrix(
            body.asset_symbols, threshold=body.threshold
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@correlation_router.get("/borrowers/{borrower_id}/correlation")
async def borrower_correlation(
    borrower_id: str,
    threshold: float = Query(
        correlation.DEFAULT_CORRELATION_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="Correlation threshold for flagging correlated collateral pairs",
    ),
) -> dict:
    """Concentration risk + hidden correlation exposure for a borrower's collateral."""
    try:
        return await correlation.compute_portfolio_correlation_exposure(
            borrower_id, threshold=threshold
        )
    except correlation.BorrowerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@correlation_router.get("/correlation/groups")
async def correlated_groups(
    threshold: float = Query(
        correlation.DEFAULT_CORRELATION_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="Minimum correlation for a group to be reported",
    ),
) -> dict:
    """Identify asset groups whose correlation is at or above the threshold."""
    try:
        return correlation.identify_correlated_groups(threshold)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
