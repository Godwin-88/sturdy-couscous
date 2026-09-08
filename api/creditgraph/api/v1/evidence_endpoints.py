"""Attestcoin evidence endpoints (E1).

POST /risk/evidence/verify  -> verify a cross-chain transaction via the real
                               Attestcoin SDK wrapper and persist Evidence +
                               Attestation lineage to Neo4j.
GET  /risk/evidence         -> list evidence, optionally filtered by borrower_id
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from creditgraph.db.neo4j import get_driver
from creditgraph.models import Evidence
from creditgraph.services.evidence import persist_evidence, verify_transaction

evidence_router = APIRouter(prefix="/risk/evidence", tags=["evidence"])


class VerifyEvidenceRequest(BaseModel):
    tx_hash: str = Field(..., min_length=1, description="Source-chain transaction hash")
    chain_key: int | None = Field(None, description="Creditcoin-internal source chain key")
    borrower_id: str | None = Field(None, description="Optional borrower to link evidence to")


@evidence_router.post("/verify", response_model=Evidence)
async def verify_evidence(req: VerifyEvidenceRequest) -> Evidence:
    """Verify a cross-chain transaction and persist the evidence lineage."""
    evidence = await verify_transaction(req.tx_hash, chain_key=req.chain_key)
    try:
        await persist_evidence(evidence, borrower_id=req.borrower_id)
    except Exception as exc:  # pragma: no cover - DB unavailable
        raise HTTPException(status_code=503, detail=f"Failed to persist evidence: {exc}")
    return evidence


@evidence_router.get("", response_model=list[Evidence])
async def list_evidence(borrower_id: str | None = Query(None, description="Filter by borrower")) -> list[Evidence]:
    """List evidence nodes, optionally filtered by borrower linkage."""
    driver = get_driver()
    if borrower_id:
        cypher = (
            "MATCH (b:Borrower {borrower_id: $borrower_id})-[:HAS_EVIDENCE]->(e:Evidence) "
            "RETURN e ORDER BY e.timestamp DESC"
        )
    else:
        cypher = "MATCH (e:Evidence) RETURN e ORDER BY e.timestamp DESC"

    results: list[Evidence] = []
    async with driver.session() as session:
        async with await session.begin_transaction() as tx:
            cursor = await tx.run(cypher, {"borrower_id": borrower_id})
            async for record in cursor:
                node = record["e"]
                status_val = node.get("status", "unverified")
                try:
                    status = Evidence.model_fields["status"].annotation(status_val)  # type: ignore[arg-type]
                except (ValueError, TypeError):
                    status = "unverified"
                results.append(
                    Evidence(
                        evidence_id=node["evidence_id"],
                        source_chain=node.get("source_chain", "unknown"),
                        tx_id=node.get("tx_id", ""),
                        timestamp=node.get("timestamp", ""),
                        attestation_id=node.get("attestation_id", ""),
                        status=status,
                        verifier=node.get("verifier"),
                        verified_at=node.get("verified_at"),
                        header_number=node.get("header_number"),
                        chain_key=node.get("chain_key"),
                        proof=node.get("proof", {}),
                        reason=node.get("reason"),
                    )
                )
    return results