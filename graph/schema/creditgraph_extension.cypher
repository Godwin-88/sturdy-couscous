// ── CreditGraph KG Extension (additive to master.cypher + dreamdex_extension) ──
// Loaded as a third pass by the graph-loader. Existing graph untouched. Idempotent.
// See docs/p10_creditgraph_merge.md §6 for the full plan.

// ── Node types ──────────────────────────────────────────────────────────────
// Borrower: an obligor being assessed
// Wallet:   an on-chain wallet (EVM or Substrate)
// Evidence: an attested cross-chain transaction (Attestcoin inclusion proof)
// Attestation: the on-chain attestation reference
// CreditDecision: a scored, explainable lending recommendation
// Asset/Collateral/Liability/Exposure: the credit picture

CREATE CONSTRAINT IF NOT EXISTS FOR (b:Borrower)       REQUIRE b.borrower_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (e:Evidence)       REQUIRE e.evidence_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (a:Attestation)    REQUIRE a.attestation_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:CreditDecision) REQUIRE d.decision_id IS UNIQUE;

// ── Relationship types added (read-only for existing graph) ─────────────────
// (Evidence)-[:VERIFIED_BY]->(Attestation)
// (Borrower)-[:HAS_EVIDENCE]->(Evidence)
// (Borrower)-[:HAS_WALLET]->(Wallet)
// (Borrower)-[:HAS_EXPOSURE]->(Exposure)
// (CreditDecision)-[:BASED_ON]->(Evidence)
// (CreditDecision)-[:ACTIVATES_IN]->(Regime)      ← REUSES GraphAlpha's regime nodes
// (CreditDecision)-[:GOVERNED_BY]->(Strategy)     ← reuses existing KG strategies

// Runtime nodes are written by the ported credit_graph.py services
// (api/creditgraph/graph/credit_graph.py) into the SHARED Neo4j instance.