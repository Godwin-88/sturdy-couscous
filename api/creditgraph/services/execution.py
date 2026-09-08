"""Creditcoin execution adapter (E10).

Translates an *approved* CreditDecision into an executable CTC transfer on
Creditcoin via the real Polkadot.js-backed execution service, then persists the
`CreditDecision ─EXECUTED_AS→ Transaction` lineage (spec §25) and flips the
decision status to `executed`.

Safety (spec §18): NO economically material transaction is executed solely
because an LLM generated a recommendation. This adapter refuses to submit
unless the decision has been explicitly human-approved (`approval_status ==
"approved"`). Verified submission results are recorded faithfully from the
execution service; failures are never conflated with success.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx

from creditgraph.core.config import settings
from creditgraph.db.neo4j import get_driver
from creditgraph.models import CreditDecision, CreditExecution, ExecutionStatus

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _execution_service_url() -> str:
    return settings.execution_service_url.rstrip("/")


async def execute_credit_decision(
    decision: CreditDecision,
    to: str,
    amount: float | None = None,
    amount_planck: str | None = None,
) -> CreditExecution:
    """Submit an approved CreditDecision as a Creditcoin transfer.

    Raises ``RuntimeError`` if the decision is not human-approved (safety,
    E10-US1). Returns a CreditExecution with status finalized/in_block/pending,
    or failed if the node reports a dispatch error.
    """
    if decision.approval_status != "approved":
        raise RuntimeError(
            "CreditDecision must be explicitly approved by a human before execution "
            f"(decision {decision.decision_id} approval_status={decision.approval_status!r}). "
            "Approve the decision first (E10 safety requirement)."
        )

    execution_id = f"exec_{uuid.uuid4().hex[:12]}"
    pledged = amount if amount is not None else decision.recommended_amount
    url = f"{_execution_service_url()}/execute"

    try:
        async with httpx.AsyncClient(timeout=settings.execution_service_timeout) as client:
            resp = await client.post(
                url,
                json={
                    "to": to,
                    "amount": str(pledged),
                    "amountPlanck": amount_planck,
                },
            )
            if resp.status_code >= 400:
                try:
                    data = resp.json()
                except Exception:
                    data = {"error": "http_error", "detail": resp.text}
                return CreditExecution(
                    execution_id=execution_id,
                    decision_id=decision.decision_id,
                    borrower_id=decision.borrower_id,
                    to=to,
                    amount=pledged,
                    amount_planck=amount_planck,
                    status=ExecutionStatus.FAILED,
                    failure=data.get("error") or data.get("detail"),
                    confirmed_at=utcnow(),
                )
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Execution service unreachable: %s", exc)
        return CreditExecution(
            execution_id=execution_id,
            decision_id=decision.decision_id,
            borrower_id=decision.borrower_id,
            to=to,
            amount=pledged,
            amount_planck=amount_planck,
            status=ExecutionStatus.TIMEOUT,
            failure="execution_service_unreachable",
            confirmed_at=utcnow(),
        )

    return _normalize_execution(data, execution_id, decision, to, pledged, amount_planck)


def _normalize_execution(
    data: dict,
    execution_id: str,
    decision: CreditDecision,
    to: str,
    amount: float,
    amount_planck: str | None,
) -> CreditExecution:
    """Normalize the execution-service payload into a domain CreditExecution."""
    raw_status = (data.get("status") or "pending").lower()
    if data.get("error"):
        status = ExecutionStatus.FAILED
        failure = data.get("error")
    elif raw_status == "finalized":
        if data.get("success") is False:
            status = ExecutionStatus.FAILED
            failure = data.get("dispatchError")
        else:
            status = ExecutionStatus.FINALIZED
            failure = None
    elif raw_status == "in_block":
        if data.get("success") is False:
            status = ExecutionStatus.FAILED
            failure = data.get("dispatchError")
        else:
            status = ExecutionStatus.IN_BLOCK
            failure = None
    elif raw_status == "pending":
        status = ExecutionStatus.PENDING
        failure = data.get("reason")
    else:
        status = ExecutionStatus.PENDING
        failure = None

    if status == ExecutionStatus.FAILED and failure is None:
        failure = data.get("detail") or data.get("error") or "execution_failed"

    return CreditExecution(
        execution_id=execution_id,
        decision_id=decision.decision_id,
        borrower_id=decision.borrower_id,
        to=to,
        amount=amount,
        amount_planck=amount_planck,
        status=status,
        tx_hash=data.get("txHash"),
        block=data.get("block"),
        block_hash=data.get("blockHash"),
        extrinsic_index=data.get("extrinsicIndex"),
        failure=failure,
        source="creditcoin",
        confirmed_at=utcnow() if status in (ExecutionStatus.FINALIZED, ExecutionStatus.FAILED) else None,
    )


async def approve_credit_decision(decision_id: str) -> bool:
    """Mark a CreditDecision as human-approved (E10-US1 safety gate).

    Returns False if the decision does not exist. This is the ONLY way a
    decision becomes executable; execution is refused for any other state.
    """
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            "MATCH (d:CreditDecision {decision_id: $decision_id}) "
            "SET d.approval_status = 'approved', d.decision_status = 'approved' "
            "RETURN d",
            {"decision_id": decision_id},
        )
        rec = await result.single()
    if rec is None:
        logger.warning("Approve failed: decision %s not found", decision_id)
        return False
    logger.info("Approved decision %s for execution", decision_id)
    return True


async def persist_execution(execution: CreditExecution) -> None:
    """Persist a CreditExecution node and link it to its CreditDecision.

    Graph (spec §25): (d:CreditDecision)-[:EXECUTED_AS]->(x:CreditExecution).
    Also flips the decision's status to 'executed' once finalized.
    """
    driver = get_driver()
    async with driver.session() as session:
        async with await session.begin_transaction() as tx:
            await tx.run(
                "MATCH (d:CreditDecision {decision_id: $decision_id}) "
                "MERGE (x:CreditExecution {execution_id: $execution_id}) "
                "SET x.borrower_id = $borrower_id, x.to = $to, "
                "    x.amount = $amount, x.amount_planck = $amount_planck, "
                "    x.status = $status, x.tx_hash = $tx_hash, x.block = $block, "
                "    x.block_hash = $block_hash, x.extrinsic_index = $extrinsic_index, "
                "    x.failure = $failure, x.source = $source, "
                "    x.created_at = $created_at, x.confirmed_at = $confirmed_at "
                "MERGE (d)-[:EXECUTED_AS]->(x)",
                {
                    "decision_id": execution.decision_id,
                    "execution_id": execution.execution_id,
                    "borrower_id": execution.borrower_id,
                    "to": execution.to,
                    "amount": execution.amount,
                    "amount_planck": execution.amount_planck,
                    "status": execution.status.value,
                    "tx_hash": execution.tx_hash,
                    "block": execution.block,
                    "block_hash": execution.block_hash,
                    "extrinsic_index": execution.extrinsic_index,
                    "failure": execution.failure,
                    "source": execution.source,
                    "created_at": execution.created_at.isoformat(),
                    "confirmed_at": execution.confirmed_at.isoformat() if execution.confirmed_at else None,
                },
            )
            if execution.status == ExecutionStatus.FINALIZED:
                await tx.run(
                    "MATCH (d:CreditDecision {decision_id: $decision_id}) "
                    "SET d.decision_status = 'executed', d.execution_transaction = $tx_hash",
                    {
                        "decision_id": execution.decision_id,
                        "tx_hash": execution.tx_hash,
                    },
                )
    logger.info(
        "Persisted execution %s (%s) for decision %s",
        execution.execution_id,
        execution.status.value,
        execution.decision_id,
    )