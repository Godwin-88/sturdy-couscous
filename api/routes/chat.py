"""
Financial Engineer chat — per-screen grounded assistant.

GET  /chat/context/{screen}   → live screen data + Hybrid GraphRAG context bundle
POST /chat/ask                → grounded financial-engineer answer (LLM via
                                agent.financial_engineer.synthesize)
GET  /chat/history/{screen}   → persisted conversation for a screen
DELETE /chat/history/{screen} → clear history
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import httpx
import psycopg2
import redis
from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from agent.financial_engineer import graphrag_retrieve, synthesize

router = APIRouter(prefix="/chat", tags=["chat"])

# Screens in the app; used to seed retrieval queries per screen.
SCREEN_HINTS: dict[str, str] = {
    "dashboard":     "portfolio P&L positions risk regime",
    "graph":         "knowledge graph concepts relationships strategies",
    "signals":       "algorithmic trading signals momentum mean reversion entry exit",
    "options":       "options greeks delta theta gamma vega implied volatility premium hedging",
    "risk":          "value at risk kelly criterion drawdown concentration portfolio risk",
    "backtest":      "backtesting walk-forward analysis strategy performance metrics",
    "intelligence":  "market regime forecast news sentiment macro",
    "analytics":     "time series stationarity cointegration regression machine learning",
    "hypothesis":    "hypothesis testing statistical significance backtest evidence",
}


def _redis():
    return redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                       port=int(os.getenv("REDIS_PORT", 6379)),
                       decode_responses=True)


def _conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "graphalpha"),
        user=os.getenv("POSTGRES_USER", "graphalpha"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )


def _live_screen_data(screen: str) -> dict:
    """Assemble a compact, numeric snapshot of whatever the screen shows.

    Best-effort; each call is guarded and degrades to empty rather than raising.
    """
    base_url = f"http://localhost:{os.getenv('API_PORT', '8000')}"
    out: dict = {}

    def _get(path: str, key: str) -> None:
        try:
            resp = httpx.get(f"{base_url}{path}", timeout=6.0)
            if resp.status_code == 200:
                out[key] = resp.json()
        except Exception as err:
            logger.debug(f"chat context {path}: {err}")

    _get("/agent/status", "agent_status")
    _get("/agent/risk", "risk_metrics")
    _get("/graph/eligible-strategies?regime=Neutral", "eligible_strategies")
    _get("/positions", "positions")
    _get("/positions/portfolio", "portfolio")
    _get("/signals?limit=12", "signals")

    if screen in ("options", "dashboard", "risk"):
        _get("/alpaca/account", "alpaca_account")
        _get("/alpaca/positions", "alpaca_positions")
        _get("/options/hedge/state", "hedge_state")
        if screen == "options":
            _get("/options/suggestions?underlying=SPY&contract_type=call", "options_suggestions")

    if screen == "intelligence":
        _get("/agent/regime-forecast", "regime_forecast")

    if screen == "backtest":
        _get("/backtest/runs?limit=5", "backtest_runs")

    if screen == "graph":
        _get("/graph/nodes?node_type=Strategy&limit=30", "strategy_nodes")

    return out


class AskRequest(BaseModel):
    screen: str = "dashboard"
    question: str = ""
    history: list[dict] = []


@router.get("/context/{screen}")
def chat_context(screen: str):
    """Return the full context bundle for a screen (live data + GraphRAG)."""
    screen = screen.lower().strip("/")
    hint = SCREEN_HINTS.get(screen, "trading strategy risk analysis")
    cache_key = f"chat:context:{screen}"

    r = _redis()
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)

    try:
        retrieval = graphrag_retrieve(hint, top_n=8, hops=2)
    except Exception as err:
        logger.error(f"graphrag_retrieve failed: {err}")
        retrieval = {"concepts": [], "sections": [], "formulas": [],
                     "strategies": [], "sources": []}

    live = _live_screen_data(screen)

    bundle = {
        "screen": screen,
        "hint": hint,
        "live": live,
        "retrieval": retrieval,
        "generated_at": datetime.utcnow().isoformat(),
    }
    try:
        r.setex(cache_key, int(os.getenv("CHAT_CONTEXT_TTL", "60")), json.dumps(bundle))
    except Exception:
        pass
    return bundle
@router.post("/ask")
def chat_ask(req: AskRequest):
    """Ask the financial engineer a question grounded in the screen + books."""
    screen = req.screen.lower().strip("/")
    hint = SCREEN_HINTS.get(screen, "trading strategy risk analysis")
    query = f"{hint} {req.question}" if req.question else hint

    try:
        retrieval = graphrag_retrieve(query, top_n=8, hops=2)
    except Exception as err:
        logger.error(f"graphrag_retrieve failed: {err}")
        retrieval = {"concepts": [], "sections": [], "formulas": [],
                     "strategies": [], "sources": []}

    live = _live_screen_data(screen)
    context = {"screen": screen, "screen_data": live, "retrieval": retrieval, "history": req.history}
    result = synthesize(context, question=req.question)

    # Persist conversation
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM chat_sessions WHERE screen=%s ORDER BY created_at DESC LIMIT 1",
                (screen,))
            row = cur.fetchone()
            if row:
                session_id = row[0]
            else:
                cur.execute(
                    "INSERT INTO chat_sessions (screen) VALUES (%s) RETURNING id", (screen,))
                session_id = cur.fetchone()[0]
            if req.question:
                cur.execute(
                    "INSERT INTO chat_messages (session_id, screen, role, content) "
                    "VALUES (%s,%s,'user',%s)",
                    (session_id, screen, req.question))
            cur.execute(
                "INSERT INTO chat_messages (session_id, screen, role, content, sources) "
                "VALUES (%s,%s,'assistant',%s,%s)",
                (session_id, screen, result["answer"],
                 json.dumps(result.get("sources", []))))
            conn.commit()
    except Exception as err:
        logger.warning(f"chat history persist failed: {err}")

    return result
@router.get("/history/{screen}")
def chat_history(screen: str):
    """Return persisted messages for a screen (newest-last)."""
    screen = screen.lower().strip("/")
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT role, content, sources FROM chat_messages WHERE screen=%s ORDER BY created_at",
                (screen,))
            return [{"role": r[0], "content": r[1], "sources": r[2]} for r in cur.fetchall()]
    except Exception as err:
        logger.warning(f"chat history read failed: {err}")
        return []


@router.delete("/history/{screen}")
def chat_history_clear(screen: str):
    """Clear persisted history for a screen."""
    screen = screen.lower().strip("/")
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM chat_sessions WHERE screen=%s", (screen,))
            conn.commit()
        return {"deleted": True, "screen": screen}
    except Exception as err:
        logger.warning(f"chat history clear failed: {err}")
        return {"deleted": False, "error": str(err)}