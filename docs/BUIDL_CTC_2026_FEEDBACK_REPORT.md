# Attestcoin Protocol & Creditcoin — Integration Feedback Report

**Submitted to: BUIDL CTC 2026 Fall — "Build For The Real World"**
**Team: GraphAlpha**

This report captures engineering feedback from a **full, working integration**
of the Attestcoin Protocol into a Creditcoin-native lending/credit stack on
testnet — written in the spirit of the hackathon's "feedback report" spirit,
focused entirely on the **Attestcoin Protocol / Creditcoin tooling** that this
submission is judged against.

---

## 1. What worked well

- **The protocol is the right primitive.** Merkle inclusion + continuity
  proofs, verified on-chain by Creditcoin's precompile, with no trusted oracle
  — we built the entire lending collateral story on it and never once felt the
  need for a centralized price feed.
- **`PrecompileChainInfoProvider` + `PrecompileBlockProver` + the
  `ProofBuilder.waitUntilHeightAttested → getProof → verifySingle` flow** are
  clear, composable, and compose exactly the way a credit-risk engineer
  expects (attest first, verify before you trust).
- **Verified live on testnet:** our first real `verifySingle` round-trip
  returned `verified: true` with a Merkle root and continuity proof against
  CC3 header `11689519` in **9.7s** for an already-attested source block.
- **The honest supported-chain constraint** (Ethereum Sepolia chainKey 1 +
  Ethereum Mainnet chainKey 3 today) is documented — respecting it kept our
  scope honest and our demo truthful.

## 2. Gaps & friction (the real cost centers)

1. **Supported-chain asymmetry is under-documented for newcomers.**
   We spent a first pass assuming other EVM L1s might be attestable. The
   "Chains and Environments" page should lead with a one-line
   *"attested source chains today = Sepolia (1), Ethereum mainnet (3)"* — it's
   the single most decision-relevant fact.
2. **RPC endpoint naming is easy to confuse.** `SOURCE_RPC_URL` (source chain)
   vs `CREDITCOIN_RPC_URL` (destination) vs `ATTESTCOIN_PROVER_URL` (proof
   service) are three distinct network endpoints. A single reference table in
   the SDK docs would remove a whole class of misconfiguration.
3. **Proof-payload sensitivity.** `getProof` returns deeply nested payloads
   (merkleProof, continuityProof, txBytes, headerNumber). Storing / forwarding
   them faithfully is straightforward, but the SDK would save real time with a
   shipped **"save this JSON → replay this JSON"** example pair.
4. **Wait-time expectations.** `waitUntilHeightAttested` with a 900s default
   can look like a hang. A short "what you're waiting for / typical latency /
   when you don't need to wait (already-attested blocks)" note would set
   correct expectations.
5. **Balance / free-balance parsing.** `@polkadot/api` returns free balances
   that are hex-encoded on some node versions and decimal on others; our
   integration needed a defensive parser. A documented return-shape for
   `balances` endpoints would remove the need to probe both.
6. **SS58 format constant.** `CREDITCOIN_SS58_FORMAT=42` is implicit across the
   tooling; an explicit constant surfaced in the SDK (not just in chain docs)
   would prevent senders accidentally producing a different address space.

## 3. Suggested priority fixes

| # | Area | Ask | Impact |
|---|---|---|---|
| 1 | Docs | Lead "Chains and Environments" with the supported source-chain list | High |
| 2 | Docs | One `RPC_URL`-overview table (source / destination / prover) | High |
| 3 | SDK | Ship proof save/replay examples | Medium |
| 4 | Docs | Explain `waitUntilHeightAttested` latency expectations | Medium |
| 5 | SDK | Document `balances` return shape (hex vs decimal) | Medium |
| 6 | SDK | Expose `CREDITCOIN_SS58_FORMAT` constant | Low |

---

## 4. What we built on top (evidence)

- `attestation-service` (Fastify) wrapping `@gluwa/usc-sdk` behind `/verify`.
- NAV anchoring (`NAVAnchor.sol` on Sepolia) **attested through the protocol**.
- Credit decisions keyed to **verified evidence only**; verified and unverified
  are never conflated.
- **One real verified attestation on testnet:**

```
evidence_id : ev_d60df323bf25
status      : verified
verifier    : attestcoin-usc-sdk
chain_key   : 1 (Ethereum Sepolia)
header      : 11689519
merkle root : 0xc6391f51f0c77151d740c0e516eddac743f5c5295d6d12d7cbcaa2ac8c1b5487
```

Thanks for shipping a protocol that rewards honest engineering — these notes
come from a team that wanted to use it properly, end-to-end, on Creditcoin.