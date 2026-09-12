"""CreditGraph domain graph repository — Neo4j (spec §25).

Provides:
  - get_borrower_state: read a borrower's aggregated graph state
  - persist_credit_decision: write CreditDecision + RiskAssessment + RiskObservation
    nodes with full lineage (BASED_ON / DERIVED_FROM / SUPPORTED_BY / OCCURS_IN)
  - seed_demo_borrower: idempotent demo borrower graph (MVP data)

All queries are parameterized; identities are stable.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

AsyncDriver = Any  # neo4j 4.x has no async driver class; the db facade provides it

from creditgraph.db.neo4j import get_driver
from creditgraph.models import (
    Asset,
    AttestationStatus,
    Collateral,
    CreditAssessment,
    CreditDecision,
    DecisionStatus,
    CurrentBorrowerState,
    Exposure,
    Liability,
    RiskRegime,
    utcnow,
    Wallet,
)

logger = logging.getLogger(__name__)


def _parse_dt(value) -> datetime | None:
    """Parse an ISO timestamp stored in Neo4j back into a datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_regime(value) -> RiskRegime:
    """Resolve a stored regime label/value into a RiskRegime enum."""
    if value is None:
        return RiskRegime.HIGH_VOLATILITY
    for candidate in RiskRegime:
        if candidate.value == value or candidate.name == value:
            return candidate
    return RiskRegime.HIGH_VOLATILITY

# Model provenance labels come from the deterministic engine
_MODEL_IDS = {
    "m_credit_score",
    "m_probability_default",
    "m_expected_loss",
    "m_ltv",
    "m_collateral_ratio",
    "m_stress",
    "m_recommended_exposure",
}

REGIME_LABEL = {
    RiskRegime.NEUTRAL: "Neutral",
    RiskRegime.TRENDING: "Trending",
    RiskRegime.MEAN_REVERTING: "MeanReverting",
    RiskRegime.LOW_VOLATILITY: "LowVolatility",
    RiskRegime.RECOVERY: "Recovery",
    RiskRegime.HIGH_VOLATILITY: "HighVolatility",
    RiskRegime.CRISIS: "Crisis",
    RiskRegime.SYSTEMIC_STRESS: "SystemicStress",
}


# ---------------------------------------------------------------------------
# Read: borrower state
# ---------------------------------------------------------------------------


async def get_borrower_state(borrower_id: str) -> CurrentBorrowerState | None:
    """Aggregate a borrower's graph state from Neo4j.

    Returns None when the borrower node does not exist.
    """
    driver: AsyncDriver = get_driver()
    query = (
        "MATCH (b:Borrower {borrower_id: $borrower_id}) "
        "OPTIONAL MATCH (b)-[:OWNS]->(w:Wallet) "
        "OPTIONAL MATCH (w)-[:HOLDS]->(a:Asset) "
        "OPTIONAL MATCH (b)-[:HAS_COLLATERAL]->(col:Collateral)-[:REFERENCES]->(casset:Asset) "
        "OPTIONAL MATCH (b)-[:HAS_LIABILITY]->(liab:Liability) "
        "OPTIONAL MATCH (b)-[:HAS_EXPOSURE]->(exp:Exposure) "
        "RETURN b, collect(DISTINCT w) AS wallets, collect(DISTINCT a) AS assets, "
        "collect(DISTINCT col) AS collateral, collect(DISTINCT liab) AS liabilities, "
        "collect(DISTINCT exp) AS exposures"
    )
    async with driver.session() as sess:
        result = await sess.run(query, {"borrower_id": borrower_id})
        rec = await result.single()
    if not rec or rec["b"] is None:
        return None

    node = rec["b"]
    borrower_id = node["borrower_id"]
    requested = float(node.get("requested_amount", 0.0))
    fico = float(node.get("fico_score", 680.0))

    assets: list[Asset] = [
        Asset(
            asset_id=a["asset_id"],
            symbol=a.get("symbol", ""),
            chain=a.get("chain", ""),
            price_usd=float(a.get("price_usd", 0.0)),
            volatility_annualized=float(a.get("volatility_annualized", 0.0)),
            quantity=float(a.get("quantity", 0.0)),
        )
        for a in rec["assets"]
        if a is not None
    ]

    collateral: list[Collateral] = []
    for c in rec["collateral"]:
        if c is None:
            continue
        collateral.append(
            Collateral(
                asset_id=c.get("asset_id", ""),
                symbol=c.get("symbol", ""),
                valuation=float(c.get("valuation", 0.0)),
                quantity=float(c.get("quantity", 0.0)),
                haircut=float(c.get("haircut", 0.0)),
                correlated_group=c.get("correlated_group", "none"),
            )
        )

    liabilities: list[Liability] = [
        Liability(
            protocol=l.get("protocol", ""),
            outstanding=float(l.get("outstanding", 0.0)),
            asset_symbol=l.get("asset_symbol", ""),
        )
        for l in rec["liabilities"]
        if l is not None
    ]

    exposures: list[Exposure] = [
        Exposure(
            protocol=e.get("protocol", ""),
            asset=e.get("asset", ""),
            exposure_amount=float(e.get("exposure_amount", 0.0)),
        )
        for e in rec["exposures"]
        if e is not None
    ]

    # Regime from linked MarketRegime node (or HIGH_VOLATILITY fallback)
    regime = RiskRegime.HIGH_VOLATILITY
    regime_name = node.get("market_regime")
    if regime_name:
        for candidate in RiskRegime:
            if candidate.value == regime_name:
                regime = candidate
                break

    total_collateral = sum(c.valuation for c in collateral)
    total_liabilities = sum(l.outstanding for l in liabilities)
    attest_refs = list(node.get("attestation_refs", []) or [])
    if isinstance(node.get("attestation_refs"), str):
        attest_refs = [node["attestation_refs"]]

    return CurrentBorrowerState(
        borrower_id=borrower_id,
        requested_amount=requested,
        fico_score=fico,
        total_collateral_value=total_collateral,
        total_liabilities=total_liabilities,
        assets=assets,
        collateral=collateral,
        liabilities=liabilities,
        exposures=exposures,
        market_regime=regime,
        attestation_refs=attest_refs,
    )


# ---------------------------------------------------------------------------
# Read: credit decision
# ---------------------------------------------------------------------------

async def get_credit_decision(decision_id: str) -> CreditDecision | None:
    """Read a persisted CreditDecision node from Neo4j.

    Returns None when the decision does not exist. Used by the execution
    adapter (E10) to verify human-approved status before submitting.
    """
    driver: AsyncDriver = get_driver()
    async with driver.session() as sess:
        result = await sess.run(
            "MATCH (d:CreditDecision {decision_id: $decision_id}) RETURN d",
            {"decision_id": decision_id},
        )
        rec = await result.single()
    if not rec or rec["d"] is None:
        return None
    node = rec["d"]
    created_at = _parse_dt(node.get("created_at")) or utcnow()
    expires_at = _parse_dt(node.get("expires_at"))
    return CreditDecision(
        decision_id=node["decision_id"],
        borrower_id=node.get("borrower_id", ""),
        requested_amount=float(node.get("requested_amount", 0.0)),
        recommended_amount=float(node.get("recommended_amount", 0.0)),
        collateral_value=float(node.get("collateral_value", 0.0)),
        required_collateral_ratio=float(node.get("required_collateral_ratio", 0.0)),
        credit_score=float(node.get("credit_score", 0.0)),
        probability_of_default=float(node.get("probability_of_default", 0.0)),
        expected_loss=float(node.get("expected_loss", 0.0)),
        risk_regime=_parse_regime(node.get("risk_regime")),
        stress_result=float(node.get("stress_ltv", 0.0)),
        principal_risk_factors=list(node.get("principal_risk_factors", []) or []),
        supporting_evidence=list(node.get("supporting_evidence", []) or []),
        attestation_references=list(node.get("attestation_references", []) or []),
        model_versions=list(node.get("model_versions", []) or []),
        created_at=created_at,
        expires_at=expires_at,
        decision_status=DecisionStatus(
            node.get("decision_status", DecisionStatus.RECOMMENDED.value)
        ),
        approval_status=node.get("approval_status", "pending"),
        execution_transaction=node.get("execution_transaction"),
    )


# ---------------------------------------------------------------------------
# Write: persist decision + lineage
# ---------------------------------------------------------------------------


async def persist_credit_decision(
    decision: CreditDecision,
    assessment: CreditAssessment,
    model_results: dict[str, dict],
) -> None:
    """Persist the decision, assessment and model provenance into Neo4j.

    Graph:
      (b:Borrower)-[:HAS_DECISION]->(d:CreditDecision)
      (d)-[:BASED_ON]->(r:RiskObservation)
      (r)-[:DERIVED_FROM]->(:RiskModel)
      (r)-[:OCCURS_IN]->(:MarketRegime)
      (d)-[:SUPPORTED_BY]->(:Evidence)        (attestation-backed evidence)

    All are idempotent MERGE operations; lineage is stable per decision_id.
    """
    driver: AsyncDriver = get_driver()
    regime_label = REGIME_LABEL.get(assessment.market_regime, "Neutral")
    regime_value = assessment.market_regime.value
    expires_at = decision.expires_at.isoformat() if decision.expires_at else None

    merge_model = (
        "MERGE (rm:RiskModel {model_id: $model_id, version: $version}) "
        "SET rm.name = $name"
    )
    merge_regime = "MERGE (mreg:MarketRegime {name: $regime})"
    merge_obs = (
        "MERGE (r:RiskObservation {observation_id: $obs_id}) "
        "SET r.model_id = $model_id, r.model_name = $model_name, "
        "    r.model_version = $model_version, r.parameters = $parameters, "
        "    r.inputs = $inputs, r.outputs = $outputs, r.observed_at = $observed_at"
    )

    async with driver.session() as session:
        async with await session.begin_transaction() as tx:
            # Merge the borrower (idempotent)
            await tx.run(
                "MERGE (b:Borrower {borrower_id: $borrower_id}) "
                "SET b.requested_amount = $requested, b.market_regime = $regime",
                {
                    "borrower_id": decision.borrower_id,
                    "requested": decision.requested_amount,
                    "regime": regime_value,
                },
            )
            # Merge the decision node and link to borrower
            await tx.run(
                "MATCH (b:Borrower {borrower_id: $borrower_id}) "
                "MERGE (d:CreditDecision {decision_id: $decision_id}) "
                "SET d.borrower_id = $borrower_id, "
                "    d.requested_amount = $requested_amount, "
                "    d.recommended_amount = $recommended_amount, "
                "    d.collateral_value = $collateral_value, "
                "    d.credit_score = $credit_score, "
                "    d.probability_of_default = $pd, "
                "    d.expected_loss = $el, "
                "    d.required_collateral_ratio = $req_ratio, "
                "    d.stress_ltv = $stress_ltv, "
                "    d.risk_regime = $regime, "
                "    d.supporting_evidence = $supporting_evidence, "
                "    d.attestation_references = $attestation_references, "
                "    d.model_versions = $model_versions, "
                "    d.expires_at = $expires_at, "
                "    d.decision_status = $status, "
                "    d.approval_status = $approval_status, "
                "    d.execution_transaction = $execution_transaction, "
                "    d.created_at = $created_at, "
                "    d.principal_risk_factors = $factors "
                "MERGE (b)-[:HAS_DECISION]->(d)",
                {
                    "borrower_id": decision.borrower_id,
                    "decision_id": decision.decision_id,
                    "requested_amount": decision.requested_amount,
                    "recommended_amount": decision.recommended_amount,
                    "collateral_value": decision.collateral_value,
                    "credit_score": decision.credit_score,
                    "pd": decision.probability_of_default,
                    "el": decision.expected_loss,
                    "req_ratio": decision.required_collateral_ratio,
                    "stress_ltv": decision.stress_result,
                    "regime": regime_value,
                    "supporting_evidence": decision.supporting_evidence,
                    "attestation_references": decision.attestation_references,
                    "model_versions": decision.model_versions,
                    "expires_at": expires_at,
                    "status": decision.decision_status.value,
                    "approval_status": decision.approval_status,
                    "execution_transaction": decision.execution_transaction,
                    "created_at": decision.created_at.isoformat(),
                    "factors": decision.principal_risk_factors,
                },
            )

            # Merge the risk model + regime for each model result
            for model_id, result in model_results.items():
                await tx.run(
                    merge_model,
                    {
                        "model_id": result["model_id"],
                        "version": result["model_version"],
                        "name": result["model_name"],
                    },
                )
            await tx.run(merge_regime, {"regime": regime_label})

            # Persist a RiskObservation per model result with full provenance
            for model_id, result in model_results.items():
                obs_id = f"{decision.decision_id}:{result['model_id']}"
                await tx.run(
                    "MATCH (d:CreditDecision {decision_id: $decision_id}) "
                    "MERGE (r:RiskObservation {observation_id: $obs_id}) "
                    "SET r.model_id = $model_id, r.model_name = $model_name, "
                    "    r.model_version = $model_version, "
                    "    r.parameters = $parameters, "
                    "    r.inputs = $inputs, "
                    "    r.outputs = $outputs, "
                    "    r.observed_at = $observed_at "
                    "MERGE (d)-[:BASED_ON]->(r) "
                    "WITH r "
                    "MATCH (rm:RiskModel {model_id: $model_id, version: $model_version}) "
                    "MERGE (r)-[:DERIVED_FROM]->(rm) "
                    "WITH r "
                    "MATCH (mreg:MarketRegime {name: $regime}) "
                    "MERGE (r)-[:OCCURS_IN]->(mreg)",
                    {
                        "decision_id": decision.decision_id,
                        "obs_id": obs_id,
                        "model_id": result["model_id"],
                        "model_name": result["model_name"],
                        "model_version": result["model_version"],
                        "parameters": json.dumps(result.get("parameters", {})),
                        "inputs": json.dumps(result.get("inputs", {})),
                        "outputs": json.dumps(result.get("outputs", {})),
                        "observed_at": result.get("timestamp"),
                        "regime": regime_label,
                    },
                )

            # Link the decision to attestation-backed evidence where it exists
            for att_ref in decision.attestation_references or []:
                await tx.run(
                    "MATCH (d:CreditDecision {decision_id: $decision_id}) "
                    "OPTIONAL MATCH (e:Evidence {attestation_id: $attestation_id}) "
                    "FOREACH (x IN CASE WHEN e IS NOT NULL THEN [1] ELSE [] END | "
                    "  MERGE (d)-[:SUPPORTED_BY]->(e))",
                    {
                        "decision_id": decision.decision_id,
                        "attestation_id": att_ref,
                    },
                )

    logger.info(
        "Persisted decision %s for borrower %s",
        decision.decision_id,
        decision.borrower_id,
    )


async def list_borrowers() -> list[str]:
    """Return all borrower IDs in the graph."""
    driver: AsyncDriver = get_driver()
    async with driver.session() as sess:
        result = await sess.run("MATCH (b:Borrower) RETURN b.borrower_id AS borrower_id ORDER BY borrower_id")
        return [row["borrower_id"] async for row in result]


async def list_credit_decisions(borrower_id: str | None = None) -> list[CreditDecision]:
    """Return persisted CreditDecision nodes, optionally filtered by borrower."""
    driver: AsyncDriver = get_driver()
    if borrower_id:
        cypher = (
            "MATCH (b:Borrower {borrower_id: $borrower_id})-[:HAS_DECISION]->"
            "(d:CreditDecision) RETURN d ORDER BY d.created_at DESC"
        )
    else:
        cypher = "MATCH (d:CreditDecision) RETURN d ORDER BY d.created_at DESC"
    decisions: list[CreditDecision] = []
    async with driver.session() as sess:
        result = await sess.run(cypher, {"borrower_id": borrower_id})
        async for rec in result:
            node = rec["d"]
            if node is None:
                continue
            created_at = _parse_dt(node.get("created_at")) or utcnow()
            expires_at = _parse_dt(node.get("expires_at"))
            decisions.append(
                CreditDecision(
                    decision_id=node["decision_id"],
                    borrower_id=node.get("borrower_id", ""),
                    requested_amount=float(node.get("requested_amount", 0.0)),
                    recommended_amount=float(node.get("recommended_amount", 0.0)),
                    collateral_value=float(node.get("collateral_value", 0.0)),
                    required_collateral_ratio=float(node.get("required_collateral_ratio", 0.0)),
                    credit_score=float(node.get("credit_score", 0.0)),
                    probability_of_default=float(node.get("probability_of_default", 0.0)),
                    expected_loss=float(node.get("expected_loss", 0.0)),
                    risk_regime=_parse_regime(node.get("risk_regime")),
                    stress_result=float(node.get("stress_ltv", 0.0)),
                    principal_risk_factors=list(node.get("principal_risk_factors", []) or []),
                    supporting_evidence=list(node.get("supporting_evidence", []) or []),
                    attestation_references=list(node.get("attestation_references", []) or []),
                    model_versions=list(node.get("model_versions", []) or []),
                    created_at=created_at,
                    expires_at=expires_at,
                    decision_status=DecisionStatus(
                        node.get("decision_status", DecisionStatus.RECOMMENDED.value)
                    ),
                    approval_status=node.get("approval_status", "pending"),
                    execution_transaction=node.get("execution_transaction"),
                )
            )
    return decisions


async def override_credit_decision(
    decision_id: str, reason: str, overridden_by: str
) -> CreditDecision | None:
    """Override a decision with a documented reason (E8-US2).

    The original decision node is preserved (its risk outputs and lineage are
    left intact) and re-labelled with an OVERRIDDEN status. The prior status is
    retained in ``original_decision_status`` and an audit ``Override`` node is
    created capturing the reason, actor and timestamp. Returns the overridden
    CreditDecision, or None when the decision does not exist.
    """
    driver: AsyncDriver = get_driver()
    override_id = f"ovr_{uuid.uuid4().hex[:12]}"
    overridden_at = utcnow().isoformat()
    async with driver.session() as session:
        async with await session.begin_transaction() as tx:
            res = await tx.run(
                "MATCH (d:CreditDecision {decision_id: $decision_id}) RETURN d",
                {"decision_id": decision_id},
            )
            rec = await res.single()
            if not rec or rec["d"] is None:
                return None
            original_status = rec["d"].get(
                "decision_status", DecisionStatus.RECOMMENDED.value
            )
            await tx.run(
                "MATCH (d:CreditDecision {decision_id: $decision_id}) "
                "SET d.decision_status = $status, "
                "    d.original_decision_status = $original_status, "
                "    d.override_reason = $reason, "
                "    d.overridden_by = $overridden_by, "
                "    d.overridden_at = $overridden_at "
                "WITH d "
                "MERGE (o:Override {override_id: $override_id}) "
                "SET o.decision_id = $decision_id, o.reason = $reason, "
                "    o.overridden_by = $overridden_by, "
                "    o.original_status = $original_status, "
                "    o.created_at = $overridden_at "
                "MERGE (d)-[:HAS_OVERRIDE]->(o)",
                {
                    "decision_id": decision_id,
                    "status": DecisionStatus.OVERRIDDEN.value,
                    "original_status": original_status,
                    "reason": reason,
                    "overridden_by": overridden_by,
                    "overridden_at": overridden_at,
                    "override_id": override_id,
                },
            )
    logger.info("Overrode decision %s by %s", decision_id, overridden_by)
    return await get_credit_decision(decision_id)


async def reconstruct_decision(decision_id: str) -> dict:
    """Reconstruct a historical decision with full lineage (E9-US2).

    Returns a dict containing the decision, its input entities (borrower graph
    state), evidence references, attestation references, graph context, model
    versions, model parameters, risk outputs and the originating timestamp. When
    the decision does not exist, ``found`` is False and only the decision_id is
    returned.
    """
    driver: AsyncDriver = get_driver()
    async with driver.session() as session:
        res = await session.run(
            "MATCH (d:CreditDecision {decision_id: $decision_id}) RETURN d",
            {"decision_id": decision_id},
        )
        rec = await res.single()
        if not rec or rec["d"] is None:
            return {"decision_id": decision_id, "found": False}

        node = rec["d"]
        borrower_id = node.get("borrower_id", "")
        created_at = _parse_dt(node.get("created_at"))
        decision = {
            "decision_id": node["decision_id"],
            "borrower_id": borrower_id,
            "requested_amount": float(node.get("requested_amount", 0.0)),
            "recommended_amount": float(node.get("recommended_amount", 0.0)),
            "collateral_value": float(node.get("collateral_value", 0.0)),
            "required_collateral_ratio": float(node.get("required_collateral_ratio", 0.0)),
            "credit_score": float(node.get("credit_score", 0.0)),
            "probability_of_default": float(node.get("probability_of_default", 0.0)),
            "expected_loss": float(node.get("expected_loss", 0.0)),
            "risk_regime": node.get("risk_regime"),
            "stress_result": float(node.get("stress_ltv", 0.0)),
            "principal_risk_factors": list(node.get("principal_risk_factors", []) or []),
            "supporting_evidence": list(node.get("supporting_evidence", []) or []),
            "attestation_references": list(node.get("attestation_references", []) or []),
            "model_versions": list(node.get("model_versions", []) or []),
            "created_at": created_at.isoformat() if created_at else None,
            "expires_at": (_parse_dt(node.get("expires_at")).isoformat()
                           if _parse_dt(node.get("expires_at")) else None),
            "decision_status": node.get("decision_status"),
            "approval_status": node.get("approval_status", "pending"),
            "execution_transaction": node.get("execution_transaction"),
            "override_reason": node.get("override_reason"),
            "overridden_by": node.get("overridden_by"),
            "original_decision_status": node.get("original_decision_status"),
            "overridden_at": node.get("overridden_at"),
        }

        # Input entities: the borrower graph state at decision time.
        state = await get_borrower_state(borrower_id)
        input_entities = state.model_dump() if state is not None else {}

        # Model provenance: parameters / inputs / outputs per risk observation.
        models: list[dict] = []
        obs_res = await session.run(
            "MATCH (d:CreditDecision {decision_id: $decision_id})-[:BASED_ON]->"
            "(r:RiskObservation)-[:DERIVED_FROM]->(rm:RiskModel) "
            "RETURN r, rm",
            {"decision_id": decision_id},
        )
        async for orec in obs_res:
            r = orec["r"]
            rm = orec["rm"]
            raw_params = r.get("parameters") or "{}"
            raw_inputs = r.get("inputs") or "{}"
            raw_outputs = r.get("outputs") or "{}"
            try:
                params = json.loads(raw_params) if isinstance(raw_params, str) else raw_params
            except (json.JSONDecodeError, TypeError):
                params = {}
            try:
                inputs = json.loads(raw_inputs) if isinstance(raw_inputs, str) else raw_inputs
            except (json.JSONDecodeError, TypeError):
                inputs = {}
            try:
                outputs = json.loads(raw_outputs) if isinstance(raw_outputs, str) else raw_outputs
            except (json.JSONDecodeError, TypeError):
                outputs = {}
            models.append(
                {
                    "model_id": r.get("model_id") or rm.get("model_id"),
                    "model_name": r.get("model_name"),
                    "model_version": r.get("model_version") or rm.get("version"),
                    "parameters": params,
                    "inputs": inputs,
                    "outputs": outputs,
                    "observed_at": r.get("observed_at"),
                }
            )

        # Evidence references backing the decision.
        ev_res = await session.run(
            "MATCH (d:CreditDecision {decision_id: $decision_id}) "
            "OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(e:Evidence) "
            "RETURN collect(DISTINCT e.evidence_id) AS evidence_ids, "
            "       collect(DISTINCT e.attestation_id) AS attestation_ids",
            {"decision_id": decision_id},
        )
        ev_rec = await ev_res.single()
        evidence_references = list(ev_rec["evidence_ids"] or []) if ev_rec else []

        # Graph context: regime, wallets, override audit trail.
        ctx_res = await session.run(
            "MATCH (d:CreditDecision {decision_id: $decision_id})<-[:HAS_DECISION]-(b:Borrower) "
            "OPTIONAL MATCH (d)-[:HAS_OVERRIDE]->(o:Override) "
            "RETURN b.market_regime AS regime, "
            "       [ (b)-[:OWNS]->(w:Wallet) | w.address ] AS wallet_addresses, "
            "       coalesce(o.reason, null) AS override_reason, "
            "       coalesce(o.overridden_by, null) AS overridden_by, "
            "       coalesce(o.original_status, null) AS original_status",
            {"decision_id": decision_id},
        )
        ctx = await ctx_res.single()
        graph_context = {
            "market_regime": ctx["regime"] if ctx else None,
            "wallet_addresses": list(ctx["wallet_addresses"] or []) if ctx else [],
            "override_reason": ctx.get("override_reason") if ctx else None,
            "overridden_by": ctx.get("overridden_by") if ctx else None,
            "original_status": ctx.get("original_status") if ctx else None,
        }

    attestation_references = list(decision["attestation_references"]) or list(
        input_entities.get("attestation_refs", [])
    )
    model_parameters = {m["model_id"]: m["parameters"] for m in models}
    risk_outputs = {
        "credit_score": decision["credit_score"],
        "probability_of_default": decision["probability_of_default"],
        "expected_loss": decision["expected_loss"],
        "stress_result": decision["stress_result"],
        "required_collateral_ratio": decision["required_collateral_ratio"],
        "recommended_amount": decision["recommended_amount"],
        "model_outputs": {m["model_id"]: m["outputs"] for m in models},
    }

    return {
        "decision_id": decision_id,
        "found": True,
        "timestamp": decision["created_at"],
        "decision": decision,
        "input_entities": input_entities,
        "evidence_references": evidence_references,
        "attestation_references": attestation_references,
        "graph_context": graph_context,
        "model_versions": models,
        "model_parameters": model_parameters,
        "risk_outputs": risk_outputs,
    }


# ---- Demo data ------------------------------------------------------------


async def seed_demo_borrower() -> str:
    """Idempotently create a demo borrower graph, return borrower_id."""
    borrower_id = "borrower_demo_alice"
    driver: AsyncDriver = get_driver()
    queries = [
        (
            """MERGE (b:Borrower {borrower_id: $bid})
               SET b.requested_amount = 100000.0,
                   b.fico_score = 645,
                   b.market_regime = 'high_volatility',
                   b.attestation_refs = [
                     'attest_eth_deposit_001',
                     'attest_usdc_loan_002'
                   ]
               MERGE (w1:Wallet {address: '0xabc...alice', chain: 'ethereum'})
               MERGE (b)-[:OWNS]->(w1)
               MERGE (w2:Wallet {address: '0xdef...alice', chain: 'polygon'})
               MERGE (b)-[:OWNS]->(w2)""",
            {"bid": borrower_id},
        ),
        (
            """MERGE (a1:Asset {asset_id: 'eth_on_ethereum', symbol: 'ETH', chain: 'ethereum'})
               SET a1.price_usd = 3500.0, a1.volatility_annualized = 0.6, a1.quantity = 20.0
               MERGE (a2:Asset {asset_id: 'usdc_on_polygon', symbol: 'USDC', chain: 'polygon'})
               SET a2.price_usd = 1.0, a2.volatility_annualized = 0.02, a2.quantity = 25000.0
               MERGE (c:Collateral {asset_id: 'eth_usdc_pool'})
               SET c.symbol = 'ETH+USDC', c.valuation = 95000.0, c.quantity = 1.0,
                   c.haircut = 0.15, c.correlated_group = 'eth_l2'
               WITH c
               MATCH (b:Borrower {borrower_id: $bid})
               MERGE (b)-[:HAS_COLLATERAL]->(c)
               WITH c, b
               MATCH (a1:Asset {asset_id: 'eth_on_ethereum'})
               MERGE (c)-[:REFERENCES]->(a1)""",
            {"bid": borrower_id},
        ),
        (
            """MATCH (b:Borrower {borrower_id: $bid})
               MERGE (l:Liability {protocol: 'Aave', asset_symbol: 'USDC'})
               SET l.outstanding = 12000.0
               MERGE (b)-[:HAS_LIABILITY]->(l)
               MERGE (e:Exposure {protocol: 'Aave', asset: 'USDC'})
               SET e.exposure_amount = 25000.0
               MERGE (b)-[:HAS_EXPOSURE]->(e)""",
            {"bid": borrower_id},
        ),
    ]
    async with driver.session() as session:
        async with await session.begin_transaction() as tx:
            for q, params in queries:
                await tx.run(q, params)
    logger.info("Seeded demo borrower %s", borrower_id)
    return borrower_id


async def seed_fund_borrower(
    nav_usd: float,
    digest: str | None = None,
    requested_amount: float | None = None,
) -> str:
    """Idempotently upsert the 'fund_graphalpha' Borrower node whose collateral is
    the strategy fund's ON-CHAIN attested NAV (RWA claim layer, H3).

    Additive-only, mirrors seed_demo_borrower's quarantine: a single Borrower +
    Collateral(+) + LENDS relationship so the deterministic risk engine can score
    "collateral = attested NAV". Every attestation cycle calls this with the fresh
    digest so the collateral value is mark-to-market.
    """
    borrower_id = "fund_graphalpha"
    driver: AsyncDriver = get_driver()
    req = requested_amount if requested_amount is not None else max(10000.0, 0.1 * nav_usd)
    digest = digest or ""
    queries = [
        (
            """MERGE (b:Borrower {borrower_id: $bid})
               SET b.display_name = 'GraphAlpha Strategy Fund',
                   b.collateral_type = 'attested_nav',
                   b.attestation_src = 'sepolia',
                   b.requested_amount = $requested_amount,
                   b.fico_score = 780.0,
                   b.last_nav_usd = $nav_usd,
                   b.last_nav_digest = $digest,
                   b.market_regime = 'high_volatility',
                   b.attestation_refs = CASE
                     WHEN $digest = '' THEN b.attestation_refs
                     ELSE [x IN b.attestation_refs WHERE x <> $digest] + [$digest]
                   END""",
            {"bid": borrower_id, "requested_amount": req,
             "nav_usd": nav_usd, "digest": digest},
        ),
        (
            """MERGE (b:Borrower {borrower_id: $bid})
               WITH b
               MERGE (col:Collateral {asset_id: 'graphalpha_attested_nav'})
               SET col.symbol = 'GASF-NAV', col.valuation = $nav_usd,
                   col.quantity = 1.0, col.haircut = 0.05,
                   col.correlated_group = 'rwa_attested'
               MERGE (b)-[:HAS_COLLATERAL]->(col)
               WITH b, col
               MERGE (a:Asset {asset_id: 'graphalpha_fund_nav', symbol: 'GASF', chain: 'sepolia'})
               SET a.price_usd = $nav_usd, a.volatility_annualized = 0.25, a.quantity = 1.0
               MERGE (col)-[:REFERENCES]->(a)
               WITH b
               MERGE (w:Wallet {address: $wallet, chain: 'creditcoin'})
               SET w.label = 'fund_ctc_borrower'
               MERGE (b)-[:OWNS]->(w)""",
            {"bid": borrower_id, "nav_usd": nav_usd,
             "wallet": os.getenv("CREDITCOIN_FUND_BORROWER_ADDRESS", "")},
        ),
        (
            """MATCH (b:Borrower {borrower_id: $bid})
               MERGE (l:Liability {protocol: 'Creditcoin', asset_symbol: 'CTC'})
               SET l.outstanding = 0.0
               MERGE (b)-[:HAS_LIABILITY]->(l)""",
            {"bid": borrower_id},
        ),
    ]
    async with driver.session() as session:
        async with await session.begin_transaction() as tx:
            for q, params in queries:
                await tx.run(q, params)
    logger.info("Upserted fund borrower %s with NAV %.2f", borrower_id, nav_usd)
    return borrower_id