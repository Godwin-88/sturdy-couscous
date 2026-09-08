"""Portfolio intelligence endpoints (E12).

GET  /risk/portfolio/exposure           -> portfolio exposure graph
GET  /risk/portfolio/counterparty/{protocol} -> counterparty exposure
POST /risk/portfolio/contagion          -> contagion analysis
POST /risk/portfolio/var                -> portfolio VaR
GET  /risk/portfolio/systemic-stress    -> systemic stress impact
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from creditgraph.services import portfolio

portfolio_router = APIRouter(prefix="/risk/portfolio", tags=["portfolio"])


class ContagionRequest(BaseModel):
    borrower_id: str = Field(
        ...,
        min_length=1,
        description="Borrower whose collateral shock seeds the contagion cascade",
    )
    shock_pct: float = Field(
        portfolio.DEFAULT_CONTAGION_SHOCK,
        ge=-0.95,
        le=0.0,
        description="Negative collateral shock applied to the source borrower",
    )


class PortfolioVarRequest(BaseModel):
    confidence: float = Field(
        0.95,
        gt=0.0,
        lt=1.0,
        description="VaR confidence level (e.g. 0.95 for 95% one-tailed)",
    )


@portfolio_router.get("/exposure")
async def portfolio_exposure() -> dict:
    """Aggregate every borrower's exposure into a portfolio-level graph."""
    return await portfolio.get_portfolio_exposure()


@portfolio_router.get("/counterparty/{protocol}")
async def counterparty_exposure(protocol: str) -> dict:
    """Total exposure to a single protocol (counterparty) across all borrowers."""
    try:
        return await portfolio.get_counterparty_exposure(protocol)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@portfolio_router.post("/contagion")
async def contagion_analysis(body: ContagionRequest) -> dict:
    """Simulate a collateral shock to one borrower and propagate contagion."""
    try:
        return await portfolio.run_contagion_analysis(body.borrower_id, body.shock_pct)
    except portfolio.BorrowerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@portfolio_router.post("/var")
async def portfolio_var(body: PortfolioVarRequest) -> dict:
    """Parametric portfolio-level Value-at-Risk at the given confidence."""
    try:
        return await portfolio.compute_portfolio_var(body.confidence)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@portfolio_router.get("/systemic-stress")
async def systemic_stress(
    shock_pct: float = Query(
        portfolio.SYSTEMIC_SHOCK,
        ge=-0.95,
        le=0.0,
        description="Portfolio-wide negative collateral shock",
    ),
) -> dict:
    """Simulate a systemic shock across the entire portfolio."""
    try:
        return await portfolio.get_systemic_stress_impact(shock_pct)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
