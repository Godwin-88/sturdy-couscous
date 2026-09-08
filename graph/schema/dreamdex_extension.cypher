// ── DreamDEX Event Contract KG Extension (additive to master.cypher) ─────────
// Loaded as a second pass by the graph-loader (after master.cypher, before
// creditgraph_extension.cypher). Existing graph untouched. Idempotent.

// ── Node types ──────────────────────────────────────────────────────────────
// EventContract: a live DreamDEX binary Up/Down market on a BTC/ETH price window
// Outcome: a binary resolution outcome
// MarketCategory: classification of event type

CREATE CONSTRAINT IF NOT EXISTS FOR (ec:EventContract) REQUIRE ec.market_id IS UNIQUE;

// Market category taxonomy (seed; runtime upserts add markets under these)
MERGE (:MarketCategory {name: "Crypto",     slug: "crypto"})
MERGE (:MarketCategory {name: "Sports",     slug: "sports"})
MERGE (:MarketCategory {name: "Politics",   slug: "politics"})
MERGE (:MarketCategory {name: "Economics",  slug: "economics"})
MERGE (:MarketCategory {name: "Technology", slug: "technology"})
MERGE (:MarketCategory {name: "Other",      slug: "other"});

// ── Relationship types added (read-only for existing graph) ─────────────────
// (EventContract)-[:ACTIVATES_IN]->(Regime)      ← links to existing regime nodes
// (EventContract)-[:CORRELATED_WITH]->(Concept)  ← links to existing BTC-USD Ticker/Concept
// (EventContract)-[:BELONGS_TO]->(MarketCategory)
// (Outcome)-[:RESOLVES]->(EventContract)

// Runtime upserts are performed by DreamDEXAgent via the shared graph helper
// (common/graph.get_db) — see agent/dreamdex_agent.py for the MERGE query.