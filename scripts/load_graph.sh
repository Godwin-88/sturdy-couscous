#!/bin/bash
# Load master.cypher into Neo4j. Waits for the bolt port to be ready.
set -euo pipefail

HOST="${NEO4J_HOST:-localhost}"
PORT="${NEO4J_PORT:-7687}"
CYPHER_FILE="${1:-master.cypher}"

echo "Waiting for Neo4j at $HOST:$PORT..."
for i in $(seq 1 30); do
    if nc -z "$HOST" "$PORT" 2>/dev/null; then
        echo "Neo4j is up."
        break
    fi
    sleep 2
done

echo "Loading $CYPHER_FILE ..."
cypher-shell -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-graphalpha}" -a "bolt://$HOST:$PORT" < "$CYPHER_FILE"
echo "Graph loaded successfully"
