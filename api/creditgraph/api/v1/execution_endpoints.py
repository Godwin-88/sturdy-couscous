"""Creditcoin execution endpoints (E10).

POST /risk/execution/approve   -> human-approve a CreditDecision (safety gate)
POST /risk/execution/execute   -> submit the approved decision as CTC transfer
POST /risk/execution/monitor   -> monitor an on-chain transfer to finalization
GET  /risk/execution/account   -> executor account info (testnet/demo only)
GET  /risk/execution/balance   -> account balance (testnet/demo only)

Per spec §18 safety, execution NEVER happens because an LLM produced a
recommendation; the decision must be explicitly human-approved first.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from creditgraph.graph.credit_graph import get_credit_decision
from creditgraph.models import CreditExecution, ExecuteCreditRequest
from creditgraph.services.execution import (
    approve_credit_decision,
    execute_credit_decision,
    persist_execution,
)

execution_router = APIRouter(prefix="/risk/execution", tags=["execution"])


class ApproveRequest(BaseModel):
    decision_id: str = Field(..., description="CreditDecision to approve")


class MonitorRequest(BaseModel):
    tx_hash: str = Field(..., description="Creditcoin extrinsic hash to monitor")


@execution_router.post("/approve", response_model=dict)
async def approve_decision(req: ApproveRequest) -> dict:
    """Explicitly human-approve a CreditDecision before it can be executed."""
    ok = await approve_credit_decision(req.decision_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Decision {req.decision_id} not found")
    return {"decision_id": req.decision_id, "status": "approved"}


@execution_router.post("/execute", response_model=CreditExecution)
async def execute_decision(req: ExecuteCreditRequest) -> CreditExecution:
    """Execute an approved CreditDecision as a Creditcoin transfer."""
    decision = await get_credit_decision(req.decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail=f"Decision {req.decision_id} not found")

    try:
        execution = await execute_credit_decision(
            decision,
            to=req.to,
            amount=req.amount,
            amount_planck=req.amount_planck,
        )
    except RuntimeError as exc:
        # Safety gate: not human-approved.
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:  # pragma: no cover - unexpected
        raise HTTPException(status_code=500, detail=f"Execution failed: {exc}")

    try:
        await persist_execution(execution)
    except Exception as exc:  # pragma: no cover - DB unavailable
        raise HTTPException(status_code=503, detail=f"Failed to persist execution: {exc}")
    return execution


@execution_router.post("/monitor", response_model=dict)
async def monitor_execution(req: MonitorRequest) -> dict:
    """Poll the execution service for an on-chain transfer's final status."""
    import httpx

    from creditgraph.core.config import settings

    url = f"{settings.execution_service_url.rstrip('/')}/monitor"
    try:
        async with httpx.AsyncClient(timeout=settings.execution_service_timeout) as client:
            resp = await client.post(url, json={"txHash": req.tx_hash})
            data = resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Execution service unreachable: {exc}")
    return data


@execution_router.get("/account", response_model=dict)
async def get_execution_account() -> dict:
    """Return the configured executor account info from the execution service."""
    import httpx

    from creditgraph.core.config import settings

    url = f"{settings.execution_service_url.rstrip('/')}/account"
    try:
        async with httpx.AsyncClient(timeout=settings.execution_service_timeout) as client:
            resp = await client.get(url)
            return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Execution service unreachable: {exc}")


@execution_router.get("/balance", response_model=dict)
async def get_execution_balance(address: str = Query(..., description="Substrate SS58 or EVM address")) -> dict:
    """Return the planck balance for an address via the execution service."""
    import httpx

    from creditgraph.core.config import settings

    url = f"{settings.execution_service_url.rstrip('/')}/balance"
    try:
        async with httpx.AsyncClient(timeout=settings.execution_service_timeout) as client:
            resp = await client.get(url, params={"address": address})
            return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Execution service unreachable: {exc}")