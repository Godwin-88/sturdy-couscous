import os
from gqlalchemy import Memgraph, Neo4j


def get_db():
    host = os.getenv("NEO4J_HOST", os.getenv("MEMGRAPH_HOST", "localhost"))
    port = int(os.getenv("NEO4J_PORT", os.getenv("MEMGRAPH_PORT", "7687")))
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")

    if password:
        return Neo4j(host=host, port=port, username=user, password=password)
    return Memgraph(host=host, port=port)
