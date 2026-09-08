# P9 — DreamDEX × Event Contracts Integration

**Project:** GraphAlpha · **Phase:** P9 · **Status:** Plan (ready for implementation)
**Hackathon:** Somnia × DreamDEX Event Contracts Hackathon — https://dorahacks.io/hackathon/event-contracts
**Design principle:** *additive only* — every new file is a new file; exactly **three** surgical edits to existing files; nothing deleted or restructured.

---

## 1. Executive Summary

GraphAlpha — a knowledge-graph-grounded multi-agent trading system — extends to **DreamDEX Event Contracts**: binary Up/Down prediction markets on BTC/ETH price windows traded on Somnia's on-chain CLOB.

- A new **Node/TypeScript relay** (`dreamdex/`) is the *only* component that touches Somnia and the `@somnia-chain/markets-sdk`.
- A new Python sub-agent **`DreamDEXAgent`** maps each live EC window to the **existing** KG crypto strategy engine (`agent/crypto_signal.py`), prices the window as a conditional probability, extracts an **edge vs. the live order book**, sizes with **binary Kelly**, and routes execution intent through the relay (dry-run → testnet).
- New EventContract nodes/edges extend the Neo4j knowledge graph (additive, loaded after `master.cypher`).
- New API routes + a new dashboard panel surface live candidates, edge, and the claim/settlement lifecycle.

**Submission driver:** the hackathon mandates a *working prototype on testnet* and weights **Technical Implementation (25%)** on "meaningful use of DreamDEX APIs and/or SDKs" — so a real (testnet) order through the SDK is part of the demo, not optional.

---

## 2. Verified Ground Truth (read before building)

Facts confirmed against `docs.dreamdex.io`, the `somnia-chain/dreamdex-bot-kit`, and the `IronicDeGawd/ec-dreamdex-hackathon-template`. These correct the mistakes that plague a naïve integration:

1. **HTTP API is spot-only — it has no event-contract endpoints.** EC is sdk-only via `@somnia-chain/markets-sdk` (TypeScript). `GET {base}/markets` returns *spot* pairs, NOT EC markets. ⚠️ The earlier draft built the whole adapter on this wrong REST call.
2. **Base URL needs the `/v0` prefix or you get 404.** Testnet: `https://stg.api.dreamdex.io/v0`; mainnet: `https://api.dreamdex.io/v0`. RPC — testnet `https://dream-rpc.somnia.network` (chain **50312**), mainnet `5031`.
3. **No "SDK key".** Trading is **wallet-based** (private key). "Bot Builder" ≈ the Bot Kit's `npm run quickstart` that writes a `.env`. The enable flag must be real (`SOMNIA_PRIVATE_KEY` + `DREAMDEX_ENABLED`), not a fabricated `DREAMDEX_SDK_KEY`.
4. **Markets are Up/Down** on a single order book; Down price = 1 − Up. Prices are probabilities in **millionths** (`900000` = 0.90). No `YES`/`NO`, no `title`/`related_ticker`.
5. **Markets die on schedule and respawn.** Market *status* is `Listed→Trading→Locked→Resolved|Voided` (0–5). Only `status == 1` accepts orders. A settled market leaves the live list — **winnings are claimed, not received** (`maybeClaim` sweep; scan `Finalized` via `listBinaryMarkets`). Key by `marketId` or `symbol`, never by pool address.
6. **Gate on on-chain status, not the indexer** (indexer lags seconds). **Never pass float prices to `createOrder`** on the 18-decimal venue (tick-grid revert `InvalidPrice`) — use `placeLimit`/`quantize` from the bot-kit's `ec-core` (integer tick/lot conversion).
7. Reverted writes don't throw in-sdk (`assertTxOk`); a taker is charged the **fill price** not the offered price; order **expiry is mandatory** (set just past the requote interval).

### 2.1 Existing repo surface to reuse (do not reinvent)

- `agent/crypto_signal.py` — KG crypto strategy engine (`suggest_crypto`) + `LENS_META` (`defensive` → max 5% NAV) + `_tape(pair)` OHLCV loader. This is the real "signal → belief" source.
- `api/routes/crypto.py` — the two-phase `proposal_token` preview/confirm gate (10-min TTL) and `MIN_CRYPTO_NOTIONAL_USD=10` conventions to mirror in the DreamDEX routes/panel.
- `agent/alpaca_data.py` — `provider` abstraction that already resolves `BTC-USD → BTC/USD`.
- `docker-compose.yml` — `graph-loader` service cats `/graph/master.cypher` into `cypher-shell` (this is **the** loader; there is no `docker/neo4j/init/`). `master.cypher` lives at the repo **root** (588 KB), not under `graph/`.
- `agent/orchestrator.py` — agents are imported bare-module style; risk is delegated to the C++ risk-engine via Redis in normal (non-shadow) mode. Let's pipeline new EC candidates with *their own* Redis keys + routes.
- `api/main.py` — flat `app.include_router(...)` list → one import + one line per router.
- Frontend — `frontend/src/hooks/usePolling.ts`, `CryptoPanel`, and `OrderTicketModal` two-phase confirm pattern to mirror.
- Makefile — `up`, `logs-agent`, `load-graph`, `verify-graph` targets — append, don't touch.

---

## 3. Architecture

```
                orchestrator.py (+1 line)
                      │  every cycle
                 dreamdex_agent.py  (NEW)
        KG/regime → suggest_crypto() → belief
        window-conditional P_up → edge vs ask → binary Kelly → intents
                 │                     │
                 ▼                     │  Redis (dreamdex:*)
       Neo4j: EventContract nodes     ├─ markets / candidates / positions / fills
       + edges (additive extension)   └──▶ API routes (dreamdex.py)  ─▶ DreamDEXPanel.tsx
                 ▲                          │
                 └──────────────────────────┘ (HTTP :8450) ─┐
                                          ┌──────────────────────────────────────┐
                                          │  somnia-relay (NEW, Node/TS)         │
                                          │  @somnia-chain/markets-sdk           │
                                          │  discover · book · placeLimit · claim│
                                          │  owns PRIVATE_KEY · DRY_RUN default  │
                                          └──────────────────────────────────────┘
```

**Ownership rules**
- Private key + on-chain signing live **only** in the relay. Python never imports web3 or the key.
- The relay never imports GraphAlpha; GraphAlpha talks to it over a narrow HTTP contract.
- The agent never signs; it emits *candidates*; the relay owns execution (dry-run by default).

---

## 4. Files: new + allowed edits (definitive)

**New files**
```
dreamdex/
  package.json           # @somnia-chain/markets-sdk@^0.28.1, viem, tsx, dotenv (Starter parity)
  tsconfig.json
  Dockerfile
  src/index.ts           # boot, env, DRY_RUN flag, Express server on :8450
  src/markets.ts         # loadMarkets snapshot, gate on-chain status, VENUE_ID re-read
  src/order.ts           # placeLimit (tick/lot quantize), IOC/resting, expiry headroom
  src/claim.ts           # settledMarkets()/maybeClaim sweep (AUTO_CLAIM)
  src/fills.ts           # positions/fills tracking + audit log
  src/doctor.ts          # read-only: wallet + balances + per-market book
  .env.example
agent/
  dreamdex_adapter.py    # httpx client to the relay (mirror crypto tape fallback style)
  dreamdex_agent.py      # KG/regime → binary candidate engine (the novelty)
api/routes/
  dreamdex.py            # 6 read-only GETs
frontend/src/components/
  DreamDEXPanel.tsx      # tabs: Markets (#edge) / Candidates / Positions & Fills
graph/schema/
  dreamdex_extension.cypher   # additive node types + relationships
.env.example             # 9 appended vars (untouched existing)
docker-compose.yml       # + somnia-relay (profiles:[dreamdex]) + graph-loader cmd edit
Makefile                 # + 3 appended targets
```

**Edits to existing files — only these 3:**
1. `agent/orchestrator.py` — `from dreamdex_agent import DreamDEXAgent`; `self.dreamdex_agent = DreamDEXAgent()`; in `run_cycle()` after `kg_signals`, one `try/except` call `await self.dreamdex_agent.run(regime=regime)` (non-fatal). No signature changes, no RiskAgent edits.
2. `docker-compose.yml` — `graph-loader` entrypoint: `cat /graph/master.cypher /graph/dreamdex_extension.cypher | cypher-shell --fail-at-end …` (+ mount `./graph/schema/dreamdex_extension.cypher` as r/o); and append the `somnia-relay` service. Nothing else changes.
3. `Makefile` — append `dreamdex-up`, `dreamdex-logs`, `dreamdex-test` targets (no existing line touched).

Everything else is a new file. Nothing deleted, nothing restructured.

---

## 5. Environment variables (`.env.example` append)

```env
# ── DreamDEX / Somnia Event Contracts ────────────────────────────────
DREAMDEX_ENABLED=0            # 0 disables the whole feature (agent self-disables)
DREAMDEX_TRADING_MODE=paper  # paper | live   (live = relay sends testnet-chain orders)
DREAMDEX_NETWORK=testnet      # testnet (50312) | mainnet (5031)
VENUE_ID=0x679795a0195a1b76cdebb7c51d74e058aee92919b8c3389af86ef24535e8a28c   # testnet seed; moves
SOMNIA_RPC_URL=https://dream-rpc.somnia.network
SOMNIA_PRIVATE_KEY=          # BOT-ONLY key → relay container; never commit; DRY_RUN=1 until demo
SOMNIA_WALLET_ADDRESS=       # derived from the SAME key
AUTO_CLAIM=1
AUTO_CLAIM_INTERVAL_MS=600000
DRY_RUN=1                     # relay logs all would-be orders until explicitly flipped
DREAMDEX_MIN_EDGE_PCT=3      # min (%) edge vs ask before a candidate fires
```

Empty (or `DREAMDEX_ENABLED=0`): the adapter returns `[]`, the agent returns `[]`, GraphAlpha boots identically — the self-disable behavior, without inventing a key that doesn't exist.

**Bot key hygiene:** use an **operator/session key** (bot-kit `scripts/operator-setup.ts`) so the hot key can trade but cannot withdraw; keep `SOMNIA_PRIVATE_KEY` out of the API/agent container entirely (relay container only).

---

## 6. Relay HTTP contract (`:8450`)

| Endpoint | Returns | Used by |
|---|---|---|
| `GET /status` | `{mode, network, venueId, wallet, dryRun, lastSnapshotAt, claimable}` | status route / panel |
| `GET /markets` | `[{marketId, symbol, asset:"BTC", strike, intervalSec, closesAt, status, up:{bid,ask,last}, down:{bid,ask,last}}]` | agent + panel |
| `POST /order` | `{ok, orderId, symbol, side, qtyContracts, estPrice, dryRun, intent}` | DreamDEXAgent |
| `GET /positions` | open positions w/ cost + claimable | positions panel |
| `GET /fills` | audit fills log | fills panel |
| `POST /claim` | `{ok, claimed, txHashes}` | claim button |

Reads come from the SDK's live market table inside the relay — it **gates every write on `getMarketOnchain().status === 1`** and reads fresh book prices each cycle (the indexer lags; the chain is the source of truth per §2).

---

## 7. Financial engine (the part judges will probe)

Replaces the naïve "score>0 → BUY YES @ 0.5" with a real prediction-market edge pipeline:

1. **Map window → existing strategy.** EC windows are Up/Down on **BTC** (`BTC-USD → BTC/USD`) / **ETH**. For each `status==1` window: `pair = asset/USD`, call **`suggest_crypto(pair, lens="defensive", regime=…)`** from `agent/crypto_signal.py` → `{strategy, signalScore, riskWeight, maxLossPctNav}`. No new strategy engine — this is the KG gate, reused.
2. **Window → conditional probability.** `P_up = P(S_T ≥ strike | S_0, t, σ)` with a log-normal lens: `σ = realized_vol(pair, 21d)·√253` from `_tape(pair)`, then `P_up = N( (ln(S_0/strike) + (μ − ½σ²)(T−t)) / (σ√(T−t)) )`, `τ = remaining / intervalSec`. Both inputs already fetched in the existing code.
3. **Edge vs. live book — the transaction.** `edge_pct = (P_up − ask_up) / ask_up` (and the Down mirror `(1−P_up − ask_down)/ask_down`) from the relay's fresh book. **Only** generate a candidate when `|edge_pct| ≥ DREAMDEX_MIN_EDGE_PCT` (default 3%). Buy `up` when `P_up > ask_up`; buy `down` when `1−P_up > ask_down`. This converts "we like momentum" into "this window is mispriced vs. our KG belief."
4. **Binary Kelly sizing.** `f* = max(0, (p − price) / (1 − price))` — binary Kelly because the payoff is 0/1. `budget_usdc = min(kelly_small · half_kelly_scale · max_loss_pct_nav · NAV, portfolio_cap_pct · NAV)` with `half_kelly_scale = 0.5`, `max_loss_pct_nav = 0.05` from `LENS_META["defensive"]`, `portfolio_cap_pct = 0.02` (new env `DREAMDEX_MAX_PORTFOLIO_PCT`, default 2%). Floor ≥ 1 lot (lot-quantize), cap ≤ ask liquidity.
5. **Lifecycle is part of the model.** Each cycle the agent calls `/claim` when a tracked window resolves (`claimable` > 0), and the relay sweeps `Finalized` markets (`listBinaryMarkets({venueId, status: "Finalized"})`), then redeems — turning "a bot that never settles" into a closed loop the demo can show (wallet credit + tx hash).
6. **Parallel pipeline — no change to existing Kelly/VaR.** EC candidates use their own Redis keys (`dreamdex:*`), own API routes, own panel. Nothing in the existing equity/crypto flow is touched.

**Candidate shape (Redis `dreamdex:candidates`):**
```json
{ "marketId": "0x…", "symbol": "BTC-0-12AUG26-1600/USDso#YES", "base": "BTC",
  "side": "up", "estimate": 0.62, "ask": 0.58, "edgePct": 6.9,
  "fstar": 0.095, "qtyContracts": 40, "sizeUsdc": 25,
  "regime": "Trending", "strategy": "Crypto Trend Following", "signalScore": 0.71 }
```
Notional basis: 1 complete set = 1 USDso at mint; priced exposure = qty × ask.

---

## 8. KG extension (`graph/schema/dreamdex_extension.cypher`) — additive

Loaded **after** `master.cypher` (graph-loader cats both files), all statements idempotent (`MERGE` / `CREATE CONSTRAINT IF NOT EXISTS`); the existing graph is untouched.

```cypher
// EventContract / EventWindow types
CREATE CONSTRAINT IF NOT EXISTS FOR (w:EventWindow) REQUIRE w.symbol IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (o:Outcome)     REQUIRE o.outcome_id IS UNIQUE;

// Market category taxonomy (appended after master.cypher content)
MERGE (:EventCategory {name: "Crypto",    slug: "crypto"});
MERGE (:EventCategory {name: "Sports",    slug: "sports"});
MERGE (:EventCategory {name: "Politics",  slug: "politics"});
MERGE (:EventCategory {name: "Economics", slug: "economics"});

// Relationship types used at runtime (read-only additions):
//   (EventWindow)-[:BELONGS_TO]->(EventCategory)
//   (EventWindow)-[:ACTIVATES_IN]->(Regime)
//   (EventWindow)-[:CORRELATED_WITH]->(Ticker {ticker:"BTC-USD"})
//   (EventWindow)-[:SCORED_BY]->(Strategy)        <- runtime, from dreamdex_agent
//   (Outcome)-[:RESOLVES]->(EventWindow)
```

**Runtime upsert** (in `dreamdex_agent`) uses the exact `MERGE`/`SET`/`MATCH` idiom already in the repo — non-blocking, `try/except` + `logger.warning` fallback, so a graph failure never breaks the cycle.

**Demo story this powers:** RegimePanel shows "Bear Trend" → KG Explorer shows `EventWindow`(BTC) `CORRELATED_WITH` existing `Ticker:BTC-USD` and `ACTIVATES_IN` the active regime → DreamDEX panel shows the priced edge. That visible causality is the "knowledge-graph-gated prediction market" differentiator.

---

## 9. Python side: `dreamdex_adapter.py` + `dreamdex_agent.py`

**`dreamdex_adapter.py`** — httpx client to the relay, mirroring the existing fallback conventions in `crypto_signal.py`/`alpaca_data.py` (provider-style, `try/except` + `logger.warning`, empty list on failure). No web3, no private key:

```python
class DreamDEXAdapter:
    def __init__(self):
        self.base  = os.getenv("DREAMDEX_RELAY_URL", "http://somnia-relay:8450")
        self.mode  = os.getenv("DREAMDEX_TRADING_MODE", "paper")
        self.enabled = os.getenv("DREAMDEX_ENABLED", "0") == "1"

    def get_status(self)   -> dict:   ...
    def get_markets(self)  -> list[dict]: ...   # relay snapshot, []; live book prices incl.
    def place_order(self, market_id, side, qty_contracts) -> dict: ...  # POST /order
    def get_positions(self)-> list[dict]: ...
    def get_fills(self)    -> list[dict]: ...
    def claim(self)        -> dict:   ...      # POST /claim
```

**`dreamdex_agent.py`** — the scheme of the cycle (loop body pseudo-code):

```python
async def run(self, regime: str) -> list[dict]:
    if not self.adapter.enabled: return []
    markets = self.adapter.get_markets()               # status==1 only
    for m in markets:
        belief = suggest_crypto(pair_for(m), lens="defensive", regime=regime)
        p_up   = window_probability(m, tape(pair_for(m)))   # §7.2 log-normal lens
        if side_edge := edge_candidate(m, p_up, belief):    # §7.3, ABS >= MIN_EDGE_PCT
            cand = size_candidate(side_edge, belief, nav)   # §7.4 binary Kelly
            candidates.append(cand | {"estimate": p_up or 1-p_up,
                                      "ask": …, "edgePct": …, "strategy": belief.strategy})
    self._cache_redis(candidates); self._upsert_kg(candidates); return candidates
```

Key design points:
- **Disabled by default** (`DREAMDEX_ENABLED=0`): early return `[]`, cycle cost ≈ 0.
- **Best-effort only**: every external call (relay, suggest_crypto, Redis, Neo4j) wrapped; a failure logs and continues — the orchestrator loop never degrades.
- **Redis keys** (5-min TTL): `dreamdex:markets`, `dreamdex:candidates`, `dreamdex:positions`, `dreamdex:fills`, `dreamdex:status`.
- **No order is ever placed from Python.** `place_order` is only invoked by the human-in-the-loop two-phase gate in the API (mirroring `/crypto/preview`), which in turn only passes intents to the relay after confirmation.

---

## 10. API routes (`api/routes/dreamdex.py`) — read-only + two-phase confirm

Registered in `api/main.py` with exactly one `app.include_router(dreamdex_router)` line. All reads come from Redis (`dreamdex:*`), mirroring `routes/signals.py`/`routes/crypto.py` patterns:

| Route | Verb | Purpose |
|---|---|---|
| `/dreamdex/status` | GET | adapter/relay status from Redis `dreamdex:status` (mode, wallet-masked, dryRun) |
| `/dreamdex/markets` | GET | live windows (relay snapshot cached by agent, 5-min TTL) |
| `/dreamdex/candidates` | GET | this cycle's sized candidates (Redis) |
| `/dreamdex/positions` | GET | open EC positions + claimable |
| `/dreamdex/fills` | GET | fills audit log |
| `/dreamdex/claim` | POST | calls relay `POST /claim` (human-gated button, not automatic) |

**Two-phase gate (parity with `/crypto/preview`):** `POST /dreamdex/preview` builds a `proposal_token` (10-min TTL) with the intent; `POST /dreamdex/confirm` calls `adapter.place_order(...)` with that token. This keeps the existing human-in-the-loop guarantee that GraphAlpha never auto-fires EC orders.

---

## 11. Frontend (`DreamDEXPanel.tsx`) — new component only

New sidebar entry under a **"PREDICTION MARKETS"** section in `App.tsx` (only existing-file edit in the frontend). Follows the existing dark design system (`border-gray-700`, `indigo-600` tabs, `usePolling(30s)` from `frontend/src/hooks/usePolling.ts`).

Three tabs:
- **Markets** — status chip (`● Trading`), asset/strike/window close, and per market an **edge %** callout vs. the live book + `estimate vs ask` mini-bar (mirrors the `CryptoCard` layout).
- **Candidates** — the sizing breakdown table: estimate / ask / edge% / binary-Kelly f* / contracts→USDC, with a **Preview** button that opens the existing two-phase OrderTicketModal shape (reuse `proposal_token` flow from `/crypto/preview`).
- **Positions & Fills** — open positions with PnL basis, a **Claim** button (`/dreamdex/claim`), and a timestamped fill log (testnet tx hashes link-out).

Data comes only from `/dreamdex/*` — no new WebSocket needed for v1 (30s poll matches existing panels).

---

## 12. Docker & Makefile (append-only)

`docker-compose.yml` — one new service block appended (flagged `profiles: ["dreamdex"]`, so it is **invisible** to the base `make up` — same pattern as the existing `backtest`/`ibkr`/`monitoring` services):

```yaml
  # ── DreamDEX / Somnia event-contract relay (optional — profile: dreamdex) ──
  somnia-relay:
    build: { context: ./dreamdex, dockerfile: Dockerfile }
    container_name: graphalpha-somnia-relay
    env_file: .env
    environment:
      SOMNIA_PRIVATE_KEY: ${SOMNIA_PRIVATE_KEY}
      SOMNIA_RPC_URL: ${SOMNIA_RPC_URL}
      DREAMDEX_NETWORK: ${DREAMDEX_NETWORK:-testnet}
      VENUE_ID: ${VENUE_ID}
      DREAMDEX_TRADING_MODE: ${DREAMDEX_TRADING_MODE:-paper}
      DRY_RUN: ${DRY_RUN:-1}
      AUTO_CLAIM: ${AUTO_CLAIM:-1}
    ports: ["8450:8450"]
    profiles: ["dreamdex"]
```

Plus the `graph-loader` block change (its one-line command edit):

```yaml
    volumes:
      - ./graph/schema/dreamdex_extension.cypher:/graph/dreamdex_extension.cypher:ro
    entrypoint: ["/bin/sh", "-c",
      "cat /graph/master.cypher /graph/dreamdex_extension.cypher | cypher-shell --fail-at-end -u \"${NEO4J_USER:-neo4j}\" -p \"${NEO4J_PASSWORD:-graphalpha}\" -a bolt://neo4j:7687 && echo 'Graph loaded successfully'"]
```

`Makefile` — append only:

```make
.PHONY: dreamdex-up dreamdex-logs dreamdex-test

dreamdex-up:    ## Start the DreamDEX relay (testnet) alongside GraphAlpha
	docker compose --profile dreamdex up -d --build somnia-relay

dreamdex-logs:
	docker compose logs -f somnia-relay

dreamdex-test:
	cd dreamdex && npm run doctor
```

---

## 13. Testnet path (submission requirement — "working prototype on testnet")

1. **Get testnet funds** — tUSDC (collateral) + STT (gas). Official faucet: **SomniaHacks dev group** → https://t.me/+XHq0F0JXMyhmMzM0 (specifically the **faucet topic**).
2. **Wire the relay env** — `dreamdex/.env`: `DREAMDEX_NETWORK=testnet`, `SOMNIA_RPC_URL=https://dream-rpc.somnia.network`, `VENUE_ID` (testnet seed §5), `SOMNIA_PRIVATE_KEY` from a testnet wallet (or an **operator/session key**), `DRY_RUN=1`.
3. **Sanity check (read-only):** `npx tsx src/doctor.ts` — prints wallet, balances, and the live order book for every market. No transactions, no risk. (Parity with bot-kit `scripts/doctor.ts`.)
4. **Prove the lifecycle once** — bot-kit `scripts/one-ioc.ts` (or the relay's own smoke test): mint a complete set → place an IOC order → cancel → (next window) claim. Confirm a **real testnet tx hash** appears on the explorer.
5. **Demo flip:** with `DRY_RUN=1` the relay logs intent; flip `DRY_RUN=0` **only during the demo clip** (small size, short-window market) to show a live testnet fill + settlement + claim.

**Why testnet-only is safe:** chain **50312** is the Shannon testnet; the private key holds only faucet testnet tokens (no mainnet value). This satisfies "working prototype on testnet" while keeping `DREAMDEX_TRADING_MODE=paper` as the shipped default.

---

## 14. Judging scorecard (weights verified from hackathon text)

| Criterion | Weight | GraphAlpha without P9 | GraphAlpha with P9 |
|---|---|---|---|
| Innovation & Originality | 20% | N/A (different domain) | KG-gated prediction-market agent: EC windows are priced by the same graph that prices BTC spot — no other entry connects a financial KG to EC trades |
| Technical Implementation | 25% | No DreamDEX integration | Real `@somnia-chain/markets-sdk` relay on testnet + agent + Neo4j EC nodes + routes + panel; two-phase human gate |
| UX & Design | 20% | Good dashboard | Same design system + new DreamDEX panel with edge/claims legibility; zero rebuilt components |
| Business & Ecosystem Impact | 20% | Zero | An autonomous agent that generates EC volume directly; claim/redeem closes the loop (sticky PnL) |
| Presentation & Demo | 15% | N/A | 90-sec scriptated cycle incl. real testnet fill + settlement + claim (§17) |

**Demo script (90 seconds):**
1. `make up` boots; panel shows RegimePanel classifying the market.
2. KG Explorer cut — `EventWindow`(BTC) `CORRELATED_WITH` the live `Ticker:BTC-USD` node, `ACTIVATES_IN` the current regime.
3. DreamDEXPanel **Markets** — live testnet windows with edge% vs the book.
4. **Candidates** — one candidate's full sizing path (estimate → edge → binary-Kelly → USDC).
5. Relay log — dry-run intent → **flip `DRY_RUN=0`** → real testnet fill (tx hash).
6. Window resolves → **Claim** → wallet credit.

---

## 15. Risk register

| Risk | Mitigation |
|---|---|
| SDK is TypeScript-only; Python stack must not sign | Narrow Node relay owns the key + SDK; Python talks HTTP only. Relay is ~400 LOC, dockerized, profile-gated |
| `VENUE_ID` moves + differs per network | `.env` seed + relay re-reads venueId from a live market row at runtime; doctor.ts surfaces drift |
| Float price on 18-decimal venue reverts (`InvalidPrice`) | Relay uses `placeLimit`/`quantize` (integer tick/lot conversion from bot-kit `ec-core`), never raw float `createOrder` |
| Operationally critical: winnings are not auto-credited | `AUTO_CLAIM` sweep (every 10 min, same loop as trading so nonces serialize); `ec-settlement` one-shot fallback |
| Markets disappear/respawn; key by pool address breaks | Key by `marketId`/`symbol`; `loadMarkets` snapshot refreshed each cycle; gate on on-chain `status==1` |
| Edge model is a simple log-normal lens, not a profit promise | Positioned as a *lens*: the story is the KG+regime gate and margin size, not alpha claims |
| Nonce conflicts (two senders, one key) | One bot per key; claim runs inside the trading loop; operator/session key limits blast radius |
| Testnet window churn / short expiries | Scale order expiry headroom to a fraction of the series interval (bot-kit guidance) |

---

## 16. Build & test sequence

```bash
# 1) Append env (`.env`), keep DREAMDEX_ENABLED=0 during development
cat >> .env.example <<'EOF'
DREAMDEX_ENABLED=0
DREAMDEX_TRADING_MODE=paper
DREAMDEX_NETWORK=testnet
VENUE_ID=0x679795a0195a1b76cdebb7c51d74e058aee92919b8c3389af86ef24535e8a28c
SOMNIA_RPC_URL=https://dream-rpc.somnia.network
SOMNIA_PRIVATE_KEY=
SOMNIA_WALLET_ADDRESS=
AUTO_CLAIM=1
DRY_RUN=1
DREAMDEX_MIN_EDGE_PCT=3
EOF

# 2) Relay, standalone first (no GraphAlpha running)
cd dreamdex && npm install && cp .env.example .env   # add funded testnet key
npm run doctor        # read-only sanity: wallet, book per market
npm run lifecycle     # mint -> maker -> taker -> cancel (Starter parity)

# 3) Persist the KG extension (repeatable / idempotent)
cat graph/schema/dreamdex_extension.cypher | docker compose exec -T neo4j \
  cypher-shell -u neo4j -p graphalpha

# 4) Boot normally — zero change to existing startup
make up                # graph-loader now also loads dreamdex_extension.cypher

# 5) Verify endpoints + agent (DREAMDEX_ENABLED=1, DRY_RUN=1)
curl http://localhost:8000/dreamdex/status
curl http://localhost:8000/dreamdex/markets
make logs-agent | grep -i dreamdex

# 6) Optional: run the relay in the compose profile
make dreamdex-up
make dreamdex-test      # npm run doctor inside the image
```

**Pytest additions (repo convention `tests/`):** unit-test `dreamdex_agent` with a stubbed adapter (no network): empty-markets → `[]`; sub-threshold edge → filtered; a synthetic book → correct `estimate/edge/fstar` math. This keeps CI green without testnet access. (Pattern: existing `tests/test_*` + fixtures under `tests/fixtures/`.)

---

## 17. Acceptance criteria

- [ ] `DREAMDEX_ENABLED=0` → GraphAlpha boots and cycles identically; no warnings, no new logs.
- [ ] Relay `npm run doctor` + `npm run lifecycle` run on Shannon testnet and print real tx hashes (once-off proof, then `DRY_RUN=1`).
- [ ] `dreamdex_agent` emits candidates only when edge ≥ `DREAMDEX_MIN_EDGE_PCT`, sized by binary Kelly, capped at 2% NAV.
- [ ] `graph/schema/dreamdex_extension.cypher` loads idempotently after `master.cypher`; `verify-graph` shows `EventWindow`+`EventCategory` counts.
- [ ] `/dreamdex/*` routes read from Redis; no testnet dependency in the API path.
- [ ] Two-phase preview/confirm gate holds for `POST /order` intents (parity with `/crypto/preview`).
- [ ] Orchestrator patch is exactly: import + `self.dreamdex_agent = DreamDEXAgent()` + one `try/except` call. Nothing else changed.
- [ ] Frontend builds with the new panel; existing components unmodified (only the sidebar nav item added).
- [ ] Demo script (§14) runnable end-to-end: regime → KG edge story → candidate → dry-run → live flip → claim.

---

## 18. References

- DreamDEX Event Contracts docs — https://docs.dreamdex.io/developers/event-contracts
- HTTP API (spot-only; `/v0` prefix; SIWE auth) — https://docs.dreamdex.io/developers/http-api
- Event-contract market structure & lifecycle — https://docs.dreamdex.io/developers/event-contracts/market-structure
- DreamDEX Bot Kit — https://github.com/somnia-chain/dreamdex-bot-kit · `docs/event-contracts.md`, `strategies/ec-*`
- markets-sdk (npm) — https://www.npmjs.com/package/@somnia-chain/markets-sdk (≥0.29.0)
- Hackathon starter template — https://github.com/IronicDeGawd/ec-dreamdex-hackathon-template
- Hackathon page — https://dorahacks.io/hackathon/event-contracts
---

## 19. Financial-Engineering Tenet Upgrades (companion)

A companion document upgrades this plan using the tenets of **Stein Smith, *Finance with Artificial Intelligence and Blockchain*** (continuous attestation, data as an asset, code-is-law, clearinghouse & custody roles, AI + human oversight), **Antonopoulos & Wood, *Mastering Ethereum*** (oracles/settlement risk, Checks-Effects-Interactions, the withdrawal pattern, nonce & gas engineering, don't-roll-your-own-crypto), ***Technical Trading and Cryptocurrencies*** (Annals of Operations Research, 2021; data-snooping/multiple testing, costs, OOS & benchmarks), **Bolfing, *Cryptographic Primitives in Blockchain Technology*** (confirmation security, Merkle/tamper-proof ledgers, ECDSA nonce hygiene, CAP/Byzantine reality) and **Raieli & Iuculano, *Building AI Agents with LLMs, RAG, and Knowledge Graphs*** (hybrid memory, planning+reflection, graph-before-generation, multi-agent composition, RaaS/OaaS).

**→ See `docs/p9_tenets_financial_engineering.md`** for the full mapped upgrade set **U1–U24**, each with principle → concrete change → files → acceptance test:

| U | Upgrade | Key tenet(s) |
|---|---|---|
| U1 | Oracle & settlement as first-class risk (divergence check, authoritative-state rule, short-τ haircut, voided-market PnL) | F4, M1, M4 |
| U2 | Checks-Effects-Interactions + withdrawal pattern in the relay (order & claim state machines, idempotency) | M2, M6 |
| U3 | Nonce & gas engineering for time-critical claim txs (gas bump, stuck-tx detector) | M3, M4 |
| U4 | **Continuous attestation ledger** — hash-chained, replayable decision trail (`/dreamdex/attest`, Audit tab) | F3, F5, F6, M2 |
| U5 | Trust-but-verify reconciliation (ledger-vs-chain, fill-price tolerance, claim-payout verification) | F5, M6 |
| U6 | Parameter attestation & human kill-switch (`/dreamdex/controls`, `/freeze`) | F6, F9 |
| U7 | Continuous-attestation + tokenized-contingent-claim narrative for the demo | F3, F7, F8, M6 |
| U8 | Code-reuse doctrine binding (SDK/ec-core only, `npm audit` in `dreamdex-test`) | M5 |
| U9 | "Code is law" priced as a sizing haircut near finality | F4, M1, M4 |
| U10 | **Multiple-comparison correction** on the edge gate — N markets tested/cycle ⇒ FWER/FDR-corrected threshold (Bonferroni/Holm/BH), `n_tested`/`alpha_eff` in attestation | T1 |
| U11 | Cost-, liquidity-, fat-tail-aware edge — net edge, ask-depth floor, kurtosis-widened σ | T2, T6 |
| U12 | **Out-of-sample & benchmark discipline** — frozen `param_set_id`, bot vs buy-and-hold vs market-neutral, Sharpe/Sortino | T3, T4 |
| U13 | Two-provider data robustness — dual feed, divergence → belief attenuation | T5 |
| U14 | **Confirmation-count settlement policy** — `REQUIRED_CONFIRMATIONS`, reorg detection, P(race) ≤ 5.9e-4 | C1 |
| U15 | **Merkle-anchored attestation** — per-batch Merkle root anchored on-chain/IPFS + inclusion proofs | C2, C4 |
| U16 | Signing-nonce & key-path hygiene — RFC-6979 only, three-nonce taxonomy, CI hygiene gate | C3 |
| U17 | Safety-over-liveness stance + endpoint security — halt-on-uncertainty, `X-Relay-Key`, rate limits, system-health | C5, C6 |
| U18 | One task-planner, per-chain specialist agents — orchestrator registry = HuggingGPT-style planner; DreamDEX/CreditGraph agents = specialist pool | A3, A4, A1 |
| U19 | Reflection loop as first-class feedback — `/backtest` + `reconstruct_decision` = plan reflection | A2 |
| U20 | **GraphRAG over the ONE shared KG** — ported credit graphrag traverses both chains' entities | A3 |
| U21 | Human-in-the-loop as a product feature — `proposal_token`/`CreditDecision` human approval + freeze | A5, A7 |
| U22 | RaaS/OaaS framing — "decision as a service"; `/risk/report` + `/dreamdex/benchmark` outcome contracts | A6 |
| U23 | Determinism contract — LLM explains, math decides; CI-enforced byte-equal deterministic endpoints | A3, A7, P3 |
| U24 | Safety-net: freeze, audit, determinism — three gates exposed in both chains' health endpoints | A5, A7 |

**Sources added for U10–U24:** *Technical Trading and Cryptocurrencies* (Annals of Operations Research, 2021), *Cryptographic Primitives in Blockchain Technology* (Andreas Bolfing, OUP) and *Building AI Agents with LLMs, RAG, and Knowledge Graphs* (Raieli & Iuculano, Packt 2025).

**Net effect (additive):** two new files (`agent/dreamdex_attestation.py`, the upgraded `api/routes/dreamdex.py`), two relay modules extended (`fills.ts`/`claim.ts` confirmation gate, `index.ts` middleware), env blocks, appended routes/rows/panel elements — no change to the additive-only discipline. The contour shifts from "an agent that trades" to **"an auditable AI trading agent whose every decision is replayable, multiplicity-corrected, benchmarked, and settlement-verified"** — the strongest defensible frame for the hackathon's Innovation and Business criteria.

---

## 20. P10 Pointer — CreditGraph × Attestcoin Merge

P10 merges the **CreditGraph (Attestcoin × Creditcoin)** platform into GraphAlpha so one knowledge graph and one agent core serve **two chains** (DreamDEX/Somnia + Sepolia→Creditcoin). The tenet upgrades U18–U24 (shared task-planner, reflection loop, GraphRAG over one KG, human-in-the-loop gate, determinism contract, three-lamp safety) are designed for that merge.

**→ See `docs/p10_creditgraph_merge.md`** for the full P10 plan (files, env, KG extension, Python port, frontend, build sequence).