# P9 — Financial-Engineering Tenet Upgrades

**Companion to:** `docs/p9_dreamdex_integration.md` (the P9 build plan)
**Sources distilled:**
- *Finance with Artificial Intelligence and Blockchain* — Sean Stein Smith (Springer, 2020) → `Finance with Artificial Intelligence and Blockchain.md`
- *Mastering Ethereum: Building Smart Contracts and DApps* — Andreas M. Antonopoulos & Gavin Wood (O'Reilly, 2018) → `Mastering Ethereum_ Building Smart Contracts.md`
- *Technical Trading and Cryptocurrencies* (Annals of Operations Research, 297:191–220, 2021) → `Technical trading and cryptocurrencies (1).md`
- *Cryptographic Primitives in Blockchain Technology: A Mathematical Introduction* — Andreas Bolfing (Oxford University Press) → `Cryptographic Primitives in Blockchain Technology_ A mathematical introduction.md`
**Discipline:** additive — this doc only *adds requirements and guardrails* to the P9 plan; nothing in the P9 file layout or the "3 edits only" rule changes.

---

## 1. Purpose

The P9 plan already has a defensible execution architecture (relay owns the key, agent prices edges, KG wires the narrative). This companion makes GraphAlpha's EC bot **auditable, settlement-aware, and operational-grade** — the difference between "a demo that trades" and "an agent a financial professional would let trade." Every upgrade below names the source tenet, the principle, the concrete change, the files touched, and a testable acceptance criterion.

---

## 2. Tenet Ledger — *Finance with AI & Blockchain* (Stein Smith)

| # | Ch. | Tenet (paraphrase from text) | Implication for P9 |
|---|---|---|---|
| F1 | 1/17 | **Data is the defining competitive advantage of the 21st century**; it must be harnessed within a logical framework | The agent's edge is only trustworthy if every input (tape, vol estimate, regime, signal) is *provenanced and replayable* → U1/U10 |
| F2 | 6 | **Data-driven decision making**: most organizations sit on data but still decide on intuition; AI's job is to make the data usable | The edge model must be *computed*, not vibes: estimate→ask→edge→size, each field auditable → U1 |
| F3 | 6/13 | **Continuous auditing & attestation**: audits shift from periodic samples to continuous, real-time verification; errors caught before material | The bot maintains an append-only, tamper-evident **decision ledger** that a control reviewer can replay any candidate from → U1 |
| F4 | 8 | **Lex Cryptographica**: cryptography becomes "code is law"; benefits (automation, transparency) coexist with risks (no clearinghouse, no recourse) | Settlement/void resolution is deterministic code — the agent must respect code-defined finality and size accordingly (no dispute path) → U8/U9 |
| F5 | 9 | **Ownership verification & tracing**: even decentralized systems converge on a clearinghouse role (custody, identity, reconciliation) | The relay reconciles its local position ledger against the on-chain view each cycle — the bot IS its own clearinghouse → U7 |
| F6 | 12 | **AI without human oversight can swing markets**; "the professional behind the wheel" and **control specialists** review bot parameters | Kill-switch + human approval gate + visible parameter attestation → U5 |
| F7 | 12 | **Settlement lag is the pain** (T+2 back office vs. 24/7 markets); blockchain verifies + settles continuously | The claim/redeem loop is the product story: on-chain settlement beats TradFi lag → demo |
| F8 | 17 | **Tokenization**: rights to an asset become tokens with explicit lifecycle (tokenized claims, clearinghouse question) | EC claims ARE tokenized binary claims; the panel shows the token lifecycle (mint→trade→settle→redeem) → U8 |
| F9 | 17 | **Bots augment, they don't replace**; new roles audit bot parameters | A "Parameter Attestation" view makes the bot's governing constants inspectable → U5 |

---

## 3. Tenet Ledger — *Mastering Ethereum* (Antonopoulos & Wood)

| # | Ch. | Tenet (paraphrase from text) | Implication for P9 |
|---|---|---|---|
| M1 | 11 | **Oracles**: the EVM is deterministic and blind; real-world price data enters only via oracles — and oracle data is untrusted until verified | The EC market resolves on an oracle feed; the agent must independently sample the same series, disqualify divergence, and treat on-chain status as authoritative (not the indexer/wall-clock) → U1 |
| M2 | 9 | **Checks-Effects-Interactions**: do all state-changing logic *before* any external call; external calls must be the last operation; never update state before the call completes | The relay's order/claim paths become an explicit C-E-I state machine; claims follow the **withdrawal pattern**: local "claimed" only after tx confirmation (`assertTxOk`) → U2 |
| M3 | 6 | **Transactions**: nonce is a replay-prevention sequence (never reuse); gas price/limit are the sender's levers; the tx is the only way to change state | Nonce discipline per key (already declared) is hardened; **gas-price bumping** on time-critical claim retries; claim is scheduled as first-class, not a lazy sweep → U3 |
| M4 | 9 | **Block timestamps are manipulable** — use block number / authoritative on-chain state for time-critical transitions | Order *expiry/validity derived from on-chain status and market state*, not local clock `closesAt` alone → U1/U3 |
| M5 | 9 | **Don't roll your own crypto / reuse vetted libraries** (OpenZeppelin ethos); raw hand-encoding breeds attack classes (short-address, tx.origin auth) | Order construction exclusively via `markets-sdk` + bot-kit `ec-core`; zero hand-rolled ABI/signing/encoding → U8 |
| M6 | 9 | **King of the Ether / EtherGame**: state that says "paid" while funds never moved; externally mutable `this.balance` traps | Reconciliation must *verify* the claim payout landed; never rely on local bookkeeping as proof of funds → U2/U5 |

---

---

## 3A. Tenet Ledger — *Technical Trading and Cryptocurrencies* (Annals of Operations Research, 2021)

| # | § | Tenet (paraphrase from text) | Implication for P9 |
|---|---|---|---|
| T1 | 5 | **Data-snooping / multiple-hypothesis testing** — testing N rules inflates false discoveries; FWER (Bonferroni α/M single-step, Holm step-wise) and FDR (BH step-up, BY dependence-robust) correct it; "if you torture the data long enough, it'll confess to anything" (Coase) | Every EC market scanned per cycle is a hypothesis test — the edge gate must be multiplicity-corrected or spurious edges fire → **U10** |
| T2 | 6.2 | **Transaction costs are decisive** — a rule can be statistically significant yet unprofitable after costs (taker pays the fill, not the quote) | Net edge = raw edge − impact − tolerance; shallow/liquid books skipped → **U11** |
| T3 | 6.5 | **Out-of-sample discipline** — best in-sample rules degraded OOS (BTC went *negative* OOS Sharpe/Sortino; market efficiency + publication decay) | Parameters frozen under a versioned `param_set_id`; performance is only declared out-of-sample → **U12** |
| T4 | 4/6.3 | **Benchmark vs. buy-and-hold** — raw returns are meaningless; the paper uses annualized Sharpe and Sortino throughout | Attestation computes bot − baseline vs. buy-and-hold **and** a market-neutral both-sides benchmark → **U12** |
| T5 | 2 | **Two-provider data robustness** — CoinDesk + Bitstamp as independent feeds for the *same* series | The model's spot/vol must not hang on a single feed; cross-check + divergence discount → **U13** |
| T6 | 2 (Table 1) | **Leptokurtic crypto returns** — excess kurtosis 12–97 across BTC/ETH/LTC/XRP; fat tails dominate the distribution | The log-normal lens understates tail vol; widen σ with an explicit kurtosis scalar → **U11** |

---

## 3B. Tenet Ledger — *Cryptographic Primitives in Blockchain Technology* (Bolfing, OUP)

| # | Ch. | Tenet (paraphrase from text) | Implication for P9 |
|---|---|---|---|
| C1 | 6.8 | **Confirmation security** — zero-confirmation crediting is the classic double-spend/race bug; each confirmation cuts race-attack success *exponentially* (k=6 → P≈5.9e-4 at attacker q=0.10) | Claims/credits require `REQUIRED_CONFIRMATIONS`; reorgs watched via the longest-chain criterion → **U14** |
| C2 | 3.5/6.5.4 | **Merkle trees / tamper-proof ledgers** — change-sensitivity flows leaves→root; the root (part of a block header) is what cannot be secretly rewritten | Attestation ledger gains a per-batch Merkle root **anchored on-chain/IPFS** + per-event inclusion proofs → **U15** |
| C3 | 3.6.6.4 | **ECDSA ephemeral-key attack** — reusing the per-message nonce k lets the adversary recover the *private key* (the PS3 hack); k must be securely generated, stored, and destroyed | Signing only via RFC-6979 deterministic k (viem/markets-sdk); no custom signing path; three-nonce taxonomy → **U16** |
| C4 | 3.4 | **Hash-function security requirements** — preimage 2^n, collision 2^(n/2) via birthday bound; SHA-256 ⇒ 2^256 / 2^128 | State the formal security claim of the attestation chain; never truncate or weaken the digest → **U15** |
| C5 | 5.2.3.2–5.2.3.3 | **CAP + Byzantine reality** — consistency is a *safety* property, availability is *liveness*; only two of three; nodes may behave arbitrarily | Explicit stance: **safety over liveness** at the money layer — halt new intents when the chain view is uncertain → **U17** |
| C6 | 4.3 | **DoS / Sybil on open networks** — untrusted entities misuse free access | Relay API behind a shared secret + per-sender rate limits; RPC pinned (TLS + chain-id) → **U17** |

---

## 3C. Tenet Ledger — *Building AI Agents with LLMs, RAG, and Knowledge Graphs* (Raieli & Iuculano, Packt 2025)

| # | Ch. | Tenet (paraphrase from text) | Implication for P9/P10 |
|---|---|---|---|
| A1 | 9 | **Hybrid memory** — short-term (within LLM context) + long-term (external: RAG/KG/DB) memory; memory reading/writing/reflection as the three operations | Redis = short-term agent state; Neo4j = long-term decision/evidence memory → **U18/U20** |
| A2 | 4 | **Planning = formulation + reflection** — CoT/ToT decomposition (single- vs multi-path), then a feedback loop that evaluates the plan; ReAct thought-act-observation | Orchestrator = plan formulation; backtest/evidence review = reflection → **U19** |
| A3 | 7 | **Graph before generation** — LLMs lack structural/spatial reasoning; the KG supplies relation context; HybridRAG unifies graph + vector | GraphRAG over ONE shared KG must *drive* the EC decision, not decorate it → **U18/U20** |
| A4 | 9 | **Multi-agent composition** (HuggingGPT-style) — a central task-planner routes subtasks to specialist agents/models; each specialist has a functional description | Orchestrator registry = task planner; per-chain agents (DreamDEX, CreditGraph) = specialist pool → **U18** |
| A5 | 10 | **Scaling/deployment reality** — agents interact with their environment; humans lead, agents propose; production needs monitoring, guardrails, human oversight (Virtual Lab PI) | Human-in-the-loop is a *feature*: human approves every materially economic action → **U21/U24** |
| A6 | 9 | **Business models** — SaaS, MaaS, DaaS, RaaS/OaaS (Results/Outcome as a Service) are the emergent paradigms | Ported panels = "Credit decision as a service"; attestation ledger = the "outcome" being sold → **U22** |
| A7 | 10 | **Responsible AI** — "Apply responsible AI practices with monitoring, guardrails, and human oversight" (book's closing directive) | All of the above: freeze, audit-ability, determinism contracts → **U23/U24** |

---

## 4. The Upgrades (U1–U24)

Each upgrade: **Principle** → **Concrete change to P9** → **Files** → **Acceptance**. All additive.

---

### U1 — Oracle & settlement as first-class risk  (tenets F4, M1, M4)

- **Principle.** EC contracts resolve via a price oracle that is *untrusted until verified*. Code-is-law means there is no dispute path — settlement risk must be priced, not assumed away.
- **Concrete change to §7 financial engine:**
  1. **Oracle-vs-tape divergence check.** In `dreamdex_agent`, keep the existing `_tape(pair)` sample; when the relay reports a window entering `Locked→Resolved`, compare the settlement price to the agent's last tape sample. If |Δ| > a band (`ORACLE_DIVERGENCE_BPS`, default 50bp), log a `settlement_variance` event and **exclude that market family from future candidates for N cycles** (trust decay).
  2. **Authoritative-state rule.** All lifecycle decisions (eligible, young, expiring) use the relay's on-chain `status` and SDK market state — never the local clock or `closesAt` string.
  3. **Short-τ haircut.** When `τ = remaining/intervalSec < HAIRCUT_TAU` (default 0.15), multiply binary-Kelly `f*` by a `code_is_law` discount (default 0.5) — as the window nears finality, oracle dispute risk dominates.
  4. **Voided-market PnL.** Track `voided` markets as realized losses in the audit trail (not "no PnL").
- **Files:** `agent/dreamdex_agent.py` (§7 engine), `graph/schema/dreamdex_extension.cypher` (add `settlement_variance` property), `api/routes/dreamdex.py` (surface `settlement_monitor`), `DreamDEXPanel.tsx` (badge).
- **Acceptance:** with a stubbed relay that resolves a market 40bp from the agent's tape, the next cycle drops that family and logs `settlement_variance`; candidate near τ<0.15 shows the haircut in `fstar` and `sizeUsdc`.

---

### U2 — Checks-Effects-Interactions + withdrawal pattern in the relay  (tenets M2, M6)

- **Principle.** Every external call (broadcast, claim tx) must be the *last* operation, and state changes must happen only *after* the external call completes or reverts.
- **Concrete change to §6 relay contract & §12:**
  1. **Order path** (`POST /order → src/order.ts`) refactored to: **Check** — validate market status==1, qty bounds, book sanity, dry-run flag → **Effect** — persist `intent` locally (idempotency key `intentId = sha256(marketId|side|qty|nonce)`) → **Interact** — sign+broadcast → **Confirm** — on success, write fill; on revert, mark `reverted` with reason. Never mutate local state before broadcast returns.
  2. **Claim path** (`src/claim.ts`) follows the **withdrawal pattern**: the relay (as the caller) pulls claims into the local ledger *only after* `assertTxOk`/confirmation; a `claimed=true` local record is never written ahead of a confirmed tx. If a tx reverts, retry with gas bump (U3) then dead-letter.
  3. **Idempotency.** Every relay write carries `intentId` so retries are safe (no double-fill/double-claim across relay restarts).
- **Files:** `dreamdex/src/order.ts`, `dreamdex/src/claim.ts`, `dreamdex/src/fills.ts` (state transitions), relay unit tests.
- **Acceptance:** relay test with a forced-reverted broadcast leaves local state `pending` (never `filled`), and a replay of the same `intentId` does not double-submit. Claim test: without a confirmed tx receipt the local ledger stays `unclaimed`.

---

### U3 — Nonce & gas engineering for time-critical transactions  (tenets M3, M4)

- **Principle.** A tx is the only way to change on-chain state; nonces are a replay-prevention sequence (never reuse); for time-boxed windows (resolved markets that must be claimed), gas is a **liveness** lever.
- **Concrete change to §12/§13:**
  1. **Single-threaded nonce discipline** (already in P9 §15) is hardened: the relay keeps a per-key monotonic nonce counter, single sender loop, and a `nonce_in_flight` guard so two txs can never race the same slot.
  2. **Claims are scheduled, not lazy.** When `AUTO_CLAIM` observes a `Resolved` market, the claim tx gets `gasPrice × (1 + CLAIM_GAS_BUMP_PCT)` (default 20%) at submission so it lands promptly; if it rests too long, resubmit with an increasing bump (up to `CLAIM_GAS_MAX_MULTIPLIER`, default 2.0).
  3. **Stuck-tx detector.** If a claim/order tx sits in mempool past `TX_STUCK_MS` (default 60s), the relay flags it on `/status` (`stuckTxs`) rather than silently duplicating (idempotency keys from U2 make retries safe).
- **Files:** `dreamdex/src/claim.ts`, `dreamdex/src/index.ts` (scheduling), `.env.example` (`CLAIM_GAS_BUMP_PCT`, `CLAIM_GAS_MAX_MULTIPLIER`, `TX_STUCK_MS`).
- **Acceptance:** forced high-mempool test shows claim retry bumps gas and completes within `CLAIM_GAS_MAX_MULTIPLIER`; `/status` reports `stuckTxs` while a mock tx is pending.

---

### U4 — Continuous attestation ledger (the differentiator)  (tenets F3, F5, F6 + M2)

- **Principle.** Stein Smith's core thesis: auditing shifts from periodic sampling to **continuous, real-time verifiable attestation**. Our bot is a public, autonomous trader — so every decision it makes must be independently replayable: *given the same inputs, the same candidate is produced*. That property is what makes an AI trading agent auditable ("review the parameters that drive the bot," F9).
- **Concrete change — new module `agent/dreamdex_attestation.py` (+ relay event sink):**
  1. **Append-only, hash-chained event stream.** Every cycle the agent appends an event to Redis `dreamdex:attest:<cycle_id>`:
     ```
     {
       "cycle_id", "ts", "regime",
       "inputs_sha256": hash(markets_snapshot + tape + signals),   # the full preimage
       "belief": {pair, P_up, sigma, tau},
       "edge":  {side, estimate, ask, edge_pct, fstar, qty, size_usdc},
       "intent_id", "status", "tx_hash", "claim_tx", "pnl"
     }
     ```
     Each event's `event_hash = sha256(prev_event_hash + payload)` — a tamper-evident chain.
  2. **Replay endpoint.** `GET /dreamdex/attest/{cycle_id}` returns the event + `inputs_sha256` + a link to the stored preimage in Redis, letting a reviewer (or a judge!) regenerate the candidate off-line. `GET /dreamdex/attest` lists recent cycles with chain continuity check (`chain_ok: true/false`).
  3. **Fill→claim linkage.** Each fill event carries `intent_id`; each claim event references the fill's `tx_hash`, so the ledger traces **regime → belief → edge → order → fill → settle → claim → wallet credit** in one continuous chain (M6: state must never claim funds moved unless verified).
  4. **Voided/loss events** are recorded as realized outcomes (U1.4), so the trail is honest about losses — not just wins.
- **Files:** `agent/dreamdex_attestation.py` (new), `api/routes/dreamdex.py` (`/attest`, `/attest/{id}`), `DreamDEXPanel.tsx` ("Audit" tab), Redis keys `dreamdex:attest:*` (TTL 24h), reused by U5 reconciliation.
- **Acceptance:** unit test: given the same Redis preimage, a stub recomputes the candidate hash; pruning/editing any prior event flips `chain_ok` to `false`. This is the demo's closing artifact.

---

### U5 — Trust-but-verify reconciliation (the bot as its own clearinghouse)  (tenets F5, M6)

- **Principle.** Decentralized systems still need a clearinghouse function — the bot plays that role for itself: it must verify that what it *thinks* happened on-chain actually happened (fill price, claim payouts).
- **Concrete change to §7.5 lifecycle & §9:**
  1. **Ledger-vs-chain reconciliation.** Each cycle the relay's position view (`GET /positions` → relay `getPositions`) is compared to the local fills ledger. Drift (missing fill, fill-price ≠ est, claim not credited) is reported as `reconciliation: {status, drift_items[]}` on `/dreamdex/status`.
  2. **Fill-price verification.** `dreamdex_adapter.get_positions()` matches each local `intent_id` to the on-chain fill; a fill whose `avg_price` diverges from `estPrice` beyond a band (`FILL_PRICE_TOLERANCE_BPS`, default 100bp) is flagged (M7: taker pays fill price, not offered price).
  3. **Claim-payout verification.** After a claim tx confirms, the relay re-pulls balances; only a positive balance delta marks the claim "credited" in the attestation ledger (M6 — never bookkeeping as proof).
- **Files:** `dreamdex/src/fills.ts` (reconciliation), `agent/dreamdex_adapter.py` (new `reconcile()`), `api/routes/dreamdex.py` (surface), `DreamDEXPanel.tsx` (reconciliation chip).
- **Acceptance:** with a stubbed relay returning a fill 150bp off est, the next cycle emits a `drift_item` on `/dreamdex/status`; a claim whose balance didn't move stays `uncredited` in the ledger.

---

### U6 — Parameter attestation & human kill-switch  (tenets F6, F9)

- **Principle.** "Bots augment; the professional stays behind the wheel." Every bot parameter that drives a trade must be inspectable, and a human must be able to freeze the bot instantly.
- **Concrete change to §9/§10/§11:**
  1. **`GET /dreamdex/controls`** returns *every* governing constant as of the last cycle: `{min_edge_pct, kelly_binary_half_scale, portfolio_cap_pct, lens, regime_map, oracle_divergence_bps, haircut_tau, code_is_law_discount, fill_price_tolerance_bps, enabled, mode}` — plus a `last_cycle_ts` so reviewers know which parameter set drove the last candidate batch.
  2. **`POST /dreamdex/freeze`** — human kill-switch: sets `frozen: true`; the agent stops generating *new* intents instantly (checks `frozen` before `run()`), **but the claim sweep and reconciliation continue** (liveness must not die with trading). `POST /dreamdex/unfreeze` requires the same two-phase token gate.
  3. **Controls reframed in the panel.** A "Controls" pane (accordion in `DreamDEXPanel`) displays the constants from `/dreamdex/controls` with a **Freeze** button — visible evidence of "the professional behind the wheel" in the demo.
- **Files:** `api/routes/dreamdex.py` (`/controls`, `/freeze`, `/unfreeze`), `agent/dreamdex_agent.py` (gate on `frozen`), `DreamDEXPanel.tsx`, `.env.example` (constants already defined; now also surfaced).
- **Acceptance:** with `frozen=true`, a normally-eligible cycle produces zero candidates; claim sweep still runs; `/dreamdex/controls` reflects the exact constants.

---

### U7 — Continuous-attestation narrative for the demo & docs  (tenets F3, F7, F8, M6)

- **Principle.** Two book threads converge into one story: (a) *continuous, real-time attestation* (Finance) and (b) *oracles make on-chain settlement instant vs. TradFi T+2* (Mastering Ethereum Ch. 11, Finance Ch. 12). The claim/redeem loop is the product story.
- **Concrete additions to §14 demo script + §2.1 framing:**
  1. **Token-lifecycle framing.** Reframe EC claims explicitly as **tokenized contingent claims** (F8): mint a complete set → trade → settle (code-is-law resolution via oracle) → **redeem** (claim). The demo's narration uses this lifecycle, tying it to tokenization and to the "settlement lag is the pain, on-chain fixes it" thesis (F7).
  2. **Close with the attestation artifact.** After the live testnet fill → settlement → claim, the presenter opens the **Audit tab** (`/dreamdex/attest/<cycle_id>`, `chain_ok: true`) and walks one chain: regime → belief → edge → fill → claim → wallet credit. "Every trade this bot makes is continuously attestable" — the strongest single sentence in the demo, and a direct lift of the book's thesis.
  3. **Two-phase human gate shown as "advisor" pattern (F2/F6).** Narration: "The bot generates *candidates* with a full reasoning trail; a human runs the confirmation gate — the bot augments, the professional decides."
- **Files:** §14 demo script in `docs/p9_dreamdex_integration.md`, optional slide text.

---

### U8 — Code-reuse doctrine made binding  (tenets M5)

- **Principle.** "Don't roll your own crypto"—the safest financial software reuses vetted libraries for every security-critical step.
- **Concrete change to §6/§15 risk register:**
  1. **Hard rule:** all order construction, price quantization, signing, and ABI encoding go exclusively through `@somnia-chain/markets-sdk` + bot-kit `ec-core` (`placeLimit`, `quantize`, `ec-settlement`). Zero hand-rolled RLP/ABI/calldata in the relay. (Adds to §2.6 and the §15 risk "float price" row.)
  2. **Dependency pins.** `dreamdex/package.json` pins `markets-sdk` to a known-good version and `npm audit` is part of `make dreamdex-test`.
  3. **Short-address / tx.origin attack classes** (from M5) get an explicit risk-row: input validation at every relay boundary; never trust address params without checksum validation.
- **Files:** `dreamdex/package.json`, `docs/p9_dreamdex_integration.md` §6 (contract), §15 (risk register), `Makefile` (`dreamdex-test` runs `npm audit`).
- **Acceptance:** code review checklist item: "no raw signing/ABI/calldata outside markets-sdk/ec-core"; `make dreamdex-test` fails on any `npm audit` high severity.

---

### U9 — "Code is law" as the sizing backdrop  (tenets F4, M1, M4)

- **Principle.** There is no dispute path on-chain; the market's smart contract *is* the settlement authority. That reality must be priced in as the `code_is_law` haircut on short-τ windows (already in U1.3) and stated in the risk register so the demo never overpromises.
- **Concrete change:** add the explicit risk row ("Settlement authority is the EC contract; a voided/divergent window is a realized loss, not a dispute") and the `code_is_law_discount` env var; the panel shows the haircut applied per candidate near finality.
- **Files:** §15 risk register, `.env.example`, candidate shape gains `code_is_law_discount`.

---

---

### U10 — Multiple-comparison correction on the edge gate  (tenet T1)

- **Principle.** Coase: "if you torture the data long enough, it'll confess to anything." Scanning N EC markets per cycle is running N hypothesis tests; without multiplicity control the agent will fire on spurious edges. The paper controls FWER (Bonferroni α/M, Holm) and FDR (BH step-up, BY dependence-robust) before claiming any rule works.
- **Concrete change to §7 engine:**
  1. Each candidate's edge is converted to a **p-value under the null** (edge ≈ 0) via a stationary bootstrap over the tape residuals (the paper's §5 method), computed lazily per market per cycle.
  2. New env `DREAMDEX_MULTICORR=` off | bonferroni | holm | bh (default **bh**, FDR δ=0.10): **bonferroni** divides the base edge p-threshold by N_tested; **bh** applies the step-up on the sorted p-values; **holm** the step-wise α/(N−i+1).
  3. Every attestation event gains `n_tested` and `alpha_eff` so reviewers see exactly how strict the gate was that cycle.
- **Files:** `agent/dreamdex_agent.py` (§7 engine + bootstrap), `.env.example`, attestation event schema (§5), `GET /dreamdex/controls` exposes `multicorr` + `alpha_eff`.
- **Acceptance:** on a synthetic *null* market set (no real edge present), `off` fires several candidates while `bh` fires ≈0 at δ=0.10; `alpha_eff` is logged and displayed per cycle.

---

### U11 — Cost-, liquidity-, and fat-tail-aware edge  (tenets T2, T6)

- **Principle.** The paper shows rules can be significant pre-cost yet unprofitable after (T2), and Table 1 shows excess kurtosis 12–97 — the log-normal lens understates tail vol (T6).
- **Concrete change to §7 engine:**
  1. **Net-edge gate:** fire only when `net_edge = edge_pct − FILL_IMPACT_BPS − MIN_EDGE_PCT > 0`, with `FILL_IMPACT_BPS` (default 20bp) standing in for taker-vs-quote slippage where the raw ask already misses depth. Both `FILL_IMPACT_BPS` and `MIN_EDGE_PCT` are already surfaced in `/dreamdex/controls` (U6).
  2. **Liquidity floor:** skip markets with `ask_depth < MIN_ASK_DEPTH_CONTRACTS` (default 5) — a "great edge" on an empty book is a mirage (fill-price reality from U5 applies *before* order construction).
  3. **Kurtosis-widened σ:** `σ_eff = σ_realized × (1 + KURTOSIS_VOL_SCALE × (ex_kurtosis/10))` with `KURTOSIS_VOL_SCALE` (default 1.0); the widened σ flows into `P_up`, shrinking the apparent edge exactly where tails are fattest (BTC ~14, ETH ~13, LTC/XRP much higher).
- **Files:** §7 engine, `.env.example` (`FILL_IMPACT_BPS`, `MIN_ASK_DEPTH_CONTRACTS`, `KURTOSIS_VOL_SCALE`), candidate shape gains `netEdgePct`, `tailScaledSigma`; `DreamDEXPanel` shows net vs raw edge.
- **Acceptance:** a synthetic 350bp raw-edge candidate with 40bp impact + kurtosis-widened σ no longer fires; a market with ask depth 2 is skipped; `netEdgePct` visible in the panel and attestation.

---

### U12 — Out-of-sample & benchmark discipline  (tenets T3, T4)

- **Principle.** The paper's starkest result: the best in-sample BTC rules went *negative* OOS (market efficiency; publication decay). Performance claims are only meaningful (a) out-of-sample and (b) against a baseline (buy-and-hold, or a market-neutral both-sides position), reported with Sharpe/Sortino.
- **Concrete change to §9/§14:**
  1. **Frozen `param_set_id`:** the agent's governing constants (U6 controls) hash into `param_set_id`; that id is stamped on every attestation event so a reviewer can prove the *same* parameters produced an entire OOS run. Any parameter change bumps the id — the ledger never rewrites the past under the new id.
  2. **Two baselines in the ledger:** `GET /dreamdex/benchmark` computes, over the same windows: (a) **buy-and-hold** of the underlying pair, (b) **market-neutral** (equal buy both sides, ≈ zero-expectation reference). Bot PnL is always reported as `bot − baseline` with annualized Sharpe and Sortino (the paper's metrics), never raw PnL dressed as alpha.
  3. Demo framing: "we do not claim alpha; we claim a *replayable, benchmarked* decision trail" — the anti-data-snooping stance *is* the pitch.
- **Files:** `agent/dreamdex_attestation.py` (params + benchmark), new `GET /dreamdex/benchmark`, `DreamDEXPanel` "Benchmark" section, `.env.example` (`OOS_SPLIT=`, freeze guard).
- **Acceptance:** with a stub PnL series, `/benchmark` returns bot vs both baselines with Sharpe/Sortino; mutating a parameter bumps `param_set_id` and the audit chain still validates.

---

### U13 — Two-provider data robustness  (tenet T5)

- **Principle.** The trading paper deliberately sources the *same* series from two independent providers (CoinDesk + Bitstamp) for robustness. A single tape feed means single-source risk inside the model (and it dovetails with U1's oracle-divergence check).
- **Concrete change to §7 engine / §9:**
  1. Extend `_tape(pair)` to a **second independent crypto feed** using the existing provider-abstraction fallback pattern (`alpaca_data.py`); the agent computes spot and σ from **both** series each cycle.
  2. If the two feeds diverge > `TAPE_DIVERGENCE_BPS` (default 25bp), the belief is attenuated: `P_up` is pulled toward 0.5 by a linear factor of the divergence, and the attestation event flags `tape_divergence: true` with both price sources recorded.
  3. U1's settlement-variance check is extended to use the same dual-feed reference (settlement vs. the *max* of the two pre-window samples).
- **Files:** `agent/dreamdex_agent.py` (§7), `agent/dreamdex_attestation.py` (record `price_sources`), `.env.example` (`TAPE_DIVERGENCE_BPS`), attestation schema.
- **Acceptance:** with a stubbed second feed 60bp off the primary, belief shrinks, `tape_divergence` is flagged, and both price sources appear in the audit event.

---

### U14 — Confirmation-count settlement policy  (tenet C1)

- **Principle.** Bolfing §6.8: crediting an unconfirmed (zero-confirmation) transaction is *the* classic double-spend/race vulnerability; each subsequent confirmation cuts the attacker's race success exponentially (his Table 6.1: k=6 → P≈5.9e-4 at q=0.10).
- **Concrete change to §6/§9/§12:**
  1. New env `REQUIRED_CONFIRMATIONS` (default **3** on testnet): a fill/claim is never marked `credited` before that many confirmations on the authoritative chain (longest-chain criterion per Bolfing §6.4.4.3).
  2. Positions and fills carry **`confirmations`** and **`reorg_detected`**: on each relay poll, if the block height of the crediting tx regresses (fork/reorg), the fill is *un-credited* pending re-confirmation and an alert is raised (do not log, do not pass).
  3. `/status` and `/dreamdex/controls` expose the policy and the implied guarantee as a number — "crediting policy: 3 confirmations ⇒ P(race success) ≤ 5.9e-4 at q=0.10" — the *quantified* safety stance for the demo.
- **Files:** `dreamdex/src/fills.ts` + `src/claim.ts` (confirmation gate), `api/routes/dreamdex.py` (surface `confirmations`/`reorg_detected`), `DreamDEXPanel` fill rows "3/3 conf", `.env.example`, `docs/p9_dreamdex_integration.md` §15 risk row.
- **Acceptance:** a fill with < required confirmations reads `pending`; forcing a simulated fork flips `reorg_detected` and suspends credit until the tx is re-confirmed at depth.

---

### U15 — Merkle-anchored attestation  (tenets C2, C4)

- **Principle.** Hash chaining is *change-sensitive* (C2); but tamper-evidence is only as strong as the anchor — the book's design puts the Merkle root *inside a block header* so it cannot be secretly rewritten, and any leaf change invalidates the root (Bolfing §6.5.4). Collision safety rests on the digest width (C4: SHA-256 ⇒ 2^256 preimage, 2^128 collision).
- **Concrete change to §9 U4:**
  1. Upgrade the attestation ledger (U4) with a **Merkle tree per batch** of cycle-events: leaves = `event_hash`, nodes = `H(left‖right)`, root stored as `dreamdex:attest:merkle:<batch_id>`.
  2. **Anchor the root** where it can't be silently rewritten: each batch root is written on-chain as a 0-value data blob tx (testnet `mint`-style, cheap) from the operator account — or pinned to IPFS when chain writes are impractical. `/status` reports `anchor_height` + `anchor_tx_hash`.
  3. `GET /dreamdex/attest/{id}` returns the event **plus its Merkle inclusion proof** (sibling hashes) so any auditor can verify root membership with O(log n) data.
  4. Document the formal security claim (C4): tamper requires a hash break (2^256 / 2^128) or rewriting the anchored root — explicit in the docs, never a truncated/weak digest.
- **Files:** `agent/dreamdex_attestation.py` (Merkle module), relay anchor writer, `api/routes/dreamdex.py`, `DreamDEXPanel` "anchored ✓" badge, `.env.example` (`MERKLE_ANCHOR_MODE=chain|ipfs|off`).
- **Acceptance:** inclusion-proof endpoint verifies against a stub tree; after an anchoring tx, `/attest` shows the on-chain anchor; mutating any historical leaf breaks root membership and flips `chain_ok=false`.

---

### U16 — Signing-nonce & key-path hygiene  (tenet C3)

- **Principle.** Bolfing §3.6.6.4: reusing the ECDSA ephemeral nonce `k` lets an adversary **recover the private key** (the PS3 hack). `k` must be securely generated, stored, and destroyed per signature — this is a *signing-level* discipline distinct from tx-account nonces.
- **Concrete change to §6/§12:**
  1. **Explicit three-nonce taxonomy** (documented in the relay README): (1) **tx account nonce** — sequential per-key replay protection (U3); (2) **ECDSA k** — RFC-6979 **deterministic** per-message (viem/`markets-sdk` handles this; never custom); (3) **intent-id** — idempotency key (U2). They are different sequences with different lifetimes; conflating them is the bug class.
  2. **No custom signing path:** signatures flow exclusively through viem/`markets-sdk`; add a `npm run crypto-hygiene` gate in `make dreamdex-test` that fails if the source imports/uses any hand-rolled `sign`, `signTypedData`, or raw `seck256k1` ops outside viem.
  3. `NFT/API` read key stays in the relay container; hot trading key is the operator/session key (U8-first hygiene from the P9 plan).
- **Files:** `dreamdex/package.json` (`crypto-hygiene` script), `dreamdex/README.md` (three-nonce taxonomy), `Makefile` (`dreamdex-test` runs it), trick: `dreamdex/src/order.ts` only if a signing fork is ever needed (it shouldn't be).
- **Acceptance:** `make dreamdex-test` fails the hygiene gate on any non-viem signing usage; relay signing call tree resolves 100% into `viem` (or `markets-sdk`).

---

### U17 — Safety-over-liveness stance + endpoint security  (tenets C5, C6)

- **Principle.** CAP (Bolfing §5.2.3.2): consistency is a *safety* property, availability is *liveness*; on a Byzantine network (nodes may misbehave) you cannot have both. Money-touching state changes choose **consistency now, availability later** — and §4.3 reminds us an open network surface invites DoS/Sybil abuse.
- **Concrete change to §6/§9/§15:**
  1. **Stance made explicit and enforced:** when the chain view is uncertain — RPC failure, stuck tx, reorg, or a reconciliation heartbeat missed > `HEARTBEAT_MS` (default 30s) — the agent **halts new intents** (safety); only reads and confirm-gated claims continue (liveness where it can't corrupt). The reconciliation loop (U5) is the *failure detector*; drift ⇒ freeze new trading.
  2. **Endpoint security:** the relay API (`/order`, `/claim`, `/freeze`, `/controls`) requires a shared-secret header `X-Relay-Key` (env `RELAY_API_KEY`); per-sender rate limits (`/order` ≤ 5/min) return 429; the RPC endpoint is pinned (TLS + chain-id) and host-whitelisted — no unauthenticated or bursty callers can burn gas or spam the book.
  3. `/status` gains a **system-health line**: `{chain_view: ok|stale, heartbeat_ms, last_reconciled_at, halted_reason}` so the "we are safety-first" behavior is *visible* to reviewers.
- **Files:** `dreamdex/src/index.ts` + middleware, `agent/dreamdex_agent.py` (halt gate), `api/routes/dreamdex.py` (`/status` health), `.env.example` (`RELAY_API_KEY`, `HEARTBEAT_MS`, rate-limit knobs), `docs/p9_dreamdex_integration.md` §15 risk row.
- **Acceptance:** with RPC stubbed to fail, new candidates stop while `/status` still serves; unauthenticated `/order` → 401; a burst beyond 5/min → 429; `system-health.halted_reason` reflects the cause.

### U18 — One task-planner, per-chain specialist agents  (tenets A3, A4, A1)

- **Principle.** The book's multi-agent pattern (Ch. 9, HuggingGPT-style): a central task-planner routes subtasks to specialist agents, each described by role/expertise/goal/tools. For a two-chain system the planner must not fork into two orchestrators — **one registry, many adapters**.
- **Concrete change (P10 §3/§8/§9):**
  1. Orchestrator stays the single task-planner. Each chain gets a thin `*_agent.py` (**DreamDEXAgent**, **CreditGraphAgent**) registered the same way — same Redis keys, same `run(regime, signals)` signature, same self-disable env flag.
  2. A `CHAIN_MAP` table (env or KG node) declares which agents are eligible for the current regime — e.g. `Stagflation → {creditgraph}` while `High Volatility → {dreamdex, creditgraph}`. The book's "functional description" of a specialist is the agent's docstring + its regime eligibility.
  3. Hybrid memory (A1): Redis = short-term (`agent_status`, `signals`, `creditgraph:*`); Neo4j = long-term (everything, now shared across chains).
- **Files:** `agent/dreamdex_agent.py`, `agent/creditgraph_agent.py`, `agent/orchestrator.py` (3-line hook each), `graph/schema/creditgraph_extension.cypher`.
- **Acceptance:** with both agents enabled, one orchestrator cycle produces `dreamdex_candidates` AND `creditgraph_candidates` in Redis; each is independently frozen by its own env flag.

---

### U19 — Reflection loop as first-class feedback  (tenet A2)

- **Principle.** Ch. 4: plan formulation must be followed by *reflection* — evaluate what the plan did and feed it back. The merged system already has `/backtest` (equities) and `reconstruct_decision` (credit) — wire them into the loop rather than leaving them as manual tools.
- **Concrete change (P10 §14 / P9 §7):**
  1. `reconstruct_decision()` becomes the credit reflection step: each cycle, settled/attested outcomes are compared to the recommendations that produced them (predicted-vs-realized).
  2. The P9 `/dreamdex/benchmark` (U12) and the credit reflection share one `reflection` Redis key namespace, surfaced in the frontend as a single "What did the plan do?" panel.
- **Files:** `api/routes/creditgraph.py` (`/reflection`), `agent/creditgraph_agent.py` (outcome comparison), frontend credit panel.
- **Acceptance:** after a stub outcome is persisted, `/reflection` shows predicted-vs-realized per decision/market with Sharpe/Sortino-style stats.

---

### U20 — GraphRAG over the ONE shared KG  (tenet A3)

- **Principle.** Ch. 7: "graph before generation" — structural context must come from the KG, not the LLM's memory. Both repos already practice this; the merge makes it *literally one graph*, so DreamDEX's `EventContract`→`Strategy` edges and CreditGraph's `Evidence`→`Regime` edges are co-traversable.
- **Concrete change:** Port attest's `graphrag.py` (entity resolution → intent classification → query planning → traversal → evidence → quant → context → LLM explain) into `api/creditgraph/services/graphrag.py`, pointed at the shared KG. Both pipelines resolve entities against the same labels.
- **Files:** `api/creditgraph/services/graphrag.py` + `graph/` helper, `api/routes/creditgraph.py` (`/risk/query`).
- **Acceptance:** a single query resolves entities from *both* domains (a `Borrower` holding `BTC-USD` exposure linked to a `Regime` that also gates a DreamDEX market) and returns both traversals.
---

### U21 — Human-in-the-loop as a product feature  (tenets A5, A7)

- **Principle.** Ch. 10's Virtual Lab: a human PI sets the agenda; agents propose; the human decides. Ch. 10 closing: "monitoring, guardrails, and human oversight." For money-touching systems this is not overhead — it is the differentiator (CreditGraph P7 already demands it).
- **Concrete change:** Formalize a **Human-Approval Gate** shared by both chains: every DreamDEX order and every CreditGraph transfer requires a `proposal_token` (two-phase preview/confirm) *or* an explicit human-approved `CreditDecision`. The U6 `/freeze` control freezes both chains. Surface as a per-candidate "Awaiting human approval" state.
- **Files:** `api/routes/dreamdex.py` + `api/routes/creditgraph.py` (shared approval module), both agents (candidate → pending until approval), frontend.
- **Acceptance:** with freeze on, neither pipeline creates *or executes* candidates; an unapproved candidate never reaches `order`/`execute`.

---

### U22 — RaaS/OaaS framing ("decision as a service")  (tenet A6)

- **Principle.** Ch. 9's business-model taxonomy: Results/Outcome as a Service is the emergent high-value model. The merged product already produces an auditable outcome per chain (a verified claim; a reconstructible credit decision) — the RaaS wrapper is presentation + API.
- **Concrete change:** The ported CreditGraph panels + DreamDEXPanel are framed as **two Outcome-as-a-Service surfaces** in the demo narrative. `/api/v1/risk/*` + `/dreamdex/*` both expose `GET` "report" endpoints (`/report`, `/benchmark`, `/reflection`) a reviewer can cite. No new execution logic — just the outcome contract.
- **Files:** `api/routes/creditgraph.py` (`/risk/report`), `api/routes/dreamdex.py` (existing `/benchmark`, `/status`), demo script.
- **Acceptance:** `/risk/report` and `/dreamdex/benchmark` return machine-readable outcome summaries with timestamps and `param_set_id`.

---

### U23 — Determinism contract between LLM and math  (tenets A3, A7, P3)

- **Principle.** Ch. 10 on responsible AI + CreditGraph P3: the LLM explains, it never alters calculated values. One hard rule — **deterministic quant is the source of truth; LLM text is display-only** — enforced in CI, not by convention.
- **Concrete change:**
  1. Port `quant_engine.py` (pure functions: historical VaR/CVaR/EL/stress) into `api/creditgraph/services/` unmodified.
  2. Extend the P9 U16 hygiene gate idea to a **determinism contract test**: any endpoint tagged `@deterministic` must return byte-identical output for identical input across runs. The LLM context-assembly path is the *only* place string generation may differ.
- **Files:** `api/creditgraph/services/quant_engine.py`, `tests/test_creditgraph_determinism.py`, Makefile `creditgraph-test`.
- **Acceptance:** `make creditgraph-test` re-runs a deterministic endpoint twice and diffs JSON equality; any non-deterministic output fails.

---

### U24 — Safety-net: freeze, audit, and the three gates  (tenets A5, A7)

- **Principle.** Ch. 10's final directive: ship agents with monitoring, guardrails, and human oversight. Three independent safety gates, explicit and *visible*:
  1. **Freeze gate** (U6/U21): `/freeze` halts both chains' new intents.
  2. **Audit gate** (U4/U15/U19): everything (candidate, decision, fill, credit) is in the attestation ledger + `reconstruct_decision` lineage.
  3. **Determinism gate** (U23): math is stable; LLM explains.
- **Concrete change:** `/api/v1/risk/health` and `/dreamdex/status` both expose a `gates: {freeze, audit_chain_ok, determinism_ok}` line; the frontend header shows three lamps.
- **Files:** `api/routes/creditgraph.py`, `api/routes/dreamdex.py`, frontend status bar, docs.
- **Acceptance:** flipping `/freeze` on flips `gates.freeze` in *both* health endpoints; the demo narrates the three lamps as "the safety story."

---

## 4B. Upgrades U25–U33 (P11 — Web3 DeFi sector expansion)

> Applied to the P11 plan (`docs/p11_web3_defi_expansion.md`). Sources:
> *Cryptographic Primitives in Blockchain Technology* (Bolfing) and
> *How to DeFi: Advanced* (CoinGecko). Each row: principle → concrete change →
> files → acceptance. New files only; the P9/P10 file lists are untouched.

### U25 — Sign everything (tenet C7: digital signatures)

- **Principle.** Bolfing Ch. 3.3.2.4: a digital signature scheme provides
  authentication, data integrity, and non-repudiation. If the bot's decisions
  are signed, *nobody* (including the operator) can later deny or silently
  rewrite a decision; tampering invalidates the signature before any dispute.
- **Concrete change:** `agent/evidence_chain.py` canonicalizes each cycle's
  decisions (sorted keys, stable floats), hashes, signs the root over the
  chain wallet; `api/routes/defi.py /evidence` exposes `verify_root`, panel
  shows the verified badge.
- **Files:** `agent/evidence_chain.py`, `api/routes/defi.py`, `DefiWorkspace.tsx`.
- **Acceptance:** a unit test tampers with one stored decision and asserts
  `verify_chain()` returns `False`; `verify_root(pubkey, root, sig)` matches.

### U26 — Merkle-batch attestations (tenet C8: Merkle trees)

- **Principle.** Bolfing Ch. 3.5: Merkle trees aggregate N leaves into one root
  with O(log N) membership proofs. Instead of attesting every decision
  individually on-chain, batch a period's roots into a Merkle root and anchor
  *that* — reuse P10's `Attestation` node semantics.
- **Concrete change:** `evidence_chain.merkle_root(entries)`; the batched root
  can be published by the `somnia-relay` (or a future anchor step) — no new
  service, no new chain.
- **Files:** `agent/evidence_chain.py`, `docs/p11_web3_defi_expansion.md`.
- **Acceptance:** `merkle_root` is stable for the same input; proof verification
  walks the path in O(log N).

### U27 — Quorum with authentication (tenet C9: Byzantine agreement)

- **Principle.** Bolfing Ch. 5.3.8: without authenticated messages consensus
  needs n > 3f; with signed messages the honest set can be smaller. For the
  CreditGraph consensus layer, signed attestation confirmations allow a
  *relaxed* quorum (e.g. 2-of-3 signed) instead of 3-of-3.
- **Concrete change:** a config knob `CREDITGRAPH_QUORUM_SIGNED` (default 2)
  and documentation; P10's `Attestation` nodes gain a `signed` flag.
- **Files:** `api/creditgraph/` consensus module, `.env.example`.
- **Acceptance:** doc + config only; no behavior change when unset.

### U28 — Edge-over-pay gate (tenet D1: AMM IL) → EC + EVM/Sepolia

- **Principle.** *How to DeFi* Ch. 3 teaches IL: an LP that overpays the risk
  systematically loses. The fix is an edge gate — applied twice:
  - **EC (DreamDEX):** buying an outcome because the signal is positive
    ignores the ask → overpay. Reject unless `edge = your_p − ask ≥ MIN_EC_EDGE_PCT`.
  - **EVM (Sepolia, D1):** real Uniswap V3 IL — reject LP when
    `fee_yield − IL(x·y=k) − gas ≤ MIN_LP_EDGE_PCT` (the book's 13.4%/20%/25.5% table).
- **Concrete change:** `defi_agent` D1/D5/D7 apply the venue-appropriate edge
  gate (EC: binary-Kelly edge; EVM: IL-adjusted edge from live pool math).
- **Files:** `agent/defi_agent.py`, `agent/web3_adapters/ethereum.py`, `tests/test_defi_agent.py`.
- **Acceptance:** hermetic tests — EC candidate with `your_p − ask ≤ 0` rejected;
  EVM LP candidate with `fee − IL − gas ≤ 0` rejected (stub book-divergence table).

### U29 — Liquidation/settlement-distance guard (tenet D2) → EC + Aave V3

- **Principle.** Ch. 5's liquidation math is *distance to the bad event*. Apply
  per venue:
  - **EC (DreamDEX):** distance-to-resolution + settlement-variance haircut
    (P9 U1) — short-τ windows or wide settlement variance get discounted.
  - **EVM (Sepolia, D2):** real Aave V3 liquidation distance — collateral
    factor, utilization; alert before the protocol fires.
- **Concrete change:** `defi_agent` D2/D5/D7 apply the venue-appropriate guard.
- **Files:** `agent/defi_agent.py`, `agent/web3_adapters/ethereum.py`, `tests/test_defi_agent.py`.
- **Acceptance:** tests — EC short-τ candidate shows haircut; Aave V3 candidate
  with collat×price below liquidation threshold → alert raised.

### U30 — Oracle-staleness circuit-breaker (tenet D3: Black Thursday)

- **Principle.** Ch. 13: stale Chainlink/Medianizer feeds caused ~$8M of ETH
  collateral liquidations. On DreamDEX, EC resolution feeds are the oracle —
  staleness/deviation must *stop* EC candidates, not throttle them.
- **Concrete change:** `defi_agent` D6 governor checks `OracleFeed` freshness
  (`ORACLE_STALE_MS`) + deviation band (`ORACLE_DEVIATION_BPS`); flips
  `paused: true` for the affected venues (D1–D8) when the feed is stale.
- **Files:** `agent/defi_agent.py` (D6), `tests/test_defi_agent.py`.
- **Acceptance:** test: `updated_at` older than `ORACLE_STALE_MS` → candidates
  empty + `paused: true`.

### U31 — Signing & approvals hygiene (tenet D4 → somnia-relay + web3-relay)

- **Principle.** Ch. 15's exploit catalogue (flash loans, unlimited approvals)
  is really about *key/approval hygiene*. Both execution relays sign with
  RFC-6979/nonce discipline, simulate before send, approve-min/revoke-after,
  and never hold a live key in `.env` (P9 U16 + stellcasp's
  `build_transaction({nonce, gas, gasPrice})`/`wait_for_receipt(status==1)`
  pattern already implements CE-I).
- **Concrete change:** re-affirm P9 U16 for the Somnia + EVM key paths; static
  check (CI) asserts no `PRIVATE_KEY` literal outside the signer modules.
- **Files:** `dreamdex/src/`, `agent/web3_adapters/ethereum.py`, CI hygiene gate, docs.
- **Acceptance:** static check passes; both relays refuse a live order without
  a prior simulation.

### U32 — Position/leverage cap (tenet D5) → EC tail-hedge + EVM vault leverage

- **Principle.** Ch. 12 (Alpha Homora) is about *leverage amplifying loss*.
  Apply per venue:
  - **EC (D7):** hard portfolio cap so a Crisis-regime tail hedge can't become
    a risk amplifier (`MAX_EC_TAILHEDGE_PCT`).
  - **EVM (D3):** yield-farm leverage capped at `MAX_LEVERAGE_X`, priced against
    liquidation distance (not chased APY).
- **Concrete change:** `defi_agent` D3/D7 enforce the venue-appropriate cap.
- **Files:** `agent/defi_agent.py`, `agent/web3_adapters/ethereum.py`, `tests/test_defi_agent.py`.
- **Acceptance:** tests — EC D7 size ≤ cap; EVM D3 candidate with leverage > cap rejected.

### U33 — Attestation hygiene for EC resolution feeds (tenet D6 + P10)

- **Principle.** Ch. 14 + the P10 merge: cross-chain data is only as trustworthy
  as its attestation. On our data chain, that means only *attested* (P10)
  resolution feeds should drive the D6 trust decision — no raw bridge API.
- **Concrete change:** `defi_agent` D8 accepts an `OracleFeed` only when it has
  a linked `Attestation` node (P10); per-feed cap.
- **Files:** `agent/defi_agent.py` (D8), `graph/schema/defi_extension.cypher`.
- **Acceptance:** doc + cap enforced; un-attested feed → D6 treats as stale.

## 5. Roll-up acceptance & demo delta

| U | One-line acceptance test (stub-based, no testnet needed) | Demo delta |
|---|---|---|
| U1 | Market family resolves 40bp from tape → family excluded + `settlement_variance` logged; τ<0.15 candidate shows haircut | "Settlement monitor" chip + haircut visible on candidates |
| U2 | Force-reverted broadcast leaves state `pending`; replay of same `intentId` doesn't double-submit; claim without confirm stays `unclaimed` | (internal — relay log evidence) |
| U3 | Claims resubmit with gas bump and complete within `CLAIM_GAS_MAX_MULTIPLIER`; `stuckTxs` surfaced | (internal — relay log evidence) |
| U4 | Same preimage recomputes same candidate hash; any edit flips `chain_ok=false` | **Audit tab closes the demo: chain_ok: true across regime→…→claim→credit** |
| U5 | 150bp fill mismatch → `drift_item` on `/status`; uncredited claim stays `uncredited` | Reconciliation chip on status bar |
| U6 | `frozen=true` → zero new candidates, claim sweep lives; `/dreamdex/controls` exact | **Freeze button + Controls pane = "human behind the wheel"** |
| U7 | — | **Narration: tokenized contingent claims; on-chain settlement beats T+2; "continuously attestable"** |
| U8 | `make dreamdex-test` fails on npm audit high; review checklist passes | (internal — dependency hygiene) |
| U9 | Candidate within τ<0.15 shows `code_is_law_discount` | Sizing transparency near finality |
| U10 | Null market set: `off` fires several candidates, `bh` fires ≈0; `n_tested`/`alpha_eff` logged | "Multiplicity" figure on Controls/Audit — anti-data-snooping visible |
| U11 | 350bp raw edge with impact+tail σ no longer fires; ask-depth 2 skipped | Net vs raw edge shown on candidates |
| U12 | `/benchmark` returns bot vs buy-and-hold vs market-neutral with Sharpe/Sortino; param change bumps `param_set_id` | **Benchmark section: "we don't claim alpha, we prove OOS"** |
| U13 | Divergent second feed shrinks belief + flags `tape_divergence` | Dual-feed provenance in Audit events |
| U14 | Fill with < 3 conf reads `pending`; forced fork flips `reorg_detected` | "3/3 conf" + `P(race)≤5.9e-4` on status |
| U15 | Inclusion proof verifies; mutated leaf breaks root membership + `chain_ok=false` | **"Anchored ✓ on-chain" badge + Merkle proof in Audit** |
| U16 | `dreamdex-test` fails hygiene gate on non-viem signing | (internal — key-path hygiene) |
| U17 | RPC failure → new intents halt while `/status` serves; 401/429 enforcement | **System-health line: "safety-over-liveness, here's why we stopped"** |
| U18 | One cycle with both agents enabled produces `dreamdex_candidates` AND `creditgraph_candidates`; each freezes independently | **Two-chain demo: one orchestrator, two specialists** |
| U19 | `/reflection` returns predicted-vs-realized per decision/market after a stub outcome | "What did the plan do?" panel |
| U20 | One GraphRAG query resolves entities from both domains (Borrower + Regime that gates a market) | Cross-domain graph traversal in the demo |
| U21 | Freeze on ⇒ neither pipeline creates/executes; unapproved candidate never reaches `order`/`execute` | "Awaiting human approval" state per candidate |
| U22 | `/risk/report` + `/dreamdex/benchmark` return outcome summaries with timestamps + `param_set_id` | **RaaS/OaaS narration: "decision as a service"** |
| U23 | Deterministic endpoint byte-identical across runs; `creditgraph-test` fails otherwise | (internal — LLM-vs-math contract) |
| U24 | `/freeze` flips `gates.freeze` in BOTH health endpoints; three lamps shown | **Three-lamp safety bar in the header** |

**New files introduced by this companion (all additive to the P9 file list):**
```
agent/dreamdex_attestation.py        # U4/U12/U13/U15 — hash-chain + Merkle attestation, benchmarks
api/routes/dreamdex.py               # + /controls /freeze /unfreeze /attest /attest/{id}
                                     #   /benchmark (U4/U6/U12/U15)
.env.example                         # + ORACLE_DIVERGENCE_BPS, HAIRCUT_TAU, CODE_IS_LAW_DISCOUNT,
                                     #   FILL_PRICE_TOLERANCE_BPS, CLAIM_GAS_BUMP_PCT,
                                     #   CLAIM_GAS_MAX_MULTIPLIER, TX_STUCK_MS (U1/U3/U9)
                                     #   DREAMDEX_MULTICORR, FILL_IMPACT_BPS, MIN_ASK_DEPTH_CONTRACTS,
                                     #   KURTOSIS_VOL_SCALE, TAPE_DIVERGENCE_BPS, OOS_SPLIT,
                                     #   REQUIRED_CONFIRMATIONS, MERKLE_ANCHOR_MODE,
                                     #   RELAY_API_KEY, HEARTBEAT_MS (U10/U11/U12/U13/U14/U15/U17)
DreamDEXPanel.tsx                    # + Audit, Controls, Benchmark, Settlement-monitor,
                                     #   confirmation badges, anchored ✓ (U1/U4/U6/U12/U14/U15)
dreamdex/src/fills.ts + claim.ts     # + confirmation gate, reorg detection (U14)
dreamdex/src/index.ts + middleware   # + X-Relay-Key auth, rate limits, system-health (U17)
```

**Risk-register rows to append to P9 §15:**
- Oracle divergence / settlement variance treated as realized-loss evidence (U1).
- King-of-the-Ether class: never write "claimed/credited" before confirmed tx (`assertTxOk`) (U2/U5).
- Time-critical claims: gas bumping + stuck-tx detection so post-settlement capital isn't stranded (U3).
- Tamper-evidence: attestation chain (`chain_ok`) as the audit substrate (U4).
- Short-address/tx.origin trap: validate every relay-boundary address/param; no raw ABI (U8).
- Code-is-law: a voided/divergent window is a realized loss, not a dispute (U1/U9).
- **Data-snooping: N markets/cycle inflates false edges — multiplicity-corrected gate required (U10).**
- **Fat tails/liquidity: log-normal σ understates crypto kurtosis; shallow books are mirages (U11).**
- **Overfitting/decay: performance only meaningful OOS under a frozen `param_set_id`, vs baselines (U12).**
- **Single-feed bias: one data provider = single-source risk inside the model (U13).**
- **Zero-confirmation race: never credit before `REQUIRED_CONFIRMATIONS`; watch reorgs (longest-chain) (U14).**
- **Anchor trust: unanchored hash chains are internal-only tamper evidence; anchor the Merkle root on-chain/IPFS (U15).**
- **Signing nonce: ECDSA k reuse ⇒ private-key recovery (PS3 class) — RFC-6979 only (U16).**
- **Byzantine/DoS: open endpoint invites abuse; safety-over-liveness + auth/rate limits (U17).**

---

## 6. Tenet → P9-section crosswalk

| P9 § (plan) | Upgrades applied |
|---|---|
| §2 Verified ground truth | U8 (SDK-only rule made binding), U7 (token-click framing) |
| §6 Relay contract | U2 (C-E-I + withdrawal pattern), U3 (nonce/gas), U8 (hard rule) |
| §7 Financial engine | U1 (oracle/settlement risk, haircut), U9 (code_is_law), U10 (multiplicity-corrected gate), U11 (cost/liquidity/tail-aware edge), U13 (two-provider tape) |
| §9 Python side | U4 (attestation ledger), U6 (freeze gate), U12 (`param_set_id` + benchmarks), U15 (Merkle tree), U17 (halt gate) |
| §10 API routes | U4 (`/attest`), U6 (`/controls`,`/freeze`), U12 (`/benchmark`), U14 (`confirmations`/`reorg_detected`), U15 (`/attest` proofs) |
| §11 Frontend | U4 (Audit tab), U6 (Controls/freeze), U1 (settlement chip), U5 (reconciliation chip), U11 (net vs raw edge), U12 (Benchmark), U14 (conf badges), U15 (anchored ✓) |
| §12 Docker & Makefile | U3 (gas env), U8 (`npm audit` in dreamdex-test), U16 (`crypto-hygiene` gate), U17 (relay middleware) |
| §13 Testnet path | U5 (reconciliation), U7 (attestation closing artifact), U14 (confirmation policy), U15 (anchor root on-chain) |
| §14 Demo script | U7 (rewritten arc), U12 ("we don't claim alpha, we prove OOS"), U14 (P(race) number), U17 (safety line) |
| §15 Risk register | rows above (U1–U17) + (U18–U24: agent-planner split, reflection debt, LLM-determinism, human-gate bypass) |

**P10 section crosswalk (CreditGraph merge — see `docs/p10_creditgraph_merge.md`):**

| P10 § (plan) | Upgrades applied |
|---|---|
| §3 Architecture | U18 (one planner, per-chain agents), U20 (shared KG graphRAG) |
| §7 Python port | U23 (determinism contract on quant_engine) |
| §8 Agent | U18 (CreditGraphAgent in registry), U19 (reflection on outcomes), U21 (human-approval gate) |
| §9 API routes | U22 (`/risk/report`), U20 (`/risk/query` cross-domain), U24 (`gates` in health) |
| §10 Frontend | U22 (RaaS framing), U24 (three-lamp bar), U19 (reflection panel) |
| §12 Execution & human gates | U21 (human-in-the-loop), U24 (freeze + audit + determinism) |
| §13 Testnet path | U19 (attested-outcome reflection), U15 (Attestcoin as Merkle anchor) |

---

## 7. TL;DR for a financial engineer reviewing this plan

1. **The blockbuster addition is the continuous attestation ledger (U4).** It converts the bot from "a black box that trades" into "an AI trading agent whose every decision is replayable and tamper-evident" — the exact thesis of *Finance with AI & Blockchain* (Ch. 13) turned into a product capability a judge can *see*.
2. **Settlement risk was the plan's biggest financial blind spot (U1/U9).** EC markets resolve on an *oracle*, and Mastering Ethereum Ch. 11 is blunt: oracle data is untrusted until verified. A financial engineer must price oracle divergence, apply a code-is-law haircut near finality, and treat voids as losses.
3. **Execution correctness was the second (U2/U3/U5).** Checks-Effects-Interactions, the withdrawal pattern, nonce/gas liveness, and trust-but-verify reconciliation are the difference between "demo" and "sound": an honest bot that books profits it can actually prove.
4. **Freeze + parameter attestation (U6) are cheap insurance** and give the demo a human moment ("the professional behind the wheel") that the Finance book's Ch. 12 explicitly argues for.
5. **The data-snooping correction (U10) is what keeps the bot honest.** Testing N windows a cycle is running N hypothesis tests; the Technical Trading paper shows how unprotected rule-mining "confesses" — its own best in-sample BTC rules went *negative* out-of-sample. A Bonferroni/Holm/BH-corrected edge gate, frozen `param_set_id`, and baseline benchmarking (U12) turn "the bot found an edge" into "the bot found an edge that survives multiplicity, costs, fat tails, and out-of-sample decay."
6. **Settlement mechanics are now cryptographic-grade, not just careful (U14/U15).** Credit only after N confirmations (P(race) ≤ 5.9e-4), reorg detection, and a *Merkle-anchored* attestation root with on-chain anchoring — direct applications of Bolfing's confirmation-security and tamper-proof-ledger theory to our audit trail.
7. **Key hygiene is a named, tested requirement (U16).** ECDSA k-reuse recovers private keys (the PS3 hack) — the relay signs exclusively via RFC-6979/viem, verified by a CI hygiene gate, with the three-nonce taxonomy documented.
8. **CAP gives the final philosophical stance (U17): safety over liveness.** When the chain view is uncertain, the bot stops *trading* but never stops *attesting* — and every halt is explained on `/status`. That is the posture a professional would defend.
9. **Agentic structure (U18–U24) turns a two-chain system into *one* auditable organism.** The Raieli & Iuculano ledger (hybrid memory, planning+reflection, graph-before-generation, multi-agent composition, RaaS/OaaS) maps directly onto the merge: one task-planner orchestrator with per-chain specialist agents (U18), a ported GraphRAG over the single shared KG (U20), human-in-the-loop as the product feature (U21), a CI-enforced LLM-vs-math determinism contract (U23), and three visible safety gates (U24).
10. Everything remains **additive**: no file from the P9/P10 file lists is modified except the ones already listed; U10–U24 only add env vars, route fields, relay/agent modules, attestation schema fields, and the `api/creditgraph/` namespaced port.

