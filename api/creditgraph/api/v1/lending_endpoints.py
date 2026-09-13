"""Lending-pool endpoints (H6-9 / DeFi track on the attested fund claim).

GET  /risk/lending/pool               -> pool snapshot (rates, LTV, borrowable)
GET  /risk/lending/liquidation-monitor-> LTV health + liquidation price
POST /risk/lending/deposit            -> lender deposits CTC
POST /risk/lending/withdraw           -> lender withdraws un-lent CTC
POST /risk/lending/borrow             -> fund borrows (requires approved decision)
POST /risk/lending/repay              -> fund repays principal

Discipline: borrow is ALWAYS gated by a human-approved CreditDecision (U6/U21).
The money leg forwards disbursement to execution-service when reachable; offline
it marks-to-model so the UI stays honest (paper-until-funded posture).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from creditgraph.services.lending_pool import (
    borrow as pool_borrow,
    deposit as pool_deposit,
    liquidation_monitor as pool_monitor,
    load_pool,
    public_pool_snapshot,
    repay as pool_repay,
    withdraw as pool_withdraw,
)

lending_router = APIRouter(prefix="/risk/lending", tags=["lending-pool"])


class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0, description="CTC amount to deposit")
    lender_id: str = Field("cc3_lender", description="Lending-party identifier")


class WithdrawRequest(BaseModel):
    amount: float = Field(..., gt=0, description="CTC amount to withdraw")
    lender_id: str = Field("cc3_lender", description="Lending-party identifier")


class BorrowRequest(BaseModel):
    amount: float = Field(..., gt=0, description="CTC amount to borrow against attested NAV")


class RepayRequest(BaseModel):
    amount: float = Field(..., gt=0, description="CTC principal to repay")


@lending_router.get("/pool", response_model=dict)
async def pool_snapshot() -> dict:
    """Full pool snapshot: utilization, rates, LTV, borrowable, event tail."""
    return public_pool_snapshot()


@lending_router.get("/liquidation-monitor", response_model=dict)
async def liquidation_status() -> dict:
    """Liquidation health: ltv, warning/liquidate thresholds, closing price."""
    return pool_monitor()


@lending_router.post("/deposit", response_model=dict)
async def deposit_endpoint(req: DepositRequest) -> dict:
    result = pool_deposit(req.amount, req.lender_id)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "deposit failed"))
    return result


@lending_router.post("/withdraw", response_model=dict)
async def withdraw_endpoint(req: WithdrawRequest) -> dict:
    result = pool_withdraw(req.amount, req.lender_id)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "withdraw failed"))
    return result


@lending_router.post("/borrow", response_model=dict)
async def borrow_endpoint(req: BorrowRequest) -> dict:
    result = pool_borrow(req.amount)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "borrow failed"))
    return result


@lending_router.post("/repay", response_model=dict)
async def repay_endpoint(req: RepayRequest) -> dict:
    result = pool_repay(req.amount)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "repay failed"))
    return result