"""Credit assessment + decision endpoints (E5/E6/E8).

POST /risk/borrowers/{borrower_id}/assessment  -> deterministic risk assessment
POST /risk/borrowers/{borrower_id}/decision    -> recommendation + persisted lineage
POST /risk/borrowers/seed                      -> idempotent demo borrower
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from creditgraph.graph.credit_graph import (
    get_borrower_state,
    list_borrowers,
    persist_credit_decision,
    seed_demo_borrower,
)
from creditgraph.models import AssessmentRequest, CreditAssessment, CreditDecision
from creditgraph.services import credit_risk

credit_router = APIRouter(prefix="/risk", tags=["credit-decision"])


@credit_router.get("/borrowers", response_model=list[str])
async def list_borrowers_endpoint() -> list[str]:
    """List all borrower IDs in the graph."""
    return await list_borrowers()


@credit_router.post("/borrowers/seed", response_model=dict)
async def seed_borrower() -> dict:
    """Idempotently create the demo borrower graph; return its id."""
    borrower_id = await seed_demo_borrower()
    return {"borrower_id": borrower_id, "status": "seeded"}


@credit_router.post("/borrowers/{borrower_id}/assessment", response_model=CreditAssessment)
async def assess_borrower(borrower_id: str, req: AssessmentRequest) -> CreditAssessment:
    """Run the deterministic risk chain for a borrower and return the assessment."""
    state = await get_borrower_state(borrower_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Borrower {borrower_id} not found")

    # Apply request-level overrides (regime + requested amount)
    state.requested_amount = req.requested_amount
    state.market_regime = req.regime

    assessment, _decision, _models = credit_risk.build_assessment_and_decision(
        state, risk_free_rate=req.risk_free_rate
    )
    return assessment


@credit_router.post("/borrowers/{borrower_id}/decision", response_model=CreditDecision)
async def decide_borrower(borrower_id: str, req: AssessmentRequest) -> CreditDecision:
    """Run the risk chain, persist the decision + lineage, return the recommendation."""
    state = await get_borrower_state(borrower_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Borrower {borrower_id} not found")

    state.requested_amount = req.requested_amount
    state.market_regime = req.regime

    assessment, decision, model_results = credit_risk.build_assessment_and_decision(
        state, risk_free_rate=req.risk_free_rate
    )
    await persist_credit_decision(decision, assessment, model_results)
    return decision