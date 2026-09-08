"""Application configuration via environment variables.

Re-pointed for the GraphAlpha merge (P10): when the dedicated
``NEO4J_URI`` / ``REDIS_URL`` vars are absent, the settings fall back to
GraphAlpha's split env names (``NEO4J_HOST``/``NEO4J_PORT``/``NEO4J_PASSWORD``
and ``REDIS_HOST``/``REDIS_PORT``) so a single ``.env`` drives both stacks.
"""

import os
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_origins(raw: str | None) -> list[str]:
    """Parse a comma-separated CORS origin list (or fall back to defaults)."""
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://frontend:5173",
    ]


def _default_neo4j_uri() -> str:
    host = os.getenv("NEO4J_HOST", "neo4j")
    port = os.getenv("NEO4J_PORT", "7687")
    return f"bolt://{host}:{port}"


def _default_neo4j_password() -> str:
    return os.getenv("NEO4J_PASSWORD", "graphalpha")


def _default_redis_url() -> str:
    host = os.getenv("REDIS_HOST", "redis")
    port = os.getenv("REDIS_PORT", "6379")
    return f"redis://{host}:{port}/0"


class Settings(BaseSettings):
    # --- App ---
    app_name: str = "CreditGraph"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"

    # --- Neo4j ---
    neo4j_uri: str = Field(default_factory=_default_neo4j_uri)
    neo4j_user: str = "neo4j"
    neo4j_password: str = Field(default_factory=_default_neo4j_password)
    neo4j_database: str = "neo4j"

    # --- Redis ---
    redis_url: str = Field(default_factory=_default_redis_url)

    # --- GraphRAG / LLM (Groq) ---
    llm_provider: str = "deterministic"  # "deterministic" | "groq"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    graphrag_max_evidence: int = 12
    graphrag_max_paths: int = 3
    graphrag_max_relationships: int = 20

    # --- Attestcoin evidence (E1) ---
    attestation_service_url: str = "http://attestation-service:8080"
    attestation_service_timeout: float = 30.0

    # --- Creditcoin execution (E10) ---
    execution_service_url: str = "http://execution-service:8081"
    execution_service_timeout: float = 90.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origins(self) -> list[str]:
        # Read raw env value directly to support comma-separated CORS_ORIGINS.
        return _parse_origins(os.getenv("CORS_ORIGINS"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
