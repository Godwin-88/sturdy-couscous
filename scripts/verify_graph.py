#!/usr/bin/env python3
"""Print node counts by label and spot-check key relationships."""

import os
from common.graph import get_db

db = get_db()

label_query = """
CALL db.labels() YIELD label
RETURN label
"""

counts_query = """
MATCH (n)
WITH labels(n) AS lbls, count(*) AS cnt
RETURN lbls[0] AS label, cnt
ORDER BY cnt DESC
"""

print("=== Node counts ===")
for row in db.execute_and_fetch(counts_query):
    print(f"  {row['label']:<25} {row['cnt']}")

rel_query = """
MATCH ()-[r]->()
RETURN type(r) AS rel_type, count(*) AS cnt
ORDER BY cnt DESC
"""
print("\n=== Relationship counts ===")
for row in db.execute_and_fetch(rel_query):
    print(f"  {row['rel_type']:<30} {row['cnt']}")

check_query = """
MATCH (s:Strategy)-[:ACTIVATED_BY]->(r:Regime)
RETURN s.name AS strategy, r.name AS regime
ORDER BY strategy LIMIT 10
"""
print("\n=== Sample Strategy->Regime links ===")
for row in db.execute_and_fetch(check_query):
    print(f"  {row['strategy']} -> {row['regime']}")
