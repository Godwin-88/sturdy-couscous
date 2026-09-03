"""
Financial-Engineer tool registry — the read-only, server-side tool surface the
agentic chat (ReAct-style loop) can call. Every tool is a thin, guarded wrapper
over existing GraphAlpha modules/routes and degrades to ``{ok:False,...}``
instead of raising into the LLM loop.

HUMAN-IN-THE-LOOP: nothing in this module executes an order. ``prefill_order``
only *builds* a draft card; the chat UI then runs the two-phase proposal flow
(preview -> proposal_token -> confirm) against the existing endpoints.
"""
from __future__ import annotations

import os
import re
from typing import Any

import httpx
from loguru import logger

from common.graph import get_db

API_BASE = f"http://localhost:{os.getenv('API_PORT', '8000')}"


def _import(name: str):
    """Import a provider from either the package (`agent.*`) or flat layout."""
    mods = {
        "provider": ("agent.alpaca_data", "alpaca_data", "provider"),
        "options_provider": ("agent.options_market", "options_market", "options_provider"),
        "compute_suggestions": ("agent.option_signal", "option_signal", "compute_suggestions"),
        "graphrag": ("agent.financial_engineer", "financial_engineer", "graphrag_retrieve"),
        "lexicon": ("agent.news_agent", "news_agent", "_lexicon_score"),
        "concepts": ("agent.news_agent", "news_agent", "_match_concepts"),
    }
    pkg, flat, attr = mods[name]
    try:
        return getattr(__import__(pkg, fromlist=[attr]), attr)
    except Exception:
        try:
            return getattr(__import__(flat, fromlist=[attr]), attr)
        except Exception as e:  # pragma: no cover
            logger.debug(f"fe_tools import {name} failed: {e}")
            return None


def _http_get(path: str, timeout: float = 20.0) -> dict | None:
    try:
        resp = httpx.get(f"{API_BASE}{path}", timeout=timeout)
        return resp.json() if resp.status_code == 200 else None
    except Exception as e:
        logger.debug(f"fe_tools GET {path}: {e}")
        return None


# ── Tool 1: graphrag (Hybrid GraphRAG in Neo4j) ───────────────────────────────
def graphrag(query: str, top_n: int = 6, hops: int = 2) -> dict:
    fn = _import("graphrag")
    if fn is None:
        return {"ok": False, "error": "graphrag unavailable"}
    try:
        return {"ok": True, "result": fn(query, top_n=top_n, hops=hops)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Tool 2: market_data (Alpaca-primary OHLCV) ────────────────────────────────
def market_data(ticker: str, days: int = 60) -> dict:
    prov = _import("provider")
    if prov is None:
        return {"ok": False, "error": "data provider unavailable"}
    try:
        df = prov.get_ohlcv(ticker.upper(), days=days)
        if df is None or df.empty:
            return {"ok": False, "error": f"no data for {ticker.upper()}"}
        close = df["Close"].astype(float)
        rets = close.pct_change().dropna()
        vol21 = float(rets.tail(21).std() * (252 ** 0.5)) if len(rets) >= 5 else None
        return {
            "ok": True,
            "result": {
                "ticker": ticker.upper(),
                "source": prov.source_name(),
                "rows": int(len(df)),
                "last_close": round(float(close.iloc[-1]), 2),
                "prev_close": round(float(close.iloc[-2]), 2) if len(close) > 1 else None,
                "range_low": round(float(df["Low"].min()), 2) if "Low" in df else None,
                "range_high": round(float(df["High"].max()), 2) if "High" in df else None,
                "vol_21d_annualized": round(vol21, 4) if vol21 is not None else None,
                "return_5d": round(float(close.iloc[-1] / close.iloc[-6] - 1), 4) if len(close) > 5 else None,
                "return_21d": round(float(close.iloc[-1] / close.iloc[-22] - 1), 4) if len(close) > 21 else None,
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Tool 3: option_chain (live Alpaca chain w/ greeks) ────────────────────────
def option_chain(underlying: str, expiration: str | None = None,
                 contract_type: str | None = None, limit: int = 24) -> dict:
    op = _import("options_provider")
    if op is None:
        return {"ok": False, "error": "options provider unavailable"}
    try:
        rows = op.get_chain(underlying.upper(), expiration=expiration,
                            contract_type=contract_type)
        compact = [
            {
                "symbol": r.get("symbol"),
                "strike": r.get("strike_price"),
                "bid": r.get("bid"),
                "ask": r.get("ask"),
                "iv": r.get("implied_volatility"),
                "delta": (r.get("greeks") or {}).get("delta"),
                "gamma": (r.get("greeks") or {}).get("gamma"),
                "theta": (r.get("greeks") or {}).get("theta"),
                "oi": r.get("open_interest"),
            }
            for r in (rows or [])[:limit]
        ]
        return {"ok": True, "result": {"contracts": compact, "count": len(compact)}}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Tool 4: news_sentiment (per-ticker Yahoo RSS + lexicon + KG concepts) ──────
def news_sentiment(ticker: str, limit: int = 8) -> dict:
    url = f"https://finance.yahoo.com/rss/headline?s={ticker.upper()}"
    try:
        resp = httpx.get(url, timeout=15.0)
        if resp.status_code != 200:
            return {"ok": False, "error": f"rss http {resp.status_code}"}
        titles: list[str] = []
        try:
            import feedparser  # type: ignore
            for e in feedparser.parse(resp.text).entries[:limit]:
                titles.append(str(getattr(e, "title", "")).strip())
        except Exception:
            titles = re.findall(r"<title>(.*?)</title>", resp.text, re.S)[:limit]
        titles = [t for t in titles if t and not t.startswith("Yahoo")]
        score_fn = _import("lexicon")
        conc_fn = _import("concepts")
        items = []
        for t in titles:
            sent = score_fn(t) if score_fn else 0.0
            items.append({
                "headline": t,
                "sentiment": round(float(sent), 3),
                "concepts": conc_fn(t) if conc_fn else [],
            })
        agg = round(float(sum(i["sentiment"] for i in items)) / len(items), 3) if items else 0.0
        return {"ok": True, "result": {"ticker": ticker.upper(),
                                       "items": items[:limit],
                                       "aggregate_sentiment": agg}}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Tool 5: strategy_matrix (all active strategies x regimes from KG) ────────
def strategy_matrix() -> dict:
    try:
        db = get_db()
        rows = list(db.execute_and_fetch(
            "MATCH (s:Strategy {status:'active'})-[a:ACTIVATED_BY]->(r:Regime) "
            "RETURN s.name AS strategy, s.signal_method AS signal_method, "
            "s.target_ticker AS target_ticker, r.name AS regime, a.weight AS weight "
            "ORDER BY s.name"
        ))
        return {"ok": True, "result": rows}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Tool 6: suggestions (per-regime or across ALL regimes) ────────────────────
def suggestions(underlying: str, expiration: str | None = None,
                contract_type: str | None = None,
                regime: str | None = None, lens: str = "defensive",
                nav: float | None = None) -> dict:
    fn = _import("compute_suggestions")
    if fn is None:
        return {"ok": False, "error": "suggestion engine unavailable"}

    def _run(r: str | None) -> dict:
        try:
            return fn(underlying.upper(), expiration, contract_type,
                      regime=r, lens=lens, nav=nav) or {}
        except Exception:
            return {}

    if regime and regime.lower() != "all":
        out = _run(regime)
    else:
        out = {"regime": "all", "underlying": underlying.upper(),
               "suggestions": [], "rejected": [], "active_strategies": []}
        try:
            db = get_db()
            regimes = [x["name"] for x in db.execute_and_fetch(
                "MATCH (r:Regime) RETURN r.name AS name")]
        except Exception:
            regimes = []
        for r in regimes:
            partial = _run(r)
            for s in (partial.get("suggestions") or []):
                if not any(d.get("strategy") == s.get("strategy")
                           for d in out["suggestions"]):
                    out["suggestions"].append({**s, "regime": r})
            for rej in (partial.get("rejected") or []):
                out["rejected"].append({**rej, "regime": r})
        out["suggestions"].sort(key=lambda x: x.get("score") or 0, reverse=True)
        out["suggestions"] = out["suggestions"][:10]
    out.setdefault("lens", lens)
    return {"ok": True, "result": out}


# ── Tool 7: hedge_state (dynamic delta hedge posture, read-only) ──────────────
def hedge_state(underlying: str = "SPY") -> dict:
    data = _http_get(f"/options/hedge/state?underlying={underlying.upper()}")
    if data is None:
        return {"ok": False, "error": "hedge state unavailable"}
    return {"ok": True, "result": data.get("hedge_state") or data}


# ── Tool 8: portfolio (risk ledger + live Alpaca account) ─────────────────────
def portfolio() -> dict:
    risk = _http_get("/agent/risk")
    alp = _http_get("/alpaca/portfolio")
    return {"ok": True, "result": {"risk": risk or {},
                                   "alpaca_account": alp or {}}}


# ── Tool 9: prefill_order (draft ONLY — never executes) ───────────────────────
def prefill_order(underlying: str, expiration: str | None = None,
                  contract_type: str | None = None,
                  strategy: str | None = None, lens: str = "defensive",
                  nav: float | None = None) -> dict:
    """Build a draft order card from the best KG-grounded suggestion (read-only)."""
    fn = _import("compute_suggestions")
    if fn is None:
        return {"ok": False, "error": "suggestion engine unavailable"}
    try:
        out = fn(underlying.upper(), expiration, contract_type,
                 regime=None, lens=lens, nav=nav) or {}
        cards = out.get("suggestions") or []
        if strategy:
            cards = [s for s in cards if s.get("strategy") == strategy]
        if not cards:
            return {"ok": False, "error": "no suggestion cards available"}
        top = cards[0]
        legs = (top.get("legs") or [])[:4]
        draft = {
            "underlying": underlying.upper(),
            "expiration": expiration,
            "contract_type": contract_type or (legs[0].get("contract_type") if legs else None),
            "strategy": top.get("strategy"),
            "signal_method": top.get("signal_method"),
            "regime": top.get("regime"),
            "score": top.get("score"),
            "loss_aversion_score": top.get("loss_aversion_score"),
            "graph_path": (top.get("graph_path") or [])[:6],
            "legs": [
                {"symbol": l.get("symbol"), "strike": l.get("strike"),
                 "contract_type": l.get("contract_type"),
                 "side": l.get("side"), "contracts": l.get("contracts") or 1}
                for l in legs
            ],
            "est_premium": top.get("est_premium"),
            "max_profit": top.get("max_profit_low"),
            "max_loss": top.get("max_loss"),
            "risk_reward_pct": top.get("risk_reward_pct"),
            "max_losspct_nav": top.get("max_loss_pct_nav"),
            "budget_pct": top.get("budget_pct"),
            "liquidity_ok": top.get("liquidity_ok"),
            "notes": (top.get("notes") or [])[:4],
            "nav": nav or 100000.0,
        }
        return {"ok": True, "result": draft}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── registry ──────────────────────────────────────────────────────────────────
TOOLS: dict[str, Any] = {
    "graphrag": graphrag,
    "market_data": market_data,
    "option_chain": option_chain,
    "news_sentiment": news_sentiment,
    "strategy_matrix": strategy_matrix,
    "suggestions": suggestions,
    "hedge_state": hedge_state,
    "portfolio": portfolio,
    "prefill_order": prefill_order,
}


def call_tool(name: str, **kwargs) -> dict:
    fn = TOOLS.get(name)
    if fn is None:
        return {"ok": False, "error": f"unknown tool {name}"}
    try:
        return fn(**kwargs)
    except Exception as e:  # never raise into the loop
        return {"ok": False, "error": str(e)}


__all__ = ["call_tool", "TOOLS"]