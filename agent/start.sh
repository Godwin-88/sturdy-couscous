#!/bin/sh
set -e

# Ensure runtime deps are present even if image build cache skipped them
python3 -c "import jsonschema" 2>/dev/null || python3 -m pip install --quiet jsonschema

exec python3 orchestrator.py
