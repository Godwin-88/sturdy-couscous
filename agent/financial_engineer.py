"""
Financial Engineer Agent — Hybrid GraphRAG analysis engine.

Retrieves grounded context for the per-screen chat popup:

1. GraphRAG in Neo4j (primary source of truth):
   - fulltext search over reference-book :Section + :Concept nodes
     (ref_section_fulltext / ref_concept_fulltext)
   - graph expansion 1-2 hops along COVERS / PREREQ_OF / HAS_FORMULA /
     BELONGS_TO / ACTIVATED_BY / DERIVED_FROM
   - optional vector search when section/concept embeddings exist
     (ref_*_vector) — fused with fulltext via RRF rank averaging.
2. Live screen data assembled by api/routes/chat.py.
3. LLM synthesis (Groq OpenAI-compatible) with book citations.

This module never executes anything — it only reads the graph + market-data
endpoints and returns a grounded explanation.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

from common.graph import get_db

LLM_URL = os.getenv("GROQ_BASE_URL", os.getenv("FEATHERLESS_BASE_URL", "https://api.groq.com/openai/v1"))
LLM_KEY = os.getenv("GROQ_API_KEY", os.getenv("FEATHERLESS_API_KEY", ""))
LLM_MODEL = os.getenv("GROQ_MODEL", os.getenv("FEATHERLESS_MODEL", "llama-3.3-70b-versatile"))

SYSTEM_PROMPT = """You are a senior financial engineer embedded inside the GraphAlpha trading platform.
You explain what each screen is showing to a quant trader, in plain numeric terms, citing the
knowledge-graph concepts, formulas and reference-book sections that ground your reasoning.

Rules:
- Be specific and numeric. Use the actual values from the screen context (regime confidence,
  signals, greeks, positions, P&L, backtest metrics) rather than generic advice.
- Ground every claim in context: cite sources as {book, chapter, section} and {concept, formula}.
- Discipline: do not recommend placing trades unless explicitly asked; frame hedging/risk in
  Taleb-style tail-risk terms (dynamic delta hedging, defined-risk structures, loss aversion).
- If the data is empty or unconfigured, say so plainly and say what would be needed.
- Keep answers under ~260 words unless the user asks for depth.
"""


def _rrf(rank_lists: list[list[Any]], k: int = 60) -> list[Any]:
    """Reciprocal-rank fusion of several ranked id lists."""
    scores: dict[Any, float] = {}
    for ranked in rank_lists:
        for rank, node in enumerate(ranked):
            scores[node] = scores.get(node, 0.0) + 1.0 / (k + rank + 1)
    return [x for x, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]


def _fulltext_index_for(label: str) -> str:
    return "ref_concept_fulltext" if label == "Concept" else "ref_section_fulltext"
def graphrag_retrieve(query: str, top_n: int = 8, hops: int = 2) -> dict:
    """Hybrid GraphRAG retrieval from the reference graph.

    Returns {concepts, sections, formulas, strategies, sources}.
    """
    db = get_db()
    concepts: list = []
    sections: list = []
    formulas: list = []
    strategies: list = []
    sources: list = []

    # ── 1. Fulltext over concepts + sections ────────────────────────────────
    # Each fulltext row becomes a (label, node) candidate; we keep the Neo4j
    # internal integer id (`_id`) for downstream graph expansion.
    fulltext_ids: list[str] = []
    seed_labels: dict[str, str] = {}
    for label in ("Concept", "Section"):
        try:
            cypher = (
                f"CALL db.index.fulltext.queryNodes('{_fulltext_index_for(label)}', $q) "
                f"YIELD node, score RETURN node, score ORDER BY score DESC LIMIT $n"
            )
            rows = list(db.execute_and_fetch(cypher, {"q": query, "n": top_n}))
            for r in rows:
                node = r["node"]
                # gqlalchemy nodes expose _id (Neo4j internal id); element_id is absent.
                nid = str(getattr(node, "_id", None))
                fulltext_ids.append(nid)
                seed_labels[nid] = label
                if label == "Concept":
                    concepts.append({"name": getattr(node, "name", "")})
                else:
                    sections.append({"book": getattr(node, "book", ""),
                                     "chapter": getattr(node, "chapter", ""),
                                     "title": getattr(node, "title", ""),
                                     "body": (getattr(node, "body", "") or "")[:600]})
        except Exception as err:
            logger.warning(f"fulltext {label} failed: {err}")

    # ── 2. Vector search (embeddings, when present) ─────────────────────────
    vector_ids: list[str] = []
    if os.getenv("EMBEDDING_API_KEY"):
        for index in ("ref_concept_vector", "ref_section_vector"):
            try:
                cypher = (
                    f"CALL db.index.vector.queryNodes($index, $n, $q) "
                    f"YIELD node, score RETURN node, score ORDER BY score DESC LIMIT $n"
                )
                rows = list(db.execute_and_fetch(cypher, {"index": index, "q": query, "n": top_n}))
                for r in rows:
                    vector_ids.append(str(getattr(r["node"], "_id", None)))
            except Exception as err:
                logger.warning(f"vector {index} failed: {err}")

    # ── 3. Fused seed ids ───────────────────────────────────────────────────
    fused = _rrf([fulltext_ids, vector_ids]) if vector_ids else fulltext_ids
    # Fall back to a keyword MATCH on concept names when fulltext is empty
    if not fused:
        try:
            rows = list(db.execute_and_fetch(
                "MATCH (c:Concept) WHERE toLower(c.name) CONTAINS toLower($q) "
                "RETURN c LIMIT $n", {"q": query.split()[0] if query else "", "n": top_n}))
            fused = [str(getattr(r["c"], "_id", None)) for r in rows]
        except Exception as err:
            logger.warning(f"concept keyword fallback failed: {err}")

    # ── 4. Graph expansion from seeds ───────────────────────────────────────
    for seed in fused[:top_n]:
        label = seed_labels.get(seed, "")
        try:
            if label == "Section":
                # Section seed: bridge to the concepts it covers, then expand those.
                cypher = f"""
                MATCH (n:Section) WHERE id(n) = toInteger($seed)
                OPTIONAL MATCH (n)-[:COVERS]->(c0:Concept)
                OPTIONAL MATCH (n)-[:PREREQ_OF*1..{hops}]->(p:Concept)
                RETURN c0, p
                """
                rows = list(db.execute_and_fetch(cypher, {"seed": seed}))
                for r in rows:
                    for key in ("c0", "p"):
                        node = r.get(key)
                        if node is None:
                            continue
                        concepts.append({"name": getattr(node, "name", "")})
            else:
                # Concept seed (or fallback): expand formulas/strategies from it.
                cypher = f"""
                MATCH (n) WHERE id(n) = toInteger($seed)
                OPTIONAL MATCH (n)-[:HAS_FORMULA]->(f:Formula)
                OPTIONAL MATCH (n)<-[:DERIVED_FROM]-(s:Strategy)
                RETURN f, s
                """
                rows = list(db.execute_and_fetch(cypher, {"seed": seed}))
                for r in rows:
                    for key in ("f", "s"):
                        node = r.get(key)
                        if node is None:
                            continue
                        if key == "f":
                            formulas.append({"id": getattr(node, "id", ""),
                                             "expression": getattr(node, "expression", "")})
                        elif key == "s":
                            strategies.append({"name": getattr(node, "name", ""),
                                               "signal_method": getattr(node, "signal_method", "")})
        except Exception as err:
            logger.warning(f"expansion for {seed} failed: {err}")

    # dedupe expanded concepts/formulas/strategies
    concepts = list({c["name"]: c for c in concepts if c.get("name")}.values())
    formulas = list({(f.get("id"), f.get("expression")): f for f in formulas if f.get("id")}.values())
    strategies = list({s.get("name"): s for s in strategies if s.get("name")}.values())

    # ── 5. Fetch best matching sections for citation ────────────────────────
    if fused:
        try:
            rows = list(db.execute_and_fetch(
                "CALL db.index.fulltext.queryNodes('ref_section_fulltext', $q) "
                "YIELD node, score RETURN node, score ORDER BY score DESC LIMIT $n",
                {"q": query, "n": min(4, top_n)}))
            for r in rows:
                n = r["node"]
                sections.append({"book": getattr(n, "book", ""),
                                 "chapter": getattr(n, "chapter", ""),
                                 "title": getattr(n, "title", ""),
                                 "body": (getattr(n, "body", "") or "")[:600]})
        except Exception as err:
            logger.warning(f"section citation fetch failed: {err}")

    # dedupe
    def _sec_label(s):
        t = (s.get("title") or "").strip()
        if not t or t.lower() in ("section", "chapter", "untitled", ""):
            # Fall back to a body prefix so citations stay meaningful
            body = (s.get("body") or "").strip().replace("\n", " ")[:90]
            return body + "…" if body else "(untitled section)"
        return t
    uniq_sections = list({(s["book"], s.get("title"), s.get("chapter")): s for s in sections}.values())
    for s in uniq_sections[:5]:
        sources.append({"book": s["book"], "chapter": s["chapter"], "section": _sec_label(s)})
    for c in list({c["name"] for c in concepts})[:6]:
        sources.append({"concept": c})
    for f in formulas[:3]:
        sources.append({"formula": f["id"]})
    for st in strategies[:3]:
        sources.append({"strategy": st["name"]})

    logger.info(f"graphrag_retrieve: {len(concepts)} concepts, "
                f"{len(uniq_sections)} sections, {len(formulas)} formulas, {len(strategies)} strategies")
    return {"concepts": concepts, "sections": uniq_sections,
            "formulas": formulas, "strategies": strategies, "sources": sources}
def synthesize(context: dict, question: str = "") -> dict:
    """Call the LLM to produce a grounded financial-engineer answer.

    context keys: {screen, screen_data, retrieval, history}
    Returns {answer, sources, suggestions}.
    """
    screen = context.get("screen", "")
    screen_data = context.get("screen_data", {})
    retrieval = context.get("retrieval", {})
    history = context.get("history", [])[-6:]

    # Build a compact, numeric screen snapshot
    def _fmt(v, default="-"):
        if v is None:
            return default
        if isinstance(v, float):
            return f"{v:,.2f}"
        return str(v)

    data_lines = []
    sd = screen_data or {}
    if isinstance(sd, dict):
        for k, v in list(sd.items())[:24]:
            data_lines.append(f"- {k}: {_fmt(v) if not isinstance(v, list) else f'{len(v)} items'}")
    screen_snap = "\n".join(data_lines) if data_lines else "(no screen data)"

    rag_lines = []
    for s in (retrieval.get("sections") or [])[:4]:
        rag_lines.append(f"[{s.get('book')} · {s.get('chapter')}] {s.get('title')}: {(s.get('body') or '')[:300]}")
    for c in (retrieval.get("concepts") or [])[:8]:
        rag_lines.append(f"concept: {c.get('name')}")
    for f in (retrieval.get("formulas") or [])[:4]:
        rag_lines.append(f"formula: {f.get('id')} = {f.get('expression')}")
    rag_snap = "\n".join(rag_lines) if rag_lines else "(no reference-graph context loaded)"

    hist_snap = ""
    if history:
        hist_snap = "\n".join(f"{m.get('role')}: {m.get('content')[:200]}" for m in history[-4:])

    task = (
        "## User question\n" + question
        if question
        else "## Task\nBreak down this screen as a financial engineer: what the numbers mean, "
             "the risks, and the actionable takeaways."
    )
    user_prompt = (
        f"SCREEN: {screen}\n\n"
        f"## Live screen data\n{screen_snap}\n\n"
        f"## Grounded reference graph (books, concepts, formulas)\n{rag_snap}\n\n"
        f"## Conversation so far\n{hist_snap or '(none)'}\n\n"
        f"{task}"
    )
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 700,
    }
    headers = {"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"}

    if not LLM_KEY:
        # Deterministic fallback when no LLM key configured — never crashes the UI.
        answer = (
            f"Context loaded for **{screen}** — but no LLM key is configured, so I can only "
            f"summarise the grounded data rather than reason over it.\n\n"
            f"- Live screen data: {len(data_lines)} fields visible.\n"
            f"- Grounded reference graph: {len(rag_lines)} items "
            f"({len(retrieval.get('concepts') or [])} concepts, "
            f"{len(retrieval.get('sections') or [])} book sections).\n"
            f"- Sources: " + "; ".join(str(s) for s in (retrieval.get("sources") or [])[:6]) + "\n\n"
            f"Set GROQ_API_KEY to enable full natural-language analysis."
        )
        suggestions = [
            "What is the current regime and what does it imply?",
            "Break down the risk exposure of this screen.",
            "Which knowledge-graph strategies apply to this regime?",
            "How should I interpret the greeks/positions shown here?",
        ]
        return {"answer": answer, "sources": retrieval.get("sources") or [], "suggestions": suggestions}

    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(f"{LLM_URL}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        answer = data["choices"][0]["message"]["content"].strip()
    except Exception as err:
        logger.error(f"FinancialEngineer LLM failed: {err}")
        answer = f"LLM call failed ({err}). Showing grounded context only — see sources below."
        if rag_lines:
            answer += "\n\n" + "\n".join(rag_lines[:6])

    suggestions = [
        "What is the current regime and what does it imply?",
        "Break down the risk exposure of this screen.",
        "Which knowledge-graph strategies apply to this regime?",
        "How should I interpret the greeks/positions shown here?",
    ]
    return {"answer": answer, "sources": retrieval.get("sources") or [], "suggestions": suggestions}


__all__ = ["graphrag_retrieve", "synthesize"]