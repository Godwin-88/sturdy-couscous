# GraphAlpha — Dual Backtest & Execution Engine Specification

**Version:** 0.3 (draft — multi-venue, Docker-first deployment)
**Scope:** Replace/extend `backtest/engine.py` with a research-grade Python backtesting framework, and introduce a C++ production execution/risk core that consumes the same signal contracts as the existing agent pipeline (RegimeAgent → NewsAgent → MacroCalendarAgent → KGSignalGenerator → SignalAgent → RiskAgent → ExecutionAgent, with ResearchAgent running hourly). Adds Interactive Brokers (paper) as a second execution venue alongside Kraken.
**Status:** For review prior to implementation sprints.

### 0.1 What changed in v0.3

- **Deployment**: dropped all Vultr-specific assumptions. Everything runs as local Docker Compose services for now; remote deployment target is deferred and treated as a future, swappable concern (Section 10).
- **Venues**: added Interactive Brokers (IBKR) paper trading as a second execution venue, run alongside Kraken paper. ExecutionEngine becomes venue-routed rather than Kraken-only (Section 5.6).

---

## 1. Goals & Non-Goals

### 1.1 Goals

- A **Python research engine** for rapid strategy iteration, KG-grounded vs ungrounded ablation, multi-asset (equities, crypto, macro/rates) walk-forward backtests, replicating the *exact* signal-merge sequence the live orchestrator uses (regime → news overlay → macro overlay → KG formula signals → quant+sentiment fusion → contradiction check).
- A **C++ production execution & risk engine** that mirrors `risk_agent.py` / `execution_agent.py` for low-latency order sizing, VaR checks, sector/position caps, and **venue-routed order execution** (Kraken + Interactive Brokers paper) — while RegimeAgent, NewsAgent, MacroCalendarAgent, KGSignalGenerator, SignalAgent, and ResearchAgent remain Python.
- A **shared signal/order contract** (schema-versioned) so strategies validated in the Python backtester produce byte-identical sizing decisions when replayed through the C++ risk engine.
- Backtest output that mirrors the live system's enriched metric set (Sharpe, Calmar, Max DD, Profit Factor, Win Rate, Avg Hold Days, Jobson-Korkie) and the same JSON contract consumed by `BacktestPanel`/`RiskPanel`.
- Support for personal live/paper trading now, with a path to packaging as a sellable product or portfolio piece for quant recruiting (WQU MScFE capstone).

### 1.2 Non-Goals (v1)

- Full C++ reimplementation of GARCH/BN/DYNOTEARS/VARLiNGAM signal models, NewsAgent RSS sentiment, or MacroCalendarAgent — these remain Python.
- Tick-level / sub-millisecond HFT infrastructure. C++ engine targets sub-100ms decision latency for minute-bar to daily strategies, not microstructure HFT.
- Multi-tenant SaaS — single-account, single-operator deployment.
- Remote/cloud deployment (Vultr or otherwise) — out of scope for this spec. All services target local Docker Compose; remote hosting is a later, separable decision (Section 10).
- Live (non-paper) IBKR trading — IBKR is paper-only in this phase. Kraken retains its existing paper→live path gated by `make enable-live-trading`.

---

## 2. System Context

```
                 ┌──────────────────────────────────────────────────────┐
                 │                 Python Research Layer                  │
                 │  RegimeAgent → NewsAgent → MacroCalendarAgent →        │
                 │  KGSignalGenerator → SignalAgent (quant+LLM fusion)    │
                 │  ResearchAgent (hourly VARLiNGAM/Speechmatics/FRED)    │
                 │  Backtest Engine (vectorized + event-driven)           │
                 │  KG queries (Memgraph/gqlalchemy)                      │
                 └───────────────────────┬──────────────────────────────┘
                                          │ Signal/Order JSON (schema v1)
                                          │ via Redis pub/sub or file replay
                 ┌───────────────────────▼──────────────────────────────┐
                 │            C++ Production Risk & Execution             │
                 │  RiskEngine (half-Kelly, VaR, sector/position caps)    │
                 │  ExecutionEngine (venue router)                         │
                 │    ├── KrakenAdapter   (paper / live)                  │
                 │    └── IBKRAdapter     (paper only, via TWS/Gateway)   │
                 │  Audit log writer (Postgres via libpqxx)                │
                 └───────────────────────┬──────────────────────────────┘
                                          │
                              PostgreSQL · Redis (/ws/events) · Kraken API · IBKR Gateway

         ── All of the above runs as Docker Compose services on a single host ──
```

The KG (Memgraph), RegimeAgent, NewsAgent, MacroCalendarAgent, KGSignalGenerator, SignalAgent, and ResearchAgent stay Python — these run on the 5-minute (or hourly, for Macro/Research) cycle and benefit from the Python data-science ecosystem. Only the **risk sizing and order execution hot path** moves to C++, with venue-specific adapters for Kraken and IBKR behind a common `ExecutionEngine` interface.

---

## 3. Signal & Order Contract (Schema v1)

Both engines exchange JSON conforming to this schema. This is the seam between Python and C++. Field set extended from v0.1 to capture the overlay architecture (news, macro, KG formula signals).

### 3.1 `Signal` object (Python → C++)

```json
{
  "schema_version": 1,
  "cycle_id": "uuid",
  "timestamp": "ISO8601 UTC",
  "regime": "BullMarket",
  "strategy": "MomentumXLE",
  "ticker": "XLE",
  "venue": "kraken | ibkr",
  "venue_symbol": "XLEUSD | XLE",
  "asset_class": "equity_xstock | crypto | macro_proxy",
  "direction": "buy | sell | hold",
  "score": -1.0,
  "quant_score": -1.0,
  "sentiment_score": -1.0,
  "news_overlay": 0.0,
  "macro_overlay": 0.0,
  "kg_formula_contribution": 0.0,
  "graph_path": ["Concept A", "TRANSMITS_TO", "Concept B"],
  "contradiction_blocked": false
}
```

Notes:
- `venue` is new in v0.3. Each strategy/ticker combination is assigned a venue in `universe.py` (Section 4.3) — typically `crypto` → `kraken`, `equity_xstock`/`macro_proxy` → `ibkr` (or `kraken` if traded as an xStock; both are valid and configurable per ticker). `venue_symbol` is venue-specific (Kraken pair vs IBKR contract symbol).
- `score` is the final fused score after applying `news_overlay` and `macro_overlay` to the 70/30 quant/sentiment fusion — i.e. exactly the value SignalAgent passes to RiskAgent today.
- `news_overlay` and `macro_overlay` are retained as separate fields (rather than folded silently into `score`) so the backtest engine and C++ risk engine can run **sensitivity/ablation** on each overlay independently (e.g. "what if MacroCalendarAgent's pre-event dampening were disabled").
- `kg_formula_contribution` captures KGSignalGenerator's Formula-node evaluation, merged into the signal list per the orchestrator flowchart.

### 3.2 `ApprovedOrder` object (C++ → Postgres / ExecutionEngine)

```json
{
  "schema_version": 1,
  "order_id": "uuid",
  "cycle_id": "uuid",
  "ticker": "XLE",
  "venue": "kraken | ibkr",
  "venue_symbol": "XLEUSD | XLE",
  "direction": "buy | sell",
  "quantity": 12.345,
  "notional_usd": 1500.00,
  "kelly_fraction": 0.18,
  "var_contribution_pct": 0.021,
  "mode": "paper | live",
  "risk_checks": {
    "position_pct_ok": true,
    "sector_pct_ok": true,
    "var_ok": true
  }
}
```

Note: `mode` is venue-aware in practice — `kraken` orders can be `paper` or `live` (per `KRAKEN_TRADING_MODE`), while `ibkr` orders are always `paper` in this phase (IBKR paper trading account via TWS/Gateway). The RiskEngine should reject any `ibkr` order with `mode: "live"` until IBKR live is explicitly scoped (see Non-Goals).

### 3.3 Versioning rule

Any change to either schema increments `schema_version`. Both engines must declare the max supported version; the C++ engine rejects (and logs) signals with an unsupported version rather than guessing field defaults.

---

## 4. Python Research Backtest Engine

### 4.1 Architecture

Two interchangeable engine modes, selected via config, both producing the metric set in Section 4.4:

| Mode | Library basis | Use case |
|---|---|---|
| **Vectorized** | pandas/numpy (extend existing `engine.py`) | Fast parameter sweeps, daily-bar multi-asset, KG-ablation A/B, 5-day rebalance per current flowchart |
| **Event-driven** | custom loop | Order-level fidelity, slippage/fee modeling, intraday crypto, validating C++ parity, full overlay sequence replay |

### 4.2 Module layout

```
backtest/
├── engine.py              # Existing walk-forward simulator (extend)
├── event_engine.py         # NEW: event-driven loop replicating orchestrator's full signal-merge sequence
├── data/
│   ├── loaders.py          # yfinance (SPY/QQQ/XLF/XLE/^VIX equities/macro), Kraken OHLCV (crypto)
│   └── universe.py         # Multi-asset universe config (tickers, asset_class, venue, venue_symbol, sector)
├── overlays/
│   ├── news_overlay.py      # Backtest-time approximation of NewsAgent (historical RSS/sentiment corpus or neutral pass-through)
│   └── macro_overlay.py     # Backtest-time approximation of MacroCalendarAgent (FRED calendar pre-event windows)
├── strategies/
│   ├── base.py              # Strategy interface: generate_signal(bar, kg_context) -> Signal
│   ├── momentum.py           # MomentumOverlay (ungrounded baseline, per README)
│   ├── garch_vol.py
│   ├── bn_proxy.py
│   ├── value.py
│   └── crisis.py
├── kg_signal_generator.py    # Backtest-mode KGSignalGenerator: evaluates Formula nodes against historical prices
├── risk_sim.py               # Python mirror of C++ RiskEngine (for parity tests); implements half-Kelly, AGENT_MAX_POSITION_PCT, RISK_MAX_SECTOR_PCT, RISK_MAX_VAR_PCT
├── metrics.py                 # Sharpe, Calmar, Max DD, Ann. Vol, Profit Factor, Win Rate, Avg Hold Days, Jobson-Korkie
├── ablation.py                # KG-grounded vs ungrounded harness
├── replay_export.py           # Dump Signal stream to JSON for C++ engine replay/parity tests
└── Dockerfile
```

### 4.3 Multi-asset requirements

- **Equities/xStocks**: daily OHLCV via yfinance for the existing SPY/QQQ/XLF/XLE + ^VIX universe (per backtest flowchart), extendable to the broader `KG_SIGNAL_TICKERS` set (SPY, QQQ, TLT, GLD, BTC-USD).
- **Crypto**: hourly/daily OHLCV via Kraken public API; BTC-USD already in `KG_SIGNAL_TICKERS`. Separate fee/slippage model (Kraken taker 0.26%, configurable).
- **Macro/rates**: FRED series used as regime/context inputs and for `macro_overlay`; tradable rates exposure via TLT (already in `KG_SIGNAL_TICKERS`) as proxy.
- Each instrument tagged with `asset_class` **and `venue`** in `universe.py`; strategies, overlays, and risk engine branch on `asset_class` (fee schedules, sector-cap applicability, VaR horizon), while `venue` determines which `ExecutionEngine` adapter handles the order (Section 5.6). Default mapping: `crypto` → `kraken`; `equity_xstock` and `macro_proxy` → `ibkr` (paper). Equities tradable as xStocks on Kraken can be dual-routed for comparison if desired, but default to one venue per ticker to avoid double-counting positions.

### 4.4 Metric parity with live system

`metrics.py` must produce **all** of the following, matching the live `BacktestPanel`/`RiskPanel` contract:

| Metric | Source |
|---|---|
| Total Return | existing |
| Sharpe Ratio (rf=5%) | existing |
| Calmar Ratio | existing |
| Max Drawdown | existing |
| Annualised Volatility | existing |
| **Profit Factor** | NEW — gross profit / gross loss from trade log |
| **Win Rate** | NEW — fraction of profitable trades |
| **Avg Hold Days** | NEW — average position holding period |
| Jobson-Korkie z-stat / p-value / significant | existing |

Output JSON (`/backtest/run` → `/backtest/status` contract) extends the existing structure with `profit_factor`, `win_rate`, `avg_hold_days`, plus `equity_curve` and `trade_log` arrays per the updated flowchart's "Output" node.

### 4.5 Walk-forward & KG ablation (extend existing)

- Preserve `--use-graph` flag and existing CLI/output behavior.
- Three modes per current README: **KG-grounded** (regime → `ACTIVATED_BY` query → graph-sanctioned strategies + KGSignalGenerator formula signals), **Ungrounded baseline** (MomentumOverlay only, regardless of regime/graph), **Ablation** (run both, Jobson-Korkie comparison).
- Extend `ablation.py` to run across the full multi-asset universe, partitioned by `asset_class`, with per-asset-class Jobson-Korkie tests in addition to portfolio-level.
- Add **regime-conditional Sharpe** breakdown: Sharpe per regime period.
- Add **overlay ablation**: optional flags `--disable-news-overlay`, `--disable-macro-overlay` to isolate each overlay's contribution — directly supports Academic Differentiator #6 (7-agent orchestration with signal overlays).

### 4.6 Parity export

`replay_export.py` writes a deterministic stream of `Signal` JSON objects (Section 3.1) for a given backtest run, replayable through the C++ RiskEngine in a standalone "dry run" mode. This is the mechanism for validating Python `risk_sim.py` and C++ `RiskEngine` produce identical `ApprovedOrder` outputs (Section 7).

---

## 5. C++ Production Risk & Execution Engine

### 5.1 Scope

Reimplements, in C++, the logic currently in `agent/risk_agent.py` and `agent/execution_agent.py`:

- Half-Kelly position sizing using `AGENT_KELLY_FRACTION` (0.5)
- `AGENT_MAX_POSITION_PCT` cap (20% NAV per position)
- `RISK_MAX_SECTOR_PCT` cap (40% NAV per sector)
- Parametric VaR contribution check at `RISK_VAR_CONFIDENCE` (99%), rejecting if contribution exceeds `RISK_MAX_VAR_PCT` (5% NAV)
- Paper fill simulation (slippage + fee model, per asset class and per venue)
- Venue-routed live/paper order submission: Kraken REST `/0/private/AddOrder` (paper or live per `KRAKEN_TRADING_MODE`), and IBKR via TWS/Gateway API (paper only)
- Immutable audit log write to PostgreSQL (`order_audit`, `positions`, `portfolio_state`), tagged with `venue`
- Circuit breaker: halt at `AGENT_MAX_DRAWDOWN_HALT` (10% drawdown from peak), matching the orchestrator flowchart's CB decision node

RegimeAgent, NewsAgent, MacroCalendarAgent, KGSignalGenerator, SignalAgent, ResearchAgent **remain Python** and are unchanged in this phase except for emitting Schema v1 signals after the full merge/overlay sequence.

### 5.2 Module layout

```
engine_cpp/
├── CMakeLists.txt
├── include/graphalpha/
│   ├── signal.hpp           # Signal struct, JSON (de)serialization
│   ├── order.hpp            # ApprovedOrder struct
│   ├── risk_engine.hpp       # RiskEngine class (Kelly, VaR, position/sector caps, circuit breaker)
│   ├── execution_engine.hpp  # ExecutionEngine: venue router, dispatches to adapters
│   ├── venues/
│   │   ├── kraken_adapter.hpp  # Kraken REST client (libcurl + HMAC-SHA512 signing), paper/live
│   │   └── ibkr_adapter.hpp    # IBKR adapter (TWS/Gateway socket API), paper only
│   └── audit_log.hpp         # Postgres writer (libpqxx)
├── src/
│   ├── risk_engine.cpp
│   ├── execution_engine.cpp
│   ├── venues/
│   │   ├── kraken_adapter.cpp
│   │   └── ibkr_adapter.cpp
│   ├── audit_log.cpp
│   └── main.cpp              # Standalone service: subscribes to Redis, emits orders + /ws/events
├── tests/
│   ├── test_risk_engine.cpp  # Mirrors agent/risk_agent.py + make test-agents test cases
│   └── parity/
│       └── replay_runner.cpp # Consumes replay_export.py output, diffs vs Python risk_sim
└── Dockerfile                # multi-stage build: gcc/cmake -> minimal runtime image
```

### 5.3 Dependencies

| Purpose | Library |
|---|---|
| JSON | `nlohmann/json` |
| HTTP/REST (Kraken) | `libcurl` |
| IBKR connectivity | TWS API C++ client (official IB `twsapi` library) or `IBKR CPAPI` socket client, connecting to a running IB Gateway/TWS container |
| HMAC signing | OpenSSL `libcrypto` |
| Postgres | `libpqxx` |
| Redis pub/sub | `hiredis` or `redis-plus-plus` |
| Testing | `Catch2` or `GoogleTest` |
| Build | CMake ≥ 3.20, C++20 |

### 5.4 Interface to existing system

- **Input**: subscribes to the same Redis channel the orchestrator currently uses for `graphalpha:latest_signals` (or a new `graphalpha:signals:v1` channel), consuming Schema v1 `Signal` JSON — i.e. signals *after* the news/macro overlay merge and `CONTRADICTED_BY` check shown in the orchestrator flowchart.
- **Output**: writes `ApprovedOrder` rows to existing Postgres tables (`order_audit`, `positions`, `portfolio_state` — schema unchanged), and pushes events to the existing `/ws/events` Redis pub/sub channel consumed by `AgentLog`, `PnLDashboard`, and `RiskPanel`. **No frontend changes required.**
- **Mode switch**: reads `KRAKEN_TRADING_MODE` from `.env` exactly as today; `make enable-live-trading` flow unchanged and applies only to the `kraken` adapter. IBKR adapter is hardcoded to paper in this phase regardless of `.env`.
- **Circuit breaker state**: writes `HALTED` status to Redis (`graphalpha:agent_status`) so `/agent/status` and `RegimePanel`/`AgentLog` reflect halts originating in the C++ engine. Halt applies globally across both venues (a drawdown breach halts both Kraken and IBKR order flow).
- Deployed as an additional Docker Compose service (`risk-engine`) alongside the existing `agent-worker`, `api`, `frontend`, `memgraph`, `postgres`, `redis`. `agent-worker` (Python) retains RegimeAgent, NewsAgent, MacroCalendarAgent, KGSignalGenerator, SignalAgent, ResearchAgent — it publishes merged/fused, venue-tagged signals instead of calling RiskAgent/ExecutionAgent in-process.

### 5.5 Configuration

All thresholds (`AGENT_KELLY_FRACTION`, `AGENT_MAX_POSITION_PCT`, `RISK_MAX_SECTOR_PCT`, `RISK_VAR_CONFIDENCE`, `RISK_MAX_VAR_PCT`, `AGENT_MAX_DRAWDOWN_HALT`) read from the same `.env` — no duplication of config sources between Python and C++.

### 5.6 IBKR Integration (new in v0.3)

**Connectivity**: IBKR has no direct REST API for retail accounts — connectivity requires a running **IB Gateway** (or TWS) instance, which the C++ `ibkr_adapter` connects to over its socket API (default port 4002 for paper Gateway, 7497 for paper TWS).

**Docker topology**:
- Add an `ib-gateway` service to `docker-compose.yml` using a community headless IB Gateway image (e.g. `ghcr.io/gnzsnz/ib-gateway`), configured for the **paper trading** account via `.env` credentials (`IBKR_USERNAME`, `IBKR_PASSWORD`, `IBKR_TRADING_MODE=paper`).
- `risk-engine` connects to `ib-gateway:4002` over the Compose network — no host networking required, consistent with the Docker-first approach.
- IB Gateway requires periodic re-authentication (session timeout ~24h); `ib-gateway` container should run with an auto-restart/re-login sidecar (community images typically bundle this via IBC — "IBKR Controller").

**Symbol mapping**: `universe.py` and the `Signal`/`ApprovedOrder` schemas carry IBKR contract identifiers (symbol, exchange, currency — e.g. `XLE/SMART/USD`) as `venue_symbol` for `venue: "ibkr"` entries, distinct from Kraken pair notation.

**Fee/slippage model**: IBKR paper fills use IBKR's simulated fill engine (via the Gateway) rather than GraphAlpha's internal slippage formula — i.e., for `venue: "ibkr"`, ExecutionEngine submits a real (paper-account) order to IB Gateway and records the Gateway's reported fill price, rather than computing `price * (1 + slippage) + fee` itself. This is a deliberate fidelity improvement over the Kraken paper-fill simulation and should be called out in the capstone writeup as an asymmetry between the two paper modes.

**Scope boundary**: only equity/ETF (and optionally future/FX macro proxy) tickers route to IBKR. Crypto (BTC-USD) stays on Kraken, since IBKR's crypto offering is limited and Kraken is the system's native crypto venue.

---

## 6. Asset-Class & Venue-Specific Risk Parameters

| Parameter | Equity/xStock (IBKR) | Crypto (Kraken) | Macro proxy (IBKR) |
|---|---|---|---|
| Slippage assumption | IBKR Gateway simulated fill (no internal model) | 0.10–0.25% (configurable, internal model) | IBKR Gateway simulated fill |
| Fee | IBKR paper commission schedule | Kraken taker 0.26% | IBKR paper commission schedule |
| VaR horizon | 1 day | 1 day (consider 4h for active crypto) | 1 day |
| Sector cap applicability | Yes (GICS sector mapping) | No (crypto = own "sector" bucket) | Yes (rates bucket) |
| Position cap override | `AGENT_MAX_POSITION_PCT` | optionally tighter (e.g. 0.10) | `AGENT_MAX_POSITION_PCT` |

These overrides are expressed as a per-asset-class config block (new `.env` keys: `AGENT_MAX_POSITION_PCT_CRYPTO`, etc.), with the global value as default. Sector concentration (`RISK_MAX_SECTOR_PCT`) and overall NAV/VaR checks apply **across both venues combined** — RiskEngine maintains a single portfolio view spanning Kraken and IBKR positions, since both contribute to the same NAV and drawdown circuit breaker.

---

## 7. Parity & Validation Plan

1. **Unit parity**: Port each `make test-agents` / Layer 4 risk-control test case to `tests/test_risk_engine.cpp`. Same inputs, same expected `kelly_fraction`, `var_contribution`, `notional_usd`.
2. **Replay parity**: `replay_export.py` → `replay_runner` (C++) → diff `ApprovedOrder` streams against `risk_sim.py` output for an identical historical signal stream (post-overlay, post-contradiction-check). Tolerance: floating-point diff < 1e-6 on quantities/notionals.
3. **Backtest-to-live consistency check**: Run the Python event-driven backtest (`event_engine.py`) over the same period the C++ engine ran in paper mode; compare cumulative P&L, trade count, Sharpe, Profit Factor, Win Rate. Material divergence (>5%) triggers investigation before enabling live mode.
4. **Ablation regression**: `make backtest-ablation` JK test, plus overlay ablation (Section 4.5), must continue to pass after the Python signal-emission refactor (Section 5.4) — refactoring SignalAgent/orchestrator to emit Schema v1 JSON instead of calling RiskAgent in-process must not change backtest results.
5. **Circuit breaker parity**: Verify C++ engine halts at `AGENT_MAX_DRAWDOWN_HALT` identically to current Python behavior, and that halt state propagates to `/agent/status` and the Dashboard tab.
6. **Cross-venue NAV consistency**: With both Kraken and IBKR paper accounts active, verify `positions`/`portfolio_state` correctly aggregate NAV, drawdown, and sector exposure across venues, and that `RISK_MAX_SECTOR_PCT`/`RISK_MAX_VAR_PCT` checks see the combined portfolio — not per-venue silos.

---

## 8. Phased Delivery Plan

| Phase | Deliverable | Depends on |
|---|---|---|
| **P0** | Schema v1 definitions (Python dataclasses + JSON Schema doc), including `venue` field and overlay fields; `replay_export.py` | None |
| **P1** | Python event-driven multi-asset backtest engine (`event_engine.py`, `universe.py` with venue assignment, overlay modules, `kg_signal_generator.py` backtest mode, asset-class fee/slippage models) | P0 |
| **P2** | `metrics.py` extension (Profit Factor, Win Rate, Avg Hold Days) + `risk_sim.py` — Python reference implementation of risk logic, refactored out of `risk_agent.py` for shared use by backtest + parity tests | P0 |
| **P3** | C++ `RiskEngine` (Kelly/VaR/position/sector caps + circuit breaker, cross-venue NAV aggregation) + unit parity tests vs P2 | P0, P2 |
| **P4** | C++ `ExecutionEngine` + `KrakenAdapter` (paper mode) + `audit_log` Postgres writer + `/ws/events` publisher | P3 |
| **P5** | Redis integration: orchestrator emits Schema v1 venue-tagged, post-overlay signals → `risk-engine` service consumes; dashboard unchanged | P3, P4 |
| **P6** | `ib-gateway` Docker service + C++ `IBKRAdapter` (paper, via TWS API socket client); cross-venue NAV validation (Section 7.6) | P4, P5 |
| **P7** | C++ Kraken live client + HMAC signing; live-mode parity validation for Kraken only (IBKR remains paper) (Section 7.3) | P5, P6 |
| **P8** | Multi-asset + multi-venue + overlay ablation results write-up (capstone deliverable, Differentiator #6); packaging docs for portfolio/recruiting use | P1, P6 |

---

## 9. Open Questions for Next Iteration

- **NewsAgent/MacroCalendarAgent in backtest**: should `overlays/news_overlay.py` and `overlays/macro_overlay.py` replay a historical news/macro corpus (high fidelity, harder to source), or use a neutral/zero pass-through with a documented limitation? This affects how much of Differentiator #6 the backtest can actually validate.
- Should macro/rates exposure remain proxy-only (TLT) in v1, or add direct futures/FX once a suitable venue is identified (IBKR supports both, so this is more tractable now)?
- Crypto VaR horizon: confirm whether 1-day parametric VaR is adequate given BTC-USD volatility, or whether a separate (e.g., EWMA-based) VaR model is needed per asset class.
- **IBKR Gateway resource footprint**: IB Gateway is a JVM-based service; confirm local Docker host has sufficient RAM headroom alongside Memgraph (up to 4GB), Postgres, Redis, agent-worker, and risk-engine.
- **IBKR session re-auth**: decide whether to use a community IBC-wrapped image (auto re-login) or handle Gateway restarts manually during development — affects reliability of overnight paper runs.
- Sellable-product framing: does the eventual commercial offering expose the backtest engine (research tool for other quants) or the live execution stack (managed strategy)? This affects how aggressively to harden the C++ engine vs the Python research API in early phases.

---

## 10. Deployment (Docker-First, Remote Target Deferred)

This phase targets **local Docker Compose only**. No Vultr or other remote host is assumed; the previous Vultr-specific deployment plan (`deploy_vultr.sh`, prod overrides, Vercel frontend hosting) is removed from active scope and can be revisited later as a separate spec once the dual-venue system is validated locally.

### 10.1 Compose services (local)

```
docker-compose.yml
├── memgraph        # KG (existing)
├── postgres        # existing
├── redis           # existing
├── graph-loader    # one-shot, existing
├── agent-worker    # Python: Regime/News/Macro/KG/Signal/Research agents (existing, refactored per Section 5.4)
├── risk-engine     # NEW: C++ RiskEngine + ExecutionEngine (Kraken + IBKR adapters)
├── ib-gateway      # NEW: headless IB Gateway, paper account
├── api             # FastAPI gateway (existing)
└── frontend        # React dev server (existing)
```

### 10.2 New `.env` keys

```env
# ── Interactive Brokers (paper) ──────────────────────────────────
IBKR_USERNAME=
IBKR_PASSWORD=
IBKR_TRADING_MODE=paper        # paper only in this phase — risk-engine rejects 'live'
IBKR_GATEWAY_HOST=ib-gateway
IBKR_GATEWAY_PORT=4002          # paper Gateway default

# ── Venue routing defaults ───────────────────────────────────────
DEFAULT_VENUE_EQUITY=ibkr
DEFAULT_VENUE_CRYPTO=kraken
DEFAULT_VENUE_MACRO_PROXY=ibkr
```

### 10.3 What stays the same

- `make up`, `make verify-graph`, `make backtest-ablation`, frontend tabs, Postgres schema, and `/ws/events`/`/ws/signals` contracts are all unchanged — IBKR and the C++ engine are additive services, not replacements for the existing Python orchestrator's observability surface.
- `make enable-live-trading` continues to gate **Kraken-only** live mode; IBKR has no equivalent live flag in this phase.

### 10.4 Future remote deployment (deferred)

When a remote target is chosen later, the main considerations carried forward from this spec are: (1) IB Gateway's session re-auth requirements may favor a host with stable uptime and IBC automation; (2) port exposure rules (Section "Port exposure" in README) will need an additional private-only entry for `ib-gateway`'s port 4002; (3) Kraken live-mode and IBKR paper-mode have different operational risk profiles and should be reviewed independently before any remote go-live.