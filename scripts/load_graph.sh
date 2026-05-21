#!/usr/bin/env bash
# Load master.cypher into Memgraph. Waits for the bolt port to be ready.
set -euo pipefail

HOST="${MEMGRAPH_HOST:-localhost}"
PORT="${MEMGRAPH_PORT:-7687}"
CYPHER_FILE="${1:-graph/schema/master.cypher}"

echo "Waiting for Memgraph at $HOST:$PORT..."
for i in $(seq 1 30); do
    if nc -z "$HOST" "$PORT" 2>/dev/null; then
        echo "Memgraph is up."
        break
    fi
    sleep 2
done

echo "Loading $CYPHER_FILE ..."

# Split on semicolons and execute each statement
grep -v '^\s*//' "$CYPHER_FILE" | \
    csplit --quiet --prefix=/tmp/stmt_ - '/;/' '{*}' 2>/dev/null || true

# Fallback: use mgconsole if available
if command -v mgconsole &>/dev/null; then
    mgconsole --host "$HOST" --port "$PORT" < "$CYPHER_FILE"
else
    python3 - <<EOF
import re, os
from gqlalchemy import Memgraph

db = Memgraph(host="$HOST", port=$PORT)
text = open("$CYPHER_FILE").read()
# Strip single-line comments
text = re.sub(r'//[^\n]*', '', text)
stmts = [s.strip() for s in text.split(';') if s.strip()]
ok = err = 0
for stmt in stmts:
    try:
        db.execute(stmt)
        ok += 1
    except Exception as e:
        err += 1
        if err <= 5:
            print(f"WARN: {e}")
print(f"Done. {ok} OK, {err} errors.")
EOF
fi
