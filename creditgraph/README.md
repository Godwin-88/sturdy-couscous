# CreditGraph × GraphAlpha (P10)

Cross-chain credit intelligence merged into GraphAlpha as a **menu item + API
mount** — one knowledge graph, per-chain agents.

```
graphalpha (this repo)
├── api/creditgraph/                  # ported attest FastAPI surface (namespaced)
│   ├── api/v1/                       #   11 routers → mounted at /api/v1
│   ├── core/config.py                #   re-pointed to GraphAlpha env
│   ├── db/neo4j.py                   #   async facade over sync neo4j 4.x
│   ├── db/redis_client.py
│   ├── graph/credit_graph.py
│   ├── services/                     #   evidence, graphrag, quant_engine, …
│   └── models.py
├── creditgraph/
│   ├── attestation-service/          # Node (fastify, @gluwa/usc-sdk) :8080
│   └── execution-service/            # Node (fastify, @polkadot/api)  :8081
├── agent/creditgraph_agent.py        # per-chain orchestrator sub-agent
├── agent/creditgraph_adapter.py      # httpx clients → the two Node services
├── api/routes/creditgraph.py         # thin /creditgraph/* Redis UI endpoints
├── frontend/src/components/credit/   # ported 7-tab CreditGraph UI
└── frontend/src/lib/creditApi.ts     # attest api.ts, BASE → /api/v1
```

## Chain model (verified from docs.attestcoin.org)

Attestcoin currently attests **Ethereum Sepolia (chainKey 1)** and
**Ethereum Mainnet (chainKey 3)** on Creditcoin (CC3 testnet/mainnet). It does
**not** attest Somnia — so DreamDEX (P9) and CreditGraph (P10) share the KG but
keep chain-specific adapters. No claim is made that Somnia is Attestcoin-attested.

## Services (profiles: [creditgraph] → invisible to `make up`)

| Service | Port | Chain | SDK |
|---|---|---|---|
| `attestation-service` | 8080 | Sepolia → CC3 | `@gluwa/usc-sdk` (Merkle + continuity proofs) |
| `execution-service` | 8081 | CC3 testnet | `@polkadot/api` (`balances.transferKeepAlive`) |

Start: `docker compose --profile creditgraph up -d --build`

## Quick checks

```bash
make creditgraph-test   # node typechecks + python suite (Docker)
curl localhost:8000/api/v1/health        # CreditGraph API
curl localhost:8000/api/v1/risk/health   # deterministic risk surface
curl localhost:8000/creditgraph/status   # thin UI endpoints
```

## Design rules

- **Driver facade**: GraphAlpha pins `neo4j<5` (gqlalchemy). The ported services
  need the async surface; `api/creditgraph/db/neo4j.py` wraps the sync 4.x
  driver with `asyncio.to_thread` — same interface the services expect.
- **Human gate**: credit intents never execute autonomously. Execution requires
  a human-approved `CreditDecision` (`approval_status == "approved"`) through
  the two-phase preview/confirm flow, plus the U6 `/freeze` kill-switch.
- **Deterministic math**: the score/PD/VaR core never calls an LLM
  (`graphrag` explains, `quant_engine` computes).
- **Self-disable**: `CREDITGRAPH_ENABLED=0` (default) ⇒ agent logs once, 0 candidates.

See `docs/p10_creditgraph_merge.md` for the full plan and tenet crosswalk.