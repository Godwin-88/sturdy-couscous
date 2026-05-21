# GraphAlpha

**Knowledge Graph-Grounded Autonomous xStocks Trading Agent**

GraphAlpha is a production-grade agentic trading system built for the WQU MScFE capstone and hackathon circuit. It grounds every trading decision in a 324-concept financial knowledge graph stored in Memgraph, fuses quantitative signals with LLM sentiment, and executes on Kraken's xStocks market — paper or live — with a full risk management stack and a real-time React dashboard.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        React Frontend                           │
│  Dashboard · KG Explorer · Signals · Backtest  (port 5173)     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ REST + WebSocket
┌───────────────────────────▼─────────────────────────────────────┐
│                     FastAPI Gateway                             │
│  /agent/status · /signals · /positions · /graph · /backtest    │
│                       (port 8000)                               │
└──────┬──────────────────────────────────────────────┬──────────┘
       │ Redis pub/sub                                 │ Postgres
┌──────▼──────────────────────────────────────────────▼──────────┐
│                    Agent Worker (Orchestrator)                  │
│                                                                 │
│   RegimeAgent → SignalAgent → RiskAgent → ExecutionAgent       │
│                    ↑ ResearchAgent (async)                      │
└──────┬──────────────────────────────────────────────┬──────────┘
       │ Bolt (gqlalchemy)                            │ yfinance / Kraken
┌──────▼───────────────┐                             │
│   Memgraph (KG)      │◄── graph/schema/master.cypher
│   324 concepts        │
│   99 formulas         │
│   26 strategies       │
│   7 regimes           │
└──────────────────────┘
```

### Five-agent pipeline

| Agent | Responsibility | Key tech |
|---|---|---|
| **RegimeAgent** | Classify market regime from SPY/VIX/HYG; query graph for active strategies | 7-regime rule engine + Cypher `ACTIVATED_BY` query |
| **SignalAgent** | Generate per-strategy signals; block contradicted pairs | GARCH(1,1), BN proxy, DYNOTEARS proxy, momentum + Featherless LLM sentiment (70/30 fusion) |
| **RiskAgent** | Size positions, check VaR, enforce concentration limits | Half-Kelly criterion, parametric VaR, sector caps |
| **ExecutionAgent** | Submit orders to Kraken; write immutable audit log | Kraken REST API, paper fill simulation, PostgreSQL |
| **ResearchAgent** | Enrich graph weekly; transcribe earnings calls | VARLiNGAM refit → `TRANSMITS_TO` weights, Speechmatics, FRED macro |

---

## Knowledge Graph

The full breakdown is in [`KG_BREAKDOWN.md`](./KG_BREAKDOWN.md).

**Cumulative stats (v0.10.1)**

| Type | Count |
|---|---|
| Concepts | 324 |
| Categories | 45 |
| Formulas | 99 |
| Strategies | 26 |
| Regimes | 7 |
| Tickers | 10 |
| Relationship types | 18 |
| QuizQuestion nodes | 51 |

**18 relationship types** cover the full causal and structural ontology:

`PREREQ_OF` · `BELONGS_TO` · `HAS_FORMULA` · `DERIVED_FROM` · `ACTIVATED_BY` · `CONTRADICTED_BY` · `TRANSMITS_TO` · `MONITORS` · `REPLICATES_WITH` · `HEDGES` · `GENERALIZES_TO` · `MOTIVATES` · `TRAINED_BY` · `EVALUATED_BY` · `FITTED_TO` · `CORRELATED_WITH` · `HAS_SIGNAL` · `TESTS`

The `CONTRADICTED_BY` edges are operationally hot: `SignalAgent` traverses them every cycle and blocks signals from strategies whose concepts are mutually contradicting. This is the core academic differentiator.

**Domain coverage**

- Bayesian Network structure learning (K2, HillClimb, BIC, BDeu, BDs)
- BN parameter estimation (MLE, Bayesian)
- Dynamic BNs, HMMs, DBNs
- D-Separation, Markov Blanket
- Credit risk (PD, LGD, EAD, EL, Vasicek, Merton, Three-Factor)
- Climate risk (Physical, Transition, CERM, Wouters)
- Sustainable Finance (Green Bonds, ESG)
- Dynamic Causal Networks (DYNOTEARS, VARLiNGAM)
- Causal Inference & Econophysics (Reichenbach, MPD, De-toning)
- BN Applications (Oil Price, Credit Scoring, Rating Migration)
- Coherent Portfolio Optimization (Rebonato-Denev)
- Contagion and systemic risk
- Momentum, GARCH volatility, regime classification

---

## Repository Structure

```
graphalpha/
├── master.cypher                   # Single source of truth for the KG (7,220 lines)
├── graph/schema/master.cypher      # Symlink — used by Docker graph-loader service
├── KG_BREAKDOWN.md                 # Full KG domain breakdown, quiz bank, version history
│
├── agent/                          # Five sub-agents + orchestrator
│   ├── orchestrator.py             # Main async loop; circuit breaker; Prometheus metrics
│   ├── regime_agent.py             # Market regime classification + graph query
│   ├── signal_agent.py             # Quant signal + LLM sentiment fusion
│   ├── risk_agent.py               # Kelly sizing, VaR, concentration limits
│   ├── execution_agent.py          # Kraken REST; paper/live mode; audit log
│   ├── research_agent.py           # VARLiNGAM refit; Speechmatics; FRED
│   ├── requirements.txt
│   └── Dockerfile
│
├── api/                            # FastAPI gateway
│   ├── main.py                     # App factory; WebSocket /ws/events and /ws/signals
│   ├── routes/
│   │   ├── agent.py                # GET /agent/status
│   │   ├── signals.py              # GET /signals, GET /signals/live
│   │   ├── positions.py            # GET /positions, GET /positions/portfolio
│   │   ├── graph.py                # GET /graph/nodes|edges|regime|contradictions
│   │   └── backtest.py             # POST /backtest/run, GET /backtest/status
│   ├── models/
│   │   ├── signal.py               # Signal, Order Pydantic models
│   │   └── position.py             # Position, PortfolioState Pydantic models
│   ├── requirements.txt
│   └── Dockerfile
│
├── backtest/                       # Walk-forward backtest engine
│   ├── engine.py                   # Walk-forward simulator; KG vs ungrounded ablation
│   ├── metrics.py                  # Sharpe, Calmar, max drawdown, Jobson-Korkie test
│   └── Dockerfile
│
├── frontend/                       # React + TypeScript + Vite + Tailwind + Sigma.js
│   ├── src/
│   │   ├── App.tsx                 # Tabbed layout: Dashboard | KG Explorer | Signals | Backtest
│   │   ├── components/
│   │   │   ├── RegimePanel.tsx     # Live regime + confidence bar + active strategies
│   │   │   ├── PnLDashboard.tsx    # NAV/P&L stats + positions table + NAV sparkline
│   │   │   ├── GraphCanvas.tsx     # Sigma.js interactive KG with ForceAtlas2 layout
│   │   │   ├── AgentLog.tsx        # WebSocket live event stream
│   │   │   ├── SignalsTable.tsx    # Paginated order history table
│   │   │   ├── BacktestPanel.tsx   # Run ablation backtest; Jobson-Korkie display
│   │   │   └── ContradictionsPanel.tsx  # Live CONTRADICTED_BY edge viewer
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts     # Auto-reconnecting WebSocket hook
│   │   │   └── usePolling.ts       # Generic polling hook with configurable interval
│   │   ├── lib/
│   │   │   ├── api.ts              # Typed API client; all fetch calls in one place
│   │   │   └── utils.ts            # Formatters, regime colour map, label colours
│   │   └── index.css               # Tailwind base + custom scrollbar
│   ├── Dockerfile.dev              # Hot-reload dev container
│   ├── Dockerfile                  # Multi-stage prod build (Nginx)
│   ├── nginx.conf                  # SPA fallback + API proxy
│   └── vercel.json                 # Vercel deployment config
│
├── infra/
│   ├── postgres/init.sql           # Schema: positions, order_audit, portfolio_state,
│   │                               #         backtest_runs, agent_cycle_log
│   ├── prometheus.yml              # Scrape agent:8001 and api:8000
│   └── grafana/dashboards/         # (add JSON dashboards here)
│
├── scripts/
│   ├── load_graph.sh               # Load master.cypher into running Memgraph
│   ├── verify_graph.py             # Print node/edge counts; spot-check Strategy→Regime links
│   └── deploy_vultr.sh             # rsync + docker compose prod up on Vultr VM
│
├── docker-compose.yml              # Local dev: all services, hot-reload
├── docker-compose.prod.yml         # Vultr overrides: 6G Memgraph, localhost binding, no frontend
├── .env.example                    # All environment variables with safe defaults
├── Makefile                        # One-command ops
└── README.md                       # This file
```

---

## Quick Start (Local Docker)

### Prerequisites

- Docker Desktop or Docker Engine + Compose plugin
- 8 GB RAM minimum (16 GB recommended — Memgraph alone takes up to 4 GB)
- Ports 5173, 8000, 7687, 3000, 5432, 6379 available

### 1. Clone and configure

```bash
git clone <your-repo-url> graphalpha
cd graphalpha
cp .env.example .env
```

Open `.env` and set at minimum:

```env
POSTGRES_PASSWORD=anysecrethere
FEATHERLESS_API_KEY=your_key        # get from featherless.ai
FEATHERLESS_MODEL=your_model_id     # e.g. a finance-tuned LLaMA variant
KRAKEN_API_KEY=your_key             # required for live mode only
KRAKEN_API_SECRET=your_secret       # required for live mode only
```

All other values have working defaults for local development.

### 2. Boot everything

```bash
make up
```

This command:
1. Builds all Docker images (agent, api, frontend)
2. Starts Memgraph, PostgreSQL, Redis
3. Waits for health checks to pass
4. Runs the graph-loader one-shot container (loads all 7,220 lines of `master.cypher`)
5. Starts the API, agent worker, and frontend dev server

**Access points after `make up`:**

| Service | URL |
|---|---|
| Frontend dashboard | http://localhost:5173 |
| API + Swagger docs | http://localhost:8000/docs |
| Memgraph Lab (KG browser) | http://localhost:3000 |

### 3. Verify the graph loaded

```bash
make verify-graph
```

Expected output shows ~324 Concept nodes, ~26 Strategy nodes, ~7 Regime nodes.

### 4. Watch the agent run

```bash
make logs-agent
```

The orchestrator runs every 300 seconds by default (`AGENT_LOOP_INTERVAL_SECONDS` in `.env`). The frontend dashboard updates live via WebSocket.

---

## Makefile Reference

```bash
make up                  # Build + start all services + load KG
make down                # Stop and remove containers
make logs                # Follow API + agent logs
make logs-agent          # Follow agent worker only
make load-graph          # Reload master.cypher into running Memgraph
make verify-graph        # Print node/edge counts from Memgraph
make shell-memgraph      # Open mgconsole Cypher shell
make shell-api           # Bash into running API container
make shell-agent         # Bash into running agent container
make backtest            # Run walk-forward backtest (KG-grounded)
make backtest-ablation   # Run both KG-grounded and ungrounded, print comparison
make up-monitoring       # Start Prometheus (port 9090) + Grafana (port 3001)
make enable-live-trading # Prompts for CONFIRM; switches paper → live in .env
make deploy              # Deploy to Vultr VM (run from your local machine)
```

---

## API Reference

All endpoints are documented interactively at http://localhost:8000/docs.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/agent/status` | Latest cycle: regime, confidence, strategies, signals, halted |
| `GET` | `/signals` | Order history (paginated, up to 200 rows) |
| `GET` | `/signals/live` | Latest signals cached in Redis |
| `GET` | `/positions` | Open positions |
| `GET` | `/positions/portfolio` | NAV, cash, drawdown, halt status |
| `GET` | `/graph/nodes` | KG nodes (filter by label, limit) |
| `GET` | `/graph/edges` | KG edges (limit) |
| `GET` | `/graph/regime?regime=X` | Strategies + concepts activated by regime X |
| `GET` | `/graph/contradictions` | All active CONTRADICTED_BY pairs |
| `POST` | `/backtest/run` | Trigger walk-forward backtest (async background task) |
| `GET` | `/backtest/status` | Poll backtest completion + results |
| `WS` | `/ws/events` | Live agent event stream (Redis pub/sub relay) |
| `WS` | `/ws/signals` | Latest signals pushed every 5 seconds |

---

## Environment Variables

```env
# ── Memgraph ────────────────────────────────────────────────────
MEMGRAPH_HOST=memgraph
MEMGRAPH_PORT=7687

# ── PostgreSQL ──────────────────────────────────────────────────
POSTGRES_HOST=postgres
POSTGRES_DB=graphalpha
POSTGRES_USER=graphalpha
POSTGRES_PASSWORD=changeme

# ── Redis ───────────────────────────────────────────────────────
REDIS_HOST=redis
REDIS_PORT=6379

# ── Featherless (LLM sentiment) ─────────────────────────────────
FEATHERLESS_BASE_URL=https://api.featherless.ai/v1
FEATHERLESS_API_KEY=
FEATHERLESS_MODEL=

# ── Kraken (trading) ────────────────────────────────────────────
KRAKEN_API_KEY=
KRAKEN_API_SECRET=
KRAKEN_TRADING_MODE=paper          # paper | live — NEVER set live manually

# ── Speechmatics (earnings transcription) ───────────────────────
SPEECHMATICS_API_KEY=

# ── FRED (macro data) ───────────────────────────────────────────
FRED_API_KEY=

# ── Agent behaviour ─────────────────────────────────────────────
AGENT_LOOP_INTERVAL_SECONDS=300    # 5-minute cycle
AGENT_MAX_DRAWDOWN_HALT=0.10       # halt at 10% drawdown from peak
INITIAL_CAPITAL_USD=10000

# ── Risk limits ─────────────────────────────────────────────────
RISK_MAX_POSITION_PCT=0.15         # max 15% NAV per position
RISK_MAX_SECTOR_PCT=0.40           # max 40% NAV per sector
RISK_VAR_CONFIDENCE=0.99
RISK_MAX_VAR_PCT=0.05              # reject order if VaR contribution > 5% NAV

# ── API ─────────────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,https://your-app.vercel.app
API_SECRET_KEY=change_this_in_production
```

---

## Signal Pipeline Deep-Dive

Each agent cycle follows this exact sequence:

```
RegimeAgent.run()
  └── yfinance: SPY, ^VIX, ^TNX, HYG (1 year)
  └── classify_regime() → one of 7 regimes
  └── Memgraph: MATCH (r:Regime)<-[:ACTIVATED_BY]-(s:Strategy {status:'active'})
  └── returns {regime, confidence, active_strategies}

SignalAgent.run(regime, active_strategies)
  └── for each strategy:
      ├── _get_strategy_formula()   → Cypher: s-[:DERIVED_FROM]->c-[:HAS_FORMULA]->f
      ├── _check_contradictions()   → Cypher: CONTRADICTED_BY traversal — BLOCKS if hit
      ├── _compute_quant_signal()
      │     GARCH(1,1)     → annualised vol → negative score when vol > 15%
      │     BN proxy       → VIX → P(IR=high) → P(SP=low|macro) vs threshold
      │     Contagion      → mean JPM/BAC/GS/MS/C correlation spike
      │     Climate        → XLE vs SPY 3m relative performance
      │     Momentum       → 12-month minus 1-month SPY momentum
      ├── _get_sentiment()          → Featherless LLM: float -1.0 to 1.0
      └── fused_score = 0.70 * quant + 0.30 * sentiment
          direction: sell if < -0.2, buy if > 0.2, hold otherwise

RiskAgent.run(signals)
  └── half-Kelly sizing: f* = (p*b - q) / b, halved
  └── sector concentration check (40% cap per sector)
  └── parametric VaR contribution check (99% confidence, 5% NAV cap)
  └── position quantity = (NAV * kelly * max_position_pct) / price

ExecutionAgent.run(approved_orders)
  └── paper mode: simulated fill = price * (1 + 0.05% slippage) + 0.26% fee
  └── live mode:  Kraken REST /0/private/AddOrder (market order)
  └── immutable write to order_audit (PostgreSQL)
  └── update positions table
```

---

## Backtesting & Academic Validation

The backtest engine (`backtest/engine.py`) runs a walk-forward simulation and produces metrics comparable across two conditions:

- **KG-grounded**: regime classification triggers graph `ACTIVATED_BY` query → only graph-sanctioned strategies produce signals
- **Ungrounded baseline**: always runs momentum regardless of regime or graph state

### Metrics produced

| Metric | Purpose |
|---|---|
| Total Return | Raw P&L over the period |
| Sharpe Ratio | Risk-adjusted return (annualised, rf=5%) |
| Calmar Ratio | Return / Max Drawdown |
| Max Drawdown | Worst peak-to-trough loss |
| Annualised Volatility | Daily std × √252 |
| **Jobson-Korkie z-stat** | Tests H₀: Sharpe(grounded) = Sharpe(ungrounded) |
| **JK p-value** | p < 0.05 → statistically significant outperformance |

The Jobson-Korkie test is the capstone's primary academic contribution: it provides statistical evidence that KG-grounded signal selection outperforms ungrounded selection, not just by chance.

### Running the ablation

```bash
# From the backtest UI (http://localhost:5173 → Backtest tab)
# Select "Both (ablation)" mode → Run Backtest

# Or from the command line:
make backtest-ablation
```

---

## Testing Checklist

Work through these in order before deploying to Vultr.

### Layer 1 — Infrastructure

```bash
# All containers healthy
docker compose ps
# Expected: all 5 core services show "healthy" or "running"

# Graph loaded correctly
make verify-graph
# Expected: Concept ~324, Strategy ~26, Regime 7, Formula ~99

# API reachable
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"1.0.0"}

# Postgres schema created
docker compose exec postgres psql -U graphalpha -c "\dt"
# Expected: positions, order_audit, portfolio_state, backtest_runs, agent_cycle_log

# Redis reachable
docker compose exec redis redis-cli ping
# Expected: PONG
```

### Layer 2 — Knowledge Graph correctness

```bash
# Open Memgraph Lab at http://localhost:3000, run these queries:

# 1. Strategy → Regime links exist
MATCH (s:Strategy)-[:ACTIVATED_BY]->(r:Regime) RETURN s.name, r.name LIMIT 20;

# 2. CONTRADICTED_BY edges present
MATCH (c1:Concept)-[:CONTRADICTED_BY]->(c2:Concept) RETURN c1.name, c2.name;

# 3. Formulas linked to concepts
MATCH (c:Concept)-[:HAS_FORMULA]->(f:Formula) RETURN c.name, f.expression LIMIT 10;

# 4. No orphan strategies (every Strategy has DERIVED_FROM and ACTIVATED_BY)
MATCH (s:Strategy)
WHERE NOT (s)-[:DERIVED_FROM]->() OR NOT (s)-[:ACTIVATED_BY]->()
RETURN s.name;
# Expected: empty result
```

### Layer 3 — Agent pipeline

```bash
# Trigger one manual cycle and watch logs
make logs-agent
# Wait up to 30s for first cycle to complete.
# Expected log lines:
#   Regime: <name> (confidence=0.XX)
#   Generated N signals
#   Risk: N/N signals approved
#   Executed N orders [paper mode]

# Check agent status endpoint
curl http://localhost:8000/agent/status | python3 -m json.tool
# Expected: regime, regime_confidence, active_strategies, signals_generated, orders_approved

# Check signals cached in Redis
docker compose exec redis redis-cli get graphalpha:latest_signals | python3 -m json.tool
```

### Layer 4 — Risk controls

Open a Python shell inside the agent container and test directly:

```bash
docker compose exec agent-worker python3
```

```python
import asyncio
from risk_agent import RiskAgent

agent = RiskAgent()

# Mock a high-score signal
mock_signal = {
    "strategy": "TestStrategy", "ticker": "SPY", "kraken_pair": "SPYXUSD",
    "direction": "buy", "score": 0.85, "quant_score": 0.9,
    "sentiment_score": 0.7, "reasoning": "test", "graph_path": [], "regime": "BullMarket"
}

approved = asyncio.run(agent.run([mock_signal]))
print(approved)
# Expected: one approved order with quantity > 0, kelly_fraction between 0 and 0.5,
#           var_contribution calculated, notional_usd = NAV * kelly * 0.15

# Test sector concentration block
# Add 5 SPY-like signals and verify only enough to reach 40% cap are approved
```

### Layer 5 — Execution (paper mode)

```bash
# Verify KRAKEN_TRADING_MODE is paper
grep KRAKEN_TRADING_MODE .env
# Expected: KRAKEN_TRADING_MODE=paper

# After at least one agent cycle, check order_audit
docker compose exec postgres psql -U graphalpha -c \
  "SELECT order_id, ticker, direction, quantity, fill_price, mode FROM order_audit LIMIT 5;"
# Expected: rows with mode='paper'

# Check positions table
docker compose exec postgres psql -U graphalpha -c \
  "SELECT ticker, direction, quantity, avg_entry_price FROM positions WHERE status='open';"
```

### Layer 6 — Frontend

Open http://localhost:5173 and verify each element manually:

```
Dashboard tab
  [ ] RegimePanel shows a regime name (not "Loading...")
  [ ] Confidence bar has a non-zero width
  [ ] Active Strategies list is populated
  [ ] ContradictionsPanel shows count (0 or more)
  [ ] AgentLog shows "open" status dot (green)
  [ ] AgentLog receives at least one event after one cycle completes
  [ ] PnLDashboard shows NAV = $10,000.00 (or updated if trades ran)
  [ ] Positions tab shows "No open positions" or actual positions

KG Explorer tab
  [ ] Graph renders within 5 seconds
  [ ] Nodes appear with correct colours per type
  [ ] Clicking a node shows the detail sidebar with properties
  [ ] Switching node type filter reloads the graph
  [ ] Zoom in / Zoom out / Reset buttons work

Signals tab
  [ ] Table renders (empty on first boot, populated after cycles)
  [ ] Mode badge shows "paper" for all rows
  [ ] Direction column coloured green (buy) / red (sell)

Backtest tab
  [ ] Date inputs pre-filled
  [ ] "Run Backtest" triggers loading state
  [ ] After completion, metrics table populates
  [ ] If both modes run: Delta column shows coloured values
  [ ] Jobson-Korkie result box appears
```

### Layer 7 — WebSocket

```bash
# Test WebSocket directly
curl --include \
  --no-buffer \
  --header "Connection: Upgrade" \
  --header "Upgrade: websocket" \
  --header "Sec-WebSocket-Key: x3JJHMbDL1EzLkh9GBhXDw==" \
  --header "Sec-WebSocket-Version: 13" \
  http://localhost:8000/ws/events
# Expected: HTTP 101 Switching Protocols

# Or use websocat if installed:
websocat ws://localhost:8000/ws/events
# Wait for an agent cycle — you should receive a JSON event
```

### Layer 8 — Backtest metrics validation

```bash
docker compose --profile backtest run --rm backtest python engine.py \
  --start 2022-01-01 --end 2022-12-31 --use-graph
```

Expected output structure:
```json
{
  "total_return": <float>,
  "sharpe_ratio": <float>,
  "calmar_ratio": <float>,
  "max_drawdown": <negative float>,
  "ann_volatility": <float between 0 and 0.5>,
  "n_days": <integer near 252>,
  "final_nav": <float near 10000>,
  "use_graph": true,
  "jk_z_stat": <float>,
  "jk_p_value": <float between 0 and 1>,
  "jk_significant": <bool>
}
```

Sanity checks:
- `max_drawdown` must be negative
- `ann_volatility` should be between 0.05 and 0.50 for a realistic period
- `n_days` should be close to the number of trading days in the range
- `jk_p_value` will rarely be < 0.05 on a single year — run 2021–2023 for meaningful results

---

## Production Deployment (Vultr)

### One-time Vultr VM setup

```bash
# From your local machine (replace IP with your Vultr VM IP)
./scripts/deploy_vultr.sh 123.456.789.0
```

This script:
1. Installs Docker on the VM if missing
2. Rsyncs the project (excluding node_modules, git history)
3. Starts services with the prod overrides (Memgraph gets 6 GB, no hot-reload, localhost-only ports)
4. Loads the knowledge graph

Then edit `.env` on the VM to add your real API keys, and restart:

```bash
ssh root@your-vultr-ip
cd /opt/graphalpha
nano .env                          # set all secrets
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart
```

### Frontend on Vercel

```bash
# In the Vercel dashboard:
# 1. Import from GitHub
# 2. Set root directory: frontend
# 3. Framework: Vite
# 4. Add environment variable:
#    VITE_API_URL = http://your-vultr-ip:8000

# Or via Vercel CLI:
cd frontend
vercel --prod
```

Update `frontend/vercel.json` with your actual Vultr IP before deploying.

### Port exposure on Vultr

Only expose these ports through the Vultr firewall:

| Port | Service | Exposure |
|---|---|---|
| 8000 | FastAPI | Public (needed by Vercel frontend) |
| 7687 | Memgraph Bolt | Private only |
| 5432 | PostgreSQL | Private only |
| 6379 | Redis | Private only |
| 3000 | Memgraph Lab | Private only (or VPN) |

### Enable live trading (only after 30-day paper run)

```bash
# On the Vultr VM:
cd /opt/graphalpha
make enable-live-trading
# Type CONFIRM when prompted
```

---

## Academic Differentiators (Capstone Thesis Points)

1. **Knowledge graph-grounded signal selection** — No other WQU MScFE capstone uses a live financial KG to constrain agent decisions at runtime. The graph is not a lookup table; it is a causal model that gates which strategies are epistemically valid for the current market regime.

2. **CONTRADICTED_BY ablation** — The `CONTRADICTED_BY` edges can be toggled off in the signal agent to produce a clean ablation: how much does mutual-contradiction blocking reduce drawdown? This is a controlled experiment, not a post-hoc claim.

3. **Jobson-Korkie statistical significance** — The backtest engine implements the full Jobson-Korkie (1981) test. p < 0.05 over 3 years of walk-forward data would constitute publishable evidence of outperformance from KG grounding.

4. **51 QuizQuestion nodes as validation harness** — The M6–M8 Q&A bank is encoded in the graph as `QuizQuestion` nodes with `TESTS` edges to the concepts they examine. This enables automated checks that the KG covers the domain it claims to cover, and creates a DPO dataset for future fine-tuning of the Featherless model.

5. **VARLiNGAM-derived TRANSMITS_TO weights** — Causal edge weights are not static; ResearchAgent refits the VARLiNGAM model weekly on fresh price data and updates the Memgraph `TRANSMITS_TO` edges. The graph evolves with the market.

---

## Troubleshooting

**`make up` hangs at graph-loader**

The loader waits for Memgraph's Bolt port. If Memgraph is slow to start (common on first boot with large RAM allocation), increase the sleep in the Makefile or run `make load-graph` separately after `docker compose ps` shows Memgraph as healthy.

**Agent worker exits immediately**

Check logs: `docker compose logs agent-worker`. The most common cause is a failed Memgraph connection. Ensure Memgraph is healthy before the agent starts (`depends_on: condition: service_healthy` handles this, but if you started services manually it may not apply).

**`RegimePanel` shows "Agent unreachable"**

The `/agent/status` endpoint reads from Redis. It returns safe defaults until the agent completes its first cycle. Wait for the cycle interval (default 5 minutes) or reduce `AGENT_LOOP_INTERVAL_SECONDS=30` in `.env` for testing.

**Sigma.js graph is empty**

The graph API returns nodes from Memgraph. If the graph-loader failed silently, Memgraph has no data. Run `make verify-graph` to check node counts. If zero, run `make load-graph`.

**Featherless returns 0.0 sentiment every cycle**

If `FEATHERLESS_API_KEY` is empty, the agent falls back to 0.0 sentiment score and logs a warning. This is expected and safe — the signal still runs on quant score alone (100% weight in practice, since 0.3 × 0 = 0).

**Paper orders not appearing in Postgres**

The ExecutionAgent writes orders after the RiskAgent approves them. If no strategies are active for the current regime (empty `active_strategies` from the graph), no signals are generated and nothing executes. Use `make shell-memgraph` and run:
```cypher
MATCH (s:Strategy) WHERE s.status = 'active' RETURN s.name, s.strategy_type;
```
If empty, the graph's strategies may not be marked `status: 'active'` — check `master.cypher` for the `SET s.status = 'active'` lines.
