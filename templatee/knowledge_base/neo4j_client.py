"""
Neo4j client for the knowledge graph: formulas, concepts, interpretations, menu concepts.
"""

import os
from typing import Any, Optional

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable
except ImportError:
    GraphDatabase = None  # type: ignore
    ServiceUnavailable = Exception  # type: ignore


class KnowledgeNotFoundError(Exception):
    """Raised when a requested formula, concept, or interpretation is not found."""

    pass


def _get_config():
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    except ImportError:
        pass
    return {
        "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        "user": os.getenv("NEO4J_USER", "neo4j"),
        "password": os.getenv("NEO4J_PASSWORD", "pricing-engine-kb"),
    }


_driver = None


def get_neo4j_driver():
    """Return a shared Neo4j driver instance (sync)."""
    global _driver
    if _driver is None:
        if GraphDatabase is None:
            raise RuntimeError("neo4j package not installed")
        cfg = _get_config()
        _driver = GraphDatabase.driver(
            cfg["uri"],
            auth=(cfg["user"], cfg["password"]),
        )
    return _driver


def close_neo4j_driver():
    """Close the shared driver (e.g. on app shutdown)."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


class Neo4jKnowledgeClient:
    """Sync Neo4j client for knowledge graph queries."""

    def __init__(self, driver=None):
        self._driver = driver or get_neo4j_driver()

    def _run(self, query: str, **params) -> list[dict[str, Any]]:
        with self._driver.session() as session:
            result = session.run(query, params)
            return [dict(record) for record in result]

    def get_formula(self, name: str) -> Optional[dict[str, Any]]:
        """Return formula by name: equation, description, variables, assumptions, inference_reasoning."""
        q = """
        MATCH (f:Formula {name: $name})
        RETURN f.name AS name, f.equation AS equation, f.description AS description,
               f.variables AS variables, f.assumptions AS assumptions,
               f.source_file AS source_file, f.inference_reasoning AS inference_reasoning
        """
        rows = self._run(q, name=name)
        if not rows:
            return None
        r = rows[0]
        return {
            "name": r.get("name"),
            "equation": r.get("equation"),
            "description": r.get("description"),
            "variables": r.get("variables") or [],
            "assumptions": r.get("assumptions") or [],
            "source_file": r.get("source_file"),
            "inference_reasoning": r.get("inference_reasoning"),
        }

    def get_metric_interpretation(
        self,
        metric_name: str,
        value: float,
        menu_context: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Return interpretation(s) for a metric value.
        Matches where value is in [min, max] (None min/max treated as unbounded).
        Optionally filter by menu_context. Ordered by confidence DESC.
        """
        q = """
        MATCH (m:Metric {name: $metric_name})-[:INTERPRETS]->(i:Interpretation)
        WHERE (i.min IS NULL OR i.min <= $value)
          AND (i.max IS NULL OR i.max >= $value)
          AND ($menu_context IS NULL OR i.menu_context = $menu_context)
        RETURN i.condition AS condition, i.interpretation AS interpretation,
               i.action AS action, i.confidence AS confidence,
               i.menu_context AS menu_context
        ORDER BY i.confidence DESC
        """
        rows = self._run(
            q,
            metric_name=metric_name,
            value=value,
            menu_context=menu_context,
        )
        return [
            {
                "condition": r.get("condition"),
                "interpretation": r.get("interpretation"),
                "action": r.get("action"),
                "confidence": r.get("confidence"),
                "menu_context": r.get("menu_context"),
            }
            for r in rows
        ]

    def get_menu_concepts(self, menu_name: str) -> list[dict[str, Any]]:
        """Return concepts that belong to a menu (via BELONGS_TO)."""
        # Menu names in graph are e.g. "Pricer", "Portfolio"; accept as-is
        q = """
        MATCH (m:Menu {name: $menu_name})<-[:BELONGS_TO]-(c:Concept)
        RETURN c.name AS name, c.definition AS definition, c.category AS category,
               c.difficulty AS difficulty
        ORDER BY c.difficulty, c.name
        """
        rows = self._run(q, menu_name=menu_name)
        return [
            {
                "name": r.get("name"),
                "definition": r.get("definition"),
                "category": r.get("category"),
                "difficulty": r.get("difficulty"),
            }
            for r in rows
        ]

    def get_related_concepts(
        self,
        concept_name: str,
        depth: int = 2,
    ) -> list[dict[str, Any]]:
        """Return concepts related to the given concept via RELATED_TO or USES (up to depth hops)."""
        q = """
        MATCH (c:Concept {name: $concept_name})-[:RELATED_TO|USES*1..%d]-(related:Concept)
        WHERE related.name <> $concept_name
        RETURN DISTINCT related.name AS name, related.definition AS definition,
               related.category AS category
        ORDER BY related.name
        """ % min(depth, 5)
        rows = self._run(q, concept_name=concept_name)
        return [
            {
                "name": r.get("name"),
                "definition": r.get("definition"),
                "category": r.get("category"),
            }
            for r in rows
        ]

    def get_concept(self, name: str) -> Optional[dict[str, Any]]:
        """Return a single concept by name."""
        q = """
        MATCH (c:Concept {name: $name})
        RETURN c.name AS name, c.definition AS definition, c.category AS category,
               c.difficulty AS difficulty, c.menu_context AS menu_context,
               c.prerequisites AS prerequisites
        """
        rows = self._run(q, name=name)
        if not rows:
            return None
        r = rows[0]
        return {
            "name": r.get("name"),
            "definition": r.get("definition"),
            "category": r.get("category"),
            "difficulty": r.get("difficulty"),
            "menu_context": r.get("menu_context"),
            "prerequisites": r.get("prerequisites"),
        }

    def list_formulas(self) -> list[dict[str, Any]]:
        """Return all formula names and descriptions."""
        q = """
        MATCH (f:Formula) RETURN f.name AS name, f.description AS description
        ORDER BY f.name
        """
        rows = self._run(q)
        return [{"name": r.get("name"), "description": r.get("description")} for r in rows]

    def list_concepts_for_menu(self, menu_name: str) -> list[dict[str, Any]]:
        """Alias for get_menu_concepts."""
        return self.get_menu_concepts(menu_name)

    def get_formula_derivation_graph(self, formula_name: str) -> dict[str, Any]:
        """Return formula with its DERIVES_FROM and USES graph for trace_derivation skill."""
        q = """
        MATCH (f:Formula {name: $name})
        OPTIONAL MATCH (f)-[:DERIVES_FROM]->(parent:Formula)
        OPTIONAL MATCH (f)-[:USES]->(concept:Concept)
        RETURN f.name AS name, f.equation AS equation, f.description AS description,
               collect(DISTINCT parent.name) AS derives_from,
               collect(DISTINCT concept.name) AS uses_concepts
        """
        rows = self._run(q, name=formula_name)
        if not rows:
            return {}
        r = rows[0]
        return {
            "name": r.get("name"),
            "equation": r.get("equation"),
            "description": r.get("description"),
            "derives_from": [x for x in (r.get("derives_from") or []) if x],
            "uses_concepts": [x for x in (r.get("uses_concepts") or []) if x],
        }

    # ── Trading Strategy queries ───────────────────────────────────────────────

    def search_trading_strategies(
        self,
        keyword: Optional[str] = None,
        menu_name: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """
        Search TradingStrategy nodes by keyword, menu, or category.
        Returns list of strategy dicts with full detail for LLM context injection.
        """
        conditions = []
        params: dict[str, Any] = {"limit": limit}
        if keyword:
            kw = keyword.lower()
            conditions.append(
                "(toLower(s.name) CONTAINS $kw OR "
                " toLower(s.description) CONTAINS $kw OR "
                " any(k IN s.keywords WHERE toLower(k) CONTAINS $kw) OR "
                " toLower(s.category) CONTAINS $kw)"
            )
            params["kw"] = kw
        if category:
            conditions.append("s.category = $category")
            params["category"] = category

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        if menu_name:
            q = f"""
            MATCH (s:TradingStrategy)-[:APPLICABLE_TO]->(m:Menu {{name: $menu_name}})
            {where_clause}
            RETURN s.name AS name, s.category AS category, s.description AS description,
                   s.entry_signal AS entry_signal, s.exit_signal AS exit_signal,
                   s.risk_management AS risk_management, s.timeframe AS timeframe,
                   s.asset_class AS asset_class, s.book_source AS book_source,
                   s.book_author AS book_author, s.keywords AS keywords
            LIMIT $limit
            """
            params["menu_name"] = menu_name
        else:
            q = f"""
            MATCH (s:TradingStrategy)
            {where_clause}
            RETURN s.name AS name, s.category AS category, s.description AS description,
                   s.entry_signal AS entry_signal, s.exit_signal AS exit_signal,
                   s.risk_management AS risk_management, s.timeframe AS timeframe,
                   s.asset_class AS asset_class, s.book_source AS book_source,
                   s.book_author AS book_author, s.keywords AS keywords
            LIMIT $limit
            """
        rows = self._run(q, **params)
        return [dict(r) for r in rows]

    def get_strategies_for_menu(self, menu_name: str, limit: int = 6) -> list[dict[str, Any]]:
        """Return all strategies applicable to a given menu."""
        return self.search_trading_strategies(menu_name=menu_name, limit=limit)

    def health_check(self) -> bool:
        """Run a trivial query to verify Neo4j is reachable."""
        try:
            self._run("RETURN 1 AS n")
            return True
        except Exception:
            return False

    # ── RLHF / GraphRAG feedback enrichment ───────────────────────────────────

    def record_user_feedback(
        self,
        session_id: str,
        menu_id: str,
        user_message: str,
        agent_reply: str,
        rating: int,           # 1 (bad) … 5 (excellent); 4/5 = positive; 1/2 = negative
        context_type: Optional[str] = None,   # "formula" | "concept" | "metric" | "workspace"
        context_target: Optional[str] = None, # name of formula/concept/metric if applicable
        corrected_reply: Optional[str] = None, # user-supplied correction (optional)
    ) -> None:
        """
        Persist a UserFeedback node in Neo4j and update knowledge graph confidence.

        Graph shape written:
          (UserFeedback)-[:FEEDBACK_ON_MENU]->(Menu)
          (UserFeedback)-[:FEEDBACK_ON_FORMULA]->(Formula)   [if context_target]
          (UserFeedback)-[:FEEDBACK_ON_CONCEPT]->(Concept)   [if context_target]
          (Interpretation)-[:confidence] boosted/penalised   [positive / negative feedback]
        """
        import datetime
        ts = datetime.datetime.utcnow().isoformat()

        # Upsert UserFeedback node
        create_q = """
        CREATE (fb:UserFeedback {
            session_id: $session_id,
            menu_id:    $menu_id,
            user_message: $user_message,
            agent_reply:  $agent_reply,
            corrected_reply: $corrected_reply,
            rating:      $rating,
            context_type:   $context_type,
            context_target: $context_target,
            timestamp:   $ts
        })
        WITH fb
        MERGE (m:Menu {name: $menu_name})
        CREATE (fb)-[:FEEDBACK_ON_MENU]->(m)
        RETURN fb
        """
        menu_name = MENU_ID_TO_NAME_KB.get(menu_id.lower(), "Transact")
        self._run(
            create_q,
            session_id=session_id,
            menu_id=menu_id,
            user_message=user_message[:2000],
            agent_reply=agent_reply[:4000],
            corrected_reply=(corrected_reply or "")[:4000],
            rating=rating,
            context_type=context_type or "",
            context_target=context_target or "",
            ts=ts,
            menu_name=menu_name,
        )

        # Link to Formula/Concept if known
        if context_target:
            if context_type == "formula":
                link_q = """
                MATCH (fb:UserFeedback {session_id: $sid, timestamp: $ts})
                MATCH (f:Formula {name: $target})
                CREATE (fb)-[:FEEDBACK_ON_FORMULA]->(f)
                """
                try:
                    self._run(link_q, sid=session_id, ts=ts, target=context_target)
                except Exception:
                    pass
            elif context_type == "concept":
                link_q = """
                MATCH (fb:UserFeedback {session_id: $sid, timestamp: $ts})
                MATCH (c:Concept {name: $target})
                CREATE (fb)-[:FEEDBACK_ON_CONCEPT]->(c)
                """
                try:
                    self._run(link_q, sid=session_id, ts=ts, target=context_target)
                except Exception:
                    pass

        # Adjust confidence on Interpretation nodes for positive/negative feedback
        if context_type == "metric" and context_target and rating >= 4:
            boost_q = """
            MATCH (m:Metric)-[:INTERPRETS]->(i:Interpretation)
            WHERE m.name = $target
              AND (i.menu_context IS NULL OR i.menu_context = $menu_name)
            SET i.confidence = coalesce(i.confidence, 0.5) + 0.02
            """
            try:
                self._run(boost_q, target=context_target, menu_name=menu_name)
            except Exception:
                pass
        elif context_type == "metric" and context_target and rating <= 2:
            penalise_q = """
            MATCH (m:Metric)-[:INTERPRETS]->(i:Interpretation)
            WHERE m.name = $target
              AND (i.menu_context IS NULL OR i.menu_context = $menu_name)
            SET i.confidence = coalesce(i.confidence, 0.5) - 0.02
            """
            try:
                self._run(penalise_q, target=context_target, menu_name=menu_name)
            except Exception:
                pass

    def get_recent_feedback(
        self,
        limit: int = 50,
        min_rating: Optional[int] = None,
        menu_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return recent UserFeedback nodes for RLHF enrichment analysis."""
        filters = []
        if min_rating is not None:
            filters.append("fb.rating >= $min_rating")
        if menu_id is not None:
            filters.append("fb.menu_id = $menu_id")
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        q = f"""
        MATCH (fb:UserFeedback)
        {where}
        RETURN fb.session_id AS session_id, fb.menu_id AS menu_id,
               fb.user_message AS user_message, fb.agent_reply AS agent_reply,
               fb.corrected_reply AS corrected_reply, fb.rating AS rating,
               fb.context_type AS context_type, fb.context_target AS context_target,
               fb.timestamp AS timestamp
        ORDER BY fb.timestamp DESC LIMIT $limit
        """
        rows = self._run(q, limit=limit, min_rating=min_rating or 1, menu_id=menu_id or "")
        return [dict(r) for r in rows]

    def upsert_enriched_concept(
        self,
        name: str,
        definition: str,
        category: str,
        menu_name: str,
        source: str = "rlhf_enrichment",
    ) -> None:
        """
        Write or update a Concept node that was discovered/refined via RLHF.
        Sets a 'rlhf_enriched' flag so it can be reviewed.
        """
        q = """
        MERGE (c:Concept {name: $name})
        SET c.definition = $definition,
            c.category   = $category,
            c.rlhf_enriched = true,
            c.rlhf_source   = $source
        WITH c
        MERGE (m:Menu {name: $menu_name})
        MERGE (c)-[:BELONGS_TO]->(m)
        """
        self._run(q, name=name, definition=definition, category=category,
                  menu_name=menu_name, source=source)

    def upsert_enriched_interpretation(
        self,
        metric_name: str,
        condition: str,
        interpretation: str,
        action: str,
        confidence: float,
        menu_context: str,
        source: str = "rlhf_enrichment",
    ) -> None:
        """
        Write or update an Interpretation node based on RLHF feedback.
        Upserts the parent Metric node if it doesn't exist.
        """
        q = """
        MERGE (m:Metric {name: $metric_name})
        WITH m
        MERGE (i:Interpretation {condition: $condition, menu_context: $menu_context})
        SET i.interpretation = $interpretation,
            i.action         = $action,
            i.confidence     = $confidence,
            i.rlhf_enriched  = true,
            i.rlhf_source    = $source
        MERGE (m)-[:INTERPRETS]->(i)
        """
        self._run(
            q, metric_name=metric_name, condition=condition,
            interpretation=interpretation, action=action,
            confidence=confidence, menu_context=menu_context, source=source,
        )

    def save_conversation_session(
        self,
        session_id: str,
        menu_id: str,
        messages: list[dict],
        workspace_snapshot: Optional[dict] = None,
    ) -> None:
        """
        Persist a completed chat session as a ConversationSession node.

        Graph shape:
          (ConversationSession)-[:SESSION_ON_MENU]->(Menu)
          (ConversationSession)-[:HAS_TURN]->(ConversationTurn) × N

        The workspace_snapshot (raw computed results) is stored as a JSON
        string on the session node for later DRL concept-linkage passes.
        """
        import datetime
        import json
        ts = datetime.datetime.utcnow().isoformat()
        menu_name = MENU_ID_TO_NAME_KB.get(menu_id.lower(), "Transact")
        snapshot_json = json.dumps(workspace_snapshot or {})[:8000]  # cap size

        # Create session node
        session_q = """
        CREATE (s:ConversationSession {
            session_id:        $session_id,
            menu_id:           $menu_id,
            menu_name:         $menu_name,
            turn_count:        $turn_count,
            workspace_snapshot:$snapshot,
            created_at:        $ts
        })
        WITH s
        MERGE (m:Menu {name: $menu_name})
        CREATE (s)-[:SESSION_ON_MENU]->(m)
        RETURN s
        """
        self._run(
            session_q,
            session_id=session_id,
            menu_id=menu_id,
            menu_name=menu_name,
            turn_count=len(messages),
            snapshot=snapshot_json,
            ts=ts,
        )

        # Store each turn as a linked node (up to 50 turns)
        for idx, msg in enumerate(messages[:50]):
            turn_q = """
            MATCH (s:ConversationSession {session_id: $session_id})
            CREATE (t:ConversationTurn {
                role:       $role,
                content:    $content,
                turn_index: $idx
            })
            CREATE (s)-[:HAS_TURN]->(t)
            """
            try:
                self._run(
                    turn_q,
                    session_id=session_id,
                    role=msg.get("role", ""),
                    content=msg.get("content", "")[:4000],
                    idx=idx,
                )
            except Exception:
                pass  # partial saves acceptable


# Map used inside the Neo4j client (avoids circular import with skills.py)
MENU_ID_TO_NAME_KB = {
    "overview": "Portfolio",
    "pricer": "Pricer",
    "portfolio": "Portfolio",
    "risk": "Risk",
    "optimizer": "Optimizer",
    "volatility": "Volatility Lab",
    "factor": "Factor Lab",
    "scenarios": "Scenarios",
    "blotter": "Blotter",
}
