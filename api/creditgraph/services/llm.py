"""LLM provider abstraction for GraphRAG explanation (spec §26, NFR-007).

The GraphRAG engine is deterministic by default so the application runs with a
single docker command and no external API keys. An optional LLM provider can be
configured via ``LLM_PROVIDER`` to generate richer natural-language
explanations.

Separation of concerns (NFR-007 / §24):
  - Neo4j supplies relational context (real traversal)
  - The quantitative engine calculates risk (deterministic)
  - The LLM explains and orchestrates; it never alters calculated values.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from creditgraph.core.config import settings

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Interface for an explanation provider.

    A provider receives the assembled GraphRAG context and returns a
    natural-language explanation. Providers must never mutate the context's
    quantitative values.
    """

    @abstractmethod
    async def explain(self, context: dict[str, Any]) -> str:
        """Return a natural-language explanation for the assembled context."""


class DeterministicLLM(LLMProvider):
    """Template-based explanation generator (no external API required).

    Builds an explanation strictly from the evidence, graph relationships and
    quantitative outputs already present in the context. It never invents
    facts: every claim maps to a retrieved graph node or model output.
    """

    async def explain(self, context: dict[str, Any]) -> str:
        lines: list[str] = []
        intent = context.get("intent", "graph_exploration")
        entities = context.get("entities", [])
        evidence = context.get("evidence", [])
        relationships = context.get("relationships", [])
        quantitative = context.get("quantitative", [])
        paths = context.get("paths", [])

        # --- Lead line grounded in the resolved entities ---
        if entities:
            names = ", ".join(e.get("name", e.get("symbol", "?")) for e in entities[:3])
            lines.append(f"Based on the graph, the relevant entities are: {names}.")
        else:
            lines.append("No specific graph entities were resolved from the query.")

        # --- Graph relationships (real traversal output) ---
        if relationships:
            lines.append("Graph relationships retrieved:")
            for rel in relationships[:8]:
                lines.append(f"  • {rel}")
        else:
            lines.append("No direct graph relationships were found for this query.")

        # --- Reasoning paths (E4-US2) ---
        if paths:
            lines.append("Reasoning path:")
            for p in paths[:3]:
                lines.append(f"  → {' → '.join(p)}")

        # --- Quantitative outputs (deterministic, never altered) ---
        if quantitative:
            lines.append("Quantitative model outputs (deterministic):")
            for q in quantitative[:8]:
                lines.append(f"  • {q.get('label', 'metric')}: {q.get('value')} {q.get('unit', '')}")

        # --- Evidence (verified vs inference, E4-US3) ---
        if evidence:
            lines.append("Supporting evidence:")
            for ev in evidence[:8]:
                tag = ev.get("kind", "graph")
                lines.append(f"  • [{tag}] {ev.get('text', '')}")
        else:
            lines.append("No supporting evidence was retrieved.")

        # --- Explicit separation of inference (E4-US3) ---
        lines.append(
            "Note: the above separates verified evidence and graph relationships "
            "from AI-generated interpretation. Quantitative values are produced "
            "by the deterministic risk engine and are not altered by this explanation."
        )
        return "\n".join(lines)


class GroqLLM(LLMProvider):
    """Groq-backed explanation provider (fast LLM inference).

    Enabled by setting ``LLM_PROVIDER=groq`` and ``GROQ_API_KEY``.
    The provider only explains the assembled context; it cannot change the
    quantitative values computed by the deterministic engine.
    """

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile") -> None:
        self._api_key = api_key
        self._model = model

    async def explain(self, context: dict[str, Any]) -> str:
        # Imported lazily so the deterministic path has no external dependency.
        try:
            from groq import AsyncGroq
        except ImportError as exc:  # pragma: no cover - guarded by config
            raise RuntimeError(
                "LLM_PROVIDER=groq requires the 'groq' package. "
                "Install it or switch to LLM_PROVIDER=deterministic."
            ) from exc

        client = AsyncGroq(api_key=self._api_key)
        system = (
            "You are CreditGraph's financial reasoning assistant. "
            "Explain the provided graph context. Distinguish verified evidence, "
            "graph relationships, quantitative model outputs, and your own "
            "interpretation. Never invent facts or alter quantitative values."
        )
        resp = await client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": _render_context(context)},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""


def _render_context(context: dict[str, Any]) -> str:
    """Render the assembled context as a compact text block for an LLM."""
    import json

    return json.dumps(context, default=str, indent=2)


def get_llm_provider() -> LLMProvider:
    """Return the configured LLM provider (deterministic by default)."""
    provider = (settings.llm_provider or "deterministic").lower()
    if provider == "groq":
        if not settings.groq_api_key:
            logger.warning(
                "LLM_PROVIDER=groq but GROQ_API_KEY is unset; "
                "falling back to deterministic provider."
            )
            return DeterministicLLM()
        return GroqLLM(api_key=settings.groq_api_key, model=settings.groq_model)
    return DeterministicLLM()
