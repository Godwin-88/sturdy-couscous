"""API v1 router: health + deterministic risk endpoints."""

import math

from fastapi import APIRouter

from pydantic import BaseModel, Field

from creditgraph.core.config import settings
from creditgraph.db.neo4j import get_driver
from creditgraph.db.redis_client import get_redis
from creditgraph.models import BorrowerProfile, ScenarioInput
from creditgraph.services.graphrag import graphrag_query

api_router = APIRouter()


@api_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@api_router.post("/risk/credit-score")
async def credit_score(profile: BorrowerProfile) -> dict[str, float]:
    """Deterministic Bayesian-backed credit score (0-100).

    Uses the graph regime blindspot + borrower obligor profile.
    Formula: base 100 minus weighted risk contributions from DTI, LTV,
    and a FICO-derived default probability term (logistic).
    """
    # PD via simple logistic mapping from FICO
    pd = 1.0 / (1.0 + math.exp((profile.fico_score - 690) / 28.0))
    # Penalty: 25% weight to PD, 30% to DTI, 25% to LTV, 20% residual
    score = 100.0 * (
        1.0
        - 0.25 * pd
        - 0.30 * profile.dti_ratio
        - 0.25 * profile.loan_to_value
        - 0.20 * 0.1
    )
    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 2),
        "probability_of_default": round(pd * 100, 2),
        "loan_to_value": round(profile.loan_to_value, 4),
        "debt_to_income": round(profile.dti_ratio, 4),
    }


class GraphQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language financial query")


@api_router.post("/risk/query")
async def query_graph(request: GraphQueryRequest) -> dict:
    """GraphRAG: translate a natural-language query into graph retrieval.

    Runs the controlled retrieval pipeline (spec §26): entity resolution,
    intent classification, query planning, Neo4j traversal, evidence
    retrieval, quantitative tool calls, context assembly and LLM explanation.
    """
    return await graphrag_query(request.query)


@api_router.get("/db")
async def db_status() -> dict[str, str]:
    """Report Neo4j + Redis connectivity for ops/debugging."""
    try:
        driver = get_driver()
        await driver.verify_connectivity()
        neo4j_ok = "ok"
    except Exception:
        neo4j_ok = "down"

    try:
        redis = get_redis()
        await redis.ping()
        redis_ok = "ok"
    except Exception:
        redis_ok = "down"

    return {"neo4j": neo4j_ok, "redis": redis_ok}


from .scenario_endpoints import scenario_router, quant_router
from .credit_endpoints import credit_router
from .correlation_endpoints import correlation_router
from .evidence_endpoints import evidence_router
from .execution_endpoints import execution_router
from .decision_endpoints import decision_router
from .wallet_endpoints import wallet_router
from .bayesian_endpoints import bayesian_router
from .governance_endpoints import governance_router
from .portfolio_endpoints import portfolio_router

api_router.include_router(scenario_router)
api_router.include_router(quant_router)
api_router.include_router(credit_router)
api_router.include_router(correlation_router)
api_router.include_router(evidence_router)
api_router.include_router(execution_router)
api_router.include_router(decision_router)
api_router.include_router(wallet_router)
api_router.include_router(bayesian_router)
api_router.include_router(governance_router)
api_router.include_router(portfolio_router)

# Re-export for main.py
__all__ = ["api_router"]