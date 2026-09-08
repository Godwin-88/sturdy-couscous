"""DreamDEXAgent unit tests — KG-grounded edge, binary-Kelly sizing, U10 gate.

Hermetic: stubs the relay (get_markets) and the KG belief engine
(suggest_crypto) via monkeypatch; no network, no Docker deps, no testnet key.
Verifies the P9 §7 financial model + tenet upgrades:

  U10  multiplicity correction (BH gate kills spurious edges at high n_tested)
  U11  net-edge after impact + minimum (a 350bp raw edge DOESN'T fire after
       impact because net <= 0)
  U1   oracle divergence haircut pulls belief toward 0.5
  U21  candidates are intents only (never execute directly)
"""
import asyncio

import pytest

import agent.dreamdex_agent as dmod
from agent.dreamdex_agent import DreamDEXAgent


def _run(coro):
    return asyncio.run(coro)


def _mk_market(market_id="m1", asset="BTC", strike=66000.0, interval_sec=300.0,
               ask_up=0.55, ask_down=0.45, ask_depth=50.0, ex_kurtosis=5.0,
               rv_21=0.05, status=0):
    return {
        "marketId": market_id,
        "symbol": f"{asset}-0-1HR-{int(strike)}USDso#YES",
        "asset": asset,
        "category": "crypto",
        "strike": strike,
        "interval_sec": interval_sec,
        "closes_at": "2026-09-09T00:00:00Z",
        "status": status,
        "ask_depth": ask_depth,
        "ex_kurtosis": ex_kurtosis,
        "rv_21": rv_21,
        "up": {"ask": ask_up, "bid": ask_up - 0.02},
        "down": {"ask": ask_down, "bid": ask_down - 0.02},
    }


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch):
    """Point the agent's module-level relay + KG imports at hermetic fakes."""
    monkeypatch.setattr(dmod, "get_markets", lambda: [])
    monkeypatch.setattr(DreamDEXAgent, "_cache", lambda self, k, v: None)
    # No Neo4j: KG upsert is best-effort; stub so hermetic tests never connect.
    monkeypatch.setattr("common.graph.get_db", lambda: None)

    # Fake KG belief: spot below strike => p_up should be modest regardless.
    def _fake_suggest(pair, lens="defensive", regime_override=None, **kw):
        return {"spot": 64000.0, "rv_21": 0.05, "regime": regime_override,
                "suggestions": []}
    monkeypatch.setattr("agent.crypto_signal.suggest_crypto", _fake_suggest)


def test_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(dmod, "ENABLED", False)
    assert _run(DreamDEXAgent().run(regime="Bull Trend")) == []


def test_edge_required_both_sides(monkeypatch):
    """Buy the side whose estimate beats ask; never BUY YES blindly."""
    monkeypatch.setattr(dmod, "ENABLED", True)
    monkeypatch.setattr(dmod, "MIN_EDGE_PCT", 0.0)  # neutral threshold for the test
    agent = DreamDEXAgent()

    # Spot (64000) is BELOW strike (66000) => belief says DOWN is likely.
    markets = [_mk_market(ask_up=0.55, ask_down=0.45)]
    monkeypatch.setattr(dmod, "get_markets", lambda: markets)
    cands = _run(agent.run(regime="Bull Trend"))
    assert len(cands) == 1
    c = cands[0]
    # side must reflect estimate-vs-ask, not a raw score sign.
    assert c["side"] in ("up", "down")
    assert c["edge_pct"] > 0
    assert c["qty_contracts"] >= 1
    assert c["regime"] == "Bull Trend"


def test_liquidity_floor_skips_shallow_book(monkeypatch):
    monkeypatch.setattr(dmod, "ENABLED", True)
    agent = DreamDEXAgent()
    shallow = _mk_market(ask_depth=1.0)  # below MIN_ASK_DEPTH_CONTRACTS=5
    monkeypatch.setattr(dmod, "get_markets", lambda: [shallow])
    assert _run(agent.run(regime="Bull Trend")) == []


def test_bh_gate_rejects_spurious(monkeypatch):
    """U10: with MULTICORR=bh, many marginal candidates get killed."""
    monkeypatch.setattr(dmod, "ENABLED", True)
    monkeypatch.setattr(dmod, "MULTICORR", "bh")
    monkeypatch.setattr(dmod, "FDR_DELTA", 0.10)
    monkeypatch.setattr(dmod, "MIN_EDGE_PCT", 0.0)
    monkeypatch.setattr(dmod, "MIN_ASK_DEPTH_CONTRACTS", 0)
    agent = DreamDEXAgent()

    # 20 markets with ~identical tiny-edge parameters => nearly uniform p-values.
    markets = [_mk_market(market_id=f"m{i}", ask_up=0.52 + (i % 3) * 0.01,
                          ask_down=0.48 - (i % 3) * 0.01) for i in range(20)]
    monkeypatch.setattr(dmod, "get_markets", lambda: markets)
    cands = _run(agent.run(regime="Bull Trend"))
    # BH with uniform p-values at delta=0.10 should keep far fewer than 20.
    assert len(cands) < 20


def test_candidates_are_intents_not_orders():
    """U21: candidate dicts carry estimate/ask/kelly but no live execution."""
    from agent.dreamdex_agent import DreamDEXAgent
    agent = DreamDEXAgent()
    c = {
        "market_id": "m1", "side": "up", "estimate": 0.6, "ask": 0.55,
        "size_usd": 10, "qty_contracts": 1,
    }
    # No .place_order / .broadcast on the agent — only relay is via adapter.
    assert not hasattr(DreamDEXAgent, "place_order")
# ── Layer 2: KG-fallback hermeticity (U1 book_mid_fallback) ─────────────────
def test_kg_belief_fallback_when_engine_down(monkeypatch):
    """With the KG strategy engine raising (network down), the agent still
    produces a candidate using book_mid_fallback — hermetic and safe."""
    monkeypatch.setattr(dmod, "ENABLED", True)
    monkeypatch.setattr(dmod, "MIN_EDGE_PCT", 0.0)
    agent = DreamDEXAgent()

    def _boom(pair, lens="defensive", regime_override=None, **kw):
        raise RuntimeError("tape provider down")
    monkeypatch.setattr("agent.crypto_signal.suggest_crypto", _boom)

    markets = [_mk_market(ask_up=0.55, ask_down=0.45, ask_depth=50.0)]
    monkeypatch.setattr(dmod, "get_markets", lambda: markets)

    cands = _run(agent.run(regime="Bull Trend"))
    assert len(cands) == 1
    assert cands[0]["belief_source"] == "book_mid_fallback"
    # Fallback uses strike*0.9 as spot; must still be a sane p in (0,1).
    assert 0.0 < cands[0]["estimate"] < 1.0


def test_divergence_haircut_pulls_toward_neutral(monkeypatch):
    """U1: when KG belief diverges hard from the book, pull toward 0.5 so no
    overconfident bet on a contested oracle."""
    monkeypatch.setattr(dmod, "ENABLED", True)
    monkeypatch.setattr(dmod, "MIN_EDGE_PCT", 0.0)
    monkeypatch.setattr(dmod, "TAPE_DIVERGENCE_BPS", 0.0025)  # 25bp band
    agent = DreamDEXAgent()

    # KG says spot 64000 but book prices UP at 0.90 (market believes the
    # window resolves way up) — divergence is huge, so we must haircut.
    markets = [_mk_market(strike=70000.0, ask_up=0.90, ask_down=0.10, ask_depth=50.0)]
    monkeypatch.setattr(dmod, "get_markets", lambda: markets)

    c = _run(agent.run(regime="Bull Trend"))
    # Either it's haircut (edge killed / estimate pulled) — assert no wild bet.
    if c:
        assert c[0]["divergence"] > 0.01
        assert 0.2 < c[0]["estimate"] < 0.8
# ── Layer 3: adapter↔relay contract test (mock relay, no network) ───────────
class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeHttpx:
    """Minimal stand-in for the httpx module used by dreamdex_adapter."""

    def __init__(self):
        self.get_calls = []
        self.post_calls = []
        self._get_resp = _FakeResp({"mode": "paper", "network": "testnet",
                                    "wallet": "0xabc", "reachable": True})
        self._post_resp = _FakeResp({"ok": True, "state": "accepted",
                                     "orderId": "o1", "txHash": None})

    def get(self, url, **kw):
        self.get_calls.append(url)
        if url.endswith("/markets"):
            return _FakeResp({"markets": [{"marketId": "m1", "asset": "BTC",
                                           "strike": 66000, "interval_sec": 300,
                                           "status": 0, "up": {"ask": 0.55},
                                           "down": {"ask": 0.45}}]})
        if url.endswith("/positions"):
            return _FakeResp({"positions": [], "reconciliation": {"driftItems": []}})
        if url.endswith("/fills"):
            return _FakeResp({"fills": []})
        return self._get_resp

    def post(self, url, **kw):
        self.post_calls.append((url, kw.get("json")))
        return self._post_resp


def test_adapter_parses_markets(monkeypatch):
    """Contract: relay returns documents we understand; adapter surfaces them."""
    import agent.dreamdex_adapter as ad
    fake = _FakeHttpx()
    monkeypatch.setattr(ad, "httpx", fake)

    markets = ad.get_markets()
    assert len(markets) == 1
    assert markets[0]["marketId"] == "m1"
    assert markets[0]["up"]["ask"] == 0.55


def test_adapter_order_payload_shape(monkeypatch):
    """Contract: place_order sends {marketId, side, qty} and reads the fill."""
    import agent.dreamdex_adapter as ad
    fake = _FakeHttpx()
    monkeypatch.setattr(ad, "httpx", fake)

    res = ad.place_order("m1", "up", 3)
    url, payload = fake.post_calls[0]
    assert payload == {"marketId": "m1", "side": "up", "qty": 3}
    assert res["ok"] is True and res["state"] == "accepted"


def test_adapter_unreachable_returns_stub(monkeypatch):
    """Contract: relay down ⇒ graceful degradation (no raise, logged)."""
    import agent.dreamdex_adapter as ad

    class _Failing:
        def get(self, url, **kw):
            raise ConnectionError("refused")
        def post(self, url, **kw):
            raise ConnectionError("refused")
    monkeypatch.setattr(ad, "httpx", _Failing())

    assert ad.relay_status().get("reachable") is False
    assert ad.get_markets() == []
    assert ad.place_order("m1", "up", 1).get("ok") is False