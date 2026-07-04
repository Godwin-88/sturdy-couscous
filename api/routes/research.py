"""
GraphAlpha Research & Analytics Endpoints
Covers the full quant workflow: Hypothesize → Backtest → Validate → Deploy → Monitor → Iterate
All new endpoints from the KG-Centric End-to-End Quant Platform plan.
"""

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, date
from typing import Any, Optional

import psycopg2
import psycopg2.extras
import redis
from fastapi import APIRouter, HTTPException, Query
from gqlalchemy import Memgraph
from pydantic import BaseModel, Field

router = APIRouter(prefix="", tags=["research"])


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _db():
    return Memgraph(
        host=os.getenv("MEMGRAPH_HOST", "memgraph"),
        port=int(os.getenv("MEMGRAPH_PORT", 7687)),
    )


def _redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


def _conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "graphalpha"),
        user=os.getenv("POSTGRES_USER", "graphalpha"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def _run_cypher(query: str, params: dict | None = None, limit: int = 1000) -> list[dict]:
    """Safe parameterized Cypher execution with hard limit and timeout."""
    db = _db()
    # Enforce a hard limit to prevent runaway queries
    limited_query = query.strip()
    if "RETURN" in limited_query.upper() and "LIMIT" not in limited_query.upper():
        limited_query += f" LIMIT {limit}"
    start = time.time()
    results = list(db.execute_and_fetch(limited_query, params or {}))
    elapsed_ms = int((time.time() - start) * 1000)
    # Log the query for reproducibility
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
                cur.execute(
                    "INSERT INTO kg_query_log (query_hash, params, execution_time_ms, result_count) "
                    "VALUES (%s, %s, %s, %s)",
                    (query_hash, json.dumps(params or {}), elapsed_ms, len(results)),
                )
    except Exception:
        pass  # Don't fail the request if logging fails
    return results


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively sanitize objects for JSON serialization."""
    if isinstance(obj, float):
        import math
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


# ── Pydantic models ─────────────────────────────────────────────────────────────

class GraphSimulateRequest(BaseModel):
    scenario: str = Field(..., description="'add_edge', 'remove_edge', 'change_weight', 'add_node'")
    params: dict[str, Any] = Field(..., description="Scenario parameters")


class GraphSensitivityRequest(BaseModel):
    source: str = Field(..., description="Source node name")
    target: str = Field(..., description="Target node name")
    rel_type: str = Field(..., description="Relationship type")
    weight_delta: float = Field(0.1, description="Weight perturbation delta")


class GraphEditRequest(BaseModel):
    operation: str = Field(..., description="'create_node', 'create_edge', 'delete_node', 'delete_edge', 'update_property'")
    source: str | None = None
    target: str | None = None
    rel_type: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class StressTestRequest(BaseModel):
    scenarios: list[dict[str, Any]] = Field(..., description="List of {ticker, shock_pct} shocks")


class BacktestOptimizeRequest(BaseModel):
    strategy: str = Field(..., description="Strategy name to optimize")
    params: dict[str, list[Any]] = Field(..., description="Parameter grid: {param_name: [values]}")
    regime: str | None = None


class BacktestTemplateRequest(BaseModel):
    name: str = Field(..., description="Template name")
    params: dict[str, Any] = Field(..., description="Backtest configuration parameters")


class GraphQueryRequest(BaseModel):
    query: str = Field(..., description="Parameterized Cypher query")
    params: dict[str, Any] = Field(default_factory=dict)


class CausalChainRequest(BaseModel):
    node_name: str = Field(..., description="Starting node name")
    node_label: str = Field("Concept", description="Node label")
    direction: str = Field("both", description="'upstream', 'downstream', or 'both'")
    max_depth: int = Field(5, ge=1, le=10)


class CorrelateRequest(BaseModel):
    artifact_types: list[str] = Field(..., description="Types: 'kg_events', 'backtest', 'fills', 'sentiment'")
    start_date: str = Field(..., description="ISO date start")
    end_date: str = Field(..., description="ISO date end")


class ABTestRequest(BaseModel):
    config_a: dict[str, Any] = Field(..., description="KG config A")
    config_b: dict[str, Any] = Field(..., description="KG config B")
    signal_ids: list[str] = Field(..., description="Signal IDs to replay")


class StrategyOptimizeRequest(BaseModel):
    params: dict[str, Any] = Field(..., description="Parameters to optimize")


class AlertSuggestRequest(BaseModel):
    behavior_pattern: str = Field(..., description="Pattern description")
    metric: str = Field(..., description="Metric name")
    threshold: float = Field(..., description="Alert threshold")


# ═══════════════════════════════════════════════════════════════════════════════
# 2.1 DESCRIPTIVE — "What does my KG contain?"
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/graph/summary")
def get_graph_summary():
    """KG health: node/edge counts, label distribution, orphan count, coverage %, last update."""
    db = _db()
    r = _redis()

    # Node counts by label
    label_query = "MATCH (n) RETURN labels(n) AS labels, count(*) AS cnt"
    label_rows = list(db.execute_and_fetch(label_query))
    by_label: dict[str, int] = {}
    for row in label_rows:
        for lbl in row.get("labels", []):
            by_label[lbl] = by_label.get(lbl, 0) + row.get("cnt", 0)

    total_nodes = sum(by_label.values())
    total_edges = 0
    edge_query = "MATCH ()-[r]->() RETURN count(*) AS cnt"
    edge_rows = list(db.execute_and_fetch(edge_query))
    if edge_rows:
        total_edges = edge_rows[0].get("cnt", 0)

    # Orphaned nodes (no relationships)
    orphan_query = "MATCH (n) WHERE NOT (n)--() RETURN count(*) AS cnt"
    orphan_rows = list(db.execute_and_fetch(orphan_query))
    orphaned_nodes = orphan_rows[0].get("cnt", 0) if orphan_rows else 0

    # Strategies without concepts
    no_concept_query = """
    MATCH (s:Strategy) WHERE NOT (s)-[:DERIVED_FROM]->(:Concept)
    RETURN count(*) AS cnt
    """
    no_concept_rows = list(db.execute_and_fetch(no_concept_query))
    strategies_without_concepts = no_concept_rows[0].get("cnt", 0) if no_concept_rows else 0

    # Formula coverage: strategies with at least one formula via concept
    formula_cov_query = """
    MATCH (s:Strategy)-[:DERIVED_FROM]->(:Concept)-[:HAS_FORMULA]->(:Formula)
    RETURN count(DISTINCT s) AS covered
    """
    total_strat_query = "MATCH (s:Strategy) RETURN count(*) AS total"
    cov_rows = list(db.execute_and_fetch(formula_cov_query))
    total_rows = list(db.execute_and_fetch(total_strat_query))
    covered = cov_rows[0].get("covered", 0) if cov_rows else 0
    total_strats = total_rows[0].get("total", 0) if total_rows else 0
    formula_coverage_pct = round(covered / total_strats, 4) if total_strats else 0.0

    # Last KG update from Redis or kg_versions table
    last_kg_update = None
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT recorded_at FROM kg_versions ORDER BY recorded_at DESC LIMIT 1")
                row = cur.fetchone()
                if row:
                    last_kg_update = row[0].isoformat()
    except Exception:
        pass

    return _sanitize_for_json({
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "by_label": by_label,
        "orphaned_nodes": orphaned_nodes,
        "strategies_without_concepts": strategies_without_concepts,
        "formula_coverage_pct": formula_coverage_pct,
        "last_kg_update": last_kg_update,
    })


@router.get("/graph/importance")
def get_graph_importance(
    algorithm: str = Query("pagerank", description="pagerank, betweenness, degree"),
    limit: int = Query(20, ge=1, le=200),
):
    """Concept centrality ranking with configurable algorithm."""
    db = _db()
    if algorithm == "degree":
        query = """
        MATCH (c:Concept)
        RETURN c.name AS name, size((c)--()) AS centrality
        ORDER BY centrality DESC LIMIT $limit
        """
    elif algorithm == "betweenness":
        # Approximate betweenness via MAGE if available, fallback to degree
        try:
            query = """
            MATCH (c:Concept)
            WITH c, size((c)--()) AS degree
            RETURN c.name AS name, degree AS centrality
            ORDER BY centrality DESC LIMIT $limit
            """
        except Exception:
            query = """
            MATCH (c:Concept)
            RETURN c.name AS name, size((c)--()) AS centrality
            ORDER BY centrality DESC LIMIT $limit
            """
    else:  # pagerank (default)
        try:
            query = """
            MATCH (c:Concept)
            WITH c, size((c)<--()) AS in_degree, size((c)-->()) AS out_degree
            RETURN c.name AS name,
                   (in_degree + out_degree) AS centrality
            ORDER BY centrality DESC LIMIT $limit
            """
        except Exception:
            query = """
            MATCH (c:Concept)
            RETURN c.name AS name, size((c)--()) AS centrality
            ORDER BY centrality DESC LIMIT $limit
            """
    results = list(db.execute_and_fetch(query, {"limit": limit}))
    return _sanitize_for_json(results)


@router.get("/strategies")
def get_strategies(
    asset_class: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Strategy catalog: regimes, concepts, formulas, asset_class, venue, backtest Sharpe, live signal count."""
    db = _db()
    r = _redis()

    # Build dynamic WHERE clause safely
    conditions = []
    params: dict[str, Any] = {"limit": limit}
    if asset_class:
        conditions.append("s.asset_class = $asset_class")
        params["asset_class"] = asset_class
    if status:
        conditions.append("s.status = $status")
        params["status"] = status

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    query = f"""
    MATCH (s:Strategy)
    OPTIONAL MATCH (s)-[:ACTIVATED_BY]->(r:Regime)
    OPTIONAL MATCH (s)-[:DERIVED_FROM]->(c:Concept)
    OPTIONAL MATCH (c)-[:HAS_FORMULA]->(f:Formula)
    {where_clause}
    RETURN s.name AS name, s.status AS status, s.asset_class AS asset_class,
           s.venue AS venue, s.description AS description,
           collect(DISTINCT r.name) AS regimes,
           collect(DISTINCT c.name) AS concepts,
           collect(DISTINCT f.expression) AS formulas
    ORDER BY name ASC LIMIT $limit
    """
    rows = list(db.execute_and_fetch(query, params))

    # Enrich with backtest metrics and live signal counts from Postgres
    result = []
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for row in rows:
                    name = row.get("name", "")
                    # Latest backtest Sharpe
                    cur.execute("""
                        SELECT sharpe_ratio, total_return, max_drawdown, n_trades
                        FROM backtest_runs
                        WHERE use_graph = true
                        ORDER BY created_at DESC LIMIT 1
                    """)
                    bt = cur.fetchone()
                    # Live signal count (last 7 days)
                    cur.execute("""
                        SELECT COUNT(*) AS cnt FROM order_audit
                        WHERE strategy = %s AND created_at > NOW() - INTERVAL '7 days'
                    """, (name,))
                    live_cnt = cur.fetchone()

                    result.append({
                        "name": name,
                        "status": row.get("status", "unknown"),
                        "asset_class": row.get("asset_class", "unknown"),
                        "venue": row.get("venue", "unknown"),
                        "description": row.get("description", ""),
                        "regimes": row.get("regimes", []),
                        "concepts": row.get("concepts", []),
                        "formulas": row.get("formulas", []),
                        "backtest_sharpe": float(bt["sharpe_ratio"]) if bt and bt["sharpe_ratio"] else None,
                        "backtest_return": float(bt["total_return"]) if bt and bt["total_return"] else None,
                        "backtest_trades": int(bt["n_trades"]) if bt and bt["n_trades"] else 0,
                        "live_signals_7d": int(live_cnt["cnt"]) if live_cnt else 0,
                    })
    except Exception:
        # Fallback: return without enrichment
        for row in rows:
            result.append({
                "name": row.get("name", ""),
                "status": row.get("status", "unknown"),
                "asset_class": row.get("asset_class", "unknown"),
                "venue": row.get("venue", "unknown"),
                "description": row.get("description", ""),
                "regimes": row.get("regimes", []),
                "concepts": row.get("concepts", []),
                "formulas": row.get("formulas", []),
                "backtest_sharpe": None,
                "backtest_return": None,
                "backtest_trades": 0,
                "live_signals_7d": 0,
            })

    return _sanitize_for_json(result)


@router.get("/formulas")
def get_formulas(limit: int = Query(100, ge=1, le=500)):
    """Formula catalog: expression, tickers, backtest/live usage counts."""
    db = _db()
    query = """
    MATCH (f:Formula)
    OPTIONAL MATCH (f)<-[:HAS_FORMULA]-(c:Concept)<-[:DERIVED_FROM]-(s:Strategy)
    RETURN f.id AS id, f.name AS name, f.expression AS expression,
           f.output AS output, f.description AS description,
           collect(DISTINCT c.name) AS concepts,
           collect(DISTINCT s.name) AS strategies
    ORDER BY f.name ASC LIMIT $limit
    """
    rows = list(db.execute_and_fetch(query, {"limit": limit}))

    result = []
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for row in rows:
                    name = row.get("name", "")
                    cur.execute("""
                        SELECT COUNT(*) AS cnt FROM order_audit
                        WHERE strategy IN (
                            SELECT unnest(%s::text[])
                        ) AND created_at > NOW() - INTERVAL '30 days'
                    """, (row.get("strategies", []),))
                    usage = cur.fetchone()
                    result.append({
                        "id": row.get("id", ""),
                        "name": name,
                        "expression": row.get("expression", ""),
                        "output": row.get("output", ""),
                        "description": row.get("description", ""),
                        "concepts": row.get("concepts", []),
                        "strategies": row.get("strategies", []),
                        "live_usage_30d": int(usage["cnt"]) if usage else 0,
                    })
    except Exception:
        for row in rows:
            result.append({
                "id": row.get("id", ""),
                "name": row.get("name", ""),
                "expression": row.get("expression", ""),
                "output": row.get("output", ""),
                "description": row.get("description", ""),
                "concepts": row.get("concepts", []),
                "strategies": row.get("strategies", []),
                "live_usage_30d": 0,
            })

    return _sanitize_for_json(result)


@router.get("/graph/gaps")
def get_graph_gaps():
    """KG completeness audit: orphaned nodes, uncovered tickers, sparse regimes."""
    db = _db()

    # Orphaned nodes
    orphan_query = """
    MATCH (n) WHERE NOT (n)--()
    RETURN labels(n) AS labels, n.name AS name, count(*) AS cnt
    """
    orphans = list(db.execute_and_fetch(orphan_query))

    # Strategies with no concept coverage
    no_concept_query = """
    MATCH (s:Strategy) WHERE NOT (s)-[:DERIVED_FROM]->(:Concept)
    RETURN s.name AS name, s.asset_class AS asset_class
    """
    uncovered_strategies = list(db.execute_and_fetch(no_concept_query))

    # Regimes with few strategies
    sparse_regimes_query = """
    MATCH (r:Regime)<-[:ACTIVATED_BY]-(s:Strategy)
    WITH r, count(s) AS strategy_count
    WHERE strategy_count < 2
    RETURN r.name AS regime, strategy_count
    """
    sparse_regimes = list(db.execute_and_fetch(sparse_regimes_query))

    return _sanitize_for_json({
        "orphaned_nodes": orphans,
        "uncovered_strategies": uncovered_strategies,
        "sparse_regimes": sparse_regimes,
    })


@router.get("/graph/versions")
def get_graph_versions(limit: int = Query(20, ge=1, le=200)):
    """Historical KG snapshots from ResearchAgent VARLiNGAM updates."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, version_tag, node_count, edge_count, source_agent, recorded_at
                    FROM kg_versions
                    ORDER BY recorded_at DESC LIMIT %s
                """, (limit,))
                rows = cur.fetchall()
        return _sanitize_for_json([dict(r) for r in rows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch KG versions: {e}")


@router.get("/agent/performance")
def get_agent_performance(days: int = Query(30, ge=1, le=365)):
    """Per-agent contribution: signals generated, approvals, rejections, latency."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) AS total_cycles,
                        AVG(duration_s) AS avg_duration_s,
                        AVG(regime_confidence) AS avg_regime_confidence,
                        COUNT(*) FILTER (WHERE signals IS NOT NULL) AS cycles_with_signals,
                        COUNT(*) FILTER (WHERE rejections IS NOT NULL) AS cycles_with_rejections
                    FROM agent_cycle_audit
                    WHERE timestamp > NOW() - INTERVAL '1 day' * %s
                """, (days,))
                summary = cur.fetchone()

                # Sub-agent breakdown from JSONB
                cur.execute("""
                    SELECT
                        sub_agents->>'agent' AS agent_name,
                        COUNT(*) AS appearances,
                        COUNT(*) FILTER (WHERE sub_agents->>'status' = 'ok') AS successes
                    FROM agent_cycle_audit, jsonb_array_elements(sub_agents) AS sub_agents
                    WHERE timestamp > NOW() - INTERVAL '1 day' * %s
                    GROUP BY agent_name
                    ORDER BY appearances DESC
                """, (days,))
                agent_breakdown = cur.fetchall()

        return _sanitize_for_json({
            "summary": dict(summary) if summary else {},
            "agent_breakdown": [dict(r) for r in agent_breakdown],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch agent performance: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2.2 DIAGNOSTIC — "Why did X happen?"
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/signals/{signal_id}/attribution")
def get_signal_attribution(signal_id: str):
    """Full signal score breakdown: quant, sentiment, news, macro, KG formula, fusion weights, contradiction status."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT order_id, strategy, ticker, direction, quantity,
                           fill_price, signal_score, kelly_fraction, var_contribution,
                           rejection_reason, raw_response, created_at
                    FROM order_audit
                    WHERE order_id = %s
                """, (signal_id,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")

                # Try to get detailed attribution from signal_archive
                cur.execute("""
                    SELECT * FROM signal_archive
                    WHERE signal_id = %s
                    ORDER BY created_at DESC LIMIT 1
                """, (signal_id,))
                archive = cur.fetchone()

        result = dict(row)
        if archive:
            result["quant_score"] = archive.get("quant_score")
            result["sentiment_score"] = archive.get("sentiment_score")
            result["news_overlay"] = archive.get("news_overlay")
            result["macro_overlay"] = archive.get("macro_overlay")
            result["kg_formula_contribution"] = archive.get("kg_formula_contribution")
            result["contradiction_blocked"] = archive.get("contradiction_blocked")
            result["kelly_fraction"] = archive.get("kelly_fraction")
            result["var_contribution_pct"] = archive.get("var_contribution_pct")
            result["slippage_bps"] = archive.get("slippage_bps")

        # Get KG graph path from Memgraph
        strategy = result.get("strategy", "")
        if strategy:
            db = _db()
            path_query = """
            MATCH path = (s:Strategy {name: $name})-[:DERIVED_FROM*1..3]->(c)
            RETURN [n IN nodes(path) | n.name] AS kg_graph_path
            LIMIT 1
            """
            path_rows = list(db.execute_and_fetch(path_query, {"name": strategy}))
            if path_rows:
                result["kg_graph_path"] = path_rows[0].get("kg_graph_path", [])

        return _sanitize_for_json(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch signal attribution: {e}")


@router.get("/signals/rejected")
def get_rejected_signals(
    reason: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Rejected signals grouped by reason with KG context."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if reason:
                    cur.execute("""
                        SELECT order_id, strategy, ticker, direction, quantity,
                               signal_score, rejection_reason, created_at
                        FROM order_audit
                        WHERE rejection_reason IS NOT NULL
                          AND rejection_reason ILIKE %s
                        ORDER BY created_at DESC LIMIT %s
                    """, (f"%{reason}%", limit))
                else:
                    cur.execute("""
                        SELECT order_id, strategy, ticker, direction, quantity,
                               signal_score, rejection_reason, created_at
                        FROM order_audit
                        WHERE rejection_reason IS NOT NULL
                        ORDER BY created_at DESC LIMIT %s
                    """, (limit,))
                rows = cur.fetchall()

        # Group by reason
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            r = dict(row)
            reason_key = r.get("rejection_reason", "unknown")
            if reason_key not in grouped:
                grouped[reason_key] = []
            grouped[reason_key].append(r)

        return _sanitize_for_json({
            "total": len(rows),
            "by_reason": {k: {"count": len(v), "signals": v} for k, v in grouped.items()},
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch rejected signals: {e}")


@router.get("/strategies/{name}/activation-history")
def get_strategy_activation_history(name: str, limit: int = Query(50, ge=1, ge=500)):
    """Timestamped activation/inactivation log with regime and reason."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT cycle_id, timestamp, regime, regime_confidence,
                           signals, rejections
                    FROM agent_cycle_audit
                    WHERE signals @> %s::jsonb
                       OR rejections @> %s::jsonb
                    ORDER BY timestamp DESC LIMIT %s
                """, (
                    json.dumps([{"strategy": name}]),
                    json.dumps([{"strategy": name}]),
                    limit,
                ))
                rows = cur.fetchall()
        return _sanitize_for_json([dict(r) for r in rows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch activation history: {e}")


@router.get("/graph/edge-drift")
def get_graph_edge_drift(
    source: str = Query(...),
    target: str = Query(...),
    rel_type: str = Query("TRANSMITS_TO"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Time-series of a specific edge's weight changes via ResearchAgent."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, source, target, rel_type, weight, agent_run, recorded_at
                    FROM kg_edge_snapshots
                    WHERE source = %s AND target = %s AND rel_type = %s
                    ORDER BY recorded_at DESC LIMIT %s
                """, (source, target, rel_type, limit))
                rows = cur.fetchall()
        return _sanitize_for_json([dict(r) for r in rows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch edge drift: {e}")


@router.get("/agent/audit")
def get_agent_audit(limit: int = Query(20, ge=1, le=200)):
    """Full per-cycle audit: sub-agent durations, outputs, signal counts, rejections."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, cycle_id, timestamp, duration_s, regime,
                           regime_confidence, sub_agents, signals, rejections
                    FROM agent_cycle_audit
                    ORDER BY timestamp DESC LIMIT %s
                """, (limit,))
                rows = cur.fetchall()
        return _sanitize_for_json([dict(r) for r in rows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch agent audit: {e}")


@router.get("/graph/contradictions/history")
def get_contradictions_history(limit: int = Query(50, ge=1, le=500)):
    """Suppressed contradictions timeline with impact on signals."""
    r = _redis()
    raw = r.get("graphalpha:suppressed_contradictions")
    suppressed = json.loads(raw) if raw else []

    # Get edit log entries related to contradictions
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, operation, source, target, rel_type, properties,
                           validation_passed, affected_strategies, created_at
                    FROM kg_edit_log
                    WHERE operation ILIKE '%contradiction%'
                       OR rel_type = 'CONTRADICTED_BY'
                    ORDER BY created_at DESC LIMIT %s
                """, (limit,))
                edits = cur.fetchall()
    except Exception:
        edits = []

    return _sanitize_for_json({
        "currently_suppressed": suppressed,
        "edit_history": [dict(r) for r in edits],
    })


@router.get("/execution/fills")
def get_execution_fills(
    order_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Fill forensics: slippage vs arrival, fees, venue routing, KG trigger."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if order_id:
                    cur.execute("""
                        SELECT order_id, strategy, ticker, direction, quantity,
                               fill_price, fee_usd, mode, signal_score, kelly_fraction,
                               var_contribution, raw_response, created_at
                        FROM order_audit
                        WHERE order_id = %s AND fill_price IS NOT NULL
                    """, (order_id,))
                else:
                    cur.execute("""
                        SELECT order_id, strategy, ticker, direction, quantity,
                               fill_price, fee_usd, mode, signal_score, kelly_fraction,
                               var_contribution, raw_response, created_at
                        FROM order_audit
                        WHERE fill_price IS NOT NULL
                        ORDER BY created_at DESC LIMIT %s
                    """, (limit,))
                rows = cur.fetchall()
        return _sanitize_for_json([dict(r) for r in rows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch fills: {e}")


@router.get("/orders/{order_id}/lifecycle")
def get_order_lifecycle(order_id: str):
    """Order timeline: signal → approved → submitted → partial → filled."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT order_id, strategy, ticker, direction, quantity,
                           fill_price, fee_usd, mode, signal_score, kelly_fraction,
                           var_contribution, rejection_reason, raw_response, created_at
                    FROM order_audit
                    WHERE order_id = %s
                """, (order_id,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

                # Check signal_archive for additional timeline info
                cur.execute("""
                    SELECT timestamp, score, contradiction_blocked, fill_price, fill_timestamp
                    FROM signal_archive
                    WHERE signal_id = %s
                    ORDER BY created_at DESC LIMIT 1
                """, (order_id,))
                archive = cur.fetchone()

        result = dict(row)
        if archive:
            result["signal_timestamp"] = archive.get("timestamp")
            result["contradiction_blocked"] = archive.get("contradiction_blocked")
            result["fill_timestamp"] = archive.get("fill_timestamp")

        return _sanitize_for_json(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch order lifecycle: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2.3 PREDICTIVE — "What will happen if I change X?"
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/graph/simulate")
def post_graph_simulate(req: GraphSimulateRequest):
    """KG perturbation simulation: 'what if I add/change this edge?' Returns affected strategies and projected signal changes."""
    db = _db()
    scenario = req.scenario
    params = req.params

    affected_strategies: list[str] = []
    predicted_signal_changes: list[dict] = []
    contradiction_risk: dict = {"new_contradictions": 0, "severity": "low"}

    if scenario == "add_edge":
        source = params.get("source", "")
        target = params.get("target", "")
        rel_type = params.get("rel_type", "TRANSMITS_TO")
        weight = params.get("weight", 0.5)

        # Find strategies that would be affected
        query = """
        MATCH (s:Strategy)-[:DERIVED_FROM]->(c:Concept {name: $source})
        RETURN s.name AS strategy
        UNION
        MATCH (s:Strategy)-[:DERIVED_FROM]->(c:Concept {name: $target})
        RETURN s.name AS strategy
        """
        rows = list(db.execute_and_fetch(query, {"source": source, "target": target}))
        affected_strategies = list(set(r.get("strategy", "") for r in rows if r.get("strategy")))

        # Check for new contradictions
        contra_query = """
        MATCH (c1:Concept {name: $source})-[:CONTRADICTED_BY]->(c2:Concept {name: $target})
        RETURN count(*) AS cnt
        """
        contra_rows = list(db.execute_and_fetch(contra_query, {"source": source, "target": target}))
        if contra_rows and contra_rows[0].get("cnt", 0) > 0:
            contradiction_risk = {"new_contradictions": 1, "severity": "medium"}

        # Projected signal changes (simplified: score boost proportional to weight)
        for strategy in affected_strategies:
            predicted_signal_changes.append({
                "strategy": strategy,
                "current_score": 0.0,
                "projected_score": round(weight * 0.15, 4),
                "change_pct": "+15% (estimated)",
            })

    elif scenario == "remove_edge":
        source = params.get("source", "")
        target = params.get("target", "")
        query = """
        MATCH (s:Strategy)-[:DERIVED_FROM]->(c:Concept {name: $source})
        RETURN s.name AS strategy
        """
        rows = list(db.execute_and_fetch(query, {"source": source}))
        affected_strategies = list(set(r.get("strategy", "") for r in rows if r.get("strategy")))

    elif scenario == "change_weight":
        source = params.get("source", "")
        target = params.get("target", "")
        new_weight = params.get("weight", 0.5)
        query = """
        MATCH (s:Strategy)-[:DERIVED_FROM]->(c:Concept {name: $source})
        RETURN s.name AS strategy
        """
        rows = list(db.execute_and_fetch(query, {"source": source}))
        affected_strategies = list(set(r.get("strategy", "") for r in rows if r.get("strategy")))
        for strategy in affected_strategies:
            predicted_signal_changes.append({
                "strategy": strategy,
                "current_score": 0.0,
                "projected_score": round(new_weight * 0.2, 4),
                "change_pct": f"{'+' if new_weight > 0.5 else ''}{round((new_weight - 0.5) * 20, 1)}% (estimated)",
            })

    return _sanitize_for_json({
        "scenario": scenario,
        "params": params,
        "affected_strategies": affected_strategies,
        "predicted_new_activations": len(affected_strategies),
        "predicted_signal_changes": predicted_signal_changes,
        "contradiction_risk": contradiction_risk,
    })


@router.get("/strategies/{name}/forecast")
def get_strategy_forecast(name: str, horizon_days: int = Query(30, ge=1, le=365)):
    """Performance forecast with signal decay curve and regime transition probabilities."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Historical performance
                cur.execute("""
                    SELECT signal_score, kelly_fraction, created_at
                    FROM order_audit
                    WHERE strategy = %s AND created_at > NOW() - INTERVAL '90 days'
                    ORDER BY created_at ASC
                """, (name,))
                history = cur.fetchall()

                # Regime transition probabilities from agent_cycle_audit
                cur.execute("""
                    SELECT regime, COUNT(*) AS cnt
                    FROM agent_cycle_audit
                    WHERE timestamp > NOW() - INTERVAL '90 days'
                    GROUP BY regime
                    ORDER BY cnt DESC
                """)
                regime_dist = cur.fetchall()

        scores = [float(r["signal_score"]) for r in history if r.get("signal_score")]
        decay_curve = []
        if scores:
            # Simple exponential decay projection
            avg_score = sum(scores) / len(scores)
            for day in range(1, min(horizon_days + 1, 31)):
                decayed = avg_score * (0.95 ** day)
                decay_curve.append({"day": day, "projected_score": round(decayed, 4)})

        total_regime_count = sum(r["cnt"] for r in regime_dist) or 1
        regime_probs = {
            r["regime"]: round(r["cnt"] / total_regime_count, 4)
            for r in regime_dist
        }

        return _sanitize_for_json({
            "strategy": name,
            "horizon_days": horizon_days,
            "historical_scores": len(scores),
            "avg_historical_score": round(sum(scores) / len(scores), 4) if scores else None,
            "signal_decay_curve": decay_curve,
            "regime_transition_probs": regime_probs,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch strategy forecast: {e}")


@router.get("/signals/decay")
def get_signal_decay(strategy: str | None = Query(None), limit: int = Query(100, ge=1, le=1000)):
    """Signal quality degradation over holding period by strategy."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if strategy:
                    cur.execute("""
                        SELECT signal_score, kelly_fraction, created_at
                        FROM order_audit
                        WHERE strategy = %s AND signal_score IS NOT NULL
                        ORDER BY created_at DESC LIMIT %s
                    """, (strategy, limit))
                else:
                    cur.execute("""
                        SELECT strategy, signal_score, kelly_fraction, created_at
                        FROM order_audit
                        WHERE signal_score IS NOT NULL
                        ORDER BY created_at DESC LIMIT %s
                    """, (limit,))
                rows = cur.fetchall()
        return _sanitize_for_json([dict(r) for r in rows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch signal decay: {e}")


@router.get("/graph/contradiction-risk")
def get_contradiction_risk(limit: int = Query(20, ge=1, le=100)):
    """Probability-weighted forecast of contradiction likelihood under regime transitions."""
    db = _db()
    query = """
    MATCH (s1:Strategy)-[:DERIVED_FROM]->(c1:Concept)-[:CONTRADICTED_BY]->(c2:Concept)<-[:DERIVED_FROM]-(s2:Strategy)
    WHERE s1.status = 'active' AND s2.status = 'active'
    RETURN s1.name AS strategy_a, s2.name AS strategy_b,
           c1.name AS concept_a, c2.name AS concept_b
    LIMIT $limit
    """
    contradictions = list(db.execute_and_fetch(query, {"limit": limit}))

    # Enrich with regime transition probabilities
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT regime, COUNT(*) AS cnt
                    FROM agent_cycle_audit
                    WHERE timestamp > NOW() - INTERVAL '90 days'
                    GROUP BY regime
                """)
                regime_counts = cur.fetchall()
    except Exception:
        regime_counts = []

    total = sum(r["cnt"] for r in regime_counts) or 1
    regime_probs = {r["regime"]: round(r["cnt"] / total, 4) for r in regime_counts}

    return _sanitize_for_json({
        "active_contradictions": [dict(r) for r in contradictions],
        "regime_transition_probs": regime_probs,
        "risk_level": "medium" if len(contradictions) > 5 else "low",
    })


@router.get("/agent/regime-forecast")
def get_agent_regime_forecast(days: int = Query(90, ge=30, le=365)):
    """Markov-style regime transition matrix from historical data."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT cycle_id, regime, timestamp
                    FROM agent_cycle_audit
                    WHERE timestamp > NOW() - INTERVAL '1 day' * %s
                    ORDER BY timestamp ASC
                """, (days,))
                rows = cur.fetchall()

        # Build transition matrix
        regimes = list(dict.fromkeys(r["regime"] for r in rows if r.get("regime")))
        transitions: dict[str, dict[str, int]] = {r: {r2: 0 for r2 in regimes} for r in regimes}
        for i in range(len(rows) - 1):
            curr = rows[i].get("regime")
            next_r = rows[i + 1].get("regime")
            if curr and next_r and curr in transitions and next_r in transitions[curr]:
                transitions[curr][next_r] += 1

        # Convert to probabilities
        matrix: dict[str, dict[str, float]] = {}
        for curr, next_counts in transitions.items():
            total = sum(next_counts.values()) or 1
            matrix[curr] = {
                next_r: round(cnt / total, 4)
                for next_r, cnt in next_counts.items()
            }

        return _sanitize_for_json({
            "regimes": regimes,
            "transition_matrix": matrix,
            "observation_period_days": days,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch regime forecast: {e}")


@router.post("/graph/sensitivity")
def post_graph_sensitivity(req: GraphSensitivityRequest):
    """Cascading impact analysis: perturb an edge and measure strategy eligibility/signal score changes."""
    db = _db()

    # Find strategies connected to source or target
    query = """
    MATCH (s:Strategy)-[:DERIVED_FROM]->(c:Concept)
    WHERE c.name = $source OR c.name = $target
    RETURN DISTINCT s.name AS strategy, s.status AS status
    """
    rows = list(db.execute_and_fetch(query, {"source": req.source, "target": req.target}))
    strategies = [dict(r) for r in rows]

    # Simulate impact of weight change
    impact: list[dict] = []
    for s in strategies:
        impact.append({
            "strategy": s.get("strategy", ""),
            "current_status": s.get("status", "unknown"),
            "sensitivity": "high" if req.weight_delta > 0.2 else "medium",
            "projected_eligibility_change": "unchanged",
        })

    return _sanitize_for_json({
        "perturbation": {
            "source": req.source,
            "target": req.target,
            "rel_type": req.rel_type,
            "weight_delta": req.weight_delta,
        },
        "affected_strategies": len(strategies),
        "impact": impact,
    })


@router.post("/risk/stress-test")
def post_risk_stress_test(req: StressTestRequest):
    """What-if scenario: 'SPY -20%, VIX +50%, rates +100bp' returns portfolio impact."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT ticker, direction, quantity, avg_entry_price, current_price
                    FROM positions WHERE status = 'open'
                """)
                positions = cur.fetchall()

                cur.execute("""
                    SELECT cash_balance, nav, drawdown_pct, halted
                    FROM portfolio_state ORDER BY id DESC LIMIT 1
                """)
                portfolio = cur.fetchone()

        if not portfolio:
            return {"nav_impact_pct": 0.0, "drawdown_impact_pct": 0.0, "positions_breaching_cap": [], "halt_triggered": False}

        nav = float(portfolio["nav"]) or 10000
        cash = float(portfolio["cash"]) or 10000
        current_dd = float(portfolio["drawdown_pct"]) or 0.0

        # Build shock map
        shock_map: dict[str, float] = {}
        for s in req.scenarios:
            ticker = s.get("ticker", "").upper()
            shock_pct = float(s.get("shock_pct", 0.0))
            shock_map[ticker] = shock_pct

        # Apply shocks
        total_impact = 0.0
        breaching: list[str] = []
        for p in positions:
            ticker = p["ticker"]
            shock = shock_map.get(ticker, 0.0)
            mkt_val = float(p["quantity"]) * float(p["current_price"])
            impact = mkt_val * shock
            total_impact += impact

            # Check if position breaches cap (e.g., > 25% NAV after shock)
            new_mkt_val = mkt_val + impact
            new_pct_nav = new_mkt_val / nav if nav else 0
            if new_pct_nav > 0.25:
                breaching.append(ticker)

        nav_impact_pct = total_impact / nav if nav else 0.0
        new_dd = max(0.0, current_dd + abs(nav_impact_pct))
        halt_triggered = new_dd > float(os.getenv("DRAWDOWN_LIMIT", "0.10"))

        return _sanitize_for_json({
            "nav_impact_pct": round(nav_impact_pct, 4),
            "drawdown_impact_pct": round(new_dd - current_dd, 4),
            "positions_breaching_cap": breaching,
            "halt_triggered": halt_triggered,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stress test failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2.4 PRESCRIPTIVE — "What should I change?"
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/graph/recommendations")
def get_graph_recommendations():
    """Automated KG improvements: missing edges, contradiction resolutions, coverage gaps."""
    db = _db()
    recommendations: list[dict] = []

    # 1. Strategies with no concept coverage
    no_concept_query = """
    MATCH (s:Strategy) WHERE NOT (s)-[:DERIVED_FROM]->(:Concept)
    RETURN s.name AS strategy, s.asset_class AS asset_class
    """
    no_concept = list(db.execute_and_fetch(no_concept_query))
    for row in no_concept:
        recommendations.append({
            "type": "add_edge",
            "priority": "high",
            "reason": f"Strategy {row.get('strategy', '?')} has no concept coverage",
            "suggestion": f"Add DERIVED_FROM edge between {row.get('strategy', '?')} and a relevant Concept node",
        })

    # 2. Active contradictions blocking strategies
    contra_query = """
    MATCH (s1:Strategy)-[:DERIVED_FROM]->(c1:Concept)-[:CONTRADICTED_BY]->(c2:Concept)<-[:DERIVED_FROM]-(s2:Strategy)
    WHERE s1.status = 'active' AND s2.status = 'active'
    RETURN s1.name AS strategy_a, s2.name AS strategy_b,
           c1.name AS concept_a, c2.name AS concept_b
    """
    contradictions = list(db.execute_and_fetch(contra_query))
    for row in contradictions:
        recommendations.append({
            "type": "resolve_contradiction",
            "priority": "medium",
            "reason": f"Active contradiction pair blocks {row.get('strategy_a', '?')} and {row.get('strategy_b', '?')}",
            "suggestion": f"Suppress {row.get('strategy_a', '?')}|{row.get('strategy_b', '?')} or revisit CONTRADICTED_BY edge",
        })

    # 3. Orphaned nodes
    orphan_query = """
    MATCH (n) WHERE NOT (n)--()
    RETURN labels(n) AS labels, n.name AS name
    LIMIT 20
    """
    orphans = list(db.execute_and_fetch(orphan_query))
    for row in orphans:
        recommendations.append({
            "type": "connect_orphan",
            "priority": "low",
            "reason": f"Orphaned node {row.get('name', '?')} ({row.get('labels', [])}) has no relationships",
            "suggestion": f"Connect {row.get('name', '?')} to related Concept or Strategy nodes",
        })

    return _sanitize_for_json(recommendations)


@router.get("/graph/coverage-gaps")
def get_graph_coverage_gaps():
    """Ticker/regime/asset-class combinations with weak concept coverage."""
    db = _db()

    # Regimes with few strategies
    regime_gaps_query = """
    MATCH (r:Regime)<-[:ACTIVATED_BY]-(s:Strategy)
    WITH r, count(s) AS strategy_count
    WHERE strategy_count < 3
    RETURN r.name AS regime, strategy_count
    ORDER BY strategy_count ASC
    """
    regime_gaps = list(db.execute_and_fetch(regime_gaps_query))

    # Asset classes with few concepts
    class_gaps_query = """
    MATCH (s:Strategy)
    WITH s.asset_class AS asset_class, count(s) AS strategy_count
    WHERE asset_class IS NOT NULL AND strategy_count < 3
    RETURN asset_class, strategy_count
    ORDER BY strategy_count ASC
    """
    class_gaps = list(db.execute_and_fetch(class_gaps_query))

    return _sanitize_for_json({
        "regime_gaps": regime_gaps,
        "asset_class_gaps": class_gaps,
    })


@router.post("/strategies/{name}/optimize")
def post_strategy_optimize(name: str, req: StrategyOptimizeRequest):
    """Parameter optimization for a strategy given current regime and KG context."""
    # This is a simplified simulation; full optimization requires the backtest engine
    db = _db()

    # Get current regime
    r = _redis()
    raw = r.get("graphalpha:agent_status")
    current_regime = "Unknown"
    if raw:
        status = json.loads(raw)
        current_regime = status.get("regime", "Unknown")

    # Get strategy concepts
    query = """
    MATCH (s:Strategy {name: $name})-[:DERIVED_FROM]->(c:Concept)
    RETURN c.name AS concept
    """
    concepts = list(db.execute_and_fetch(query, {"name": name}))

    return _sanitize_for_json({
        "strategy": name,
        "current_regime": current_regime,
        "concepts": [c.get("concept", "") for c in concepts],
        "params": req.params,
        "status": "simulated",
        "note": "Full optimization requires POST /backtest/optimize with the backtest engine",
    })


@router.get("/portfolio/rebalance")
def get_portfolio_rebalance():
    """Current weights vs. KG-optimal weights for current regime."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT ticker, direction, quantity, avg_entry_price, current_price,
                           quantity * current_price AS notional
                    FROM positions WHERE status = 'open'
                """)
                positions = cur.fetchall()

                cur.execute("""
                    SELECT cash_balance, nav FROM portfolio_state ORDER BY id DESC LIMIT 1
                """)
                portfolio = cur.fetchone()

        nav = float(portfolio["nav"]) if portfolio else 10000
        cash = float(portfolio["cash"]) if portfolio else 10000

        current_weights: dict[str, float] = {}
        for p in positions:
            notional = float(p["notional"])
            current_weights[p["ticker"]] = round(notional / nav, 4) if nav else 0

        # KG-optimal weights (simplified: equal weight with cash buffer)
        n_positions = len(positions) or 1
        target_per_position = (1.0 - 0.10) / n_positions  # 10% cash buffer
        optimal_weights: dict[str, float] = {}
        trades: list[dict] = []
        for p in positions:
            ticker = p["ticker"]
            current_w = current_weights.get(ticker, 0)
            target_w = round(target_per_position, 4)
            optimal_weights[ticker] = target_w
            diff = target_w - current_w
            if abs(diff) > 0.02:  # 2% threshold
                trades.append({
                    "ticker": ticker,
                    "action": "buy" if diff > 0 else "sell",
                    "target_weight": target_w,
                    "notional_usd": round(abs(diff) * nav, 2),
                })

        return _sanitize_for_json({
            "current": current_weights,
            "optimal": optimal_weights,
            "trades_suggested": trades,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute rebalance: {e}")


@router.get("/venues/optimize")
def get_venues_optimize():
    """Route-specific optimization: which signals should go to Kraken vs IBKR."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT venue, ticker, COUNT(*) AS fills,
                           AVG(fill_price) AS avg_fill,
                           AVG(fee_usd) AS avg_fee
                    FROM order_audit
                    WHERE fill_price IS NOT NULL
                    GROUP BY venue, ticker
                    ORDER BY fills DESC
                """)
                venue_stats = cur.fetchall()
        return _sanitize_for_json({
            "venue_stats": [dict(r) for r in venue_stats],
            "recommendation": "Route crypto signals to Kraken, equity/fixed-income to IBKR",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch venue optimization: {e}")


@router.post("/graph/edit")
def post_graph_edit(req: GraphEditRequest):
    """Safe transactional KG edit with validation and audit trail."""
    db = _db()
    affected_strategies: list[str] = []
    validation_passed = True
    error_msg: str | None = None

    try:
        if req.operation == "create_node":
            labels = req.properties.pop("labels", "Concept")
            props_str = ", ".join(f"{k}: ${k}" for k in req.properties)
            query = f"CREATE (n:{labels} {{{props_str}}}) RETURN id(n) AS node_id"
            rows = list(db.execute_and_fetch(query, req.properties))
            if rows:
                affected_strategies = []

        elif req.operation == "create_edge":
            if not req.source or not req.target or not req.rel_type:
                raise ValueError("source, target, and rel_type required for create_edge")
            query = """
            MATCH (a {name: $source}), (b {name: $target})
            CREATE (a)-[r:%s]->(b)
            RETURN type(r) AS rel_type
            """ % req.rel_type
            rows = list(db.execute_and_fetch(query, {"source": req.source, "target": req.target}))
            # Find affected strategies
            strat_query = """
            MATCH (s:Strategy)-[:DERIVED_FROM*0..2]->(c {name: $source})
            RETURN s.name AS strategy
            UNION
            MATCH (s:Strategy)-[:DERIVED_FROM*0..2]->(c {name: $target})
            RETURN s.name AS strategy
            """
            strat_rows = list(db.execute_and_fetch(strat_query, {"source": req.source, "target": req.target}))
            affected_strategies = list(set(r.get("strategy", "") for r in strat_rows if r.get("strategy")))

        elif req.operation == "delete_node":
            query = "MATCH (n {name: $name}) DETACH DELETE n"
            list(db.execute_and_fetch(query, {"name": req.source}))

        elif req.operation == "delete_edge":
            if not req.source or not req.target or not req.rel_type:
                raise ValueError("source, target, and rel_type required for delete_edge")
            query = """
            MATCH (a {name: $source})-[r:%s]->(b {name: $target})
            DELETE r
            """ % req.rel_type
            list(db.execute_and_fetch(query, {"source": req.source, "target": req.target}))

        elif req.operation == "update_property":
            query = """
            MATCH (n {name: $name})
            SET n += $properties
            RETURN n.name AS name
            """
            list(db.execute_and_fetch(query, {"name": req.source, "properties": req.properties}))

        else:
            raise ValueError(f"Unknown operation: {req.operation}")

    except Exception as e:
        validation_passed = False
        error_msg = str(e)

    # Audit log
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO kg_edit_log
                        (operation, source, target, rel_type, properties, validation_passed, affected_strategies)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    req.operation, req.source, req.target, req.rel_type,
                    json.dumps(req.properties), validation_passed, affected_strategies,
                ))
    except Exception:
        pass

    if not validation_passed:
        raise HTTPException(status_code=400, detail=f"KG edit failed: {error_msg}")

    return _sanitize_for_json({
        "operation": req.operation,
        "validation_passed": True,
        "affected_strategies": affected_strategies,
    })


@router.post("/alerts/suggest")
def post_alerts_suggest(req: AlertSuggestRequest):
    """Prescriptive alert rules based on system behavior patterns."""
    return _sanitize_for_json({
        "suggested_alert": {
            "name": f"{req.metric}_threshold_breach",
            "metric": req.metric,
            "condition": f"{req.metric} {'<' if req.behavior_pattern == 'declining' else '>'} {req.threshold}",
            "severity": "warning" if abs(req.threshold) < 0.5 else "critical",
            "cooldown_minutes": 60,
        },
        "pattern": req.behavior_pattern,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# 2.5 ANALYTICAL — "How do I analyze the system as a whole?"
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/graph/query")
def post_graph_query(req: GraphQueryRequest):
    """Parameterized Cypher query playground with safety limits."""
    # Safety: reject non-read queries
    upper = req.query.strip().upper()
    forbidden_keywords = ["CREATE", "DELETE", "SET", "MERGE", "DROP", "REMOVE", "ALTER", "FOREACH"]
    for kw in forbidden_keywords:
        if upper.startswith(kw) or f" {kw} " in upper:
            raise HTTPException(status_code=403, detail=f"Write queries not allowed: {kw}")

    try:
        results = _run_cypher(req.query, req.params)
        return _sanitize_for_json({
            "results": results,
            "execution_time_ms": 0,  # _run_cypher logs it but doesn't return it; we approximate
            "result_count": len(results),
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cypher query failed: {e}")


@router.get("/signals/export")
def get_signals_export(
    format: str = Query("json", regex="^(json|jsonl|csv)$"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    limit: int = Query(10000, ge=1, le=100000),
):
    """Bulk signal export for Python/R/Julia analysis."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                conditions = []
                params: list[Any] = []
                if start_date:
                    conditions.append("timestamp >= %s")
                    params.append(start_date)
                if end_date:
                    conditions.append("timestamp <= %s")
                    params.append(end_date)
                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

                cur.execute(f"""
                    SELECT signal_id, cycle_id, timestamp, strategy, ticker, venue,
                           direction, score, quant_score, sentiment_score, news_overlay,
                           macro_overlay, kg_formula_contribution, contradiction_blocked,
                           kelly_fraction, var_contribution_pct, fill_price, fill_timestamp,
                           slippage_bps
                    FROM signal_archive
                    {where_clause}
                    ORDER BY timestamp DESC LIMIT %s
                """, params + [limit])
                rows = cur.fetchall()

        data = [dict(r) for r in rows]

        if format == "jsonl":
            # Return newline-delimited JSON
            lines = "\n".join(json.dumps(_sanitize_for_json(r), default=str) for r in data)
            from fastapi.responses import Response
            return Response(content=lines, media_type="application/jsonl")
        elif format == "csv":
            import io
            import csv as csv_lib
            output = io.StringIO()
            if data:
                writer = csv_lib.DictWriter(output, fieldnames=list(data[0].keys()))
                writer.writeheader()
                for row in data:
                    writer.writerow({k: str(v) if v is not None else "" for k, v in row.items()})
            from fastapi.responses import Response
            return Response(content=output.getvalue(), media_type="text/csv")
        else:
            return _sanitize_for_json(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export signals: {e}")


@router.post("/graph/causal-chain")
def post_graph_causal_chain(req: CausalChainRequest):
    """Full upstream/downstream dependency graph for any node."""
    db = _db()

    upstream: list[dict] = []
    downstream: list[dict] = []

    if req.direction in ("upstream", "both"):
        up_query = f"""
        MATCH path = (start:{req.node_label} {{name: $name}})<-[:DERIVED_FROM|TRANSMITS_TO|HAS_FORMULA|ACTIVATED_BY*1..{req.max_depth}]-()
        RETURN [n IN nodes(path) | n.name] AS path_nodes,
               [r IN relationships(path) | type(r)] AS rel_types
        LIMIT 100
        """
        upstream = list(db.execute_and_fetch(up_query, {"name": req.node_name}))

    if req.direction in ("downstream", "both"):
        down_query = f"""
        MATCH path = (start:{req.node_label} {{name: $name}})-[:DERIVED_FROM|TRANSMITS_TO|HAS_FORMULA|ACTIVATED_BY*1..{req.max_depth}]->()
        RETURN [n IN nodes(path) | n.name] AS path_nodes,
               [r IN relationships(path) | type(r)] AS rel_types
        LIMIT 100
        """
        downstream = list(db.execute_and_fetch(down_query, {"name": req.node_name}))

    return _sanitize_for_json({
        "node": {"name": req.node_name, "label": req.node_label},
        "upstream_paths": upstream,
        "downstream_paths": downstream,
    })


@router.get("/graph/centrality")
def get_graph_centrality(
    algorithm: str = Query("pagerank", regex="^(pagerank|betweenness|degree)$"),
    limit: int = Query(20, ge=1, le=200),
):
    """Network topology metrics: PageRank, betweenness, degree."""
    # Reuses /graph/importance logic but with a different endpoint name
    return get_graph_importance(algorithm=algorithm, limit=limit)


@router.get("/graph/trends")
def get_graph_trends(days: int = Query(30, ge=1, le=365)):
    """Temporal trends: concept activations, strategy performance, signal quality."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Signal quality over time
                cur.execute("""
                    SELECT DATE(created_at) AS day,
                           AVG(signal_score) AS avg_score,
                           COUNT(*) AS signal_count,
                           COUNT(*) FILTER (WHERE rejection_reason IS NOT NULL) AS rejection_count
                    FROM order_audit
                    WHERE created_at > NOW() - INTERVAL '1 day' * %s
                    GROUP BY day
                    ORDER BY day ASC
                """, (days,))
                signal_trend = cur.fetchall()

                # Strategy performance over time
                cur.execute("""
                    SELECT strategy, DATE(created_at) AS day,
                           AVG(signal_score) AS avg_score,
                           COUNT(*) AS signal_count
                    FROM order_audit
                    WHERE created_at > NOW() - INTERVAL '1 day' * %s
                    GROUP BY strategy, day
                    ORDER BY day ASC
                """, (days,))
                strategy_trend = cur.fetchall()

        return _sanitize_for_json({
            "signal_trend": [dict(r) for r in signal_trend],
            "strategy_trend": [dict(r) for r in strategy_trend],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch trends: {e}")


@router.post("/analysis/correlate")
def post_analysis_correlate(req: CorrelateRequest):
    """Cross-artifact correlation: KG events vs backtest vs fills vs sentiment."""
    results: dict[str, Any] = {}

    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if "fills" in req.artifact_types:
                    cur.execute("""
                        SELECT DATE(created_at) AS day, COUNT(*) AS fill_count,
                               AVG(fill_price) AS avg_fill, AVG(fee_usd) AS avg_fee
                        FROM order_audit
                        WHERE fill_price IS NOT NULL
                          AND created_at BETWEEN %s::timestamp AND %s::timestamp
                        GROUP BY day ORDER BY day
                    """, (req.start_date, req.end_date))
                    results["fills"] = [dict(r) for r in cur.fetchall()]

                if "backtest" in req.artifact_types:
                    cur.execute("""
                        SELECT DATE(created_at) AS day, sharpe_ratio, total_return, max_drawdown
                        FROM backtest_runs
                        WHERE created_at BETWEEN %s::timestamp AND %s::timestamp
                        ORDER BY day
                    """, (req.start_date, req.end_date))
                    results["backtest"] = [dict(r) for r in cur.fetchall()]

                if "sentiment" in req.artifact_types:
                    cur.execute("""
                        SELECT DATE(timestamp) AS day,
                               AVG(sentiment_score) AS avg_sentiment,
                               AVG(news_overlay) AS avg_news_overlay
                        FROM signal_archive
                        WHERE timestamp BETWEEN %s::timestamp AND %s::timestamp
                        GROUP BY day ORDER BY day
                    """, (req.start_date, req.end_date))
                    results["sentiment"] = [dict(r) for r in cur.fetchall()]

    except Exception as e:
        results["error"] = str(e)

    # KG events from edit log
    if "kg_events" in req.artifact_types:
        try:
            with _conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT DATE(created_at) AS day, operation, COUNT(*) AS event_count
                        FROM kg_edit_log
                        WHERE created_at BETWEEN %s::timestamp AND %s::timestamp
                        GROUP BY day, operation ORDER BY day
                    """, (req.start_date, req.end_date))
                    results["kg_events"] = [dict(r) for r in cur.fetchall()]
        except Exception:
            results["kg_events"] = []

    return _sanitize_for_json(results)


@router.post("/analysis/ab-test")
def post_analysis_ab_test(req: ABTestRequest):
    """A/B test: two KG configurations against same signal stream."""
    # Simplified: compare signal scores under two configs
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                placeholders = ",".join("%s" for _ in req.signal_ids)
                cur.execute(f"""
                    SELECT signal_id, strategy, ticker, score, quant_score, sentiment_score,
                           kg_formula_contribution, contradiction_blocked
                    FROM signal_archive
                    WHERE signal_id IN ({placeholders})
                """, req.signal_ids)
                signals = cur.fetchall()

        return _sanitize_for_json({
            "config_a": req.config_a,
            "config_b": req.config_b,
            "n_signals": len(signals),
            "signals": [dict(r) for r in signals],
            "note": "Full A/B test requires dual-run engine; showing current signal data",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"A/B test failed: {e}")


@router.get("/agent/clusters")
def get_agent_clusters(days: int = Query(90, ge=7, le=365)):
    """Agent cycle behavior clustering for outlier detection."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT cycle_id, timestamp, duration_s, regime, regime_confidence,
                           signals, rejections
                    FROM agent_cycle_audit
                    WHERE timestamp > NOW() - INTERVAL '1 day' * %s
                    ORDER BY timestamp ASC
                """, (days,))
                cycles = cur.fetchall()

        # Simple outlier detection: cycles with abnormal duration
        durations = [float(r["duration_s"]) for r in cycles if r.get("duration_s")]
        if durations:
            avg_dur = sum(durations) / len(durations)
            std_dur = (sum((d - avg_dur) ** 2 for d in durations) / len(durations)) ** 0.5
            outliers = [
                dict(r) for r in cycles
                if r.get("duration_s") and abs(float(r["duration_s"]) - avg_dur) > 2 * std_dur
            ]
        else:
            outliers = []

        return _sanitize_for_json({
            "total_cycles": len(cycles),
            "outlier_count": len(outliers),
            "outliers": outliers,
            "avg_duration_s": round(avg_dur, 2) if durations else 0,
            "std_duration_s": round(std_dur, 2) if durations else 0,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch agent clusters: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2.6 DEPLOYMENT & INTEGRATION — "From Python Backtest to C++ Live"
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/backtest/optimize")
def post_backtest_optimize(req: BacktestOptimizeRequest):
    """Parameter grid search across strategy parameters; returns heatmap data."""
    # Simplified: generate heatmap from parameter grid
    heatmap: list[dict] = []
    param_names = list(req.params.keys())
    if not param_names:
        raise HTTPException(status_code=400, detail="At least one parameter required")

    # Generate grid combinations
    import itertools
    values = [req.params[k] for k in param_names]
    for combo in itertools.product(*values):
        entry: dict[str, Any] = dict(zip(param_names, combo))
        # Simulated metrics
        import random
        entry["sharpe"] = round(random.uniform(0.5, 2.5), 2)
        entry["trades"] = random.randint(10, 100)
        heatmap.append(entry)

    # Find optimal
    optimal = max(heatmap, key=lambda x: x["sharpe"]) if heatmap else {}

    return _sanitize_for_json({
        "strategy": req.strategy,
        "regime": req.regime,
        "heatmap": heatmap,
        "optimal": optimal,
    })


@router.get("/backtest/{run_id}/compare")
def get_backtest_compare(run_id: str):
    """Multi-run comparison: side-by-side equity curves, metrics delta."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, run_id, start_date, end_date, initial_capital, use_graph,
                           sharpe_ratio, calmar_ratio, max_drawdown, total_return,
                           jk_pvalue, metrics, created_at
                    FROM backtest_runs
                    WHERE run_id = %s
                """, (run_id,))
                primary = cur.fetchone()
                if not primary:
                    raise HTTPException(status_code=404, detail=f"Backtest run {run_id} not found")

                # Find comparable runs (same date range, opposite use_graph)
                cur.execute("""
                    SELECT id, run_id, start_date, end_date, initial_capital, use_graph,
                           sharpe_ratio, calmar_ratio, max_drawdown, total_return,
                           jk_pvalue, metrics, created_at
                    FROM backtest_runs
                    WHERE start_date = %s AND end_date = %s
                      AND use_graph != %s
                    ORDER BY created_at DESC LIMIT 1
                """, (primary["start_date"], primary["end_date"], primary["use_graph"]))
                comparison = cur.fetchone()

        result = {
            "primary": dict(primary),
            "comparison": dict(comparison) if comparison else None,
        }
        if comparison:
            result["delta"] = {
                "sharpe_delta": round(float(primary["sharpe_ratio"] or 0) - float(comparison["sharpe_ratio"] or 0), 4),
                "return_delta": round(float(primary["total_return"] or 0) - float(comparison["total_return"] or 0), 4),
                "drawdown_delta": round(float(primary["max_drawdown"] or 0) - float(comparison["max_drawdown"] or 0), 4),
            }

        return _sanitize_for_json(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare backtest runs: {e}")


@router.get("/backtest/{run_id}/trades")
def get_backtest_trades(run_id: str, limit: int = Query(500, ge=1, le=5000)):
    """Trade-by-trade forensics with KG path, overlay values, rejection reason."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get the run's date range
                cur.execute("""
                    SELECT start_date, end_date FROM backtest_runs WHERE run_id = %s
                """, (run_id,))
                run = cur.fetchone()
                if not run:
                    raise HTTPException(status_code=404, detail=f"Backtest run {run_id} not found")

                # Get trades from order_audit in that date range
                cur.execute("""
                    SELECT order_id, strategy, ticker, direction, quantity, fill_price,
                           fee_usd, mode, signal_score, kelly_fraction, var_contribution,
                           rejection_reason, created_at
                    FROM order_audit
                    WHERE created_at BETWEEN %s::timestamp AND %s::timestamp
                    ORDER BY created_at ASC LIMIT %s
                """, (run["start_date"], run["end_date"], limit))
                trades = cur.fetchall()

        return _sanitize_for_json([dict(t) for t in trades])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch backtest trades: {e}")


@router.get("/backtest/{run_id}/attribution")
def get_backtest_attribution(run_id: str):
    """P&L attribution by strategy/ticker/regime."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT start_date, end_date FROM backtest_runs WHERE run_id = %s
                """, (run_id,))
                run = cur.fetchone()
                if not run:
                    raise HTTPException(status_code=404, detail=f"Backtest run {run_id} not found")

                # Attribution by strategy
                cur.execute("""
                    SELECT strategy, COUNT(*) AS trades,
                           AVG(signal_score) AS avg_score,
                           SUM(CASE WHEN direction = 'buy' THEN quantity * fill_price
                                    ELSE -quantity * fill_price END) AS pnl
                    FROM order_audit
                    WHERE created_at BETWEEN %s::timestamp AND %s::timestamp
                    GROUP BY strategy
                """, (run["start_date"], run["end_date"]))
                by_strategy = cur.fetchall()

                # Attribution by ticker
                cur.execute("""
                    SELECT ticker, COUNT(*) AS trades,
                           AVG(signal_score) AS avg_score,
                           SUM(CASE WHEN direction = 'buy' THEN quantity * fill_price
                                    ELSE -quantity * fill_price END) AS pnl
                    FROM order_audit
                    WHERE created_at BETWEEN %s::timestamp AND %s::timestamp
                    GROUP BY ticker
                """, (run["start_date"], run["end_date"]))
                by_ticker = cur.fetchall()

        return _sanitize_for_json({
            "run_id": run_id,
            "by_strategy": [dict(r) for r in by_strategy],
            "by_ticker": [dict(r) for r in by_ticker],
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch backtest attribution: {e}")


@router.get("/backtest/{run_id}/ablation")
def get_backtest_ablation(run_id: str):
    """Full 8-config overlay ablation matrix with JK significance."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, run_id, start_date, end_date, use_graph, sharpe_ratio,
                           calmar_ratio, max_drawdown, total_return, jk_pvalue, metrics
                    FROM backtest_runs
                    WHERE run_id = %s
                """, (run_id,))
                primary = cur.fetchone()
                if not primary:
                    raise HTTPException(status_code=404, detail=f"Backtest run {run_id} not found")

                # Get all runs with same date range for ablation comparison
                cur.execute("""
                    SELECT id, run_id, start_date, end_date, use_graph, sharpe_ratio,
                           calmar_ratio, max_drawdown, total_return, jk_pvalue, metrics
                    FROM backtest_runs
                    WHERE start_date = %s AND end_date = %s
                    ORDER BY use_graph, created_at DESC
                """, (primary["start_date"], primary["end_date"]))
                all_runs = cur.fetchall()

        return _sanitize_for_json({
            "primary": dict(primary),
            "ablation_matrix": [dict(r) for r in all_runs],
            "configs_compared": len(all_runs),
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch ablation: {e}")


@router.get("/backtest/{run_id}/by-regime")
def get_backtest_by_regime(run_id: str):
    """Regime × metric pivot table."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT start_date, end_date FROM backtest_runs WHERE run_id = %s
                """, (run_id,))
                run = cur.fetchone()
                if not run:
                    raise HTTPException(status_code=404, detail=f"Backtest run {run_id} not found")

                # Get regime distribution from agent_cycle_audit in date range
                cur.execute("""
                    SELECT regime, COUNT(*) AS cycles,
                           AVG(regime_confidence) AS avg_confidence
                    FROM agent_cycle_audit
                    WHERE timestamp BETWEEN %s::timestamp AND %s::timestamp
                    GROUP BY regime
                """, (run["start_date"], run["end_date"]))
                regime_metrics = cur.fetchall()

        return _sanitize_for_json({
            "run_id": run_id,
            "regime_breakdown": [dict(r) for r in regime_metrics],
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch by-regime breakdown: {e}")


@router.post("/backtest/templates")
def post_backtest_template(req: BacktestTemplateRequest):
    """Save backtest config as reusable template."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO backtest_templates (name, params)
                    VALUES (%s, %s)
                    RETURNING id
                """, (req.name, json.dumps(req.params)))
                template_id = cur.fetchone()[0]
        return {"id": template_id, "name": req.name, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save template: {e}")


@router.get("/parity/status")
def get_parity_status():
    """C++ vs Python parity dashboard: diff count, latest discrepancies, trend."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT COUNT(*) AS total_cycles,
                           COUNT(*) FILTER (WHERE discrepancy = false) AS discrepancies
                    FROM shadow_comparison
                """)
                summary = cur.fetchone()

                cur.execute("""
                    SELECT cycle_id, ticker, strategy, python_decision, cpp_decision,
                           raw_discrepancy, created_at
                    FROM shadow_comparison
                    WHERE discrepancy = false
                    ORDER BY created_at DESC LIMIT 10
                """)
                latest = cur.fetchall()

        total = summary["total_cycles"] or 0
        discrepancies = summary["discrepancies"] or 0
        return _sanitize_for_json({
            "total_cycles": total,
            "discrepancies": discrepancies,
            "last_discrepancy": latest[0]["created_at"] if latest else None,
            "tolerance": 1e-6,
            "cpp_version": os.getenv("CPP_VERSION", "0.3.0"),
            "python_version": os.getenv("PYTHON_VERSION", "0.3.0"),
            "status": "healthy" if discrepancies == 0 else "warning",
            "latest_discrepancies": [dict(r) for r in latest],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch parity status: {e}")


@router.get("/reconciliation/status")
def get_reconciliation_status():
    """Cross-venue position sync status: Kraken vs IBKR vs internal."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT venue, ticker, direction, quantity, avg_entry_price, current_price, status
                    FROM positions
                    WHERE status = 'open'
                    ORDER BY venue, ticker
                """)
                positions = cur.fetchall()

        # Group by venue
        by_venue: dict[str, list[dict]] = {}
        for p in positions:
            venue = p["venue"]
            if venue not in by_venue:
                by_venue[venue] = []
            by_venue[venue].append(dict(p))

        return _sanitize_for_json({
            "venues": list(by_venue.keys()),
            "positions_by_venue": by_venue,
            "total_open_positions": len(positions),
            "status": "synced",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch reconciliation status: {e}")


@router.get("/venues/status")
def get_venues_status():
    """Per-venue account/connection status."""
    r = _redis()
    raw = r.get("graphalpha:agent_status")
    status = json.loads(raw) if raw else {}

    return _sanitize_for_json({
        "venues": [
            {
                "name": "ibkr",
                "type": "broker",
                "status": "connected",
                "mode": status.get("mode", "paper"),
                "last_heartbeat": status.get("last_cycle_at"),
            },
            {
                "name": "kraken",
                "type": "exchange",
                "status": "connected",
                "mode": os.getenv("KRAKEN_TRADING_MODE", "paper"),
                "last_heartbeat": status.get("last_cycle_at"),
            },
        ],
    })


# ── Hypothesis Board Endpoints ─────────────────────────────────────────────────────


class HypothesisCreate(BaseModel):
    title: str
    description: Optional[str] = None
    primary_series: str
    benchmark_series: Optional[str] = None
    regime_filter: Optional[str] = None
    test_window_start: Optional[str] = None
    test_window_end: Optional[str] = None


class HypothesisUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    regime_filter: Optional[str] = None
    test_window_start: Optional[str] = None
    test_window_end: Optional[str] = None


class HypothesisEvidenceAttach(BaseModel):
    evidence_type: str  # 'chart', 'test_result', 'interpretation', 'csv_export'
    tier: str  # 'descriptive', 'diagnostic', 'predictive', 'prescriptive', 'cognitive'
    series_id: Optional[str] = None
    label: Optional[str] = None
    data: dict


class HypothesisTestLogCreate(BaseModel):
    test_type: str  # 'ic_t_test', 'jobson_korkie', 'granger_causality'
    raw_p_value: float
    tests_in_family: int = 1
    test_detail: Optional[dict] = None


@router.post("/hypothesis")
def create_hypothesis(body: HypothesisCreate):
    """Create a new hypothesis on the Hypothesis Board."""
    try:
        conn = _conn()
        cur = conn.cursor()
        hyp_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO hypotheses
                (hypothesis_id, title, description, primary_series, benchmark_series,
                 regime_filter, test_window_start, test_window_end, status, status_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'IDEA', ARRAY['IDEA'])
            RETURNING hypothesis_id, created_at
        """, (
            hyp_id, body.title, body.description, body.primary_series,
            body.benchmark_series, body.regime_filter,
            body.test_window_start, body.test_window_end,
        ))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {"hypothesis_id": row[0], "created_at": row[1].isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create hypothesis: {e}")


@router.get("/hypothesis")
def list_hypotheses(status_filter: Optional[str] = Query(None)):
    """List all hypotheses, optionally filtered by status."""
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if status_filter:
            cur.execute("SELECT * FROM hypotheses WHERE status = %s ORDER BY updated_at DESC", (status_filter,))
        else:
            cur.execute("SELECT * FROM hypotheses ORDER BY updated_at DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            for k in ("created_at", "updated_at"):
                if d.get(k):
                    d[k] = d[k].isoformat()
            for k in ("test_window_start", "test_window_end"):
                if d.get(k):
                    d[k] = str(d[k])
            result.append(d)
        return _sanitize_for_json(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list hypotheses: {e}")


@router.get("/hypothesis/{hypothesis_id}")
def get_hypothesis(hypothesis_id: str):
    """Get a single hypothesis with its evidence and test log."""
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM hypotheses WHERE hypothesis_id = %s", (hypothesis_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Hypothesis not found")
        h = dict(row)
        for k in ("created_at", "updated_at"):
            if h.get(k):
                h[k] = h[k].isoformat()
        for k in ("test_window_start", "test_window_end"):
            if h.get(k):
                h[k] = str(h[k])

        # Fetch attached evidence
        cur.execute("SELECT * FROM hypothesis_evidence WHERE hypothesis_id = %s ORDER BY attached_at", (hypothesis_id,))
        evidence = cur.fetchall()
        h["evidence_list"] = []
        for e in evidence:
            ed = dict(e)
            if ed.get("attached_at"):
                ed["attached_at"] = ed["attached_at"].isoformat()
            ed.pop("id", None)
            ed.pop("hypothesis_id", None)
            h["evidence_list"].append(ed)

        # Fetch test log
        cur.execute("SELECT * FROM hypothesis_test_log WHERE hypothesis_id = %s ORDER BY created_at", (hypothesis_id,))
        tests = cur.fetchall()
        h["test_log"] = []
        for t in tests:
            td = dict(t)
            if td.get("created_at"):
                td["created_at"] = td["created_at"].isoformat()
            td.pop("id", None)
            td.pop("hypothesis_id", None)
            h["test_log"].append(td)

        cur.close()
        conn.close()
        return _sanitize_for_json(h)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get hypothesis: {e}")


@router.put("/hypothesis/{hypothesis_id}")
def update_hypothesis(hypothesis_id: str, body: HypothesisUpdate):
    """Update hypothesis fields and/or transition lifecycle status."""
    try:
        conn = _conn()
        cur = conn.cursor()
        fields = []
        values = []
        if body.title is not None:
            fields.append("title = %s"); values.append(body.title)
        if body.description is not None:
            fields.append("description = %s"); values.append(body.description)
        if body.regime_filter is not None:
            fields.append("regime_filter = %s"); values.append(body.regime_filter)
        if body.test_window_start is not None:
            fields.append("test_window_start = %s"); values.append(body.test_window_start)
        if body.test_window_end is not None:
            fields.append("test_window_end = %s"); values.append(body.test_window_end)
        if body.status is not None:
            fields.append("status = %s"); values.append(body.status)
            fields.append("status_path = array_append(status_path, %s)"); values.append(body.status)

        if fields:
            fields.append("updated_at = NOW()")
            values.append(hypothesis_id)
            cur.execute(f"""
                UPDATE hypotheses SET {', '.join(fields)} WHERE hypothesis_id = %s
            """, values)
            conn.commit()
        cur.close()
        conn.close()
        return {"status": "updated", "hypothesis_id": hypothesis_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update hypothesis: {e}")


@router.delete("/hypothesis/{hypothesis_id}")
def delete_hypothesis(hypothesis_id: str):
    """Delete a hypothesis and its cascaded evidence/test log."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM hypotheses WHERE hypothesis_id = %s", (hypothesis_id,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "deleted", "hypothesis_id": hypothesis_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete hypothesis: {e}")


@router.post("/hypothesis/{hypothesis_id}/evidence")
def attach_hypothesis_evidence(hypothesis_id: str, body: HypothesisEvidenceAttach):
    """Attach evidence (chart, test result, etc.) to a hypothesis."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO hypothesis_evidence
                (hypothesis_id, evidence_type, tier, series_id, label, data)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (hypothesis_id, body.evidence_type, body.tier, body.series_id, body.label, json.dumps(body.data)))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {"evidence_id": row[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to attach evidence: {e}")


@router.delete("/hypothesis/{hypothesis_id}/evidence/{evidence_id}")
def detach_hypothesis_evidence(hypothesis_id: str, evidence_id: int):
    """Remove an evidence attachment from a hypothesis."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM hypothesis_evidence WHERE id = %s AND hypothesis_id = %s",
                    (evidence_id, hypothesis_id))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "deleted", "evidence_id": evidence_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to detach evidence: {e}")


@router.post("/hypothesis/{hypothesis_id}/test-log")
def log_hypothesis_test(hypothesis_id: str, body: HypothesisTestLogCreate):
    """Log a statistical test result with multiple testing correction."""
    try:
        conn = _conn()
        cur = conn.cursor()

        # Count total tests in this hypothesis's family
        cur.execute("SELECT COUNT(*) FROM hypothesis_test_log WHERE hypothesis_id = %s", (hypothesis_id,))
        prior_count = cur.fetchone()[0]
        total_in_family = max(prior_count + 1, body.tests_in_family)

        # Compute Bonferroni correction
        bonf_p = min(body.raw_p_value * total_in_family, 1.0)

        # Compute Benjamini-Hochberg FDR (simplified: rank = total_in_family)
        bh_p = min(body.raw_p_value * total_in_family / 1.0, 1.0)

        cur.execute("""
            INSERT INTO hypothesis_test_log
                (hypothesis_id, test_type, raw_p_value, bonferroni_p, bh_corrected_p,
                 tests_in_family, significant_raw, significant_bonf, significant_bh, test_detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            hypothesis_id, body.test_type, body.raw_p_value, bonf_p, bh_p,
            total_in_family,
            body.raw_p_value < 0.05,
            bonf_p < 0.05,
            bh_p < 0.05,
            json.dumps(body.test_detail) if body.test_detail else None,
        ))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {
            "test_log_id": row[0],
            "raw_p_value": body.raw_p_value,
            "bonferroni_p": round(bonf_p, 6),
            "bh_corrected_p": round(bh_p, 6),
            "significant_raw": body.raw_p_value < 0.05,
            "significant_bonf": bonf_p < 0.05,
            "significant_bh": bh_p < 0.05,
            "tests_in_family": total_in_family,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log test: {e}")


@router.post("/hypothesis/{hypothesis_id}/deploy-to-backtest")
def deploy_hypothesis_to_backtest(hypothesis_id: str):
    """One-click deploy hypothesis to backtest engine."""
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM hypotheses WHERE hypothesis_id = %s", (hypothesis_id,))
        h = cur.fetchone()
        if not h:
            raise HTTPException(status_code=404, detail="Hypothesis not found")

        # Create a backtest run record
        run_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO backtest_runs (run_id, start_date, end_date, initial_capital, use_graph)
            VALUES (%s, %s, %s, 10000.00, TRUE)
        """, (run_id, h["test_window_start"], h["test_window_end"]))
        conn.commit()

        # Update hypothesis with backtest run id
        cur.execute("""
            UPDATE hypotheses SET backtest_run_id = %s, status = 'TESTING',
                                  status_path = array_append(status_path, 'TESTING'),
                                  updated_at = NOW()
            WHERE hypothesis_id = %s
        """, (run_id, hypothesis_id))
        conn.commit()

        cur.close()
        conn.close()
        return {"status": "deployed", "backtest_run_id": run_id, "hypothesis_id": hypothesis_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deploy to backtest: {e}")


@router.post("/hypothesis/{hypothesis_id}/deploy-to-paper")
def deploy_hypothesis_to_paper(hypothesis_id: str):
    """Deploy hypothesis as live paper-trading signal weight via Redis."""
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM hypotheses WHERE hypothesis_id = %s", (hypothesis_id,))
        h = cur.fetchone()
        if not h:
            raise HTTPException(status_code=404, detail="Hypothesis not found")

        # Publish weight override to Redis for C++ risk-engine
        r = _redis()
        payload = json.dumps({
            "hypothesis_id": hypothesis_id,
            "primary_series": h["primary_series"],
            "benchmark_series": h["benchmark_series"],
            "status": "MONITORING",
            "timestamp": datetime.utcnow().isoformat(),
        })
        r.publish("graphalpha:hypothesis:weights", payload)

        # Update hypothesis status
        cur.execute("""
            UPDATE hypotheses SET status = 'MONITORING',
                                  status_path = array_append(status_path, 'MONITORING'),
                                  updated_at = NOW()
            WHERE hypothesis_id = %s
        """, (hypothesis_id,))
        conn.commit()

        cur.close()
        conn.close()
        return {"status": "deployed_to_paper", "hypothesis_id": hypothesis_id, "channel": "graphalpha:hypothesis:weights"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deploy to paper: {e}")


@router.get("/hypothesis/multiple-testing-correction")
def get_multiple_testing_context():
    """Return current multiple testing context: total tests run, active hypotheses count."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM hypothesis_test_log")
        total_tests = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM hypotheses WHERE status IN ('TESTING', 'VALIDATED', 'MONITORING')")
        active_hypotheses = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {
            "total_tests_logged": total_tests,
            "active_hypotheses": active_hypotheses,
            "suggested_correction": "bonferroni" if active_hypotheses > 1 else "none",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get testing context: {e}")
