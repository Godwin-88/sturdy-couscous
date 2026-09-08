"""Attestcoin evidence adapter (E1).

Calls the real Attestcoin Protocol SDK wrapper (attestation-service, a Node/TS
service using @gluwa/usc-sdk) to verify cross-chain transaction inclusion
proofs, then normalizes the result into the Evidence domain model and persists
it to Neo4j with full lineage (E1-US2 / E1-US3).

Verified and unverified evidence are never conflated (NFR-006).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx

from creditgraph.core.config import settings
from creditgraph.db.neo4j import get_driver
from creditgraph.models import AttestationStatus, Evidence

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _attestation_service_url() -> str:
    base = settings.attestation_service_url.rstrip("/")
    return f"{base}/verify"


async def verify_transaction(tx_hash: str, chain_key: int | None = None) -> Evidence:
    """Verify a cross-chain transaction via the Attestcoin SDK wrapper.

    Returns an Evidence object with status VERIFIED or UNVERIFIED. Never raises
    for a failed verification — it is recorded as unverified evidence.
    """
    evidence_id = f"ev_{uuid.uuid4().hex[:12]}"
    url = _attestation_service_url()
    payload: dict = {"txHash": tx_hash}
    if chain_key is not None:
        payload["chainKey"] = chain_key

    try:
        async with httpx.AsyncClient(timeout=settings.attestation_service_timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                # The service returns 4xx with a structured body for unverifiable txs.
                try:
                    data = resp.json()
                except Exception:
                    data = {"verified": False, "reason": "http_error", "error": resp.text}
            else:
                data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Attestation service unreachable: %s", exc)
        data = {"verified": False, "reason": "service_unreachable", "error": str(exc)}

    verified = bool(data.get("verified", False))
    status = AttestationStatus.VERIFIED if verified else AttestationStatus.UNVERIFIED

    evidence = Evidence(
        evidence_id=evidence_id,
        source_chain=data.get("sourceChain", "unknown"),
        tx_id=tx_hash,
        timestamp=utcnow(),
        attestation_id=f"att_{tx_hash[:10]}",
        status=status,
        verifier="attestcoin-usc-sdk" if verified else None,
        verified_at=utcnow() if verified else None,
        header_number=data.get("headerNumber"),
        chain_key=data.get("chainKey", chain_key),
        proof=data.get("proof", {}),
        reason=data.get("reason") or data.get("error"),
    )
    return evidence


async def persist_evidence(evidence: Evidence, borrower_id: str | None = None) -> None:
    """Persist an Evidence node (+ Attestation) into Neo4j with lineage.

    Graph (spec §25):
      (e:Evidence)-[:VERIFIED_BY]->(a:Attestation)
      (b:Borrower)-[:HAS_EVIDENCE]->(e)   (when borrower_id provided)
    """
    driver = get_driver()
    async with driver.session() as session:
        async with await session.begin_transaction() as tx:
            await tx.run(
                "MERGE (e:Evidence {evidence_id: $evidence_id}) "
                "SET e.source_chain = $source_chain, e.tx_id = $tx_id, "
                "    e.timestamp = $timestamp, e.status = $status, "
                "    e.verifier = $verifier, e.verified_at = $verified_at, "
                "    e.header_number = $header_number, e.chain_key = $chain_key, "
                "    e.reason = $reason "
                "MERGE (a:Attestation {attestation_id: $attestation_id}) "
                "SET a.tx_id = $tx_id, a.source_chain = $source_chain, "
                "    a.status = $status, a.verifier = $verifier, "
                "    a.verified_at = $verified_at "
                "MERGE (e)-[:VERIFIED_BY]->(a)",
                {
                    "evidence_id": evidence.evidence_id,
                    "source_chain": evidence.source_chain,
                    "tx_id": evidence.tx_id,
                    "timestamp": evidence.timestamp.isoformat(),
                    "status": evidence.status.value,
                    "verifier": evidence.verifier,
                    "verified_at": evidence.verified_at.isoformat() if evidence.verified_at else None,
                    "header_number": evidence.header_number,
                    "chain_key": evidence.chain_key,
                    "reason": evidence.reason,
                    "attestation_id": evidence.attestation_id,
                },
            )
            if borrower_id:
                await tx.run(
                    "MATCH (e:Evidence {evidence_id: $evidence_id}) "
                    "MERGE (b:Borrower {borrower_id: $borrower_id}) "
                    "MERGE (b)-[:HAS_EVIDENCE]->(e)",
                    {
                        "evidence_id": evidence.evidence_id,
                        "borrower_id": borrower_id,
                    },
                )
    logger.info(
        "Persisted evidence %s (%s) for tx %s",
        evidence.evidence_id,
        evidence.status.value,
        evidence.tx_id,
    )