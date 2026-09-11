"""DreamDEX financial-engineer chat wiring (P11, UI chat).

Verifies the additive seams used to make the per-screen chat DreamDEX-aware:
  1. SCREEN_HINTS has a dreamdex entry (EC-specific GraphRAG retrieval query).
  2. _live_screen_data('dreamdex') pulls the live relay bundle into the chat
     context (markets/candidates/positions/fills/status) — guarded/empty when
     the relay is down, never raising.
  3. The shared SYSTEM_PROMPT contains the EC rule markers so the LLM answers
     as a financial engineer over Event-Contract books (edge=estimate-ask,
     binary Kelly, human-gated).
Hermetic: no network, no testnet, no LLM calls.
"""
from __future__ import annotations

import os

os.environ.setdefault("REDIS_HOST", "redis")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("API_PORT", "8000")

from agent.financial_engineer import SYSTEM_PROMPT, synthesize  # noqa: E402
from routes.chat import SCREEN_HINTS, _live_screen_data  # noqa: E402


def test_screen_hint_has_dreamdex():
    hint = SCREEN_HINTS.get("dreamdex", "")
    assert hint, "dreamdex screen hint missing"
    for kw in ("event contract", "probability", "edge", "kelly"):
        assert kw in hint, f"dreamdex hint missing keyword {kw!r}"


def test_live_screen_data_dreamdex_hermetic(monkeypatch):
    """_live_screen_data('dreamdex') must build the relay bundle with
    zero network access (patched httpx.get) and never raise."""

    class _Resp:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            pass

    def _fake_get(url, *a, **k):
        us = str(url)
        if "dreamdex/markets" in us:
            return _Resp({"markets": [{"symbol": "BTC-0-TEST"}], "cached": False})
        if "dreamdex/candidates" in us:
            return _Resp({"candidates": [{"symbol": "BTC-0-TEST", "net_edge_pct": 3.2}]})
        if "dreamdex/status" in us:
            return _Resp({"mode": "live", "dry_run": True})
        if "dreamdex/positions" in us or "dreamdex/fills" in us:
            return _Resp({"positions": [], "fills": []})
        return _Resp({})

    import httpx

    monkeypatch.setattr(httpx, "get", _fake_get)

    out = _live_screen_data("dreamdex")
    assert isinstance(out, dict)
    assert out["dreamdex_markets"]["markets"][0]["symbol"] == "BTC-0-TEST"
    assert out["dreamdex_candidates"]["candidates"][0]["net_edge_pct"] == 3.2
    assert out["dreamdex_status"]["dry_run"] is True
    assert "dreamdex_fills" in out and "dreamdex_positions" in out


def test_system_prompt_has_ec_rules():
    for marker in (
        "DREAMDEX EVENT-CONTRACT RULE",
        "binary prediction market",
        "Edge = your probability estimate minus the market ask",
        "binary Kelly",
        "human-gated",
    ):
        assert marker in SYSTEM_PROMPT, f"SYSTEM_PROMPT missing EC marker {marker!r}"


def test_synthesize_prompt_paths_exist():
    import inspect

    sig = inspect.signature(synthesize)
    params = set(sig.parameters)
    assert "context" in params
    assert "question" in params or "query" in params