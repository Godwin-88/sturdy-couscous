# DreamDEX × Somnia + Attestcoin — SDK & Documentation Feedback Report

**Submitted to: Somnia × DreamDEX Event Contracts Hackathon**
**Team: GraphAlpha**

This is a good-faith engineering feedback report on the **DreamDEX Bot Kit /
`@somnia-chain/markets-sdk`** and the **Attestcoin Protocol docs / `@gluwa/usc-sdk`**,
written from direct integration experience on testnet (chain 50312 / CC3 testnet)
during the hackathon. It follows the spirit of the hackathon's optional
"feedback report regarding SDK and documentation" deliverable.

---

## 1. DreamDEX Bot Kit / `@somnia-chain/markets-sdk`

### 1.1 What worked well
- `loadMarkets` + per-market live update streams are solid; reading the order
  book and gating on on-chain market status worked reliably once wired.
- The **staging venue story** (a venue seeded with 5-min series markets) is a
  genuinely useful way to demonstrate the full lifecycle without waiting hours.
- SIWE / wallet-based auth is the right call — no API keys to leak.

### 1.2 Gaps & friction (things that cost real time)

1. **No Python SDK; TypeScript-only surface.**
   The bot-kit is TS/Node (`@somnia-chain/markets-sdk` + `@dreamdex-bot-kit/ec-core`).
   Teams with Python-only stacks must budget a Node relay service just to talk
   to Event Contracts. A thin REST surface (or at least a documented,
   maintained REST example for EC) would remove a whole integration class.
2. **`ec-core` is not published to npm** (as of writing). The quantize/tick/lot
   helpers we needed for safe `placeLimit` pricing had to be vendored from the
   bot-kit into the repo. Please publish `@dreamdex-bot-kit/ec-core` (or a
   stable code path) to a package registry.
3. **`/v0` path prefix trap.** The HTTP API silently returns 404 on
   `/markets` without the `/v0` prefix, but the docs were not consistently
   explicit that every path requires `/v0`. This burned debugging time.
4. **`VENUE_ID` drift.** The venue id we used migrated between deployments;
   hard-coding it (even from docs) broke on-chain gating until re-discovered at
   runtime. A resolved "default venueId" returned by an SDK/home endpoint (or a
   `loadMarkets()` that reports the venue's own id) would prevent this class of
   bug.
5. **Decimal / grid pitfalls.** The 18-decimal test token grid vs. 6-decimal
   familiar USDC adapters, plus the float-→grid quantization trap, are
   documented only implicitly (in bot-kit `ec-core`). A prominent "Pricing
   grid & quantization" page (18-decimals, tick×lot, never pass floats to
   `createOrder`) would be the single highest-value doc addition.
6. **Testnet token decimals** (tUSDC 6-decimals vs. the 18-decimal venue grid)
   are easy to conflate; a per-market "decimals" field in market snapshots
   would remove ambiguity.

### 1.3 Suggested priority fixes
| # | Area | Ask | Impact |
|---|---|---|---|
---

## 2. Attestcoin Protocol / `@gluwa/usc-sdk`

### 2.1 What worked well
- **The protocol itself is elegant**: Merkle inclusion + continuity proofs,
  verified on-chain by CC3's precompile, with no oracle. Our first real
  `verifySingle` round-trip resolved in ~10s against an 18h-old source block.
- `PrecompileChainInfoProvider` (supported chains), `PrecompileBlockProver`,
  and the `ProofBuilder.waitUntilHeightAttested → getProof → verifySingle` flow
  are clear and composable.
- The honest constraint that **only Ethereum Sepolia (chainKey 1) and Ethereum
  Mainnet (chainKey 3) are attested today** is documented — we respect and
  build around it.

### 2.2 Gaps & friction

1. **Supported-chain asymmetry is under-documented for newcomers.** We spent
   the first pass assuming other EVM L1s might be attestable; the "Chains and
   Environments" page could lead with a one-line "attested source chains = x, y"
   list (it exists; make it the first callout).
2. **RPC endpoint naming is easy to confuse.** `SOURCE_RPC_URL` (source chain)
   vs `CREDITCOIN_RPC_URL` (destination) vs `ATTESTCOIN_PROVER_URL` (proof
   service) are three distinct network endpoints; a single reference table
   (which URL for what) in the SDK docs would prevent misconfiguration.
3. **Proof payload sensitivity.** `getProof` returns complex nested objects
   (merkleProof, continuityProof, txBytes, headerNumber). Storing/forwarding
   them faithfully is fine, but the SDK could ship dedicated "save this JSON,
   replay this JSON" examples — we had to reverse-engineer the shape.
4. **Wait-times.** `waitUntilHeightAttested` default-to-900s can look like a
   hang. A "what you're waiting for / typical latency / when you don't need
   to wait (already-attested blocks)" note would set expectations.

### 2.3 Suggested priority fixes
| # | Area | Ask | Impact |
|---|---|---|---|
| 1 | Docs | Lead "Chains and Environments" with the supported source-chain list | High |
| 2 | Docs | One `RPC_URL`-overview table (source / destination / prover) | High |
| 3 | SDK | Ship proof save/replay examples | Medium |
| 4 | Docs | Explain `waitUntilHeightAttested` latency expectations | Medium |

---

## 3. What we built on top (brief)

- `attestation-service` (Fastify) wrapping `@gluwa/usc-sdk` behind `/verify`.
- NAV anchoring (`NAVAnchor.sol` on Sepolia) attested through the protocol.
- One **real verified attestation** on testnet:

```
evidence_id : ev_d60df323bf25
status      : verified
verifier    : attestcoin-usc-sdk
chain_key   : 1 (Ethereum Sepolia)
header      : 11689519
merkle root : 0xc6391f51f0c77151d740c0e516eddac743f5c5295d6d12d7cbcaa2ac8c1b5487
```

Thanks for shipping a protocol that rewards honest engineering — these are
notes from a team that wanted to use it properly.

### 1.3 Suggested priority fixes (DreamDEX Bot Kit)
| # | Area | Ask | Impact |
|---|---|---|---|
| 1 | npm | Publish `@dreamdex-bot-kit/ec-core` (or stable equivalent) | High — removes vendoring |
| 2 | REST | Document (or add) a minimal EC REST path | High — Python stacks |
| 3 | Docs | "Pricing grid & quantization" page + per-market decimals | High — prevents pricing bugs |
| 4 | SDK | `loadMarkets()` reports venueId | Medium — kills VENUE_ID drift |
| 5 | Docs | Global note: every HTTP path needs `/v0` | Medium — saves hours |
| 6 | Testnet | Document the 5-min staging-venue lifecycle end-to-end | Medium — demo velocity |