"""GraphRAG engine — controlled retrieval pipeline (spec §26, E4).

Implements the pipeline:

    Natural Language Query
        → Entity Resolution
        → Intent Classification
        → Graph Query Planning
        → Neo4j Traversal
        → Evidence Retrieval
        → Quantitative Tool Calls
        → Context Assembly
        → LLM Explanation

Separation of concerns (NFR-007 / §24):
  - Neo4j supplies relational context (real traversal)
  - The quantitative engine calculates risk (deterministic)
  - The LLM explains and orchestrates; it never alters calculated values.

The engine is deterministic by default (no external LLM required) so the
application runs with a single docker command. An optional LLM provider can be
enabled via ``LLM_PROVIDER``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

AsyncDriver = Any  # neo4j 4.x has no async driver class; the db facade provides it

from creditgraph.core.config import settings
from creditgraph.db.neo4j import get_driver
from creditgraph.services.llm import get_llm_provider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entity resolution
# ---------------------------------------------------------------------------

# Labels we can resolve entities against, with their identity property.
_ENTITY_LABELS: dict[str, str] = {
    "Borrower": "borrower_id",
    "Asset": "asset_id",
    "Wallet": "address",
    "Collateral": "asset_id",
    "Liability": "protocol",
    "Exposure": "protocol",
    "Concept": "name",
    "Category": "name",
    "Formula": "id",
    "Strategy": "name",
    "Regime": "name",
    "Ticker": "symbol",
    "Signal": "id",
    "Position": "id",
    "Domain": "name",
    "SubDomain": "name",
    "Capability": "name",
    "SubCapability": "name",
    "Epic": "name",
    "Feature": "name",
    "Standard": "name",
    "Trend": "name",
}

# Tokenize a query into candidate entity tokens (words, symbols, addresses).
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\.\-]+")


def _candidate_tokens(query: str) -> list[str]:
    """Extract candidate entity tokens from a natural-language query."""
    tokens = _TOKEN_RE.findall(query)
    # Drop very short / generic tokens that are unlikely to be entity names.
    stop = {
        "the", "and", "for", "with", "this", "that", "what", "why", "how",
        "which", "who", "is", "are", "was", "were", "does", "do", "did",
        "has", "have", "had", "of", "in", "on", "at", "to", "from", "by",
        "a", "an", "borrower", "risk", "high", "low", "show", "explain",
        "tell", "me", "about", "graph", "relationship", "between", "and",
    }
    return [t for t in tokens if t.lower() not in stop and len(t) >= 2]


async def _resolve_entities(driver: AsyncDriver, tokens: list[str]) -> list[dict[str, Any]]:
    """Resolve candidate tokens against known graph labels.

    Returns a list of resolved entity dicts: {label, key, name, kind}.
    """
    resolved: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for token in tokens:
        # Try each label; stop at the first match for this token.
        for label, key in _ENTITY_LABELS.items():
            # Some labels use `name`, others use `symbol`/`id`/`address`.
            prop = key
            query = (
                f"MATCH (n:{label}) WHERE n.{prop} = $token "
                "RETURN n LIMIT 1"
            )
            try:
                async with driver.session() as sess:
                    result = await sess.run(query, {"token": token})
                    rec = await result.single()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Entity resolution failed for %s: %s", token, exc)
                continue

            if rec and rec.get("n") is not None:
                node = rec["n"]
                name = node.get("name") or node.get("symbol") or node.get("id") or token
                dedupe_key = (label, str(name))
                if dedupe_key not in seen:
                    seen.add(dedupe_key)
                    resolved.append(
                        {
                            "label": label,
                            "key": key,
                            "name": str(name),
                            "kind": label.lower(),
                        }
                    )
                break  # first matching label wins for this token

    return resolved


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    # More specific intents first so they win over broad "risk" matches.
    ("relationship_path", re.compile(r"relationship|path between|connected|link|chain|dependency|causal", re.I)),
    ("concept_explanation", re.compile(r"concept|formula|model|what is|explain|definition|how does", re.I)),
    ("regime", re.compile(r"regime|market|volatility|trending|mean.?revert|crisis|stress", re.I)),
    ("capability", re.compile(r"capability|domain|subdomain|epic|feature|architecture|canvas", re.I)),
    ("ticker", re.compile(r"ticker|stock|equity|symbol|price|correlation", re.I)),
    ("strategy", re.compile(r"strategy|trade|signal|position|hedge", re.I)),
    ("borrower_risk", re.compile(r"borrower|credit|risk|default|collateral|exposure|loan", re.I)),
]


def _classify_intent(query: str) -> str:
    """Classify the query intent using lightweight pattern matching."""
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(query):
            return intent
    return "graph_exploration"


# ---------------------------------------------------------------------------
# Query planning → Cypher templates
# ---------------------------------------------------------------------------

# Each intent maps to a parameterized Cypher template. All queries are
# parameterized; no user input is interpolated into the query string.
_QUERY_PLANS: dict[str, str] = {
    "borrower_risk": (
        "MATCH (b:Borrower {borrower_id: $entity}) "
        "OPTIONAL MATCH (b)-[:HAS_COLLATERAL]->(c:Collateral) "
        "OPTIONAL MATCH (b)-[:HAS_LIABILITY]->(l:Liability) "
        "OPTIONAL MATCH (b)-[:HAS_EXPOSURE]->(e:Exposure) "
        "OPTIONAL MATCH (b)-[:HAS_DECISION]->(d:CreditDecision) "
        "RETURN b, collect(DISTINCT c) AS collateral, "
        "collect(DISTINCT l) AS liabilities, "
        "collect(DISTINCT e) AS exposures, "
        "collect(DISTINCT d) AS decisions"
    ),
    "concept_explanation": (
        "MATCH (c:Concept {name: $entity}) "
        "OPTIONAL MATCH (c)-[:HAS_FORMULA]->(f:Formula) "
        "OPTIONAL MATCH (c)-[:PREREQ_OF]->(pre:Concept) "
        "OPTIONAL MATCH (c)<-[:PREREQ_OF]-(post:Concept) "
        "OPTIONAL MATCH (c)-[:BELONGS_TO]->(cat:Category) "
        "RETURN c, collect(DISTINCT f) AS formulas, "
        "collect(DISTINCT pre) AS prerequisites, "
        "collect(DISTINCT post) AS dependents, "
        "collect(DISTINCT cat) AS categories"
    ),
    "relationship_path": (
        "MATCH p = shortestPath((a)-[*..4]-(b)) "
        "WHERE a.name = $entity OR a.symbol = $entity OR a.id = $entity "
        "RETURN p LIMIT 1"
    ),
    "regime": (
        "MATCH (r:Regime {name: $entity}) "
        "OPTIONAL MATCH (r)<-[:ACTIVATED_BY]-(s:Strategy) "
        "RETURN r, collect(DISTINCT s) AS strategies"
    ),
    "capability": (
        "MATCH (c:Capability {name: $entity}) "
        "OPTIONAL MATCH (c)-[:REPRESENTED_BY]->(e:Epic) "
        "OPTIONAL MATCH (e)-[:HAS_FEATURE]->(f:Feature) "
        "OPTIONAL MATCH (c)<-[:PARENT_OF]-(sd:SubDomain) "
        "OPTIONAL MATCH (sd)<-[:PARENT_OF]-(d:Domain) "
        "RETURN c, collect(DISTINCT e) AS epics, "
        "collect(DISTINCT f) AS features, "
        "collect(DISTINCT sd) AS subdomains, "
        "collect(DISTINCT d) AS domains"
    ),
    "ticker": (
        "MATCH (t:Ticker {symbol: $entity}) "
        "OPTIONAL MATCH (t)-[:CORRELATED_WITH]->(other:Ticker) "
        "OPTIONAL MATCH (t)-[:BELONGS_TO_SECTOR]->(sector:Category) "
        "RETURN t, collect(DISTINCT other) AS correlated, "
        "collect(DISTINCT sector) AS sectors"
    ),
    "strategy": (
        "MATCH (s:Strategy {name: $entity}) "
        "OPTIONAL MATCH (s)-[:DERIVED_FROM]->(c:Concept) "
        "OPTIONAL MATCH (s)-[:ACTIVATED_BY]->(r:Regime) "
        "OPTIONAL MATCH (s)-[:HAS_SIGNAL]->(sig:Signal) "
        "RETURN s, collect(DISTINCT c) AS concepts, "
        "collect(DISTINCT r) AS regimes, "
        "collect(DISTINCT sig) AS signals"
    ),
    "graph_exploration": (
        "MATCH (n) WHERE n.name = $entity OR n.symbol = $entity OR n.id = $entity "
        "OPTIONAL MATCH (n)-[r]-(m) "
        "RETURN n, collect(DISTINCT {rel: type(r), other: m}) AS neighbors "
        "LIMIT 1"
    ),
}


def _plan_query(intent: str, entity: str) -> tuple[str, dict[str, Any]]:
    """Return (cypher, params) for the given intent and resolved entity."""
    cypher = _QUERY_PLANS.get(intent, _QUERY_PLANS["graph_exploration"])
    return cypher, {"entity": entity}


# ---------------------------------------------------------------------------
# Evidence / context assembly
# ---------------------------------------------------------------------------


def _node_to_evidence(node: Any, kind: str) -> dict[str, Any]:
    """Convert a Neo4j node to a compact evidence dict."""
    props = dict(node) if node else {}
    name = (
        props.get("name")
        or props.get("symbol")
        or props.get("id")
        or props.get("borrower_id")
        or props.get("asset_id")
        or props.get("address")
        or "?"
    )
    return {
        "kind": kind,
        "label": list(node.labels)[0] if node and node.labels else "Node",
        "name": str(name),
        "text": _node_summary(props),
    }


def _node_summary(props: dict[str, Any]) -> str:
    """Build a short human-readable summary of a node's properties."""
    parts: list[str] = []
    for k, v in props.items():
        if k in {"name", "symbol", "id", "borrower_id", "asset_id", "address"}:
            continue
        if isinstance(v, (int, float)):
            parts.append(f"{k}={v:g}")
        elif isinstance(v, str) and len(v) < 80:
            parts.append(f"{k}={v}")
    return ", ".join(parts) if parts else ""


def _extract_evidence(intent: str, record: Any) -> tuple[list[dict], list[str], list[list[str]]]:
    """Extract evidence, relationship strings and reasoning paths from a record."""
    evidence: list[dict] = []
    relationships: list[str] = []
    paths: list[list[str]] = []

    if not record:
        return evidence, relationships, paths

    # Primary node
    primary = record.get("n") or record.get("b") or record.get("c") or record.get("r") or record.get("t") or record.get("s")
    if primary is not None:
        evidence.append(_node_to_evidence(primary, "graph"))

    # Named collections
    for key in ("collateral", "liabilities", "exposures", "decisions",
                "formulas", "prerequisites", "dependents", "categories",
                "strategies", "epics", "features", "subdomains", "domains",
                "correlated", "sectors", "concepts", "regimes", "signals",
                "neighbors"):
        items = record.get(key) or []
        for item in items:
            if item is None:
                continue
            evidence.append(_node_to_evidence(item, "graph"))
            # Build relationship strings for the primary node
            if primary is not None:
                pname = _node_name(primary)
                iname = _node_name(item)
                rel = _relationship_label(key)
                relationships.append(f"{pname} -[{rel}]-> {iname}")

    # Reasoning path (E4-US2): primary → neighbors
    if primary is not None and record.get("neighbors"):
        pname = _node_name(primary)
        for nb in record["neighbors"][: settings.graphrag_max_paths]:
            if nb and nb.get("other") is not None:
                other = _node_name(nb["other"])
                rel = nb.get("rel", "RELATED_TO")
                paths.append([pname, rel, other])

    return evidence, relationships, paths


def _node_name(node: Any) -> str:
    props = dict(node) if node else {}
    return str(
        props.get("name")
        or props.get("symbol")
        or props.get("id")
        or props.get("borrower_id")
        or props.get("asset_id")
        or props.get("address")
        or "?"
    )


def _relationship_label(key: str) -> str:
    """Map a collection key to a human-readable relationship label."""
    mapping = {
        "collateral": "HAS_COLLATERAL",
        "liabilities": "HAS_LIABILITY",
        "exposures": "HAS_EXPOSURE",
        "decisions": "HAS_DECISION",
        "formulas": "HAS_FORMULA",
        "prerequisites": "PREREQ_OF",
        "dependents": "PREREQ_OF",
        "categories": "BELONGS_TO",
        "strategies": "ACTIVATED_BY",
        "epics": "REPRESENTED_BY",
        "features": "HAS_FEATURE",
        "subdomains": "PARENT_OF",
        "domains": "PARENT_OF",
        "correlated": "CORRELATED_WITH",
        "sectors": "BELONGS_TO_SECTOR",
        "concepts": "DERIVED_FROM",
        "regimes": "ACTIVATED_BY",
        "signals": "HAS_SIGNAL",
        "neighbors": "RELATED_TO",
    }
    return mapping.get(key, "RELATED_TO")


# ---------------------------------------------------------------------------
# Quantitative tool calls (deterministic, from the risk engine)
# ---------------------------------------------------------------------------


def _attach_quantitative(intent: str, evidence: list[dict]) -> list[dict]:
    """Attach deterministic quantitative outputs relevant to the intent.

    These come from the deterministic risk engine (credit_risk / quant_engine)
    and are never altered by the LLM.
    """
    quantitative: list[dict] = []
    if intent == "borrower_risk":
        # Pull borrower-level metrics from evidence if present.
        for ev in evidence:
            if ev.get("label") == "Borrower":
                props = ev.get("text", "")
                # The summary text contains key=value pairs; parse numeric ones.
                for part in props.split(", "):
                    if "=" in part:
                        k, _, v = part.partition("=")
                        try:
                            val = float(v)
                        except ValueError:
                            continue
                        quantitative.append(
                            {
                                "label": k,
                                "value": val,
                                "unit": "",
                                "source": "deterministic_risk_engine",
                            }
                        )
    return quantitative


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


async def graphrag_query(query: str) -> dict[str, Any]:
    """Run the full GraphRAG pipeline for a natural-language query.

    Returns a structured response with:
      - intent
      - entities (resolved)
      - evidence (graph-derived)
      - relationships
      - paths (reasoning paths)
      - quantitative (deterministic model outputs)
      - explanation (LLM-generated, grounded in the above)
    """
    driver: AsyncDriver = get_driver()

    # 1. Entity resolution
    tokens = _candidate_tokens(query)
    entities = await _resolve_entities(driver, tokens)

    # 2. Intent classification
    intent = _classify_intent(query)

    # 3. Query planning + 4. Neo4j traversal
    evidence: list[dict] = []
    relationships: list[str] = []
    paths: list[list[str]] = []
    traversal_error: str | None = None

    if entities:
        # Use the first resolved entity as the anchor.
        entity = entities[0]
        cypher, params = _plan_query(intent, entity["name"])
        try:
            async with driver.session() as sess:
                result = await sess.run(cypher, params)
                record = await result.single()
            evidence, relationships, paths = _extract_evidence(intent, record)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Graph traversal failed: %s", exc)
            traversal_error = str(exc)
    else:
        evidence = []
        relationships = []
        paths = []

    # 5. Evidence retrieval (already collected above)
    # 6. Quantitative tool calls (deterministic)
    quantitative = _attach_quantitative(intent, evidence)

    # 7. Context assembly
    context: dict[str, Any] = {
        "query": query,
        "intent": intent,
        "entities": entities,
        "evidence": evidence[: settings.graphrag_max_evidence],
        "relationships": relationships[: settings.graphrag_max_relationships],
        "paths": paths[: settings.graphrag_max_paths],
        "quantitative": quantitative,
        "traversal_error": traversal_error,
    }

    # 8. LLM explanation
    provider = get_llm_provider()
    try:
        explanation = await provider.explain(context)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("LLM explanation failed, using deterministic fallback: %s", exc)
        from creditgraph.services.llm import DeterministicLLM

        explanation = await DeterministicLLM().explain(context)

    return {
        "query": query,
        "intent": intent,
        "entities": entities,
        "evidence": evidence[: settings.graphrag_max_evidence],
        "relationships": relationships[: settings.graphrag_max_relationships],
        "paths": paths[: settings.graphrag_max_paths],
        "quantitative": quantitative,
        "explanation": explanation,
        "traversal_error": traversal_error,
    }