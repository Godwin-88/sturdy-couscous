// ── DeFi KG Extension (additive to master.cypher + dreamdex + creditgraph) ──
// Loaded as a fourth pass by the graph-loader. Existing graph untouched. Idempotent.
// See docs/p11_web3_defi_expansion.md §5 for the full plan.

// ── Node types ──────────────────────────────────────────────────────────────
// EventWindow:     a DreamDEX EC market window (reuses P9 EventContract)
// Outcome:         EC resolution outcome (YES/NO, P9)
// Attestation:     P10 Merkle+continuity proof (Sepolia → Creditcoin)
// ── EVM DeFi types (ported strategy nodes; venue = Ethereum Sepolia testnet) ─
// AMMPool:         Uniswap V3 testnet pool
// LendingPool:     Aave V3 testnet market
// VaultStrategy:   yield-aggregator strategy (book Ch.12)
// PerpetualMarket: perp venue + funding rate
// OracleFeed:      EC/EVM price-feed freshness + deviation

CREATE CONSTRAINT IF NOT EXISTS FOR (w:EventWindow)     REQUIRE w.symbol IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (p:AMMPool)         REQUIRE p.pool_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (l:LendingPool)     REQUIRE l.pool_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (v:VaultStrategy)   REQUIRE v.strategy_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (m:PerpetualMarket) REQUIRE m.market_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (o:OracleFeed)      REQUIRE o.feed_id IS UNIQUE;

// OracleFeed freshness taxonomy (seed; runtime upserts refresh feed state)
MERGE (:OracleFeed {feed_id: "ec-resolver-somnia",    kind: "ec_resolution", chain: "somnia"})
MERGE (:OracleFeed {feed_id: "evm-price-sepolia",     kind: "evm_price",      chain: "sepolia"})
MERGE (:OracleFeed {feed_id: "attested-creditcoin",   kind: "attested_data",  chain: "creditcoin"});

// ── Relationship types added (read-only for existing graph) ─────────────────
// (EventWindow)-[:ACTIVATES_IN]->(Regime)          ← shared market-state spine
// (EventWindow)-[:GOVERNED_BY]->(Strategy)         ← shared strategy spine
// (EventWindow)-[:CORRELATED_WITH]->(Ticker)       ← spot/EC correlation (D5)
// (EventWindow)-[:RESOLVED_BY]->(OracleFeed)       ← EC resolution oracle (D6)
// (AMMPool)-[:PROVIDES_LIQUIDITY_TO]->(LiquidityRange)
// (BorrowerPosition)-[:HELD_AT]->(LendingPool)
// (VaultStrategy)-[:INVESTS_IN]->(AMMPool)
// (PerpetualMarket)-[:PRICED_BY]->(OracleFeed)
// (OracleFeed)-[:AUTHENTICATED_BY]->(Attestation)  ← P10 tie-in (D8)

// Runtime upserts are performed by DeFiAgent via the shared graph helper
// (common/graph.get_db) — see agent/defi_agent.py for the MERGE query.