"""
Agent API endpoints.

POST /agents/chat       — Main conversational agent (workspace-aware + KB skills)
POST /agents/explain    — One-shot formula / metric / concept explanation
POST /agents/feedback   — RLHF: store user rating; optionally correct the reply
POST /agents/enrich     — Trigger RLHF GraphRAG enrichment pass (admin / background)
GET  /agents/menus/{menu_id}/concepts — List Neo4j concepts for a menu
GET  /agents/health     — Neo4j + LLM status
"""

import logging
import os
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from app.knowledge_base.neo4j_client import (
    get_neo4j_driver,
    Neo4jKnowledgeClient,
    KnowledgeNotFoundError,
)
from app.agents.llm_client import get_llm_client
from app.agents.skills import (
    route_and_run,
    explain_formula,
    interpret_metric,
    explain_concept,
    list_menu_concepts,
    enrich_graph_from_feedback,
    MENU_ID_TO_NAME,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

# ── Lazy singletons ────────────────────────────────────────────────────────────

_kb: Optional[Neo4jKnowledgeClient] = None
_llm = None
_kb_last_failed: float = 0.0          # epoch timestamp of last failed attempt
_KB_RETRY_COOLDOWN = 30.0             # seconds to wait before retrying after failure


def _try_get_kb() -> Optional[Neo4jKnowledgeClient]:
    """Return KB client, or None if Neo4j is unavailable (graceful degradation).
    Performs an actual connectivity test so callers never get a dead client.
    Uses a 30-second cooldown to avoid hammering a downed Neo4j instance."""
    import time
    global _kb, _kb_last_failed
    # Return cached live client without re-checking every request
    if _kb is not None:
        return _kb
    # Respect cooldown — don't retry immediately after a failure
    if time.time() - _kb_last_failed < _KB_RETRY_COOLDOWN:
        return None
    try:
        driver = get_neo4j_driver()
        client = Neo4jKnowledgeClient(driver)
        alive = client.health_check()
        if not alive:
            raise RuntimeError("Neo4j health_check returned False")
        _kb = client
        return _kb
    except Exception as e:
        _kb_last_failed = time.time()
        logger.warning("Neo4j unavailable (graceful degradation): %s", e)
        return None


def get_kb() -> Neo4jKnowledgeClient:
    """Return KB — raises 503 if Neo4j unreachable (used by endpoints that require KB)."""
    kb = _try_get_kb()
    if kb is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Neo4j (knowledge base) is not reachable. "
                "Start Neo4j (docker compose -f docker-compose.kb.yml up -d) "
                "and check NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD."
            ),
        )
    return kb


def get_llm():
    global _llm
    if _llm is None:
        _llm = get_llm_client()
    return _llm


# ── Rate limiter ───────────────────────────────────────────────────────────────

_rate_limit: dict[str, tuple[int, float]] = {}
RATE_LIMIT_WINDOW = 60.0
RATE_LIMIT_MAX = int(os.getenv("AGENT_RATE_LIMIT_PER_MIN", "20"))


def _check_rate_limit(request: Request) -> None:
    client = request.client
    ip = client.host if client else "unknown"
    now = time.time()
    if ip not in _rate_limit:
        _rate_limit[ip] = (1, now)
        return
    count, start = _rate_limit[ip]
    if now - start > RATE_LIMIT_WINDOW:
        _rate_limit[ip] = (1, now)
        return
    if count >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many agent requests; try again later.")
    _rate_limit[ip] = (count + 1, start)


def _menu_name(menu_id: str) -> Optional[str]:
    return MENU_ID_TO_NAME.get(menu_id.lower()) if menu_id else None


# ── Request / Response models ──────────────────────────────────────────────────

class ChatRequest(BaseModel):
    menu_id: Optional[str] = None
    message: str = ""
    context: Optional[dict[str, Any]] = None
    # context may include:
    #   workspace_data: dict       — full computed results from workspace (enables LLM-only analysis)
    #   formula_name: str          — route to explain_formula
    #   metric_name + metric_value — route to interpret_metric
    #   concept_name: str          — route to explain_concept


class ExplainRequest(BaseModel):
    menu_id: Optional[str] = None
    type: str  # "formula" | "metric" | "concept"
    target: str
    value: Optional[float] = None


class FeedbackRequest(BaseModel):
    """RLHF feedback: the user rates an agent reply and optionally provides a correction."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    menu_id: str = "overview"
    user_message: str
    agent_reply: str
    rating: int = Field(..., ge=1, le=5, description="1=poor … 5=excellent")
    corrected_reply: Optional[str] = None   # user-supplied better answer
    context_type: Optional[str] = None     # "formula" | "concept" | "metric" | "workspace"
    context_target: Optional[str] = None   # name of the formula/concept/metric if known


# ── Helpers ────────────────────────────────────────────────────────────────────

def _agent_unavailable_detail(e: Exception) -> str:
    import os
    err_text = str(e)
    err = err_text.lower()
    using_groq = bool((os.getenv("GROQ_API_KEY") or "").strip())
    # Neo4j errors must be checked FIRST — they also contain "connection"/"refused"
    if "neo4j" in err or "7687" in err or "bolt" in err or "serviceunavailable" in err:
        return (
            "Neo4j (knowledge base) is not reachable — it is optional. "
            "The agent works without it when workspace data is provided. "
            "To enable GraphRAG: docker compose -f docker-compose.kb.yml up -d. "
            f"(error: {err_text})"
        )
    if "groq_api_key" in err or "401" in err or "unauthorized" in err:
        return (
            "Groq authentication failed — check GROQ_API_KEY in .env. "
            f"(error: {err_text})"
        )
    if "connection" in err or "refused" in err or "11434" in err or "ollama" in err:
        if using_groq:
            return (
                "Groq API request failed — check your GROQ_API_KEY and network. "
                f"(error: {err_text})"
            )
        return (
            "Ollama (LLM) is not running. "
            "Start Ollama and ensure OLLAMA_HOST is correct (e.g. http://localhost:11434). "
            f"(error: {err_text})"
        )
    if "timeout" in err:
        provider = "GROQ_TIMEOUT" if using_groq else "OLLAMA_TIMEOUT"
        return (
            f"Request timed out. Try again or increase {provider} in .env. "
            f"(error: {err_text})"
        )
    return f"Agent temporarily unavailable. Check server logs. (error: {err_text})"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/health")
async def agents_health():
    """Check Neo4j and LLM (Groq or Ollama) availability."""
    import os
    neo4j_ok = False
    try:
        kb = _try_get_kb()
        neo4j_ok = kb.health_check() if kb else False
    except Exception:
        neo4j_ok = False
    llm_ok = False
    llm_provider = "groq" if (os.getenv("GROQ_API_KEY") or "").strip() else "ollama"
    try:
        llm = get_llm()
        llm_ok = llm.health_check()
    except Exception:
        llm_ok = False
    status = "healthy" if llm_ok else "degraded"
    return {"status": status, "neo4j": neo4j_ok, "llm": llm_ok, "llm_provider": llm_provider}


@router.post("/chat")
async def agents_chat(request: Request, body: ChatRequest):
    """
    Main conversational agent endpoint.

    When context.workspace_data is present the agent performs expert financial
    analysis of the live workspace results — Neo4j is NOT required for this path.

    For formula / metric / concept explanations Neo4j is required.
    Gracefully degrades to LLM-only if Neo4j is down and workspace_data is provided.
    """
    _check_rate_limit(request)
    menu_id = body.menu_id
    message = (body.message or "").strip()
    context = body.context or {}

    if not message and not context.get("formula_name") and context.get("metric_name") is None and not context.get("workspace_data"):
        raise HTTPException(status_code=400, detail="message or context required")
    if len(message) > 4000:
        raise HTTPException(status_code=400, detail="message too long (max 4000 chars)")

    global _kb, _kb_last_failed
    import time as _time
    try:
        llm = get_llm()
        kb = _try_get_kb()
        result = route_and_run(kb, llm, message, menu_id=menu_id, context=context)
        return {"reply": result["reply"], "sources": result.get("sources", [])}
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        err = str(e).lower()
        # If Neo4j went down after being cached, invalidate and retry LLM-only
        if "7687" in err or "bolt" in err or "neo4j" in err or "serviceunavailable" in err:
            _kb = None
            _kb_last_failed = _time.time()
            try:
                result = route_and_run(None, get_llm(), message, menu_id=menu_id, context=context)
                return {"reply": result["reply"], "sources": result.get("sources", [])}
            except Exception:
                pass
        logger.exception("Agent chat failed")
        raise HTTPException(status_code=503, detail=_agent_unavailable_detail(e))


@router.post("/explain")
async def agents_explain(request: Request, body: ExplainRequest):
    """One-shot explain: formula | metric | concept."""
    _check_rate_limit(request)
    explain_type = (body.type or "").strip().lower()
    target = (body.target or "").strip()
    value = body.value
    if not target:
        raise HTTPException(status_code=400, detail="target required")
    menu_name = _menu_name(body.menu_id) if body.menu_id else None
    try:
        kb = get_kb()  # KB required for explicit explain
        llm = get_llm()
        if explain_type == "formula":
            result = explain_formula(kb, llm, target)
        elif explain_type == "metric":
            if value is None:
                raise HTTPException(status_code=400, detail="value required for metric explain")
            result = interpret_metric(kb, llm, target, float(value), menu_name)
        elif explain_type == "concept":
            result = explain_concept(kb, llm, target)
        else:
            raise HTTPException(status_code=400, detail="type must be formula, metric, or concept")
        return {"reply": result["reply"], "sources": result.get("sources", [])}
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agent explain failed")
        raise HTTPException(status_code=503, detail=_agent_unavailable_detail(e))


@router.post("/feedback")
async def agents_feedback(body: FeedbackRequest, background_tasks: BackgroundTasks):
    """
    RLHF feedback endpoint.

    Stores the user's rating + optional correction in Neo4j.
    For negative ratings (1–2) with a correction, schedules a background
    GraphRAG enrichment pass to update the knowledge graph.
    """
    kb = _try_get_kb()
    if kb is None:
        # Gracefully accept feedback even when Neo4j is down (just log it)
        logger.warning(
            "Feedback received but Neo4j unavailable — "
            "menu=%s rating=%s msg=%s...",
            body.menu_id, body.rating, body.user_message[:80],
        )
        return {"status": "accepted", "note": "Neo4j unavailable; feedback logged but not persisted."}

    try:
        kb.record_user_feedback(
            session_id=body.session_id,
            menu_id=body.menu_id,
            user_message=body.user_message,
            agent_reply=body.agent_reply,
            rating=body.rating,
            context_type=body.context_type,
            context_target=body.context_target,
            corrected_reply=body.corrected_reply,
        )
    except Exception as e:
        logger.error("Failed to record feedback: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to persist feedback: {e}")

    # For negative feedback with correction → trigger enrichment asynchronously
    if body.rating <= 2 and body.corrected_reply:
        background_tasks.add_task(_run_enrichment_pass)

    return {"status": "recorded", "session_id": body.session_id}


def _run_enrichment_pass() -> None:
    """Background task: RLHF GraphRAG enrichment. Errors are logged, not raised."""
    try:
        kb = _try_get_kb()
        if kb is None:
            return
        llm = get_llm()
        result = enrich_graph_from_feedback(kb, llm, limit=30)
        logger.info("RLHF enrichment pass: %s", result)
    except Exception as e:
        logger.error("RLHF enrichment pass failed: %s", e)


@router.post("/enrich")
async def agents_enrich(background_tasks: BackgroundTasks):
    """
    Manually trigger a RLHF GraphRAG enrichment pass (admin use).
    Runs asynchronously; returns immediately.
    """
    background_tasks.add_task(_run_enrichment_pass)
    return {"status": "enrichment_pass_scheduled"}


class ConversationMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    timestamp: Optional[int] = None


class SaveConversationRequest(BaseModel):
    """Full conversation session — stored in Neo4j for DRL graph enrichment."""
    menu_id: str = "overview"
    messages: list[ConversationMessage] = Field(default_factory=list)
    workspace_snapshot: Optional[dict[str, Any]] = None


@router.post("/conversations/save")
async def agents_save_conversation(body: SaveConversationRequest, background_tasks: BackgroundTasks):
    """
    Persist a completed chat session for Deep Reinforcement Learning.

    Creates a ConversationSession node in Neo4j linked to the menu, user
    messages, and assistant replies.  The workspace_snapshot (raw computed
    results at the time of the conversation) is stored so the enrichment pass
    can later link concepts → real data.

    Accepts gracefully if Neo4j is unavailable — conversation is still logged.
    """
    assistant_count = sum(1 for m in body.messages if m.role == "assistant")
    if assistant_count == 0:
        return {"status": "skipped", "reason": "no assistant messages"}

    kb = _try_get_kb()
    if kb is None:
        logger.info(
            "Conversation save: Neo4j unavailable — session logged only "
            "(menu=%s, turns=%d)", body.menu_id, len(body.messages)
        )
        return {
            "status": "accepted",
            "note": "Neo4j unavailable; conversation logged but not persisted to graph.",
        }

    try:
        session_id = str(uuid.uuid4())
        kb.save_conversation_session(
            session_id=session_id,
            menu_id=body.menu_id,
            messages=[m.model_dump() for m in body.messages],
            workspace_snapshot=body.workspace_snapshot,
        )
        # Schedule async enrichment pass to extract concepts from this conversation
        background_tasks.add_task(_run_enrichment_pass)
        return {"status": "saved", "session_id": session_id}
    except Exception as e:
        logger.warning("Failed to save conversation session: %s", e)
        return {"status": "accepted", "note": f"Logged but graph persistence failed: {e}"}


@router.get("/menus/{menu_id}/concepts")
async def agents_menu_concepts(menu_id: str):
    """List concepts for a menu from Neo4j (no LLM)."""
    menu_name = _menu_name(menu_id)
    if not menu_name:
        raise HTTPException(status_code=400, detail=f"Unknown menu_id: {menu_id}")
    try:
        kb = get_kb()
        concepts = kb.get_menu_concepts(menu_name)
        return {"menu_id": menu_id, "menu_name": menu_name, "concepts": concepts}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Concepts fetch failed")
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")
