# web3-relay — EVM DeFi (Ethereum Sepolia, chain 11155111)

P11 Venue B execution relay. **Ported from `stellcasp/`** (sibling repo) — the
adapter pattern (`zkkyc/adapters/ethereum.py`) and the contracts
(`ethereum/contracts/*.sol`) are copied and adapted, not reinvented.

## What it owns

- The only module in GraphAlpha that talks to an **EVM RPC** (Sepolia).
- The only holder of `WEB3_ORACLE_AUTHORITY_PRIVATE_KEY`.
- D1–D4 sector gates (fee−IL−gas edge, spread, funding carry, leverage cap).

## Routes (narrow HTTP contract, :8460)

| Route | Purpose |
|---|---|
| `GET /status` | mode / network / chainId / contracts / gates / system-health |
| `GET /markets` | EVM DeFi snapshot (Uniswap-V3 pool, Aave pool, vault, perp) |
| `POST /order` | place order — sector-gated, `stub_` fill in DRY_RUN |
| `POST /anchor` | publish evidence-chain Merkle root (U26; stub in DRY_RUN) |
| `GET /positions` / `GET /fills` | ledger views with U14 confirmations |

## Ported from stellcasp

- `ethereum/contracts/{ZKPassport,UltraVerifier,UltraHonkVerifier}.sol` →
  **`contracts/`** (Foundry, Sepolia deploy via `scripts/deploy.sh`)
- `zkkyc/adapters/ethereum.py` (web3.py) → **`src/evmAdapter.ts`** (viem) —
  same interface, viem handles RFC-6979 nonce discipline (U16/C3)

## Run

```bash
npm install
npm run typecheck && npm run crypto-hygiene   # CI gate
npm run doctor                                 # read-only sanity
npm run dev                                    # :8460
```

## Wire the live path (Sepolia testnet funded key)

1. `contracts/`, `foundry.toml`, `scripts/deploy.sh` — deploy ZKPassport +
   UltraHonkVerifier to Sepolia:
   ```bash
   bash scripts/deploy.sh sepolia
   ```
2. Set `WEB3_ENABLED=1`, `WEB3_TRADING_MODE=live`, fill
   `WEB3_PASSPORT_CONTRACT` / `WEB3_VERIFIER_CONTRACT`.
3. Implement `liveSnapshot()` / `liveBroadcast()` in `src/evmAdapter.ts`
   (viem `createPublicClient` / `createWalletClient` — TODO markers in place).
4. `npm run doctor` — confirm live rows, then flip `DRY_RUN=0` for the demo clip.

## Contract hygiene

- DRY_RUN defaults to 1 — nothing broadcasts until explicitly flipped (U17).
- All intent staged before broadcast (U2/M2), fills only credited after
  confirmations + balance move (U14/M6).