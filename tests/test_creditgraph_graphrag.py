"""GraphRAG engine tests (E4, DoD)."""

import asyncio

import pytest

from creditgraph.services import graphrag
from creditgraph.services.llm import DeterministicLLM, GroqLLM


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_candidate_tokens_filters_stopwords():
    tokens = graphrag._candidate_tokens(
        "Why is this borrower considered high risk for ETH?"
    )
    assert "borrower" not in tokens
    assert "risk" not in tokens
    assert "ETH" in tokens


def test_classify_intent_borrower_risk():
    assert graphrag._classify_intent("why is this borrower high risk") == "borrower_risk"


def test_classify_intent_concept():
    assert graphrag._classify_intent("what is the formula for VaR") == "concept_explanation"


def test_classify_intent_relationship():
    assert graphrag._classify_intent("explain the path between collateral and credit risk") == "relationship_path"


def test_classify_intent_regime():
    assert graphrag._classify_intent("what happens in a high volatility regime") == "regime"


def test_classify_intent_capability():
    assert graphrag._classify_intent("which capability manages treasury") == "capability"


def test_classify_intent_default():
    assert graphrag._classify_intent("hello world") == "graph_exploration"


def test_plan_query_returns_parameterized_cypher():
    cypher, params = graphrag._plan_query("borrower_risk", "borrower_demo_alice")
    assert "$entity" in cypher
    assert params == {"entity": "borrower_demo_alice"}


def test_node_summary_skips_identity_keys():
    props = {"name": "VaR", "definition": "short", "value": 1.5}
    summary = graphrag._node_summary(props)
    assert "name" not in summary
    assert "value=1.5" in summary


def test_relationship_label_mapping():
    assert graphrag._relationship_label("collateral") == "HAS_COLLATERAL"
    assert graphrag._relationship_label("formulas") == "HAS_FORMULA"
    assert graphrag._relationship_label("unknown") == "RELATED_TO"


# ---------------------------------------------------------------------------
# Evidence extraction (uses a fake record)
# ---------------------------------------------------------------------------


class _FakeNode:
    def __init__(self, labels, props):
        self.labels = labels
        self._props = props

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __iter__(self):
        return iter(self._props.items())


def test_extract_evidence_borrower_record():
    record = {
        "b": _FakeNode(["Borrower"], {"borrower_id": "b1", "requested_amount": 100000.0}),
        "collateral": [_FakeNode(["Collateral"], {"asset_id": "c1", "valuation": 95000.0})],
        "liabilities": [_FakeNode(["Liability"], {"protocol": "Aave", "outstanding": 12000.0})],
        "exposures": [],
        "decisions": [],
    }
    evidence, relationships, paths = graphrag._extract_evidence("borrower_risk", record)
    assert any(e["label"] == "Borrower" for e in evidence)
    assert any(e["label"] == "Collateral" for e in evidence)
    assert any("HAS_COLLATERAL" in r for r in relationships)


def test_extract_evidence_empty_record():
    evidence, relationships, paths = graphrag._extract_evidence("borrower_risk", None)
    assert evidence == []
    assert relationships == []
    assert paths == []


# ---------------------------------------------------------------------------
# Deterministic LLM explanation
# ---------------------------------------------------------------------------


def test_deterministic_llm_explanation_grounded():
    context = {
        "intent": "borrower_risk",
        "entities": [{"label": "Borrower", "name": "b1", "kind": "borrower"}],
        "evidence": [{"kind": "graph", "label": "Borrower", "name": "b1", "text": "requested_amount=100000"}],
        "relationships": ["b1 -[HAS_COLLATERAL]-> c1"],
        "paths": [["b1", "HAS_COLLATERAL", "c1"]],
        "quantitative": [{"label": "requested_amount", "value": 100000.0, "unit": ""}],
    }
    explanation = asyncio.run(DeterministicLLM().explain(context))
    assert "b1" in explanation
    assert "HAS_COLLATERAL" in explanation
    assert "deterministic" in explanation.lower()


# ---------------------------------------------------------------------------
# Groq LLM provider
# ---------------------------------------------------------------------------


def test_groq_llm_explanation(monkeypatch):
    """GroqLLM calls the Groq client and returns the model's content."""
    captured = {}

    class _FakeMessage:
        content = "Groq explanation"

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    class _FakeCompletions:
        async def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeAsyncGroq:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.chat = _FakeChat()

    import sys
    import types

    fake_groq = types.ModuleType("groq")
    fake_groq.AsyncGroq = _FakeAsyncGroq
    monkeypatch.setitem(sys.modules, "groq", fake_groq)

    provider = GroqLLM(api_key="test-key", model="llama-3.3-70b-versatile")
    explanation = asyncio.run(provider.explain({"intent": "borrower_risk"}))
    assert explanation == "Groq explanation"
    assert captured["api_key"] == "test-key"
    assert captured["kwargs"]["model"] == "llama-3.3-70b-versatile"
    assert captured["kwargs"]["temperature"] == 0.2


# ---------------------------------------------------------------------------
# Full pipeline with a mocked driver
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, record):
        self._record = record

    async def single(self):
        return self._record


class _FakeSession:
    def __init__(self, record):
        self._record = record

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def run(self, query, *args, **params):
        if args and isinstance(args[0], dict):
            params = {**args[0], **params}
        # Entity resolution queries return a Borrower node only for the known
        # demo borrower token; unknown tokens resolve to nothing.
        if "RETURN n LIMIT 1" in query and params.get("token") == "borrower_demo_alice":
            return _FakeResult(
                {"n": _FakeNode(["Borrower"], {"borrower_id": "borrower_demo_alice"})}
            )
        return _FakeResult(self._record)


class _FakeDriver:
    def __init__(self, record):
        self._record = record

    def session(self):
        return _FakeSession(self._record)


def test_graphrag_query_returns_structured_response(monkeypatch):
    """End-to-end pipeline with a mocked Neo4j driver (no DB needed)."""
    record = {
        "b": _FakeNode(["Borrower"], {"borrower_id": "borrower_demo_alice", "requested_amount": 100000.0}),
        "collateral": [_FakeNode(["Collateral"], {"asset_id": "c1", "valuation": 95000.0})],
        "liabilities": [],
        "exposures": [],
        "decisions": [],
    }
    driver = _FakeDriver(record)
    monkeypatch.setattr(graphrag, "get_driver", lambda: driver)

    result = asyncio.run(graphrag.graphrag_query("why is borrower_demo_alice high risk"))
    assert result["intent"] == "borrower_risk"
    assert result["entities"], "should resolve at least one entity"
    assert result["evidence"], "should retrieve graph evidence"
    assert result["explanation"], "should produce an explanation"
    assert result["traversal_error"] is None


def test_graphrag_query_no_entities(monkeypatch):
    """Pipeline handles a query that resolves no entities gracefully."""
    driver = _FakeDriver(None)
    monkeypatch.setattr(graphrag, "get_driver", lambda: driver)

    result = asyncio.run(graphrag.graphrag_query("zzz unknown gibberish"))
    assert result["entities"] == []
    assert result["evidence"] == []
    assert result["explanation"], "should still produce an explanation"