"""Agent gateway: skills, Neo4j context, Ollama RAG."""

from .llm_client import OllamaClient
from .routes import router

__all__ = ["OllamaClient", "router"]
