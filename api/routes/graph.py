import os
from fastapi import APIRouter, Query
from gqlalchemy import Memgraph

router = APIRouter(prefix="/graph", tags=["graph"])

def _db():
    return Memgraph(
        host=os.getenv("MEMGRAPH_HOST", "memgraph"),
        port=int(os.getenv("MEMGRAPH_PORT", 7687)),
    )


@router.get("/regime")
def get_regime_graph(regime: str = Query(...)):
    db = _db()
    query = f"""
    MATCH (r:Regime {{name: '{regime}'}})<-[:ACTIVATED_BY]-(s:Strategy)
    OPTIONAL MATCH (s)-[:DERIVED_FROM]->(c:Concept)
    OPTIONAL MATCH (c)-[:HAS_FORMULA]->(f:Formula)
    RETURN r.name AS regime, s.name AS strategy,
           collect(DISTINCT c.name) AS concepts,
           collect(DISTINCT f.expression) AS formulas
    """
    results = list(db.execute_and_fetch(query))
    return results


@router.get("/nodes")
def get_graph_nodes(node_type: str = Query(None), limit: int = 200):
    db = _db()
    if node_type:
        query = f"MATCH (n:{node_type}) RETURN n LIMIT {limit}"
    else:
        query = f"MATCH (n) RETURN n LIMIT {limit}"
    rows = list(db.execute_and_fetch(query))
    nodes = []
    for r in rows:
        n = r["n"]
        nodes.append({"id": n._id, "labels": list(n._labels),
                      "properties": dict(n._properties)})
    return nodes


@router.get("/edges")
def get_graph_edges(limit: int = 500):
    db = _db()
    query = f"""
    MATCH (a)-[r]->(b)
    RETURN a._id AS source, type(r) AS rel_type,
           b._id AS target, properties(r) AS props
    LIMIT {limit}
    """
    return list(db.execute_and_fetch(query))


@router.get("/contradictions")
def get_contradictions():
    db = _db()
    query = """
    MATCH (s:Strategy)-[:DERIVED_FROM]->(c:Concept)
    MATCH (c)-[:CONTRADICTED_BY]->(c2:Concept)<-[:DERIVED_FROM]-(s2:Strategy)
    WHERE s.status = 'active' AND s2.status = 'active'
    RETURN s.name AS strategy_a, s2.name AS strategy_b,
           c.name AS via_concept_a, c2.name AS via_concept_b
    """
    return list(db.execute_and_fetch(query))
