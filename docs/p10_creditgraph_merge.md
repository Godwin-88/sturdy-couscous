# P10 — CreditGraph (Attestcoin × Creditcoin) Merge

**Project:** GraphAlpha · **Phase:** P10 · **Status:** Plan (ready for implementation)
**Hackathon:** BUIDL CTC 2026 Fall — "BUIDL For The Real World" (Creditcoin & Credit Labs, Attestcoin Protocol series)
**Deadline:** September 13, 2026 23:59 ET (extended)
**Design principle:** *additive only* — every new file is a new file; exactly **four** surgical edits to existing files; nothing deleted or restructured.

---

## 1. Executive Summary

GraphAlpha — a knowledge-graph-grounded multi-agent trading system — merges with **CreditGraph**, a functional Creditcoin (Attestcoin Protocol) credit-intelligence platform, so that **one system, one knowledge graph, and one agent core serve two chains**:

- **DreamDEX / Somnia** (P9) — Event-Contract prediction markets on BTC/ETH windows.
- **CreditGraph / Creditcoin** (P10) — verifiable cross-chain credit risk decisioning, where cross-chain transaction **evidence is attested on Ethereum Sepolia and proved on Creditcoin** via the Attestcoin Protocol (`@gluwa/usc-sdk`).

Both chains share a single Neo4j knowledge graph, a single Redis, a single FastAPI gateway (`:8000`), and a single frontend — where the existing CreditGraph UI becomes **one menu item** in GraphAlpha's sidebar.

**Why this is achievable (verified, not assumed):**
- The two repos' `master.cypher` files are the **same lineage** — same `Concept`/`Formula`/`Strategy`/`Regime`/`Category` labels; GraphAlpha's 7,927-line file is a superset of CreditGraph's 7,027-line file. One KG is the *natural* end state.
- The two businesses are complementary, not overlapping: Somnia prediction markets (A) and Sepolia→Creditcoin lending (B) both consume the same regime/signal/KG machinery.
- CreditGraph ships **two working testnet Node services** (attestation-service, execution-service) and a 21-file Python FastAPI backend — the merge is a **namespaced port + env re-point**, not a rewrite.

---

## 2. Verified Ground Truth (read before building)

### 2.1 Attestcoin Protocol (from `docs.attestcoin.org`)

| Fact | Detail |
|---|---|
| SDK | `@gluwa/usc-sdk` (TypeScript/JavaScript; requires ethers v6 as peer) |
| Verification model | Transaction **inclusion proof** = Merkle proof (tx ∈ block tx-tree) + **continuity proof** (block ∈ sequence anchored at a Creditcoin attestation point) |
| Flow | `PrecompileChainInfoProvider` (query chainKey) → `ProofBuilder.waitUntilHeightAttested` (periodic attestation poll, default 15s / 15m timeout) → `getProof(txHash)` → `PrecompileBlockProver.verifySingle(chainKey, headerNumber, txBytes, merkleProof, continuityProof)` |
| Supported source chains (CC3 testnet) | **Ethereum Sepolia (chainKey 1)**, Ethereum Mainnet (chainKey 3) |
| Proof builder | Genesis attestation + hosted proof API (`https://proof-gen-api.cc3-testnet.creditcoin.network`) |
| On-chain verifier | `BlockProver` precompile `0x...0fd2`, `ChainInfo` precompile `0x...0fd3` (CC3) |

### 2.2 The `/attest` repo (CreditGraph, fully functional on testnet)

| Artifact | Path in `/attest` | What it is |
|---|---|---|
| Attestation relay | `attestation-service/` (Node/TS, Fastify) | Wraps `@gluwa/usc-sdk`; `POST /verify` returns `{verified, status, proof:{merkleProof, continuityProof}}`. Env: `SOURCE_RPC_URL` (Sepolia), `CREDITCOIN_RPC_URL`, `ATTESTCOIN_PROVER_URL`. Port **8080** |
| Execution relay | `creditcoin-execution-service/` (Node/TS, `@polkadot/api`) | Signs + monitors CTC transfers on CC3 testnet. `POST /execute` (needs human-approved decision), `POST /monitor` (scans finalized blocks for tx + dispatch success). Port **8081** |
| Python backend | `backend/app/` (FastAPI) | 11 routers under `/api/v1/risk/*` (credit, evidence, execution, decision, wallet, bayesian, correlation, portfolio, governance, scenario, quant) + `services/` (graphrag, quant_engine, credit_risk, evidence, governance, bayesian, correlation, portfolio, wallet_discovery, execution, llm) |
| Domain graph | `backend/app/graph/credit_graph.py` | Neo4j persistence for `Borrower`, `Wallet`, `Evidence`, `Attestation`, `Collateral`, `Liability`, `Exposure`, `CreditDecision` + lineage queries |
| Frontend | `frontend/` (React, Vite) | 7 tabs (Credit Dashboard, Risk Graph, Quantitative Risk, Evidence, Chat, Portfolio, Governance); `api.ts` uses `const BASE = "/api/v1"` |
| Knowledge graph | `master.cypher` (7,027 lines) | Same lineage as GraphAlpha's; **subset** (same labels) |
| Product spec | `CreditGraph — Product & Technical Specification.md` | Single source of truth for the CreditGraph domain (EPICs E1–E10, principles P1–P7) |

### 2.3 Repo surface to reuse (do not reinvent)

| Thing | Where | Reuse as |
|---|---|---|
| `orchestrator.py` agent registry + cycle | `agent/orchestrator.py` | 3-line additive hook: import / instantiate / `run()` |
| Regime classification | `agent/regime_agent.py` | Shared market-state view for both chains |
| KG crypto strategy engine | `agent/crypto_signal.py` (`suggest_crypto`) | Same strategy library gates CreditGraph scoring |
| Two-phase human gate | `api/routes/crypto.py` `/preview`→`/signals/place` | Apply to credit execution (P7: human decision authority) |
| Graph loader | `docker-compose.yml` `graph-loader` | Chain `cat` of 3 cypher files (one-line edit) |
| Router registration | `api/main.py` | One import + one `include_router` (+ lifespan init) |
| Sidebar nav | `frontend/src/App.tsx` `OP_TABS` + panel render | One menu item "Credit" + one route |
| `profiles:` compose convention | `backtest`/`ibkr`/`monitoring`/`dreamdex` | New `creditgraph` profile (invisible to `make up`) |
| P9 relay patterns | `dreamdex/` (config/sdkAdapter/order/claim/fills/index) | Blueprint for consent/execution in the CreditGraph agent |
---

## 3. Architecture (single-system view after merge)

```
                    ┌────────────────────────────── GraphAlpha (this repo) ──────────────────────────────┐
                    │  ONE Neo4j (Master KG: Concept/Formula/Strategy/Regime +                          │
                    │                 CreditGraph: Borrower/Evidence/Attestation/CreditDecision)        │
                    │  ONE Redis (agent status, signals, creditgraph:* keys)                            │
                    │                                                                                   │
   Somnia/DreamDEX  │   orchestrator.py (1-line register each)                                          │
   adapter (P9)     │     ├── DreamDEXAgent ──────────► DreamDEX relay (:8450, Node)                    │
   Sepolia→CC3      │     └── CreditGraphAgent ───────► creditgraph_adapter.py                          │
   adapter (NEW)    │           │  reads: RegimeAgent + KGStrategies + Attestcoin Evidence              │
                    │           ▼                                                                       │
   attestation-     │   GraphRAG + quant (deterministic) → CreditRecommendation (human-gated)          │
   service (:8080)  │           │                                                                       │
   execution-       │   api/routes/creditgraph.py :: /api/v1/risk/* (mounted in main.py)                 │
   service (:8081)  │           │                                                                       │
                    │   frontend: App.tsx + "Credit" menu item → CreditWorkspace (ported panels)        │
                    └───────────────────────────────────────────────────────────────────────────────────┘
```

Three new runtime pieces (all off the default `make up` path):

| Service | Source | Port | Chain |
|---|---|---|---|
| `attestation-service` | `creditgraph/attestation-service/` (verbatim copy) | 8080 | Ethereum Sepolia → CC3 testnet |
| `execution-service` | `creditgraph/execution-service/` (verbatim copy) | 8081 | Creditcoin CC3 testnet |
| `creditgraph` Python package | `api/creditgraph/` (ported, namespaced) | in-process on :8000 | shared KG |

**Data path (the money flow):**
```
Sepolia tx → attestation-service /verify → {verified, merkleProof, continuityProof}
              → CreditGraphAgent (evidence node in Neo4j)
              → GraphRAG + quant_engine (deterministic VaR/CVaR/EL)
              → CreditRecommendation (human approves)
              → execution-service /execute (signed CC3 transfer, CC keyring)
              → execution-service /monitor (finalized block scan → success/failure)
              → Neo4j CreditDecision lineage (reconstructible, auditable)
```

---

## 4. Files: new + allowed edits (definitive)

### 4.1 New files (all additive)

```
creditgraph/                                   # NEW root umbrella (mirrors dreamdex/)
  attestation-service/                         #   copied VERBATIM from /attest (node, fastify, usc-sdk)
  execution-service/                           #   copied VERBATIM (node, polkadot/api)
  README.md                                    #   points at this doc + both services' design rules

api/creditgraph/                               # NEW — the attest FastAPI surface, namespaced
  __init__.py
  main_router.py                               #   = attest backend/app/api/v1/router.py
  models.py                                    #   = attest backend/app/models.py (unchanged)
  core/config.py                               #   pydantic-settings, re-pointed to GraphAlpha env
  db/neo4j.py  db/redis_client.py              #   re-pointed to GraphAlpha credentials
  services/                                    #   attest services/ (evidence, graphrag, quant_engine,
                                               #     credit_risk, bayesian, correlation, portfolio,
                                               #     governance, wallet_discovery, execution, llm)
  graph/credit_graph.py                        #   attest graph persistence (unchanged queries)

agent/
  creditgraph_agent.py                         # NEW — per-chain agent (mirrors DreamDEXAgent)
  creditgraph_adapter.py                       # NEW — httpx clients → attestation-service/execution-service

api/routes/creditgraph.py                      # NEW — thin adapters: /api/v1/risk/* → creditgraph.services

graph/schema/
  creditgraph_extension.cypher                 # NEW — additive KG types + edges

frontend/src/components/credit/
  CreditWorkspace.tsx                          # NEW — hosts the 7 ported panels + tab set
  CreditDashboard.tsx  RiskGraph.tsx  StressTab.tsx  EvidenceTab.tsx
  ChatTab.tsx  PortfolioTab.tsx  GovernanceTab.tsx  Skeleton.tsx  MetricGrid.tsx
  NetworkGraph.tsx  StepIndicator.tsx  ScenarioBuilder.tsx  Toast.tsx  DemoModeButton.tsx
frontend/src/lib/creditApi.ts                  # NEW — attest api.ts (BASE /api/v1 retained)
frontend/src/types/credit.ts                   # NEW — attest types.ts
frontend/src/hooks/useScenarioState.ts         # NEW — attest hook

.env.example                                  # + 12 vars appended (creditgraph block)
docker-compose.yml                             # + attestation-service + execution-service blocks
Makefile                                       # + creditgraph-up/logs/test targets
```
### 4.2 Allowed edits to existing files (exactly four, nothing else)

| File | Edit | Why it's safe |
|---|---|---|
| `api/main.py` | +1 import (`creditgraph.main_router`), +1 `app.include_router(credit_router, prefix="/api/v1")`, +2 lifespan lines (init/close creditgraph Neo4j+Redis) | Router list is already `include_router`-based; additive |
| `docker-compose.yml` | `graph-loader` entrypoint: `cat /graph/master.cypher /graph/dreamdex_extension.cypher /graph/creditgraph_extension.cypher \| cypher-shell …` | One-line additive change; idempotent MERGE/CONSTRAINT files |
| `frontend/src/App.tsx` | +1 sidebar menu item "Credit" → `/credit`, +1 import, +1 route render | Same pattern as "Crypto" tab addition |
| `Makefile` | append `creditgraph-up/logs/test` + `.PHONY` additions | Append-only |

---

## 5. Environment variables (append to `.env.example`)

```env
# ── CreditGraph / Attestcoin × Creditcoin ─────────────────────────────────
CREDITGRAPH_ENABLED=0                  # master switch; agent self-disables when 0
# Attestation relay (:8080)
SOURCE_RPC_URL=https://sepolia.infura.io/v3/    # Sepolia (chainKey 1) — attested source
CREDITCOIN_RPC_URL=https://rpc.cc3-testnet.creditcoin.network
ATTESTCOIN_PROVER_URL=https://proof-gen-api.cc3-testnet.creditcoin.network
ATTESTATION_SERVICE_URL=http://localhost:8080
# Execution relay (:8081)
CREDITCOIN_WS_URL=wss://rpc.cc3-testnet.creditcoin.network
CREDITCOIN_EXECUTOR_SEED=              # lender Substrate seed (MANDATORY to enable execution; never commit)
CREDITCOIN_SS58_FORMAT=42
EXECUTION_SERVICE_URL=http://localhost:8081
# GraphRAG / LLM (optional)
LLM_PROVIDER=deterministic             # deterministic | groq
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
```

All existing vars unchanged. GraphAlpha boots identically if these are empty — `CREDITGRAPH_ENABLED=0` disables the agent with a warning log (same property as P9).

---

## 6. KG extension (`graph/schema/creditgraph_extension.cypher`) — additive

Appended as a third pass after `master.cypher` and `dreamdex_extension.cypher` by the graph-loader. Idempotent (`MERGE`/`CREATE CONSTRAINT IF NOT EXISTS`) — existing graph untouched.

```cypher
// ── CreditGraph Node Types ───────────────────────────────────────────────
// Borrower: an obligor being assessed
// Wallet:   an on-chain wallet (EVM or Substrate)
// Evidence: an attested cross-chain transaction (Attestcoin inclusion proof)
// Attestation: the on-chain attestation reference
// CreditDecision: a scored, explainable lending recommendation
// Asset/Collateral/Liability/Exposure: the credit picture

CREATE CONSTRAINT IF NOT EXISTS FOR (b:Borrower)        REQUIRE b.borrower_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (e:Evidence)        REQUIRE e.evidence_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (a:Attestation)     REQUIRE a.attestation_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:CreditDecision)  REQUIRE d.decision_id IS UNIQUE;

// Relationship types added (read-only for existing graph):
// (Evidence)-[:VERIFIED_BY]->(Attestation)
// (Borrower)-[:HAS_EVIDENCE]->(Evidence)
// (Borrower)-[:HAS_WALLET]->(Wallet)
// (Borrower)-[:HAS_EXPOSURE]->(Exposure)
// (CreditDecision)-[:BASED_ON]->(Evidence)
// (CreditDecision)-[:ACTIVATES_IN]->(Regime)      ← REUSES GraphAlpha's regime nodes
// (CreditDecision)-[:GOVERNED_BY]->(Strategy)     ← reuses existing KG strategies
```

Runtime nodes are written by `credit_graph.py` exactly as CreditGraph does today — but into **GraphAlpha's Neo4j**. This is what makes the two-chain claim real: `Borrower`/`Evidence`/`CreditDecision` nodes are *linked to* the same `Regime` and `Strategy` nodes that gate the DreamDEX/Somnia agent. One KG, multiple chain-readers.
---

## 7. Python port (`api/creditgraph/`)

The attest backend is 21 Python files on pydantic-settings + async `neo4j` driver + optional `groq`. Merge mechanics:

1. Create `api/creditgraph/` as a namespaced package.
2. Copy attest's `backend/app/` tree; rewrite **only** `app.` → `creditgraph.` in imports.
3. Re-point `db/neo4j.py` + `db/redis_client.py` + `core/config.py` to GraphAlpha's env names:
   - `bolt://neo4j:7687` → same service; auth `${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD:-graphalpha}`.
   - `redis://localhost:6379/0` → `REDIS_HOST`/`REDIS_PORT` (GraphAlpha redis service).
4. Gate endpoint modules that reference optional services (groq LLM → deterministic fallback, already built in).
5. Verify `/api/v1/risk/health` live on the merged :8000.

**No port race, no second CORS origin** — the attest surface is a router mount inside the existing app.

---

## 8. Agent (`agent/creditgraph_agent.py` + `agent/creditgraph_adapter.py`)

`creditgraph_agent.py` mirrors `DreamDEXAgent` exactly (P9 §9) — three-line orchestrator hook:

```python
# agent/orchestrator.py (3 additive lines)
from creditgraph_agent import CreditGraphAgent
self.creditgraph_agent = CreditGraphAgent(driver=self.driver)
credit_candidates = self.creditgraph_agent.run(regime=current_regime, signals=merged_signals)
```

Responsibilities:
- **Read** `agent_status`/`signals` from Redis (same keys GraphAlpha publishes).
- **Fetch/verify** cross-chain evidence via `creditgraph_adapter.py` → `attestation-service /verify`.
- **Score** borrower/credit via `api/creditgraph/services/` (deterministic quant + GraphRAG).
- **Write** `Borrower`/`Evidence`/`CreditDecision` nodes into the shared Neo4j.
- **Publish** `creditgraph:*` keys to Redis for the API/panel.
- **Self-disable** when `CREDITGRAPH_ENABLED=0` (identical safety to DreamDEX).

`creditgraph_adapter.py` = httpx clients for the two Node services, same `try/except` + `logger.warning` fallback conventions as `dreamdex_adapter.py`.

**Human gate (non-negotiable, P7 + U6):** execution never proceeds without a human-approved `CreditDecision` (`approval_status == "approved"`), the same two-phase preview/confirm pattern as `/crypto/preview` → `/signals/place`, plus the U6 kill-switch (`/freeze`).

---

## 9. API routes

Mount the attest `api_router` (11 sub-routers) at **`/api/v1`** in `api/main.py`:

| Router | Prefix (attest-compatible) | Purpose |
|---|---|---|
| scenario/quant | `/api/v1/risk/quant/*` | Scenario generation + analyze (deterministic) |
| credit | `/api/v1/risk/credit-score` | Bayesian-backed credit score (PD via logistic) |
| correlation | `/api/v1/risk/correlation/*` | Correlation matrix, groups |
| evidence | `/api/v1/risk/evidence/*` | `POST /verify` (attestation), list |
| execution | `/api/v1/risk/execution/*` | CC3 execution account/balances, human-gated execute |
| decision | `/api/v1/risk/decisions/*` | List/reconstruct/override decision lineage |
| wallet | `/api/v1/risk/wallet/*` | Resolve/aggregate wallet exposure |
| bayesian | `/api/v1/risk/bayesian/*` | Posterior updates from evidence |
| governance | `/api/v1/risk/governance/*` | Model registration, policy, audit log |
| portfolio | `/api/v1/risk/portfolio/*` | Exposure, counterparty, contagion, VaR, systemic stress |

**Frontend compatibility:** attest's `frontend/src/api.ts` hardcodes `const BASE = "/api/v1"` — so the ported panel code hits the right paths with **zero changes** to its API layer (only the Vite proxy / `VITE_API_URL` points at the merged :8000).
---

## 10. Frontend (`CreditWorkspace` + `App.tsx` menu item)

- Port attest's `frontend/src/components/*` (7 tabs) + `frontend/src/api.ts` → `creditApi.ts` + `types.ts` → `types/credit.ts` + hooks, namespaced under `frontend/src/components/credit/`.
- New `CreditWorkspace.tsx` hosts the tab set (Credit Dashboard, Risk Graph, Quantitative Risk, Evidence, Chat, Portfolio, Governance) exactly as attest's `App.tsx` renders them.
- `App.tsx`: add one sidebar item **"Credit"** (icon e.g. `Gold`/`Scale`) → `navigate("/credit")`, and render `<CreditWorkspace />` when `location.pathname.startsWith("/credit")`. That is the **only** edit to existing frontend code.
- Styling: the attest panels bring their own `index.css` classes; ship it scoped under `frontend/src/components/credit/` (or a `credit.css` import) so it doesn't clash with GraphAlpha's design system.

---

## 11. Docker & Makefile (append-only)

```yaml
  # ── CreditGraph: Attestcoin relay (:8080) ──────────────────────────────────
  attestation-service:
    build: { context: ./creditgraph/attestation-service }
    container_name: graphalpha-attestation
    env_file: .env
    environment:
      - SOURCE_RPC_URL=${SOURCE_RPC_URL:-https://sepolia.infura.io/v3/}
      - CREDITCOIN_RPC_URL=${CREDITCOIN_RPC_URL:-https://rpc.cc3-testnet.creditcoin.network}
      - ATTESTCOIN_PROVER_URL=${ATTESTCOIN_PROVER_URL:-https://proof-gen-api.cc3-testnet.creditcoin.network}
    ports: ["8080:8080"]
    profiles: ["creditgraph"]

  # ── CreditGraph: Creditcoin execution relay (:8081) ────────────────────────
  execution-service:
    build: { context: ./creditgraph/execution-service }
    container_name: graphalpha-execution
    env_file: .env
    environment:
      - CREDITCOIN_WS_URL=${CREDITCOIN_WS_URL:-wss://rpc.cc3-testnet.creditcoin.network}
      - CREDITCOIN_EXECUTOR_SEED=${CREDITCOIN_EXECUTOR_SEED:-}
    ports: ["8081:8081"]
    profiles: ["creditgraph"]
```

Makefile appends (matching `dreamdex-*` pattern):
```make
creditgraph-up:   docker compose --profile creditgraph up -d --build attestation-service execution-service
creditgraph-logs: docker compose logs -f attestation-service execution-service
creditgraph-test: (port attest's pytest suite; run inside api container) + npm typecheck in both node services
```

`profiles: [creditgraph]` ⇒ **completely invisible** to base `make up`.

---

## 12. Execution & human gates (financial-engineer view)

- **No autonomous money movement.** The merged bot *recommends*, a human *approves* (P7), then execution-service signs.
- **Evidence before inference (P1).** Every material risk conclusion references an attestation status (`verified`/`unverified` — never conflated). An `unverified` attestation is recorded as `unverified`, not dropped or upgraded.
- **Deterministic quant (P3).** VaR/CVaR/expected-loss/stress are computed by `quant_engine.py` (pure functions), not by the LLM. The LLM (opt-in groq) only *explains* the assembled context.
- **Lineage (P4/P6).** `reconstruct_decision()` walks the graph. This is the CreditGraph analog of P9's U4/U15 attestation ledger: every decision is a replayable, reconstructible path.
- **Human kill-switch + freeze.** The U6 `/freeze` control (from P9 tenet upgrades) extends to the credit pipeline: frozen ⇒ no new candidates, no execution; claims/evidence reads still work.

---

## 13. Testnet path (submission requirement — "deployed on a testnet")

1. **Attestation (Sepolia → CC3 testnet):** `attestation-service /health` + `/chains` verify supported chainKeys. `POST /verify {txHash}` for a Sepolia tx → `waitUntilHeightAttested` → proof → `verifySingle` → `verified: true`. (Functional in CreditGraph today.)
2. **Execution (CC3 testnet):** set `CREDITCOIN_EXECUTOR_SEED` (Substrate sr25519 via `@polkadot/keyring`); fund the lender; `POST /execute` only after a human-approved decision; `POST /monitor` confirms finalization + dispatch success in finalized-block scan.
3. **Demo artifact:** show Evidence(attestation) node → GraphRAG → CreditRecommendation → (human) → executed CC3 transfer → `monitor` confirms → `reconstruct_decision` replays the whole lineage. That single 90-second reel satisfies both "working prototype on testnet" and "meaningful Attestcoin Protocol integration."
---

## 14. Judging alignment (Creditcoin hackathon criteria)

| Requirement | How the merge satisfies it | Evidence |
|---|---|---|
| Working testnet prototype | CreditGraph's two Node services already run against CC3 testnet + Sepolia | repo state: services wired, RPC URLs testnet |
| Attestcoin Protocol integration (core) | `attestation-service` uses `@gluwa/usc-sdk` (`getProof`/`verifySingle`); evidence nodes + lineage persist | `attestation-service/src/index.ts` |
| Technical documentation | This doc + `creditgraph/README.md` + ported spec | docs/ |
| Depth of protocol utilization | Full verify→persist→decide→execute→reconstruct arc; not a mock | 11 routers + graph persistence |
| Original work during hackathon | The *merge* (shared KG, one agent core, cross-chain linkage) is new | this repo's diff |

---

## 15. Risk register

| Risk | Mitigation |
|---|---|
| Attestcoin supports only Sepolia/Mainnet today — no Somnia | Stated honestly in §1/§2; DreamDEX stays on its own on-chain oracle; if chain support expands, it's a one-line `chainKey` map |
| Key custody (executor seed) | Seed only in the execution-service container env; never committed; empty ⇒ 503 "not configured" (already built) |
| Neo4j constraint collisions | `CREATE CONSTRAINT IF NOT EXISTS`; unique properties namespaced (`borrower_id`/`evidence_id`/`decision_id`) vs P9 `market_id` |
| Redis key collisions | creditgraph uses `creditgraph:*` prefix (evidence, decisions, candidates) |
| API port / CORS | Routers mounted in-process on :8000; frontend BASE `/api/v1` unchanged; GraphAlpha CORS already `*` |
| groq dependency | `LLM_PROVIDER=deterministic` default (no key) — the deterministic GraphRAG path already falls back gracefully |
| Python version skew | attest backend on python:3.11-slim (same as GraphAlpha api); async neo4j + fastapi already in GraphAlpha requirements |
| Time budget (deadline Sep 13) | Port is copy+rewrite, not from-scratch; all creditgraph code lands behind `profiles:` |

---

## 16. Build & test sequence

```bash
# 1. Append env (kept empty except CREDITGRAPH_ENABLED=0 during development)
cat >> .env << 'EOF'
CREDITGRAPH_ENABLED=0
SOURCE_RPC_URL=https://sepolia.infura.io/v3/
CREDITCOIN_RPC_URL=https://rpc.cc3-testnet.creditcoin.network
ATTESTCOIN_PROVER_URL=https://proof-gen-api.cc3-testnet.creditcoin.network
...
EOF

# 2. Copy the two Node services
cp -r /path/to/attest/attestation-service   creditgraph/
cp -r /path/to/attest/creditcoin-execution-service creditgraph/

# 3. Boot relay containers standalone (profile)
docker compose --profile creditgraph up -d --build attestation-service execution-service
curl localhost:8080/health && curl localhost:8081/health

# 4. Load the KG extension (idempotent)
docker compose run --rm graph-loader   # now cats master + dreamdex + creditgraph

# 5. Port the Python backend, then boot normally
make up
curl localhost:8000/api/v1/risk/health

# 6. Agent + orchestrator (CREDITGRAPH_ENABLED=1)
make logs-agent | grep CreditGraph

# 7. Frontend
#    App.tsx "Credit" menu item → http://localhost:5173/credit
```

---

## 17. Acceptance criteria

| Stage | Acceptance (stub-based unless noted; no testnet key required) |
|---|---|
| Node services | `/health` returns ok; `attestation-service /chains` lists supported chainKeys; `execution-service /account` returns `configured:false` cleanly when no seed |
| KG extension | graph-loader completes; `MATCH (n) RETURN labels(n)[0]` shows Borrower/Evidence/Attestation present after CreditGraph service runs once |
| Python port | `/api/v1/risk/health` 200 on merged :8000; `/api/v1/risk/credit-score` returns deterministic score |
| Agent | `CREDITGRAPH_ENABLED=0` ⇒ no candidates, warning log; `=1` ⇒ evidence fetch + candidates in `creditgraph:*` Redis keys |
| Frontend | `/credit` renders the 7 ported tabs against merged /api/v1 |
| Audit | `reconstruct_decision` replays a full lineage from Neo4j |

---

## 18. References

- Attestcoin Protocol docs — https://docs.attestcoin.org (chains: `/attestcoin-protocol/attestcoin-protocol-chains-environments`; SDK: `/attestcoin-protocol/dapp-builder-infrastructure/attestcoin-sdk-usc-sdk`)
- CreditGraph source — `/attest` (this machine); spec: `CreditGraph — Product & Technical Specification.md`; services: `attestation-service/`, `creditcoin-execution-service/`, `backend/app/`
- GraphAlpha P9 plan — `docs/p9_dreamdex_integration.md`; tenet upgrades — `docs/p9_tenets_financial_engineering.md`

---

## 19. Tenet crosswalk (financial-engineering + agentic)

See `docs/p9_tenets_financial_engineering.md` §3C (Agentic ledger A1–A7) and §4 U18–U24 for the full mapping. Quick view:

| Tenet | CreditGraph application |
|---|---|
| U1 / M1 (oracle verify) | Attestcoin `waitUntilHeightAttested → getProof → verifySingle` is U1's oracle verification, formalized |
| U5 (own clearinghouse) | `execution-service /monitor` + `credit_graph` reconciliation = cross-chain position book |
| U14 / C1 (confirmations) | Apply `REQUIRED_CONFIRMATIONS` to CC3 transfers (finalized-block scan) |
| U15 / C2 (Merkle anchor) | Attestcoin **is** the Merkle+continuity anchor — reuse instead of custom |
| U16 / C3 (key hygiene) | `@polkadot/keyring` sr25519; extend `crypto-hygiene` gate to `creditgraph/` |
| P3 / F3 (deterministic quant) | `quant_engine.py` pure functions; LLM only explains |
| P6/P7 + U6 (governance/human) | override-with-reason + two-phase confirm + freeze |
| A1 (hybrid memory) | Redis = short-term; Neo4j Evidence graph = long-term |
| A2 (plan/reflection) | orchestrator = plan formulation; `/backtest` + `reconstruct_decision` = reflection |
| A3 (graph before generation) | one GraphRAG over one KG |
| A4 (multi-agent) | orchestrator registry = task planner; per-chain agents = specialist pool |
| A7 (human-in-the-loop) | P7 + U6 give the "professional behind the wheel" |

---

## 20. Implementation status (built & validated)

Implemented additive-only per §4 and validated **in Docker** (per repository
policy — no host-side tests):

| Artifact | Status | Evidence |
|---|---|---|
| `creditgraph/{attestation-service,execution-service}` | ✅ copied verbatim | images build; added `typecheck` script; both `npm run typecheck` pass (via `make creditgraph-test`) |
| `api/creditgraph/` (33 files) | ✅ ported + namespaced | `app.` → `creditgraph.`; `from neo4j import AsyncDriver` type-only imports neutralized |
| `api/creditgraph/db/neo4j.py` | ✅ async facade over sync 4.x | `asyncio.to_thread` wraps `GraphDatabase.driver`; full `session()/run()/single()/__aiter__` API |
| `api/creditgraph/core/config.py` | ✅ re-pointed | falls back to GraphAlpha `NEO4J_HOST/PORT/PASSWORD` + `REDIS_HOST/PORT` |
| `api/main.py` | ✅ +5 lines | router include at `/api/v1` (42 routes) + best-effort lifespan init |
| `api/routes/creditgraph.py` | ✅ +4 thin endpoints | `/creditgraph/{services,candidates,status,health}` (prefix fix applied — name collision resolved) |
| `agent/creditgraph_adapter.py` | ✅ 10 defensive fns | httpx clients to both Node services + merged gateway |
| `agent/creditgraph_agent.py` | ✅ mirrors DreamDEXAgent | self-disable, chain probe, deterministic scoring, `creditgraph:*` Redis keys |
| `agent/orchestrator.py` | ✅ +7 lines | import + instantiate + non-fatal run() in cycle (Step 2e) |
| `frontend/src/components/credit/` | ✅ 14 components + workspace | scoped `credit.css` (127 rules); imports re-pointed; chart deps added |
| `frontend/src/App.tsx` | ✅ +4 lines | "Credit" sidebar item → `CreditWorkspace` |
| `frontend` typecheck + build | ✅ Docker | `tsc --noEmit` exit 0; `vite build` exit 0 |
| Tests | ✅ 40 passed | `tests/test_creditgraph_*.py` (agent, credit_risk, evidence, execution, graphrag) |
| Full suite | ✅ **222 passed** | `pytest tests -q` in api container (was 182 pre-P10) |
| `Makefile` | ✅ `creditgraph-test` | typechecks both Node services + python suite, all in Docker |

**Actual deviations from this plan (all additive, no scope reduction):**
1. `core/config.py` uses `pydantic.Field(default_factory=...)` fallbacks instead of a separate `NEO4J_URI` env — same `.env`, one driver config for both stacks.
2. The async facade (§7) lives in `api/creditgraph/db/neo4j.py`, not a shared `common/` module — keeps the port self-contained.
3. Node services gained a `typecheck` script (they previously had only `build`).
4. Test fakes were widened to accept the positional `run(query, params_dict)` neo4j contract (`*args` merged into `**params`).

**Remaining (deferred to demo day, needs funded testnet keys):**
- Sepolia/CC3 lifecycle proof — `attestation-service /verify` on a real tx + `execution-service /execute` (human-approved).
- KG extension load — `graph/schema/creditgraph_extension.cypher` is written; `graph-loader` cat order already includes it (P9 commit).
- `CREDITGRAPH_ENABLED=1` end-to-end with live services up.

*End of P10 plan. Implementation order (see §16): Node services → KG extension → Python port → agent → frontend.*
**Honest constraint (from `docs.attestcoin.org`):** the Attestcoin Protocol currently attests exactly two source chains — **Ethereum Sepolia (chainKey 1)** and **Ethereum Mainnet (chainKey 3)** — on Creditcoin CC3 testnet/mainnet. It does **not** attest Somnia. The merge therefore uses **Sepolia→Creditcoin as the functional attested chain**, and keeps DreamDEX on its own on-chain market status (unchanged from P9). We do not claim Somnia is Attestcoin-attested.