"""Decision lifecycle endpoints (E8-US2 / E9-US2).

POST /risk/decisions/{decision_id}/override  -> override a decision (requires reason)
GET  /risk/decisions/{decision_id}/reconstruct -> reconstruct decision lineage
GET  /risk/decisions                          -> list decisions (filter by borrower_id)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from creditgraph.graph.credit_graph import (
    list_credit_decisions,
    override_credit_decision,
    reconstruct_decision,
)

decision_router = APIRouter(prefix="/risk/decisions", tags=["decisions"])


class OverrideDecisionRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="Documented reason for the override")
    overridden_by: str = Field(
        ..., min_length=1, description="Actor (user/role) performing the override"
    )


@decision_router.post("/{decision_id}/override", response_model=dict)
async def override_decision(decision_id: str, req: OverrideDecisionRequest) -> dict:
    """Override a credit decision with a documented reason (E8-US2).

    The original decision is preserved and re-labelled OVERRIDDEN; the prior
    status and the override audit trail are retained.
    """
    decision = await override_credit_decision(
        decision_id, reason=req.reason, overridden_by=req.overridden_by
    )
    if decision is None:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
    return decision.model_dump()


@decision_router.get("/{decision_id}/reconstruct", response_model=dict)
async def reconstruct_decision_endpoint(decision_id: str) -> dict:
    """Reconstruct a historical decision with full lineage (E9-US2)."""
    result = await reconstruct_decision(decision_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
    return result


@decision_router.get("", response_model=list[dict])
async def list_decisions(
    borrower_id: str | None = Query(None, description="Filter by borrower")
) -> list[dict]:
    """List credit decisions, optionally filtered by borrower_id."""
    decisions = await list_credit_decisions(borrower_id=borrower_id)
    return [d.model_dump() for d in decisions]
