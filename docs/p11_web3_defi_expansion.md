# P11 — "Web3 Agentic Alpha": Attested DeFi Agent Expansion

> **One KG. One agent core. Every chain + every DeFi sector as a strategy module,
> all decisions signed, hashed, chained, and human-gated. Practice on testnets.
> Profits on mainnet. Everything additive.**

Companion to `p9_dreamdex_integration.md` and `p10_creditgraph_merge.md`.
Derives its assurance layer from *Cryptographic Primitives in Blockchain
Technology* (Bolfing, OUP) and its profit catalogue from *How to DeFi: Advanced*
(CoinGecko, 1st ed. 2021). Tenet ledger & upgrades U25–U33 are appended to
`p9_tenets_financial_engineering.md`.

---

## 1. Executive Summary

The two source books supply the **two halves of one machine**:

- **Cryptographic Primitives → the assurance layer.** Hash functions
  (256-bit outputs, birthday-attack semantics), digital signatures
  (unforgeability + integrity + non-repudiation), Merkle trees (O(log n)
  membership proofs), Byzantine agreement (signed messages relax quorums —
  with authentication you need fewer independent confirmations than the
  n > 3f bound), and Proof-of-Work (cheap to *verify*, expensive to *forge*).
  **Design rule: every agent decision is signed, hashed into a chain,
  batched into a Merkle root, and optionally anchored on-chain — the KG
  becomes tamper-evident.**
- **How to DeFi: Advanced → the profit catalogue.** AMMs (slippage,
  front-running, impermanent loss), lending/borrowing (utilization → rates,
  collateral factor → liquidation math), yield farming & aggregators (Yearn v2
  multi-strategy vaults; leveraged farming risks), decentralized derivatives
  (perpetual funding, options, synthetics), prediction markets (P9 already),
  oracles & data aggregators (Black Thursday: stale feeds → $8M ETH collateral
  lost), cross-chain bridges (P10 already), and the exploit catalogue (flash
  loans, oracle attacks, unlimited-approval hygiene).

**The target:** GraphAlpha as a **KG-gated, on-chain-attested agent platform** —
one Neo4j reasoning over Equities (existing), Somnia prediction markets (P9,
execution via `somnia-relay`), **Ethereum/Sepolia EVM DeFi** (this plan's
`web3-relay`, template-ported from the `stellcasp` repo), and Creditcoin
attested credit (P10, via `attestation-service`/`execution-service`).

**P11 grounded as three execution venues:**
1. **DreamDEX Event Contracts — Somnia 50312** (current default; `somnia-relay` :8450).
2. **EVM DeFi — Ethereum Sepolia testnet** (`web3-relay` :8460, **ported from
   `stellcasp/zkkyc/adapters/ethereum.py`** — a working web3.py EVM client with
   Sepolia RPC, contract ABI calls, build/sign/send/wait-receipt — plus the
   Foundry + Solidity contracts in `stellcasp/ethereum/`). D1–D4 attach here.
3. **CreditGraph — Sepolia→Creditcoin** (attested data; P10 services).

The *How to DeFi* catalogue (D1–D4) executes here on **real Sepolia testnet**
contracts (Uniswap V3 / Aave V3) through a **real, already-written code path**
ported from `stellcasp` — no invention, no phantom. The `web3-relay` is a
first-class venue alongside the existing Somnia and Creditcoin services.

---

## 2. Verified ground truth (read before building)

All line references are to the markdown exports in this repo.

### 2.1 From *Cryptographic Primitives in Blockchain Technology*

| Book fact (verified) | Agent/KG application |
|---|---|
| Digital Signature scheme = keypair + unforgeability + integrity + non-repudiation (Ch. 3.3.2.4) | **Every agent decision signed.** `evidence_chain.py` signs canonical decision JSON; API + panel verify with the public key. |
| Hash security: 128-bit level required; birthday attack ⇒ 256-bit outputs (Ch. 3.4) | Every decision hashed to `sha256`; chain links `hash(prev, cycle)` so tampering breaks continuity. |
| Merkle trees: aggregate N leaves, O(log N) proof (Ch. 3.5) | Batch all cycle decisions into one **Merkle root** per period; optionally anchor root on a testnet contract. |
| Byzantine agreement: without authentication n > 3f; authenticated messages relax quorums (Ch. 5.3.8) | Signed attestations (P10 Attestcoin already Merkle+continuity) let the agent trust **fewer** independent confirmations — cheaper, still sound. |
| PoW = cheap to verify, expensive to forge, difficulty adjustable, nonce semantics (Ch. 6.7) | Deterministic quant is **recompute-verifiable** (`verify_candidate()`); cycle nonce = f(prev_root, round, regime) → replay protection. |
| Blockchain security goals: identification = address, authentication = wallet sig, authorization = tx sig, integrity = chain, non-repudiation = executed tx (Ch. 6.6) | Map the same five into the pipeline: agent identity = pubkey, orders = signed intents, execution = on-chain tx, ledger = hash-chain + Neo4j, receipts = fills with tx_hash. |

### 2.2 From *How to DeFi: Advanced*

| Sector (ch.) | Lesson (verified) | KG/agent strategy |
|---|---|---|
| AMMs (Ch. 3) | Constant-product `x·y = k`; slippage; front-running; IL: 3× price = 13.4%, 4× = 20%, 5× = 25.5% loss vs HODL | `AMMPool` + `LiquidityRange` nodes; LP only when fee-yield − IL − gas > 0; range width from KG vol regime. |
| Lending & Borrowing (Ch. 5) | Utilization ratio drives rates; collateral factor defines liquidation | `LendingPool` + `BorrowerPosition` nodes; agent monitors utilization + liquidation distance; collateral-swap rescue. |
| Yield farming & aggregators (Ch. 2, 12) | Vaults socialize gas + auto-compound (Yearn v2: up to 20 strategies); new farms ≈ hack-risk; leveraged farming multiplies IL + liquidation risk | `VaultStrategy` nodes; risk-adjusted APY = raw − hack-prior − IL − liq-risk; leverage capped by liquidation distance. |
| Derivatives (Ch. 7) | Perpetual funding, options, synthetics | `PerpetualMarket` + `FundingRate` nodes; funding-carry trade gated by KG trend. |
| Prediction markets (Ch. 10) | YES/NO shares pay $1/$0; resolution/oracle risk; hedge-any-risk | Already P9 (DreamDEX). Add: cross-hedge EC vs spot via KG correlation edges. |
| Oracles & data aggregators (Ch. 13) | Black Thursday: stale Chainlink/Medianizer feeds → $8M ETH collateral lost; Band slashing → honest validators | `OracleFeed` nodes; **staleness/deviation circuit-breaker**: pause aggressive strategies when feed stale or outside deviation band. |
| Insurance (Ch. 8) | Cover pricing/claims; capital efficiency | Tail-hedge premium model keyed to KG regime (Crisis/Stress → buy cover). |
| Multi-chain / bridges (Ch. 14) | Cross-chain protocols, bridge risk | Already P10 (Attestcoin Sepolia→Creditcoin). Audited-attested feeds only (D8). |

> **Scope note (v3).** The AMM/Lending/Yield/Derivatives rows above are the
> *book's* sector catalogue — ground truth for the strategies. They now have a
> **real venue**: **Ethereum Sepolia testnet**, where Uniswap V3 and Aave V3
> have live testnet deployments. `web3-relay` :8460 executes D1–D4 via a
> **ported EVM adapter from `stellcasp/zkkyc/adapters/ethereum.py`** (a working
> web3.py Sepolia client). D5–D8 execute on DreamDEX/Somnia as before.

---

## 3. Target architecture (additive — grounded on the chains we run)

```
                    ┌─────────────────────────── GraphAlpha ONE (this repo) ────────────────────────────┐
                    │  ONE Neo4j KG: Concept/Formula/Strategy/Regime/Category +                          │
                    │     EventContract (P9) + Borrower/Evidence/CreditDecision (P10)                    │
                    │     + EventWindow/AMMPool/LendingPool/VaultStrategy/OracleFeed (P11, additive)     │
                    │  ONE Redis: agent_status, signals, evidence_chain, dreamdex:*, creditgraph:*,      │
                    │             defi:* keys                                                            │
                    │                                                                                    │
  Somnia (P9, EXEC) │   orchestrator.py (= registry: DreamDEX, CreditGraph + NEW DeFiAgent hook)         │
  EVM (P11, EXEC)   │     ├─ DreamDEXAgent ───────► somnia-relay (:8450, Node, markets-sdk)              │
  Creditcoin (P10)  │     ├─ CreditGraphAgent ─────► attestation (:8080) + execution (:8081)             │
  (attested data)   │     └─ DeFiAgent ─────────────► web3-relay (:8460, EVM DeFi, Sepolia)              │
                    │           │   reads: Regime + KGStrategies + Attestation(creditgraph) integrity    │
                    │           ▼                                                                        │
                    │   evidence_chain.py: sign → sha256 → hash-chain → Merkle-batch → optional anchor    │
                    │   api/routes/defi/* + DefiWorkspace.tsx (EC + EVM DeFi / EvidenceChain)            │
                    └────────────────────────────────────────────────────────────────────────────────────┘
```

- **Execution venue A — DreamDEX Event Contracts on Somnia (chain 50312), via
  `somnia-relay` (:8450).** D5–D8 candidates flow through the existing
  DreamDEX path (unchanged).
- **Execution venue B — Ethereum/Sepolia EVM DeFi via `web3-relay` (:8460).**
  D1–D4 (AMM-LP, lending carry, yield-farm, perp funding) execute here. The
  relay is **ported from `stellcasp/zkkyc/adapters/ethereum.py`** (web3.py
  Sepolia client + `build_transaction`/`sign_transaction`/`wait_for_receipt`
  = the U2/U3 action path) plus **`stellcasp/ethereum/` Foundry contracts**
  (Soulbound ERC-721 anchor + UltraHonk verifier).
- **Data venue — Ethereum Sepolia → Creditcoin (P10).** `Attestation` nodes
  (Merkle+continuity proofs) inform which EC resolution + EVM data feeds are
  trustworthy (D6/D8).
- P11 is additive across **all three venues**; `web3-relay` is `profiles: [web3]`
  (invisible to `make up`), exactly like `dreamdex`/`creditgraph`.

---

## 4. The cryptographic assurance layer (`agent/evidence_chain.py`)

Pure-Python (hashlib; ECDSA via `eth_account` for signing — no new heavy deps),
fully hermetic, stub-able.

1. **`canonicalize(obj)`** — deterministic JSON of a cycle's decisions (sorted
   keys, stable float formatting, stable list ordering).
2. **`hash_decision(d)`** → `"sha256:" + hexdigest(sha256(canonical))` — the
   Merkle-Damgård security level from the book (Ch. 3.4).
3. **Hash chain** — Redis key `evidence_chain:root` = hash of
   `(prev_root, cycle_id, regime, decision_hashes[])`; each entry stores the
   leaf hashes + prev pointer. **Tampering anywhere breaks the chain.**
4. **`sign_root(privkey, root)` / `verify_root(pubkey, root, sig)`** — the
   relay signs the daily root with the chain wallet; API + panel display
   verification. The signature brings unforgeability + non-repudiation
   (Ch. 3.3.2.4).
5. **`merkle_root(batch)`** — batch day-root leaves → Merkle root (mirrors
   Attestcoin's Merkle+continuity design; P10 `Attestation` nodes reuse).
6. **Optional anchor** — `web3-relay` exposes `POST /anchor` → publishes the
   periodic root to a minimal `GraphAlphaAnchor` testnet contract (deploy
   script included). Demo wow: *"every decision this bot made is provably
   chained — one hash on testnet."*
7. **`verify_candidate(d, recompute_fn)`** — recompute path (deterministic
   quant recompute → bool) — the "PoW cheap-to-verify" analog; every strategy
   module ships one.
8. **Replay nonce** — `cycle_id = sha256(prev_root, round_timestamp // cycle_sec,
   regime)` — no two cycles are identical → no replay / double-submit.

```python
# sketch (full impl in agent/evidence_chain.py)
class EvidenceChain:
    def __init__(self, redis, namespace="evidence_chain"): ...
    def append(self, cycle_id, regime, decisions) -> Entry   # hashes + links
    def root(self) -> str                                     # current chain root
    def verify_chain(self) -> bool                            # walk, break on mismatch
    def merkle_root(self, entries) -> str                     # batch attestation root
    def sign_root(self, privkey) -> str
    @staticmethod
    ---

## 5. KG extension (`graph/schema/defi_extension.cypher`)

Additive; `MERGE` / `CREATE CONSTRAINT IF NOT EXISTS`, same pattern as
P9/P10 extensions. Loaded by `graph-loader` after `master.cypher`,
`dreamdex_extension.cypher`, `creditgraph_extension.cypher` (any order — all
applied once, idempotent).

**Scope correction (v3):** the AMM/Lending/Vault/Perp/Insurance types are
**restored** — they now point at a **real venue (Ethereum Sepolia testnet)**,
and their runtime nodes are upserted by the ported EVM adapter (stellcasp).

```
EventWindow        — a DreamDEX EC market window (reuses P9 EventContract)
Outcome            — EC resolution outcome (YES/NO, P9)
Attestation        — P10 Merkle+continuity proof (Sepolia→Creditcoin)
── EVM DeFi types (ported strategy nodes; venue = Sepolia) ──────────
AMMPool            — Uniswap V3 testnet pool
LendingPool        — Aave V3 testnet market
VaultStrategy      — yield-aggregator strategy (book Ch.12)
PerpetualMarket    — perp venue + funding rate
OracleFeed         — EC/EVM price feed freshness + deviation

(EventWindow)-[:ACTIVATES_IN]->(Regime)            ← shared market-state spine
(EventWindow)-[:GOVERNED_BY]->(Strategy)           ← shared strategy spine
(EventWindow)-[:CORRELATED_WITH]->(Ticker)         ← spot/EC correlation (D5)
(EventWindow)-[:RESOLVED_BY]->(OracleFeed)         ← EC resolution oracle (D6)
(AMMPool)-[:PROVIDES_LIQUIDITY_TO]->(LiquidityRange)
(BorrowerPosition)-[:HELD_AT]->(LendingPool)
(VaultStrategy)-[:INVESTS_IN]->(AMMPool)
(PerpetualMarket)-[:PRICED_BY]->(OracleFeed)
(OracleFeed)-[:AUTHENTICATED_BY]->(Attestation)    ← P10 tie-in (D8)
```

The EVM types' runtime upsert comes from the **ported stellcasp adapter**
(`agent/web3_adapters/ethereum.py`), which already returns structured
`chain_id`/`contract_address`/`network` data (stellcasp `DeploymentInfo`) →
field-mapped into these KG nodes. No new "sector" labels beyond these;
`OracleFeed` is the thin freshness/over-noded guard the D6 breaker reads.

Runtime agents upsert nodes exactly like `dreamdex_agent._upsert_kg_nodes()`
(non-blocking, `except: logger.warning`).

---

## 6. Strategy catalogue (grounded: Ethereum/Sepolia EVM + DreamDEX/Somnia EC)

**Scope correction (v3):** D1–D4 are **re-enabled** — they execute on
**Ethereum Sepolia testnet** via `web3-relay` (:8460), ported from
`stellcasp/zkkyc/adapters/ethereum.py` (web3.py EVM client + Sepolia RPC) with
Uniswap V3 / Aave V3 testnet contracts. D5–D8 remain on DreamDEX/Somnia.

| # | Sector (grounded) | Edge model (KG-gated) | Execution | Risk gates |
|---|---|---|---|---|
| **D1** | AMM concentrated-LP | fee-yield − IL(`x·y=k`) − gas > threshold (`MIN_LP_EDGE_PCT`); range width from KG vol regime | **Ethereum/Sepolia via web3-relay (:8460)** — ported Uniswap V3 adapter | U28, slippage cap, range-width cap |
| **D2** | Lending carry | lend-rate − borrow-rate spread > cost (`MIN_LENDING_SPREAD_PCT`); utilization trend from KG | **Ethereum/Sepolia via web3-relay (:8460)** — ported Aave V3 adapter | U29 liquidation-distance, collateral factor |
| **D3** | Yield-farm ranking | risk-adj APY = raw − hack-prior − IL − liq-risk | **Ethereum/Sepolia via web3-relay (:8460)** | U32 leverage guard, per-farm cap, hack-prior |
| **D4** | Perp funding carry | \|funding\| > threshold ∧ KG regime agrees → delta-neutral book | **Ethereum/Sepolia via web3-relay (:8460)** | funding-change stop, basis risk, venue cap |
| **D5** | EC cross-hedge (P9++) | KG `CORRELATED_WITH` (EventWindow ↔ Ticker) high → hedge spot with EC | **DreamDEX via somnia-relay (:8450)** | binary-Kelly (U9), correlation minimum, EC-position cap |
| **D6** | EC/EVM resolution-oracle integrity breaker | EC/spot settles on an oracle → staleness/deviations (`OracleFeed`) pause aggressive candidates (Black-Thursday lesson) | n/a (risk governor over D1–D8) | U30 staleness + deviation band |
| **D7** | EC tail-hedge | regime=Crisis/Stress → buy EC shares as portfolio tail hedge ($0/$1 contingent claim) | **DreamDEX via somnia-relay (:8450)** | premium cap, strike/tenor from KG vol, regime gate |
| **D8** | Attested-data edge | P10 `Attestation` (Sepolia→Creditcoin) marks which EC + EVM resolution feeds are trustworthy → filters D1/D5/D7 | n/a (data governor) | U33: only attested feeds; per-feed cap |

**Every strategy implements the same interface** as `DreamDEXAgent.run(regime,
signals) → candidates[]` — one more registry entry in the orchestrator. Each
strategy's *execution venue* is selected by the adapter registry (ported from
stellcasp's `AdapterRegistry`) → D1–D4 dispatch to `web3-relay` (Ethereum/
Sepolia), D5–D8 to `somnia-relay` (DreamDEX). The Risk/Execution spine is
unchanged; the relay selection is data, not branching.

---

## 7. Practice → Profit ladder

| Level | What | Mode | Gate to advance |
|---|---|---|---|
| L0 | Lab sandbox (already) | paper fills, deterministic quant, backtests | edge OOS-validated |
| L1 | **DreamDEX testnet (Somnia 50312)** + **Ethereum/Sepolia testnet** | EC paper fills + EVM/DeFi testnet orders via `web3-relay` (Sepolia faucets) + evidence-chain continuity | N testnet cycles + evidence-chain unbroken + tests green |
| L2 | Live small-cap, audited | `live` with per-market caps, kill-switch, air-gapped signer | human-approve each sector + evidence-chain public |
| L3 | Scaled multi-sector | portfolio-level KG risk (sector correlation on the graph) | regime stops, per-sector caps, periodic anchoring |

Each rung unlocks only when: evidence chain unbroken, edge survived OOS
(existing multiplicity framework U10/U12), risk gates green in Docker, and
human sign-off (U6 freeze/controls, P7 human authority).

---

## 8. Files + allowed edits (definitive)

**New (ported from `stellcasp/` — reuse, don't reinvent):**
```
web3/                         Node relay :8460 — Ethereum/Sepolia EVM DeFi.
                              Render of: zkkyc/adapters/ethereum.py (web3.py EVM
                              client), ethereum/contracts/*.sol (Foundry), deploy.sh
agent/defi_agent.py          strategy orchestrator (D1–D8) — same run() interface
agent/web3_adapters/base.py  ← stellcasp zkkyc/adapters/base.py (PassportAdapterBase)
agent/web3_adapters/registry.py ← stellcasp zkkyc/adapters/registry.py (AdapterRegistry)
agent/web3_adapters/ethereum.py ← stellcasp zkkyc/adapters/ethereum.py (web3.py Sepolia)
agent/evidence_chain.py      hash-chain, Merkle, verify, nonce (§4) — ✅ built
api/routes/defi.py           Redis-backed read-only: /defi/{candidates,positions,evidence}
graph/schema/defi_extension.cypher   additive KG types (§5)
frontend/src/components/DefiWorkspace.tsx   tabs + EvidenceChain viewer
frontend/src/lib/defiApi.ts
frontend/src/lib/web3Api.ts (optional, future charting)
tests/test_evidence_chain.py   ✅ built (16 tests)
tests/test_defi_agent.py       D1–D8 gates + U30 breaker hermetic tests
.env.example                  +§9 vars (EVM + DreamDEX names)
docker-compose.yml            +web3-relay block, profiles: [web3]
```

**Ported `stellcasp` artifacts (exact sources):**
- `zkkyc/adapters/{base,registry,ethereum,stellar,algorand,sui,aptos,polkadot,casper,icp,hedera}.py`
  → evm/chain adapter family (one interface, N chains — EP-08 pattern).
- `ethereum/{contracts,foundry.toml,scripts/deploy.sh,.env.example,README.md}`
  → deployed Sepolia contracts + Foundry deploy (anchor/verifier).
- `zkkyc/agents/settlement.py` + `toolkit/*` + `payments/x402.py`
  → registry-based settlement dispatcher + optional x402 payment clearing.

**Edits to existing files — exactly 4 (same pattern as P9/P10):**
1. `agent/orchestrator.py` — +4 lines: import, instantiate, non-fatal `run()`
   hook, evidence-chain flush.
2. `api/main.py` — +1 line: `app.include_router(defi_router)`.
3. `frontend/src/App.tsx` — +1 menu item "DeFi" → `DefiWorkspace`.
4. `docker-compose.yml` — `web3-relay` service block (profiles: [web3]);
   `graph-loader` cat unchanged (defi_extension idempotent).

---

## 9. Environment variables (append to `.env.example`)

```env
# ── EVM DeFi (P11) — Ethereum Sepolia testnet (ported from stellcasp ETHEREUM_*) ─
WEB3_ENABLED=0                 # master switch; defi_agent self-disables
WEB3_RPC_URL=https://rpc.sepolia.org      # Sepolia testnet RPC (stellcasp default)
WEB3_CHAIN_ID=11155111         # Sepolia chain id
WEB3_PASSPORT_CONTRACT=0x0     # deployed ZKPassport anchor (stellcasp ethereum/)
WEB3_VERIFIER_CONTRACT=0x0     # deployed UltraHonk verifier
WEB3_ORACLE_AUTHORITY_PRIVATE_KEY=  # signing key (RFC-6979; never commit)
WEB3_RELAY_URL=http://localhost:8460
WEB3_RELAY_API_KEY=            # shared with dreamdex RELAY_API_KEY
MIN_LP_EDGE_PCT=0.05           # D1 gate (fee−IL−gas)
MIN_LENDING_SPREAD_PCT=0.02    # D2 gate
MIN_FUNDING_CARRY_PCT=0.10     # D4 gate
MAX_LEVERAGE_X=2.0             # D3/U32 leverage cap
MAX_BRIDGE_EXPOSURE_PCT=0.05   # D8/U33 cap
ORACLE_STALE_MS=600000         # D6/U30 staleness breaker
ORACLE_DEVIATION_BPS=50        # D6/U30 deviation band
# ── Existing P11 EC vars (unchanged, D5–D8) ──
DEFI_ENABLED=0                 # master switch for the orchestrator hook
DEFI_EC_CROSSHEDGE=1           # D5
DEFI_EC_TAILHEDGE=1            # D7
DEFI_EC_ORACLE_BREAKER=1       # D6
MIN_EC_EDGE_PCT=0.03           # D5/D7 edge gate
MAX_EC_TAILHEDGE_PCT=0.02      # D7 cap
MIN_CORRELATION=0.60           # D5 correlation floor
```

Reuses the `DREAMDEX_*`/`SOMNIA_*`/`CREDITGRAPH_*` families for the EC + data
venues; the **new** `WEB3_*` block is the Ethereum/Sepolia venue, mirroring
stellcasp's `ETHEREUM_RPC_URL/CHAIN_ID/PASSPORT_CONTRACT/VERIFIER_CONTRACT`
names. If `WEB3_ENABLED=0`, D1–D4 self-disable; GraphAlpha boots identically.

---

## 10. Tenet ledger extension (U25–U33)

Full rows appended to `p9_tenets_financial_engineering.md` §4B (after U24):

| U | Tenet (source) | Concrete change (re-grounded) | Acceptance |
|---|---|---|---|
| U25 | Sign everything (Crypto: DS) | decisions signed via `evidence_chain.py`; root verified in API + panel | unit test: tampered decision → `verify_chain()==False` |
| U26 | Merkle-batch attestations (Crypto: Merkle) | decision roots → Merkle batch; P10 `Attestation` reuse | test: proof length O(log n) |
| U27 | Quorum with auth (Crypto: Byzantine) | signed confirmations ⇒ relaxed quorum in CreditGraph consensus | doc + config knob |
| U28 | IL-aware LP gating (DeFi Ch3→Sepolia) | **re-grounded:** real IL (`x·y=k` on Uniswap V3 Sepolia) — reject LP when fee−IL−gas ≤ 0 | hermetic test w/ IL table |
| U29 | Liquidation-distance guard (DeFi Ch5→Sepolia) | **re-grounded:** Aave V3 liquidation distance (collat factor, utilization) | test: distance math |
| U30 | Oracle-staleness breaker (DeFi Ch13) | EC/EVM feed stale/deviation → pause D1–D8 (Black Thursday) | test: stale feed → paused |
| U31 | Signing hygiene (DeFi Ch15→both relays) | web3-relay + somnia-relay RFC-6979/nonce, simulate-first, approve-min; no live key in `.env` | static check + relay tests |
| U32 | Vault leverage guard (DeFi Ch12→Sepolia) | yield-farm leverage capped (MAX_LEVERAGE_X) + liquidation distance | test: leverage ≤ bound |
| U33 | Bridge/attestation hygiene (DeFi Ch14+P10) | only attested (P10) feeds filter D1/D5/D7; per-bridge cap | doc + caps enforced |

---

## 11. Build & test sequence (Docker-first; each stage independently stub-able)

1. `evidence_chain.py` + `tests/test_evidence_chain.py` ✅ (16 tests, hermetic).
2. **Port stellcasp adapters** → `agent/web3_adapters/{base,registry,ethereum}.py`
   (copy + rename; web3.py already a dep). `pytest tests/test_web3_adapters.py`.
3. `agent/defi_agent.py` (D1–D8) + `tests/test_defi_agent.py` — hermetic (stub
   relay/get_markets/suggest_crypto/Attestation), paper mode end-to-end.
4. KG `graph/schema/defi_extension.cypher` (additive types) + load in Neo4j ✅
   (verified live: 6 constraints — EventWindow/AMMPool/LendingPool/VaultStrategy/
   PerpetualMarket/OracleFeed — plus 3 seeded OracleFeed nodes).
5. API routes (`/defi/*`) + `DefiWorkspace.tsx` + App menu item.
6. `web3/` relay + Foundry deploy (`ethereum/scripts/deploy.sh` on Sepolia) —
   D1–D4 orders against Uniswap V3 / Aave V3 Sepolia testnet, `make web3-test`.
7. Demo wiring: Somnia EC lifecycle + **Sepolia EVM lifecycle** — `web3-relay`
   dry-run → one testnet AMM/LP/lend order → evidence-chain appended →
   EvidenceChain tab shows hash-chain + Merkle root (+ ERC-721 anchor if funded).

---

## 12. Risk register

| Risk | Mitigation |
|---|---|
| EC resolution-oracle divergence (Black Thursday analog) | U30 breaker + `OracleFeed` freshness; P9 U1 haircut |
| EVM smart-contract exploit (Ch. 15: code-in-production) | audited-protocols-only (Uniswap V3/Aave V3), small testnet caps, U28/U32 gates |
| EVM/slots IL (Ch. 3) | U28 real IL table + range-width from KG vol |
| EVM liquidation cascade (Ch. 5) | U29 liquidation-distance guard + collateral-swap rescue |
| MEV/front-running (Ch. 3,15) | simulate-first (`eth_call`), REP of stellcasp relay nonce/gas (U2/U3), private RPC (lab) |
| Attestation/bridge trust (Ch. 14 + P10) | U33 only attested feeds; per-bridge cap |
| Key custody (Ch. 15) | web3-relay + somnia-relay RFC-6979, air-gapped signer for live keys; never in `.env` |
| Regulatory | testnet-first (Somnia 50312 + Sepolia); USD-pegged permissioning docs in repo |

---

## 14. References

- `Cryptographic Primitives in Blockchain Technology — A mathematical
  introduction.md` (Bolfing; Ch. 3.4 hashes, 3.5 Merkle, 3.3.2.4 DS,
  5.3.8 Byzantine, 6.6 security goals, 6.7 PoW).
- `How to DeFi_ Advanced.md` (CoinGecko; Ch. 2/3/5/7/8/10/12/13/14/15).
- This repo: `agent/dreamdex_agent.py`, `agent/dreamdex_adapter.py`,
  `agent/creditgraph_agent.py`, `agent/orchestrator.py`,
  `graph/schema/dreamdex_extension.cypher`, `graph/schema/creditgraph_extension.cypher`,
  `graph/schema/defi_extension.cypher` (P11),
  `api/routes/dreamdex.py`, `api/routes/creditgraph.py`, `frontend/src/App.tsx`.

---

## 15. Implementation status

| Artifact | Status | Evidence |
|---|---|---|
| `docs/p11_web3_defi_expansion.md` | ✅ this document | — |
| `p9_tenets_financial_engineering.md` §4 U25–U33 | ✅ appended | — |
| `agent/evidence_chain.py` | ✅ built | pure-python, hermetic tests green in Docker |
| `tests/test_evidence_chain.py` | ✅ | see §16 command output |
| D5–D8 strategies, `defi_agent.py`, API, frontend, KG loader | ⏳ staged (Stages 2–4 of §11) |

*End of P11 plan.*

---