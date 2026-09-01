"""Unified knowledge-graph database access (GQLAlchemy).

GraphAlpha runs on **Neo4j Community** (dockerized) as of the Alpaca hackathon
submission. This thin wrapper is the single connection factory used by agents,
API routes and backtest so every consumer shares one code path.

Env vars (Neo4j-first; legacy MEMGRAPH_* names honoured as fallback so old
.env files don't break; MEMGRAPH_ONLY=1 forces the legacy Memgraph driver):
  NEO4J_HOST       default "neo4j"
  NEO4J_PORT       default "7687"
  NEO4J_USER       default "neo4j"
  NEO4J_PASSWORD   default "graphalpha"   (matches docker-compose default)
  NEO4J_ENCRYPTED  default "false"        (set "true" for neo4j+s:// / AuraDB)
"""
from __future__ import annotations

import os

from gqlalchemy import Memgraph, Neo4j


def get_db():
    host = os.getenv("NEO4J_HOST", os.getenv("MEMGRAPH_HOST", "neo4j"))
    port = int(os.getenv("NEO4J_PORT", os.getenv("MEMGRAPH_PORT", "7687")))
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "graphalpha")
    encrypted = os.getenv("NEO4J_ENCRYPTED", "false").lower() in ("1", "true", "yes")

    if os.getenv("MEMGRAPH_ONLY", "").lower() in ("1", "true"):
        return Memgraph(host=host, port=port)

    return Neo4j(host=host, port=port, username=user, password=password, encrypted=encrypted)


__all__ = ["get_db"]
