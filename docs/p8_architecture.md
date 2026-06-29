# P8 Feature 3 — Architecture & Decision-Record Writeup

## System Architecture Summary

GraphAlpha employs a **dual-engine split** between research (Python) and production (C++), with a versioned signal contract as the integration seam.

```
Python Layer (Research/Agents)              C++ Layer (Risk/Execution)
──────────────────────────────────          ─────────────────────────
RegimeAgent → NewsAgent ──┐                
          → MacroAgent ─────┼─► Signal (v1) ──► RiskEngine ──► ExecutionEngine ──► Venues
          → KGSignalGenerator ─┘
          → SignalAgent (fusion)
          
Backtest Engine (optional)                   KrakenAdapter (paper/live)
     │                                         IBKRAdapter (paper only)
     └─► replay_export ────────────────────────► parity tests
```

## Key Design Decisions

### 1. Python/C++ Boundary (P0, P2, P3)

| Component | Layer | Rationale |
|-----------|-------|-----------|
| Signal generation, overlays | Python | Rapid iteration, LLM integration, pandas/numpy |
| Risk sizing (Kelly, VaR, caps) | C++ | Low-latency, numerically stable, FFI-safe |
| Order execution | C++ | Venue APIs require deterministic latency |

**Decision trace:** P0 defined Schema v1. P2 extracted `risk_sim.py` as Python reference. P3 implemented mirrored `RiskEngine` in C++ with 1e-6 tolerance.

### 2. Schema Versioning (P0, P23)

Signal objects carry `schema_version: 1`. The C++ engine rejects unsupported versions rather than guessing defaults.

**Cross-reference:** See `common/schema_validator.py` and `cpp-risk/include/graphalpha/signal.hpp`.

### 3. Multi-Venue Routing (P6)

Default venue assignment:
- `crypto` → Kraken
- `equity_xstock`, `macro_proxy` → IBKR

**Known limitation:** IBKR Gateway requires JVM (2-4GB RAM), increasing Docker host requirements.

**Decision trace:** P6 cross-venue sector tests enforce unified sector cap across venues (`RISK_MAX_SECTOR_PCT=0.40` applied to combined portfolio).

### 4. Overlay Architecture (P1, P2)

`news_overlay` and `macro_overlay` are stored as separate fields (not folded into `score`) to enable:
- Per-overlay ablation testing
- Sensitivity analysis to individual news/macro events

**Limitation:** Historical news corpus unavailable; `NewsOverlay.get()` returns neutral (0.0) in backtest. Documented in Feature 1 report.

### 5. Execution Fidelity Asymmetry (P6)

| Venue | Paper Mode Implementation |
|-------|--------------------------|
| Kraken | Internal slippage model (`BACKTEST_CRYPTO_SLIP_PCT`) |
| IBKR | Actual Gateway simulated fills |

This is a deliberate choice favoring IBKR fidelity over cross-venue consistency. Both are documented as paper in backtest metric metadata.

## Known Limitations

### Deferred Features
- **IBKR live trading**: Out of scope for P7; paper-only
- **Futures/FX macro exposure**: TLT proxy used only
- **Historical news sentiment**: Neutral pass-through in backtest
- **Guaranteed Redis delivery**: At-most-once delivery assumed

### Known Asymmetries
- Overlay backtest approximations (P1 Feature 3)
- IBKR vs Kraken fill model difference (P6)
- Venue symbol mapping v2 pending (P0 deferred question)

## Asset Class Coverage

| Class | Tickers | Venue | Status |
|-------|---------|-------|--------|
| equity_xstock | SPY, QQQ, XLF, XLE | IBKR | ✓ live paper |
| crypto | BTC-USD, ETH-USD | Kraken | ✓ live paper, live trading gated |
| macro_proxy | TLT, GLD | IBKR | ✓ paper only |

## Phase Completion Evidence

| Phase | Artifact | Verification |
|-------|----------|--------------|
| P3 | `cpp-risk/tests/test_parity.cpp` | 9 unit tests passing |
| P5 | `shadow_comparison` table | Schema verified |
| P6 | `tests/test_p6.py` | Cross-venue tests pass |
| P7 | `tests/test_p7.py` | 19 tests passing |