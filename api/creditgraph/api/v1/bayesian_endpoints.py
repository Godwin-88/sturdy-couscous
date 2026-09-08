"""Bayesian risk inference endpoints (E5-US2).

POST /risk/bayesian/update     -> update PD with evidence
POST /risk/bayesian/posterior  -> compute full posterior PD
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from creditgraph.services import bayesian

bayesian_router = APIRouter(prefix="/risk/bayesian", tags=["bayesian-risk"])


class EvidenceItem(BaseModel):
    type: str = Field(..., description="One of: attestation, liability, exposure, collateral")
    strength: float = Field(..., ge=0.0, le=1.0, description="Evidence strength 0.0-1.0")


class UpdateEvidenceRequest(BaseModel):
    prior_pd: float = Field(..., ge=0.0, le=1.0, description="Prior probability of default")
    evidence: list[EvidenceItem] = Field(..., min_length=1, description="Evidence items to update PD")


class PosteriorRequest(BaseModel):
    fico_score: float = Field(..., ge=300.0, le=850.0, description="Borrower FICO score")
    leverage: float = Field(..., ge=0.0, description="Leverage ratio")
    regime: str = Field(..., description="Market regime")
    evidence_posterior: float = Field(..., ge=0.0, le=1.0, description="Posterior PD from evidence update")


@bayesian_router.post("/update", response_model=dict)
async def update_evidence(req: UpdateEvidenceRequest) -> dict:
    """Update posterior PD given new evidence items."""
    evidence_list = [e.model_dump() for e in req.evidence]
    return bayesian.update_with_evidence(req.prior_pd, evidence_list)


@bayesian_router.post("/posterior", response_model=dict)
async def compute_posterior(req: PosteriorRequest) -> dict:
    """Compute full posterior PD combining features and evidence."""
    return bayesian.compute_posterior_pd(
        req.fico_score,
        req.leverage,
        req.regime,
        req.evidence_posterior,
    )
