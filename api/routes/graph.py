import os
import re
import redis
import json
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from common.graph import get_db

router = APIRouter(prefix="/graph", tags=["graph"])


class GraphQueryRequest(BaseModel):
    """Read-only Cypher query. Mutating Cypher is rejected."""
    cypher: str
    params: dict = {}


# ── Read-only guard: reject any mutation or procedure call ──────────────────
_FORBIDDEN = re.compile(
    r"\b(MERGE|CREATE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|CALL)\b"
    r"|\b(db|apoc|algo|gds)\.[A-Za-z_]+"
    r"|\bUSING\s+PERIODIC\s+COMMIT\b",
    re.IGNORECASE,
)

def _db():
    return get_db()

def _redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


@router.post("/query")
def graph_query(req: GraphQueryRequest):
    """Read-only Cypher query for the WebMCP agent tool surface.

    The _FORBIDDEN guard rejects MERGE/CREATE/DELETE/SET/DROP/FOREACH/CALL and
    any procedure access (db.*, apoc.*, gds.*), so agents can traverse the
    knowledge graph but never mutate it.
    """
    if not req.cypher.strip():
        raise HTTPException(status_code=422, detail="Empty cypher query")
    if _FORBIDDEN.search(req.cypher):
        raise HTTPException(
            status_code=403,
            detail="Read-only guard: mutating Cypher (MERGE/CREATE/DELETE/SET/CALL/db.*) is not allowed",
        )
    db = _db()
    try:
        rows = list(db.execute_and_fetch(req.cypher, req.params or {}))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cypher error: {e}")
    # Serialize Neo4j values (Node/Relationship/ints/Date) to JSON-safe primitives.
    def _js(v):
        if hasattr(v, "element_id"):  # gqlalchemy Node
            return {"_id": str(getattr(v, "element_id", "")),
                    "labels": list(getattr(v, "labels", [])),
                    "properties": _js(getattr(v, "_properties", getattr(v, "properties", {})))}
        if hasattr(v, "items"):  # list/tuple
            return [_js(x) for x in v]
        if isinstance(v, dict):
            return {k: _js(x) for k, x in v.items()}
        if hasattr(v, "iso_format"):  # Neo4j temporal
            return str(v)
        if isinstance(v, float) and (v != v):  # NaN
            return None
        return v
    return {"rows": [_js(r) for r in rows], "count": len(rows)}


def _safe_db_call(fn, *args, **kwargs):
    """Execute a Memgraph call with error handling."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Memgraph unavailable: {e}")


@router.get("/regime")
def get_regime_graph(regime: str = Query(...)):
    try:
        db = _db()
    except Exception as e:
        return []
    query = f"""
    MATCH (r:Regime {{name: '{regime}'}})<-[:ACTIVATED_BY]-(s:Strategy)
    OPTIONAL MATCH (s)-[:DERIVED_FROM]->(c:Concept)
    OPTIONAL MATCH (c)-[:HAS_FORMULA]->(f:Formula)
    RETURN r.name AS regime, s.name AS strategy,
           collect(DISTINCT c.name) AS concepts,
           collect(DISTINCT f.expression) AS formulas
    """
    try:
        results = list(db.execute_and_fetch(query))
        return results
    except Exception:
        return []


@router.get("/nodes")
def get_graph_nodes(node_type: str = Query(None), limit: int = 200):
    try:
        db = _db()
    except Exception:
        return []
    if node_type:
        query = f"MATCH (n:{node_type}) RETURN n LIMIT {limit}"
    else:
        query = f"MATCH (n) RETURN n LIMIT {limit}"
    try:
        rows = list(db.execute_and_fetch(query))
        nodes = []
        for r in rows:
            n = r["n"]
            nodes.append({"id": n._id, "labels": list(n._labels),
                          "properties": dict(n._properties)})
        return nodes
    except Exception:
        return []


@router.get("/edges")
def get_graph_edges(limit: int = 500):
    try:
        db = _db()
    except Exception:
        return []
    query = f"""
    MATCH (a)-[r]->(b)
    RETURN id(a) AS source, type(r) AS rel_type,
           id(b) AS target, properties(r) AS props
    LIMIT {limit}
    """
    try:
        return list(db.execute_and_fetch(query))
    except Exception:
        return []


@router.get("/contradictions")
def get_contradictions():
    try:
        db = _db()
    except Exception:
        return []
    r = _redis()
    suppressed_raw = r.get("graphalpha:suppressed_contradictions")
    suppressed = json.loads(suppressed_raw) if suppressed_raw else []
    query = """
    MATCH (s:Strategy)-[:DERIVED_FROM]->(c:Concept)
    MATCH (c)-[:CONTRADICTED_BY]->(c2:Concept)<-[:DERIVED_FROM]-(s2:Strategy)
    WHERE s.status = 'active' AND s2.status = 'active'
    RETURN s.name AS strategy_a, s2.name AS strategy_b,
           c.name AS via_concept_a, c2.name AS via_concept_b
    """
    try:
        results = list(db.execute_and_fetch(query))
        for row in results:
            key = f"{row['strategy_a']}|{row['strategy_b']}"
            rev = f"{row['strategy_b']}|{row['strategy_a']}"
            row["suppressed"] = key in suppressed or rev in suppressed
        return results
    except Exception:
        return []


@router.post("/contradictions/suppress")
def suppress_contradiction(strategy_a: str, strategy_b: str):
    r = _redis()
    raw = r.get("graphalpha:suppressed_contradictions")
    suppressed = json.loads(raw) if raw else []
    key = f"{strategy_a}|{strategy_b}"
    if key not in suppressed:
        suppressed.append(key)
    r.set("graphalpha:suppressed_contradictions", json.dumps(suppressed))
    return {"suppressed": suppressed}


@router.delete("/contradictions/suppress")
def unsuppress_contradiction(strategy_a: str, strategy_b: str):
    r = _redis()
    raw = r.get("graphalpha:suppressed_contradictions")
    suppressed = json.loads(raw) if raw else []
    key = f"{strategy_a}|{strategy_b}"
    rev = f"{strategy_b}|{strategy_a}"
    suppressed = [s for s in suppressed if s not in (key, rev)]
    r.set("graphalpha:suppressed_contradictions", json.dumps(suppressed))
    return {"suppressed": suppressed}


@router.get("/signal-lineage")
def get_signal_lineage(strategy: str = Query(...)):
    """Returns the KG path: Strategy → Concepts → Formulas → Regime for a given strategy name."""
    try:
        db = _db()
    except Exception:
        return {}
    query = f"""
    MATCH (s:Strategy {{name: '{strategy}'}})
    OPTIONAL MATCH (s)-[:DERIVED_FROM]->(c:Concept)
    OPTIONAL MATCH (c)-[:HAS_FORMULA]->(f:Formula)
    OPTIONAL MATCH (s)-[:ACTIVATED_BY]->(reg:Regime)
    OPTIONAL MATCH (c)-[:BELONGS_TO]->(cat:Category)
    RETURN s.name AS strategy, s.description AS strategy_desc,
           collect(DISTINCT {{
               name: c.name,
               definition: c.definition,
               category: c.category,
               difficulty: c.difficulty
           }}) AS concepts,
           collect(DISTINCT {{
               id: f.id,
               name: f.name,
               expression: f.expression,
               output: f.output
           }}) AS formulas,
           collect(DISTINCT reg.name) AS regimes,
           collect(DISTINCT cat.name) AS categories
    """
    try:
        results = list(db.execute_and_fetch(query))
        return results[0] if results else {}
    except Exception:
        return {}


@router.get("/eligible-strategies")
def get_eligible_strategies(regime: str = Query(...)):
    """Returns all strategies eligible for a regime, with their active status."""
    try:
        db = _db()
    except Exception:
        return []
    r = _redis()
    raw = r.get("graphalpha:agent_status")
    active_strategies = []
    if raw:
        status = json.loads(raw)
        active_strategies = status.get("active_strategies", [])

    query = f"""
    MATCH (s:Strategy)-[:ACTIVATED_BY]->(reg:Regime {{name: '{regime}'}})
    RETURN s.name AS name, s.status AS status, s.description AS description
    """
    try:
        rows = list(db.execute_and_fetch(query))
        result = []
        for row in rows:
            name = row["name"]
            result.append({
                "name":        name,
                "description": row.get("description", ""),
                "db_status":   row.get("status", "unknown"),
                "active":      name in active_strategies,
            })
        return result
    except Exception:
        return []
