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
execution via `somnia-relay`), and Creditcoin attested credit (P10, via
`attestation-service`/`execution-service`). **P11's strategy catalogue is
re-grounded onto those two chains — there is no third ("web3") relay.**
The *How to DeFi* sector tactics that require an EVM mainnet venue (AMMs,
lending, yield farms) are explicitly **parked as future scope**, not invented
into a phantom testnet.

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

> **Scope note (v2).** The AMM/Lending/Yield/Derivatives rows above are the
> *book's* sector catalogue — educational ground truth for the strategies, NOT
> things P11 builds. They require an EVM mainnet venue (Uniswap/Aave/…) we do
> not run, so **D1–D4 are parked**. P11 implements only what executes on the
> two live chains: DreamDEX Event Contracts (Somnia) + CreditGraph attested
> data (Sepolia→Creditcoin): **D5–D8**.

---

## 3. Target architecture (additive — grounded on the chains we run)

```
                    ┌─────────────────────────── GraphAlpha ONE (this repo) ────────────────────────────┐
                    │  ONE Neo4j KG: Concept/Formula/Strategy/Regime/Category +                          │
                    │     EventContract (P9) + Borrower/Evidence/CreditDecision (P10)                    │
                    │     + EventWindow/outcome/evidence edges (P11 — additive to existing types)        │
                    │  ONE Redis: agent_status, signals, evidence_chain, dreamdex:*, creditgraph:* keys   │
                    │                                                                                    │
  Somnia (P9, EXEC) │   orchestrator.py (= registry: DreamDEX, CreditGraph + NEW DeFiAgent hook)         │
  Creditcoin (P10)  │     ├─ DreamDEXAgent ───────► somnia-relay (:8450, Node, markets-sdk)  X  EXEC   │
  (attested data)   │     ├─ CreditGraphAgent ─────► attestation (:8080) + execution (:8081)             │
  NEW (P11)         │     └─ DeFiAgent ─────────────► (same DreamDEX executions, EC strategies)          │
                    │           │   reads: Regime + KGStrategies + Attestation(creditgraph) integrity    │
                    │           ▼                                                                        │
                    │   evidence_chain.py: sign → sha256 → hash-chain → Merkle-batch → optional anchor    │
                    │   api/routes/defi/* + DefiWorkspace.tsx (EC strategies / EvidenceChain)            │
                    └────────────────────────────────────────────────────────────────────────────────────┘
```

- **Execution chain = DreamDEX Event Contracts on Somnia (chain 50312), via the
  existing `somnia-relay` (:8450).** The P11 `DeFiAgent` produces *candidate
  intents* that the same DreamDEX execution path (RiskAgent sizing →
  `somnia-relay` order) fills — **no new relay, no new port, no third chain.**
- **Data chain = Ethereum Sepolia → Creditcoin (P10).** `Attestation` nodes
  (Merkle+continuity proofs) inform which EC windows' resolution data is
  trustworthy (D6/D8).
- P11 is additive **within the existing infra**: a new agent module + the
  `evidence_chain.py` assurance layer; both invisible unless enabled. Nothing
  about the Somnia or Creditcoin services changes.

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

**Scope correction (v2):** the earlier AMM/Lending/Vault/Perp/Insurance types
implied an EVM DeFi venue we do not run. **Withdrawn.** P11 extends only the
**types that already exist** on the two live chains:

```
EventWindow        — a DreamDEX EC market window (reuses P9 EventContract)
Outcome            — EC resolution outcome (YES/NO, P9)
Attestation        — P10 Merkle+continuity proof (Sepolia→Creditcoin)

(EventWindow)-[:ACTIVATES_IN]->(Regime)            ← shared market-state spine
(EventWindow)-[:GOVERNED_BY]->(Strategy)           ← shared strategy spine
(EventWindow)-[:CORRELATED_WITH]->(Ticker)         ← spot/EC correlation (D5)
(EventWindow)-[:RESOLVED_BY]->(OracleFeed)         ← EC resolution oracle (D6)
(OracleFeed)-[:AUTHENTICATED_BY]->(Attestation)    ← P10 tie-in (D8)
```

`OracleFeed` is a **thin additive node** (name/type/`updated_at`/`deviation_bps`)
that records the EC resolution feed's freshness — the D6 circuit-breaker reads
it. No new "sector" labels, no AMM/lending types.

Runtime agents upsert nodes exactly like `dreamdex_agent._upsert_kg_nodes()`
(non-blocking, `except: logger.warning`).

---

## 6. Strategy catalogue (grounded on DreamDEX + attested data)

**Scope correction (v2):** D1 (AMM-LP), D2 (lending carry), D3 (yield-farm),
and D4 (perp funding) require an **EVM mainnet DeFi venue** we do not run.
They are **parked (future scope)** — their tenet rows (U28/U29/U32) are kept
for the day a venue is added, but no phantom `web3/` relay is built for them.

| # | Sector (grounded) | Edge model (KG-gated) | Execution | Risk gates |
|---|---|---|---|---|
| **D5** | EC cross-hedge (P9++) | KG `CORRELATED_WITH` (EventWindow ↔ Ticker) high → hedge a spot position with EC shares | **DreamDEX via somnia-relay (:8450)** | binary-Kelly (U9), correlation minimum, EC-position cap |
| **D6** | EC resolution-oracle integrity breaker | EC settles on an oracle → staleness/deviations (`OracleFeed`) pause aggressive EC candidates (Black-Thursday lesson) | n/a (risk governor over D5/D7/D8) | U30 staleness + deviation band |
| **D7** | EC tail-hedge | regime=Crisis/Stress → buy EC shares as portfolio tail hedge ($0/$1 contingent claim) | **DreamDEX via somnia-relay (:8450)** | premium cap, strike/tenor from KG vol, regime gate |
| **D8** | Attested-data edge | P10 `Attestation` (Sepolia→Creditcoin) marks which EC resolution feeds are trustworthy → filters D5/D7 | n/a (data governor) | U33: only attested feeds; per-feed cap |

**Every strategy implements the same interface** as `DreamDEXAgent.run(regime,
signals) → candidates[]` — one more registry entry in the orchestrator, zero
changes to the **existing DreamDEX Risk/sizing/execution path** (candidates
flow into the same `somnia-relay` order flow; nothing parallel, no new relay).
Parked D1–D4 would slot in identically the day a venue exists.

---

## 7. Practice → Profit ladder

| Level | What | Mode | Gate to advance |
|---|---|---|---|
| L0 | Lab sandbox (already) | paper fills, deterministic quant, backtests | edge OOS-validated |
| L1 | **DreamDEX testnet (Somnia 50312)** — P11 grounded | EC paper fills + evidence-chain continuity; `somnia-relay` in dry-run | N testnet cycles + evidence-chain unbroken + tests green |
| L2 | Live small-cap, audited | `live` with per-market caps, kill-switch, air-gapped signer | human-approve each sector + evidence-chain public |
| L3 | Scaled multi-sector | portfolio-level KG risk (sector correlation on the graph) | regime stops, per-sector caps, periodic anchoring |

Each rung unlocks only when: evidence chain unbroken, edge survived OOS
(existing multiplicity framework U10/U12), risk gates green in Docker, and
human sign-off (U6 freeze/controls, P7 human authority).

---

## 8. Files + allowed edits (definitive)

**New:**
```
agent/defi_agent.py           EC strategy orchestrator (D5–D8 registry) — same
                              run(regime, signals) interface as DreamDEXAgent
agent/evidence_chain.py       hash-chain, Merkle, verify, nonce (§4) — ✅ built
api/routes/defi.py            Redis-backed read-only: /defi/{candidates,positions,evidence}
graph/schema/defi_extension.cypher   additive KG types (§5) — reuses P9 EventContract
frontend/src/components/DefiWorkspace.tsx   tabs + EvidenceChain viewer
frontend/src/lib/defiApi.ts
tests/test_evidence_chain.py   ✅ built (16 tests)
tests/test_defi_agent.py       D5–D8 gates + U30 breaker hermetic tests
.env.example                  +§9 vars (all reuse existing DREAMDEX_/SOMNIA_/CREDITGRAPH_ names)
```

**No new relay, no new port, no new container.** P11 executes entirely through
the existing `somnia-relay` (:8450) + the P10 attestation services.

**Edits to existing files — exactly 3 (same pattern as P9/P10):**
1. `agent/orchestrator.py` — +4 lines: import, instantiate, non-fatal `run()`
   hook, evidence-chain flush.
2. `api/main.py` — +1 line: `app.include_router(defi_router)`.
3. `frontend/src/App.tsx` — +1 menu item "DeFi" → `DefiWorkspace`.

(`docker-compose.yml` is NOT touched — no new service block; `graph-loader`
cat order is unchanged because `defi_extension.cypher` types are additive to
types `master.cypher` already creates via P9/P10, and the file is idempotent.)

## 9. Environment variables (append to `.env.example`)

```env
# ── P11 (grounded on DreamDEX/Somnia + P10 attestation) ───────────
DEFI_ENABLED=0                 # master switch; defi_agent self-disables
DEFI_EC_CROSSHEDGE=1           # D5 on/off
DEFI_EC_TAILHEDGE=1            # D7 on/off
DEFI_EC_ORACLE_BREAKER=1       # D6 on/off
MIN_EC_EDGE_PCT=0.03           # D5/D7 edge gate (reuses P9 MIN_EDGE_PCT family)
MAX_EC_TAILHEDGE_PCT=0.02      # D7 cap (reuses P9 MAX_EC_POSITION_PCT_PORTFOLIO)
MIN_CORRELATION=0.60           # D5 EC↔spot correlation floor
ORACLE_STALE_MS=600000         # D6 staleness breaker (EC resolution feed)
ORACLE_DEVIATION_BPS=50        # D6 deviation band
```

**No new `WEB3_*` names.** All P11 vars reuse the existing `DREAMDEX_*`/`SOMNIA_*`
and `CREDITGRAPH_*` env families already in this repo — P11 adds only the seven
D5–D8 gating/control knobs above plus the §4 assurance knobs
(`EVIDENCE_CHAIN_NAMESPACE`). No `WEB3_RPC_URL`, no `:8460`.

---

## 10. Tenet ledger extension (U25–U33)

Full rows appended to `p9_tenets_financial_engineering.md` §4B (after U24):

| U | Tenet (source) | Concrete change (re-grounded) | Acceptance |
|---|---|---|---|
| U25 | Sign everything (Crypto: DS) | decisions signed via `evidence_chain.py`; root verified in API + panel | unit test: tampered decision → `verify_chain()==False` |
| U26 | Merkle-batch attestations (Crypto: Merkle) | decision roots → Merkle batch; P10 `Attestation` reuse | test: proof length O(log n) |
| U27 | Quorum with auth (Crypto: Byzantine) | signed confirmations ⇒ relaxed quorum in CreditGraph consensus | doc + config knob |
| U28 | EC edge over pay (DeFi Ch3 IL→EC) | **re-grounded:** never overpay — `edge = your-p − ask` gate (P9 binary-Kelly) | hermetic test: low-edge EC rejected |
| U29 | Liquidation-distance guard (DeFi Ch5) | **now EC:** distance-to-resolution / settlement haircut (P9 U1) | test: short-τ candidate shows haircut |
| U30 | Oracle-staleness breaker (DeFi Ch13) | EC resolution feed stale/deviation → pause D5/D7 (Black Thursday) | test: stale feed → paused |
| U31 | Signing hygiene (DeFi Ch15→relay) | `somnia-relay` RFC-6979/nonce, simulate-first, approve-min; no live key in `.env` | static check + relay tests (P9 U16) |
| U32 | Position cap (DeFi Ch12→EC tail) | **re-grounded:** EC tail-hedge position cap = fraction of portfolio | test: D7 size ≤ cap |
| U33 | Bridge/attestation hygiene (DeFi Ch14+P10) | only attested (P10) resolution feeds drive D8 filtering; per-feed cap | doc + caps enforced |

---

## 11. Build & test sequence (Docker-first; each stage independently stub-able)

1. `evidence_chain.py` + `tests/test_evidence_chain.py` ✅ (16 tests, hermetic).
2. `agent/defi_agent.py` (D5–D8) + `tests/test_defi_agent.py` — hermetic (stub
   `get_markets`/`suggest_crypto`/`Attestation`), paper mode end-to-end.
3. KG `graph/schema/defi_extension.cypher` (additive `OracleFeed`/edges) + load
   in Neo4j (idempotent).
4. API routes (`/defi/*`) + `DefiWorkspace.tsx` + App menu item (read-only,
   Redis-backed).
5. `.env.example` append + `Makefile` `web3-test`? no — **`Makefile` untouched**;
   run the new tests via the existing `pytest` target + a `pytest tests/test_defi_agent.py`
   selection. Full suite in Docker.
6. Demo wiring: DreamDEX/Somnia testnet lifecycle — `somnia-relay` dry-run →
   one paper EC order → evidence-chain appended → EvidenceChain tab shows
   hash-chain + Merkle root.

---

## 12. Risk register

| Risk | Mitigation |
|---|---|
| EC resolution-oracle divergence (Ch. 13 Black Thursday analog) | U30 breaker + `OracleFeed` freshness; P9 U1 haircut re-grounded |
| EC settlement/void variance | P9 U1/U9: code-is-law, treat voids as losses, τ<cutoff haircut |
| Overpaying EC (book's IL lesson analog) | U28 EC edge gate (`your-p − ask`) + binary-Kelly sizing |
| Tail-hedge over-risk | U32 D7 portfolio cap; premium cap; regime gate (Crisis/Stress only) |
| MEV/front-running on discrete EC | simulate-first; the `somnia-relay` nonce serialization (P9 U2/U3) |
| Attestation/bridge trust (Ch. 14 + P10) | U33 only attested feeds filter D8; per-feed cap |
| Key custody (Ch. 15) | `somnia-relay` RFC-6979, air-gapped signer for live Somnia key; never in `.env` |
| Regulatory | testnet-first (Somnia 50312); USD-pegged permissioning docs in repo |

---

## 13. Judging alignment

- **Somnia × DreamDEX:** the P9 core plus D5 (EC cross-hedge) and D6/D7
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