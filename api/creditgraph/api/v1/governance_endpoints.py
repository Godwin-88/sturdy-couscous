"""Governance endpoints (E11).

POST /risk/governance/models           -> register a risk model
GET  /risk/governance/models/{model_id} -> get model governance
GET  /risk/governance/models            -> list registered models
POST /risk/governance/policies          -> update a policy
GET  /risk/governance/audit/{entity_type}/{entity_id} -> audit log for an entity
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from creditgraph.services import governance

governance_router = APIRouter(prefix="/risk/governance", tags=["governance"])


class RegisterModelRequest(BaseModel):
    model_id: str = Field(..., description="Unique model identifier")
    name: str = Field(..., description="Human-readable model name")
    version: str = Field(..., description="Semantic version")
    owner: str = Field(..., description="Model owner / responsible party")
    description: str | None = Field(None, description="Model description")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Model parameters")
    effective_date: datetime | None = Field(None, description="Effective date of registration")
    status: str = Field("active", description="Model status")


class UpdatePolicyRequest(BaseModel):
    policy_id: str = Field(..., description="Unique policy identifier")
    previous_value: Any = Field(..., description="Previous policy value")
    new_value: Any = Field(..., description="New policy value")
    user: str = Field(..., description="Actor performing the update")
    reason: str = Field(..., description="Reason for the change")
    effective_date: datetime | None = Field(None, description="Effective date of the change")


@governance_router.post("/models", response_model=dict)
async def register_model(req: RegisterModelRequest) -> dict:
    """Register a risk model with governance metadata."""
    return governance.register_model(
        model_id=req.model_id,
        name=req.name,
        version=req.version,
        owner=req.owner,
        description=req.description,
        parameters=req.parameters,
        effective_date=req.effective_date,
        status=req.status,
    )


@governance_router.get("/models/{model_id}", response_model=dict)
async def get_model_governance(model_id: str) -> dict:
    """Retrieve governance metadata for a registered model."""
    record = governance.get_model_governance(model_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return record


@governance_router.get("/models", response_model=list[dict])
async def list_models() -> list[dict]:
    """List all registered risk models."""
    return governance.list_models()


@governance_router.post("/policies", response_model=dict)
async def update_policy(req: UpdatePolicyRequest) -> dict:
    """Record a policy change with full audit trail."""
    return governance.update_policy(
        policy_id=req.policy_id,
        previous_value=req.previous_value,
        new_value=req.new_value,
        user=req.user,
        reason=req.reason,
        effective_date=req.effective_date,
    )


@governance_router.get("/audit/{entity_type}/{entity_id}", response_model=list[dict])
async def get_audit_log(entity_type: str, entity_id: str) -> list[dict]:
    """Get audit log entries for an entity."""
    return governance.get_audit_log(entity_type, entity_id)
