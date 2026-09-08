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

**The target:** GraphAlpha as a **KG-gated, on-chain-attested, per-sector DeFi
agent platform** — one Neo4j reasoning over Equities (existing), Somnia
prediction markets (P9), Creditcoin attested credit (P10), and a new EVM DeFi
sector relay (this plan, P11).

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
| Multi-chain / bridges (Ch. 14) | Cross-chain protocols, bridge risk | Already P10 (Attestcoin Sepolia→Creditcoin). `CrossChainMessage` nodes; audited-bridges-only + exposure caps. |
---

## 3. Target architecture (additive)

```
                    ┌─────────────────────────── GraphAlpha ONE (this repo) ────────────────────────────┐
                    │  ONE Neo4j KG: Concept/Formula/Strategy/Regime/Category +                          │
                    │     EventContract (P9) + Borrower/Evidence/CreditDecision (P10)                    │
                    │     + AMMPool/LendingPool/VaultStrategy/PerpetualMarket/OracleFeed/Bridge (P11)    │
                    │  ONE Redis: agent_status, signals, evidence_chain, defi:* keys                     │
                    │                                                                                    │
  Somnia (P9)      │   orchestrator.py (= 5-line registry: DreamDEX, CreditGraph, NEW DeFiAgent)         │
  Creditcoin (P10) │     ├─ DreamDEXAgent ───────► dreamdex relay (:8450, Node, markets-sdk)             │
  EVM DeFi (P11)   │     ├─ CreditGraphAgent ─────► attestation (:8080) + execution (:8081) services     │
  NEW              │     └─ DeFiAgent ─────────────► web3 relay (:8460, Node, viem/ethers)               │
                    │           │   reads: Regime + KGStrategies + OracleFeed integrity                  │
                    │           ▼                                                                        │
                    │   evidence_chain.py: sign → sha256 → hash-chain → Merkle-batch → optional anchor    │
                    │   api/routes/defi/* + DefiWorkspace.tsx (AMM/Lending/Yield/Perps/Oracles/Evidence)  │
                    └────────────────────────────────────────────────────────────────────────────────────┘
```

Everything P11 lands under `profiles: [web3]` — **invisible to `make up`**,
exactly like `dreamdex` (`profiles: [dreamdex]`) and `creditgraph`
(`profiles: [creditgraph]`).

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

## 5. KG extension (`graph/schema/web3_extension.cypher`)

Additive; `MERGE` / `CREATE CONSTRAINT IF NOT EXISTS`, same pattern as
P9/P10 extensions. Loaded by `graph-loader` after `master.cypher`,
`dreamdex_extension.cypher`, `creditgraph_extension.cypher` (one-line cat).

```
AMMPool, LiquidityRange, LendingPool, BorrowerPosition, VaultStrategy,
PerpetualMarket, FundingRate, InsuranceCover, OracleFeed, BridgeLiquidity,
CrossChainMessage

(AMMPool)-[:PROVIDES_LIQUIDITY_TO]->(LiquidityRange)
(BorrowerPosition)-[:HELD_AT]->(LendingPool)
(VaultStrategy)-[:INVESTS_IN]->(AMMPool)
(PerpetualMarket)-[:PRICED_BY]->(OracleFeed)
(OracleFeed)-[:AUTHENTICATED_BY]->(Attestation)      ← P10 tie-in
(*Sector*)-[:ACTIVATES_IN]->(Regime)                 ← shared market-state spine
(*Sector*)-[:GOVERNED_BY]->(Strategy)                ← shared strategy spine
(*Sector*)-[:CORRELATED_WITH]->(Ticker)              ← spot/EC/DeFi in one graph
(CrossChainMessage)-[:ATTESTED_VIA]->(Attestation)   ← Creditcoin attestation reuse
```

Runtime agents upsert nodes exactly like `dreamdex_agent._upsert_kg_nodes()`
(non-blocking, `except: logger.warning`).

---

## 6. Strategy catalogue (the profit engines)

| # | Sector | Edge model (KG-gated) | Execution (relay) | Risk gates |
|---|---|---|---|---|
| D1 | AMM concentrated-LP | fee-yield − IL(`x·y=k`) − gas > threshold; range width from KG vol regime | Uniswap V3 position/rebalance via relay | U28 IL gate, slippage cap, range-width cap |
| D2 | Lending carry | lend-rate − borrow-rate spread > cost; utilization trend from KG | Aave/Compound supply/borrow via relay | U29 liquidation-distance, collateral factor |
| D3 | Yield-farm ranking | risk-adj APY = raw − hack-prior − IL − liq-risk | Yearn-style auto-compound loop + scheduler | U32 leverage guard, per-farm cap, hack-prior |
| D4 | Perp funding carry | \|funding\| > threshold ∧ KG regime agrees → delta-neutral book | Perp venues via relay (+ spot leg) | funding-change stop, basis risk, venue cap |
| D5 | EC cross-hedge (P9++) | KG correlation (EC ↔ spot ticker) high → hedge spot with EC | DreamDEX relay (existing) | binary-Kelly, correlation minimum |
| D6 | Oracle-staleness breaker | feed staleness/deviation > band → pause aggressive sectors | n/a (risk governor) | U30; Black-Thursday lesson encoded |
| D7 | Tail-hedge insurance | KG regime Crisis/Stress → buy cover until premium ≤ expected-tail-loss | Nexus/Armor-style (lab first) | premium cap, strike/tenor from KG vol |
| D8 | Cross-chain/bridge arb | attested data (P10) drives where liquidity is thin; spread − bridge fee > 0 | audited relays only (lab first) | U33 per-bridge cap |

**Every strategy implements the same interface** as `DreamDEXAgent.run(regime,
signals) → candidates[]` — one more registry entry in the orchestrator, zero
changes to the Risk/Execution spine (parallel `defi:*` pipeline, same as
P9/P10).

---

## 7. Practice → Profit ladder

| Level | What | Mode | Gate to advance |
|---|---|---|---|
| L0 | Lab sandbox (already) | paper fills, deterministic quant, backtests | edge OOS-validated |
| L1 | Testnet DeFi (this plan) | `WEB3_TRADING_MODE=paper\|testnet` on Sepolia: Uniswap V3/Aave via relay, faucets | N testnet cycles + evidence-chain continuity + tests green |
| L2 | Live small-cap, audited | `live` with per-market caps, kill-switch, air-gapped signer | human-approve each sector + evidence-chain public |
| L3 | Scaled multi-sector | portfolio-level KG risk (sector correlation on the graph) | regime stops, per-sector caps, periodic anchoring |

Each rung unlocks only when: evidence chain unbroken, edge survived OOS
(existing multiplicity framework U10/U12), risk gates green in Docker, and
human sign-off (U6 freeze/controls, P7 human authority).

---

## 8. Files + allowed edits (definitive)

**New:**
```
web3/                        Node relay :8460 — viem/ethers; Uniswap V3 + Aave v3 adapters;
                             doctor.ts, order.ts, positions.ts, anchor.ts, routes.ts,
                             Dockerfile, .env.example
agent/web3_adapter.py        httpx client → :8460 (mirrors dreamdex_adapter)
agent/defi_agent.py          sector-agnostic orchestrator-agent (D1–D8 registry)
agent/evidence_chain.py      hash-chain, Merkle, verify, nonce (§4) — NEW, hermetic
api/routes/defi.py           Redis-backed read-only: /defi/{sectors,candidates,positions,evidence,anchor}
graph/schema/web3_extension.cypher    additive KG types (§5)
frontend/src/components/DefiWorkspace.tsx   tabs + EvidenceChain viewer
frontend/src/lib/defiApi.ts
tests/test_evidence_chain.py
tests/test_defi_agent.py
tests/test_web3_adapter.py
.env.example                 +~14 vars (§9)
docker-compose.yml           +web3-relay block, profiles: [web3]
Makefile                     +web3-up/logs/test targets
```

**Edits to existing files — exactly 4 (same pattern as P9/P10):**
1. `agent/orchestrator.py` — +4 lines: import, instantiate, non-fatal `run()`
   hook, evidence-chain flush.
2. `api/main.py` — +1 line: `app.include_router(defi_router)`.
3. `frontend/src/App.tsx` — +1 menu item "DeFi" → `DefiWorkspace`.
---

## 9. Environment variables (append to `.env.example`)

```env
# ── Web3 DeFi (P11) ─────────────────────────────────────────────
WEB3_ENABLED=0                  # master switch; agent self-disables silently
WEB3_TRADING_MODE=paper         # paper | testnet | live
WEB3_RPC_URL=https://sepolia.infura.io/v3/   # testnet RPC
WEB3_RELAY_URL=http://localhost:8460
WEB3_RELAY_API_KEY=             # shared with dreamdex RELAY_API_KEY
ANCHOR_CONTRACT=0x0             # GraphAlphaAnchor testnet address (deploy script)
ANCHOR_EVERY_CYCLES=288         # ~1/day at 5-min cycles
MIN_LP_EDGE_PCT=0.05            # D1 gate (fee−IL−gas)
MIN_LENDING_SPREAD_PCT=0.02     # D2 gate
MIN_FUNDING_CARRY_PCT=0.10      # D4 gate
MAX_LEVERAGE_X=2.0              # D3/U32 leverage cap
MAX_BRIDGE_EXPOSURE_PCT=0.05    # D8/U33 cap
ORACLE_STALE_MS=600000          # D6/U30 staleness breaker
ORACLE_DEVIATION_BPS=50         # D6/U30 deviation band
```

All existing vars unchanged. If `WEB3_ENABLED=0`, the agent self-disables with a
warning log — GraphAlpha boots identically.

---

## 10. Tenet ledger extension (U25–U33)

Full rows appended to `p9_tenets_financial_engineering.md` §4 (after U24):

| U | Tenet (source) | Concrete change | Acceptance |
|---|---|---|---|
| U25 | Sign everything (Crypto: DS) | decisions signed; `verify_root` in API | unit test: tampered decision fails verify |
| U26 | Merkle-batch attestations (Crypto: Merkle) | daily decision roots → Merkle; P10 reuse | test: proof length O(log n) |
| U27 | Quorum with auth (Crypto: Byzantine) | signed confirmations ⇒ relaxed quorum in CreditGraph consensus | doc + config knob |
| U28 | IL-aware LP gating (DeFi: Ch3) | reject LP when fee−IL−gas ≤ 0 | hermetic test w/ IL table |
| U29 | Liquidation-distance guard (DeFi: Ch5) | margin-call proximity alert + self-liquidate rescue path | test: distance math |
| U30 | Oracle-staleness breaker (DeFi: Ch13) | pause sectors when feed stale/deviation > band | test: stale feed → paused |
| U31 | Flash-loan hygiene (DeFi: Ch15) | approve-min, revoke-after, simulate-first (`eth_call`), nonce serialize | static checks + relay tests |
| U32 | Vault leverage guard (DeFi: Ch12) | leveraged-farm positions capped by liquidation distance | test: leverage ≤ bound |
| U33 | Bridge hygiene (DeFi: Ch14 + P10) | audited-bridges-only, per-bridge cap, attested-msg reuse | doc + caps enforced |

---

## 11. Build & test sequence (Docker-first; each stage independently stub-able)

1. `evidence_chain.py` + `tests/test_evidence_chain.py` (pure-python,
   deterministic — fully hermetic, run in api container).
2. `web3/` relay scaffold (doctor, routes, typecheck, crypto-hygiene gate —
   mirror `dreamdex/`) + Docker build.
3. KG `web3_extension.cypher` + graph-loader 4-file cat + load in Neo4j.
4. `defi_agent.py` + `web3_adapter.py` + orchestrator hook — paper mode
   end-to-end (D1–D8 candidate streams in Redis) + tests.
5. API routes + `DefiWorkspace.tsx` + App menu item (read-only, Redis-backed).
6. `.env`/compose/Makefile + `make web3-test` (Node typecheck + pytest), full
   suite in Docker.
7. Demo wiring: Sepolia testnet lifecycle (`doctor` → one simulated order →
   anchor → EvidenceChain tab shows hash-chain + Merkle root).

---

## 12. Risk register

| Risk | Mitigation |
|---|---|
| Oracle staleness/deviation (Ch. 13 Black Thursday) | U30 breaker + `OracleFeed` nodes + deviation bands |
| Smart-contract exploit (Ch. 15: code-in-production, rug pulls) | audited-protocols-only, small caps, insurance (D7), per-sector caps |
| Impermanent loss (Ch. 3) | U28 IL-adjusted edge (book's 13.4%/20%/25.5% table) + range-width from KG vol |
| Liquidation cascade (Ch. 5, 12) | U29/U32 distance guards, collateral-swap rescue, leverage caps |
| MEV/front-running (Ch. 3, 15) | simulate-first (`eth_call`), gas-tip strategy, private-mempool relay option (lab first) |
| Bridge risk (Ch. 14) | U33 audited-only, per-bridge cap, P10 attestation reuse |
| Key custody (Ch. 15: HW wallets) | air-gapped signer, approve-min, revoke-after, never-in-`.env` for live keys |
| Regulatory | testnet-first, USD-pegged permissioning docs in repo |

---

## 13. Judging alignment

- **Somnia × DreamDEX:** the P9 core plus D5 (EC cross-hedge) and D4/D6
  deepening makes "KG-gated EC agent" a richer, stronger demo.
- **Creditcoin/Attestcoin (AI track):** attested cross-chain data (P10)
  *driving* DeFi decisions (D8, `OracleFeed ← Attestation` edges) is precisely
  "AI apps that process cryptographically verified cross-chain data … without
  centralized oracle operators". P11 makes the KG the decision spine fed by
  attested data.
- **Both:** 90-sec demo arc — regime → KG strategy fired → evidence-chain
  signed+batched+Merkle-anchored → testnet order → fill with tx_hash → panel
  shows the hash chain.

---

## 14. References

- `Cryptographic Primitives in Blockchain Technology — A mathematical
  introduction.md` (Bolfing; Ch. 3.4 hashes, 3.5 Merkle, 3.3.2.4 DS,
  5.3.8 Byzantine, 6.6 security goals, 6.7 PoW).
- `How to DeFi_ Advanced.md` (CoinGecko; Ch. 2/3/5/7/8/10/12/13/14/15).
- This repo: `agent/dreamdex_agent.py`, `agent/dreamdex_adapter.py`,
  `agent/creditgraph_agent.py`, `agent/orchestrator.py`,
  `graph/schema/dreamdex_extension.cypher`, `graph/schema/creditgraph_extension.cypher`,
  `api/routes/dreamdex.py`, `api/routes/creditgraph.py`, `frontend/src/App.tsx`.

---

## 15. Implementation status

| Artifact | Status | Evidence |
|---|---|---|
| `docs/p11_web3_defi_expansion.md` | ✅ this document | — |
| `p9_tenets_financial_engineering.md` §4 U25–U33 | ✅ appended | — |
| `agent/evidence_chain.py` | ✅ built | pure-python, hermetic tests green in Docker |
| `tests/test_evidence_chain.py` | ✅ | see §16 command output |
| D1–D8 strategies, `web3/` relay, `defi_agent.py`, API, frontend, KG loader | ⏳ staged | Stage 2+ of §11 |

*End of P11 plan.*

---