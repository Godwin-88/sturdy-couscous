# graphalpha-somnia-relay

Somnia / DreamDEX event-contract relay for GraphAlpha (P9). The **only** component
that touches `SOMNIA_PRIVATE_KEY`, the chain, and `@somnia-chain/markets-sdk`.

Design rules (from `docs/p9_tenets_financial_engineering.md`):

- **U8 / M5** — order construction, price quantization, signing, and ABI encoding
  live exclusively in `src/sdkAdapter.ts` (via `markets-sdk` + viem).
  Zero hand-rolled signing anywhere else; enforced by `npm run crypto-hygiene`.
  *(`@dreamdex-bot-kit/ec-core` — the tick/lot `quantize` helper — is a bot-kit
  workspace package, not on npm; vendor the bot-kit in and add it when wiring the
  live path.)*
- **U2 / M2** — orders and claims are Checks-Effects-Interactions state machines in
  `src/order.ts` / `src/fills.ts`. State changes only after the external call
  returns or reverts; idempotent on `intentId`.
- **U14 / C1** — no zero-confirmation crediting: `REQUIRED_CONFIRMATIONS`
  (default 3). Fills expose `confirmations` and `reorgDetected`.
- **U17 / C5–C6** — safety over liveness: `DRY_RUN=1` by default; `X-Relay-Key`
  auth + `/order` rate limits; `/status` exposes `systemHealth`.
- **U16 / C3** — three-nonce taxonomy: (1) tx account nonce, (2) ECDSA k
  (RFC-6979, deterministic, via viem), (3) `intentId` (idempotency).

## Run (paper/stub — no key required)

```bash
cp .env.example .env        # DREAMDEX_ENABLED=0, DRY_RUN=1
npm install
npm run doctor              # read-only, stub market row
npm run dev                 # :8450 — GET /status /markets /positions /fills
# POST /order requires: curl -H "x-relay-key: $RELAY_API_KEY" ...
```

## Wire the live testnet path (P9 §13)

1. Fund a testnet wallet (SomniaHacks faucet — tUSDC + STT, chain 50312).
2. Set `DREAMDEX_ENABLED=1`, `DREAMDEX_TRADING_MODE=live`, `SOMNIA_PRIVATE_KEY`,
   `VENUE_ID` (seed in `.env.example`; re-read from a live market row if it moves).
3. Implement `liveSnapshot()` and `liveBroadcast()` in `src/sdkAdapter.ts`:
   `loadMarkets({ venueId })` → gate `getMarketOnchain().status === 1` →
   `placeLimit` (tick/lot `quantize` from `ec-core`) → `assertTxOk`.
4. Keep `DRY_RUN=1`; flip to `0` only for the demo clip.

## Verify

```bash
npm test        # typecheck + crypto-hygiene gate
make dreamdex-test   # (repo root) same, plus npm audit for high severity
```