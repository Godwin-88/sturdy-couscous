# P1 Implementation Plan — Python Multi-Asset Event-Driven Backtest Engine

> **Scope:** Deliver Features 1–7 from `docs/p1.md` as a new event-driven backtest engine
> that produces Schema v1 `Signal` records, while preserving the existing vectorized
> `backtest/engine.py` untouched.

---

## Guiding Constraints

- **No edits to `backtest/engine.py`** — the existing vectorized backtest is preserved as-is.
- **All new code lives under `backtest/`** (universe, loaders, event engine, strategies,
  overlays, fees) and re-uses `schemas/`, `common/`, `agent/` where safe.
- **`docs/p1.md`** is the canonical requirement source; acceptance criteria below trace
  directly to its features.
- **`memory_practical.py`** is referenced in plan-mode guidance as a lightweight prototype /
  scratch target; treat it as a development sandbox only (not shipped artifact).

---

## Execution Order

### 0 · Infrastructure scaffolding
**Files:** `backtest/config.py`, `backtest/__init__.py`, `backtest/schemas.py` (re-export P0)

- [x] Create `backtest/config.py` — load `.env` with `python-dotenv`, expose fee/slip/cadence
      constants (crypto kraken taker 0.26%, equity ibkr maker 0.0010%, slippage defaults
      0.10% / 0.25%, rebalance freq, fusion threshold from P0).
- [x] Re-export P0 schemas + validators from `backtest/schemas.py` so backtest code has one
      import path.

---

### 1 · Feature 1 — Multi-Asset Universe Definition
**Files:** `backtest/universe.py`

- [x] Define the 5-instrument `KG_SIGNAL_TICKERS` default universe:
      SPY (equity_xstock, ibkr, SPY, Technology), QQQ (equity_xstock, ibkr, QQQ, Technology),
      TLT (macro_proxy, ibkr, TLT, Rates), GLD (macro_proxy, ibkr, GLD, Commodities),
      BTC-USD (crypto, kraken, XBTUSD, "").
- [x] Each entry: `ticker`, `asset_class`, `venue`, `venue_symbol`, `sector` (GICS-level,
      empty string for crypto).
- [x] `get_universe()` returns the list; `lookup(ticker)` returns single entry or raises.
- [x] **AC:** every entry validated against P0 `validate_signal` field constraints.

---

### 2 · Feature 2 — Multi-Asset Historical Data Loading
**Files:** `backtest/loaders.py`

- [x] `load_ohlcv(start, end, tickers, interval="1d")`
  - equities/macro → `yfinance` with `auto_adjust=True` (splits + dividends applied).
  - crypto → Coinbase public REST OHLCV (no auth, daily by default; hourly via `interval`).
- [x] Normalise both sources to same schema: `pd.DataFrame` with columns
  `Open/High/Low/Close/Volume` and `DatetimeIndex(tz="UTC")`.
- [x] `load_for_ticker(ticker, start, end)` — convenience wrapper.
- [x] **Loud failure:** if any requested ticker returns empty DataFrame or the row count
      for `[start, end]` drops below a configurable minimum, raise `DataGapError(ticker,
      start, end, available)` before returning.

---

### 3 · Feature 3 — Overlay Modules (News & Macro)
**Files:** `backtest/overlays.py`

- [x] `class NewsOverlay` — per `(ticker, date)` returns float in `[-1, 1]`.
  - Default approximation: **neutral pass-through (0.0)** — corpus not available this phase.
  - Method documented in docstring; toggled by `--disable-news-overlay`.
- [x] `class MacroOverlay` — per `(ticker, date)` returns float in `[-1, 1]`.
  - Default approximation: **FRED pre-event dampening windows replayed from a static
    calendar bundled in `backtest/data/macro_calendar.csv`** (date, event, window_start,
    window_end, affected_tickers, dampening).
  - Falls back to 0.0 when no event window overlaps.
  - Method documented in docstring; toggled by `--disable-macro-overlay`.
- [x] Signature: `get_overlay(overlay_name, ticker, dt, universe, macro_df=None) -> float`.
- [x] Overlays are applied **after** quant/sentiment fusion and **before** final `score`
      computation, matching live orchestrator order.

---

### 4 · Feature 4 — KG Formula Signal Generation (Backtest Mode)
**Files:** `backtest/kg_backtest.py`

- [x] `evaluate_formulas(universe_entry, bar, formulas: list[dict]) -> float`
  - `formulas` loaded once from `master.cypher` via a Cypher export step:
    `MATCH (c:Concept)-[:HAS_FORMULA]->(f:Formula) RETURN c.name, f.expression, f.parameters`
  - Parse expression strings into evaluable form (ast-based safe evaluator using only
    price/indicator names present in `bar`).
- [x] If a formula references a concept/ticker not in the loaded universe, raise
      `MissingReferenceError(formula_id, missing_key)` loudly.
- [x] Clip result to `[-1, 1]` and return `kg_formula_contribution`.
- [x] Deterministic: same inputs → identical float (no random seeding).

---

### 5 · Feature 5 — Strategy Library (Grounded & Ungrounded)
**Files:** `backtest/strategies/__init__.py`, `backtest/strategies/base.py`,
          `backtest/strategies/momentum.py`, `backtest/strategies/garch_vol.py`,
          `backtest/strategies/bayesian_proxy.py`, `backtest/strategies/value.py`,
          `backtest/strategies/crisis.py`

- [x] Common interface:

```python
class Strategy(ABC):
    @abstractmethod
    def generate_signal(self, bar: pd.Series, kg_context: dict) -> Signal:
        ...
```

- [x] Implementations (each returns Schema v1 `Signal`, already validated):
  - `MomentumOverlay` — 252d vs 21d momentum, no graph dependency.
  - `GARCHVolStrategy` — 1,1 GARCH forecast volatility, score = clip(-(av-0.15)/0.30, -1, 1).
  - `BayesianNetworkProxy` — rolling 63d correlation matrix proxy, score from eigen-centrality
    of returns covariance (approx BN evidence propagation).
  - `ValueMeanReversion` — 50d/200d MA crossover inverse score.
  - `CrisisAlpha` — VIX-level trigger, score = clip((VIX - 25) / 20, 0, 1).
- [x] `MomentumOverlay` is ungrounded: it always runs regardless of `--use-graph`.
  - KG-grounded strategies are only activated when the regime's `ACTIVATED_BY` edges
    sanction them (live orchestrator parity).
- [x] Each strategy's output passes `validate_signal` immediately before returning.

---

### 6 · Feature 6 — Event-Driven Backtest Loop
**Files:** `backtest/event_engine.py`

- [x] `class EventEngine`
  - Takes `universe`, `start`, `end`, `rebal_freq`, `use_graph`,
    `disable_news_overlay`, `disable_macro_overlay`, `fee_pct`, `slip_pct`.
- [x] Per-timestep sequence (**must match live orchestrator order**):
  1. Load bar for current date; skip if market closed for all venues.
  2. `RegimeClassifier.classify(prices, idx)` — reuse existing logic.
  3. Query KG for `ACTIVATED_BY` strategies (or use MomentumOverlay only if `--no-graph`).
  4. For each activated strategy: `strategy.generate_signal(bar, kg_context)` → raw `Signal`.
  5. `quant_score` = 0.70 × strategy score; `sentiment_score` = 0.30 × sentiment
     (sentiment = `compute_sentiment_proxy(bar, prices, idx)` derived from momentum /
     volume / VIX — same formula as live SignalAgent's fallback).
  6. `score_raw` = 70/30 fusion of `quant_score` and `sentiment_score`.
  7. Apply `news_overlay` (Feature 3) → add to `score_raw`.
  8. Apply `macro_overlay` (Feature 3) → add to `score_raw`.
  9. Add `kg_formula_contribution` (Feature 4).
  10. Final `score = clip(score_raw, -1, 1)`.
  11. `contradiction_blocked` = `check_contradictions(bar, kg_context, strategy)` using
      cached `CONTRADICTED_BY` pairs from `master.cypher`.
  12. Populate remaining Signal fields: `schema_version=1`, `cycle_id`, `timestamp`,
      `venue`, `venue_symbol`, `asset_class`, `direction` (buy/sell/hold).
  13. Emit validated `Signal` to `signal_stream`.
- [x] **Rebalance cadence:** default 5-day rebalance (`rebal_freq`), configurable per run.
- [x] **CLI flags composable:** `--use-graph`, `--no-graph`, `--disable-news-overlay`,
  `--disable-macro-overlay` — each independently tested by toggling and asserting only
  overlay-specific fields change.
- [x] **Trade log** emitted alongside signal stream with fields:
  `open_timestamp, close_timestamp, ticker, direction, size, entry_price, exit_price,
  pnl, hold_days, strategy, regime`.

---

### 7 · Feature 7 — Asset-Class & Venue-Aware Fee/Slippage Modeling
**Files:** `backtest/fees.py` (logic pulled from `_fee_slippage_for` helper in engine)

- [x] `fee_slippage_for(ticker: str, asset_class: str, venue: str) -> (fee_pct: float, slip_pct: float)`
  - crypto / kraken: fee = 0.26% + slip = 0.10–0.25% (env-configurable).
  - equity_xstock / ibkr: fee = 0.0010% + slip = 0.05% (env-configurable).
  - macro_proxy / ibkr: same as equity.
- [x] All numbers sourced from `.env` / `backtest/config.py`; **no magic numbers inside
  the event loop**.
- [x] Applied at fill time in event engine (`fill_price = price * (1 + slip * sign)`).
- [x] Backtest docs note: *this internal model is a backtest-only approximation;
  live IBKR paper fills use Gateway-reported fills and will differ.*
  → Add docstring + `docs/BACKTEST_COST_MODEL.md` note.

---

### 8 · CLI & Integration
**Files:** `backtest/cli.py`

- [x] `python -m backtest.cli` or `python backtest/cli.py` entry-point.
- [x] Flags:
  ```
  --start YYYY-MM-DD   --end YYYY-MM-DD
  --capital FLOAT       --rebal-freq N
  --output PATH         --export-replay PATH   (wires to P0 replay_export.py)
  [--use-graph | --no-graph]
  [--disable-news-overlay] [--disable-macro-overlay]
  --interval 1d|1h
  ```
- [x] Orchestrates: load prices → load universe → run `EventEngine` →
  compute metrics → print JSON → optionally call `replay_export.export_signals`.
- [x] Tears down KG connection cleanly on exit.

---

### 9 · Schema v1 Signal Injection (P0 follow-on)
**Files:** `agent/orchestrator.py`, `agent/signal_agent.py`, `agent/risk_agent.py`,
         `api/models/signal.py`

- [x] Before RiskAgent, orchestrator stamps each Signal with `schema_version=1`,
  `cycle_id=uuid4()`, `timestamp=utcnow().isoformat()`, `venue`, `asset_class`
  from universe lookup.
- [x] `signal_agent.py` legacy keys (`strategy_type`, `kraken_pair`, `reasoning`)
  → Schema v1 keys (`asset_class`, `venue_symbol`, drop `reasoning`).
- [x] `risk_agent.py` legacy keys (`var_contribution`) → ApprovedOrder v1
  (`var_contribution_pct`, `risk_checks` sub-object with `position_pct_ok`,
  `sector_pct_ok`, `var_ok`).
- [x] `api/models/signal.py` Pydantic model updated to match `signal_schema_v1.json`.

---

### 10 · Smoke-Test Suite
**Files:** `tests/test_p1.py`

- [x] `TestUniverse` — all 5 instruments pass `validate_signal`.
- [x] `TestLoaders` — equity/crypto load, gap error raised for missing range.
- [x] `TestOverlays` — bounds [-1,1], disable flags force 0.0 independence.
- [x] `TestKG` — formula eval raises on missing ticker, deterministic.
- [x] `TestStrategies` — each returns valid Signal; MomentumOverlay ungrounded.
- [x] `TestEventEngine` — full 1-month mini-backtest (SPY only, daily) produces
  non-empty signal stream + trade log; regime distribution populated.
- [x] `TestFees` — crypto/kraken fee = 0.26%, equity/ibkr = 0.0010%.
- [x] `TestAblationFlags` -- run engine with --no-graph vs --use-graph; assert momentum
  identically non-empty.
- [x] `TestReplayExport` — end-to-end: cli → replay jsonl → parse → all lines pass
  validate_signal.

Target: **`python3 -m unittest tests.test_p1 -v`** green (no external DB needed; mocks for Memgraph).

---

## Tickability Matrix

| # | Deliverable | File(s) | AC Check |
|---|---|---|---|
| 1 | Universe config | `backtest/universe.py` | ✅ venue/asset_class valid; crypto→kraken; equity→ibkr |
| 2 | Data loaders | `backtest/loaders.py` | ✅ OHLCV loads; adj applied; gap raises |
| 3 | Overlays | `backtest/overlays.py` | ✅ bounds [-1,1]; disable flags; fusion order matches |
| 4 | KG formulas | `backtest/kg_backtest.py` | ✅ raises on missing ref; deterministic |
| 5 | Strategy lib | `backtest/strategies/` | ✅ 5 strategies; MomentumOverlay ungrounded; valid Signal |
| 6 | Event loop | `backtest/event_engine.py` | ✅ 13-step sequence; rebalance; contradiction; trade log |
| 7 | Fee/slippage | `backtest/fees.py` | ✅ per venue+asset; env-sourced; documented asymmetry |
| 8 | CLI | `backtest/cli.py` | ✅ flags composable; replay export wired |
| 9 | Schema injection | `agent/` files | ✅ v1 keys stamped; legacy mapped |
| 10 | Tests | `tests/test_p1.py` | ✅ runs with stdlib unittest only |

---

## Out-of-Scope for P1 (honoured)

- Metric computation (Sharpe etc.) → P2 consumes trade log.
- Python `risk_sim.py` → P2.
- C++ replay runner → P7.
- Real IBKR / Kraken fills → P3+.
- Reconciliation with existing vectorized engine → preserved as-is.

---

## Risk / Open Decisions

1. **Sentiment proxy** — live SignalAgent uses Featherless LLM. P1 backtest uses a
   deterministic momentum/VIX-based proxy; documented as approximation.
2. **KG query path** — backtest event engine queries Memgraph directly (same as live).
   Optionally cache a static export to avoid Docker requirement for development runs;
   flag this as a `--kg-export PATH` fallback if Memgraph is unreachable.
3. **`memory_practical.py`** — not maintained; any scratch prototyping happens in
   `tests/test_p1.py` or a throw-away notebook outside version control.
