# Plan: P0 — Schema v1 Definitions & Replay Export

## Overview
Implement the canonical, versioned data contract (Signal + ApprovedOrder + versioning policy) and the `replay_export.py` mechanism, grounded in actual codebase artifacts. No engine logic changes—only contracts, validation, and export.

---

## Step 1: Extract Canonical Artifacts from Codebase

Before writing code, collect the three inputs listed in `p0.md` "Dependencies / Inputs Needed Before P0 Can Be Marked Done"Section## Dependencies / Inputs Needed Before P0 Can Be Marked Done [108]: **Run the extraction queries / readings**: Regime list from master.cypher (already observed: 7 names), graph_path structure from signal_agent.py, and threshold constants from .env. No code changes yet; this step produces the authoritative values that drive all schema constraints. **Owner:** agent or scripts/verify_graph.py, with results stored in artifacts/ for cross-reference.

---

## Step 2: Schema Definition — `schemas/signal_schema_v1.json` and `schemas/order_schema_v1.json`

Create JSON Schema documents (Draft 2020-12) under a new `schemas/` directory.

### 2.1 Signal Schema
Fieldset exactly as specified in `docs/p0.md` Section## Feature 1 [19]:  `schema_version` (required integer, const=1), `cycle_id` (UUID string), `timestamp` (date-time), `regime` (enum from Step 1), `strategy` (str, minLength≥1), `ticker` (str), `venue` (enum: "kraken" | "ibkr"), `venue_symbol` (str), `asset_class` (enum: "equity_xstock" | "crypto" | "macro_proxy"), `direction` (enum: "buy" | "sell" | "hold"), `score` (number ∈ [-1,1]), `quant_score` (number ∈ [-1,1]), `sentiment_score` (number ∈ [-1,1]), `news_overlay` (number ∈ [-1,1], default 0.0), `macro_overlay` (number ∈ [-1,1], default 0.0), `kg_formula_contribution` (number ∈ [-1,1], default 0.0), `graph_path` (array of strings), `contradiction_blocked` (boolean).

Constraints:
- **Conditional**: if `asset_class` == "crypto" then `venue` != "ibkr"; if `asset_class` in ("equity_xstock","macro_proxy") then `venue` != "kraken". Express via `if`/`then` in JSON Schema.
- **hold-consistency**: if `direction` == "hold" then absolute value of `score` < `$threshold` (read threshold from config via an `$defs`/`$ref` dynamic anchor). The threshold itself lives in `.env` (TODO FusionThreshold) and is loaded at validation time, not baked into the schema file; the schema notes "must match config".
- **venue-asset cross-check**: cannot have crypto on ibkr, equity on kraken (per default routing rules in main spec `docs/quantprod.md` 4.3 [175]). 

### 2.2 ApprovedOrder Schema
Fieldset from `docs/p0.md` Section## Feature 2 [45]:  `schema_version` (const=1), `order_id` (UUID), `cycle_id` (UUID), `ticker` (str), `venue` (enum), `venue_symbol` (str), `direction` (enum: "buy" | "sell"), `quantity` (>0), `notional_usd` (>0), `kelly_fraction` [0, 0.5], `var_contribution_pct` [0,1], `mode` (enum: "paper" | "live"), `risk_checks` (object with `position_pct_ok`, `sector_pct_ok`, `var_ok` booleans, all required true).

Hard rule via JSON Schema `if`/`then`:
- **ibkr-paper lock**: `if` `venue` == "ibkr" `then` `mode` == "paper". A failed risk check (any sub-field false) makes the entire object invalid—reject before serialising.

### 2.3 Shared Validation Library
Add a new Python module `common/schema_validator.py` that:
- Loads both schema files at startup.
- Exposes `validate_signal(dict) -> None` and `validate_order(dict) -> None`, raising `ValueError` with a descriptive message on failure.
- Reads the fusion threshold from `.env` at validation time (dynamic value injection) to enforce the `hold` rule without hardcoding.

---

## Step 3: Versioning Policy — `docs/SCHEMA_POLICY.md`

Write a short, human-readable policy document (2-3 pages max) covering:
1. Every schema change (field add, enum change, range change) bumps `schema_version`.
2. Consumers declare a `MAX_SUPPORTED_SCHEMA_VERSION`; they must **reject** messages with a higher version rather than guess defaults.
3. Additive optional fields may still require a version bump if they affect risk/routing logic.
4. Flag the known v2 candidate: IBKR `venue_symbol` needs exchange/currency decomposition (e.g., `"XLE/SMART/USD"`) as noted in `docs/quantprod.md` 4.3 [175] and Section 5.6 [280].

Place at `docs/SCHEMA_POLICY.md`; reference from both schemas via `$comment`.

---

## Step 4: Signal Replay Export — `backtest/replay_export.py`

Implement a new module `backtest/replay_export.py` with:

- **`export_signals(signals: list[dict], metadata: dict, output_path: Path)`** — writes one JSON object per line (newline-delimited JSON / JSONL).
- **Stable ordering**: sort by `(timestamp, cycle_id, strategy)` before writing.
- **Per-signal validation**: every signal is passed through `validate_signal()` before being written. Invalid signals cause an abort with a clear error (not silent skip).
- **Metadata header**: one extra first line prefixed with `# META ` containing a JSON object with keys: `run_id` (UUID), `schema_version`, `date_range` (string "START→END"), `use_graph` (bool), `instrument_universe` (list), `signal_count`, `generated_at` (ISO8601). The C++ replay runner (P7) will read this to know what to expect.

Add a CLI entry point `python -m backtest.replay_export --help` with flags mirroring existing backtest CLI conventions.

---

## Step 5: Integrate Export into Existing Backtest

In `backtest/engine.py` and `backtest/metrics.py` (or new `ablation.py`):
- After `run_period` / `walk_forward_backtest` completes, if `--export-replay` flag is passed, call `replay_export.export_signals()` with the generated signals list and computed metadata.
- The export occurs **after** all overlays (news, macro, KG) but **before** metrics aggregation—signals must already be fully formed Schema v1 objects.

**New CLI flag**: `--export-replay PATH` (optional; default None).

---

## Step 6: Update Existing Orchestrator & Model Layer (Minimal Touch)

The orchestrator currently emits raw dicts without `schema_version`. For P0 we need Signals to carry `schema_version=1` before they hit RiskAgent/ExecutionAgent. The minimal change:

1. **In `agent/orchestrator.py`**: before passing `signals` to `risk_agent.run(signals=signals)`, normalise each signal dict to include `schema_version=1`, `cycle_id=self._tick_cycle_id` (generate a UUID at cycle start if not already), and `timestamp=now`. This is a single function `_normalise_signal(sig, cycle_id)` in `orchestrator.py`.

2. **In `agent/signal_agent.py` line 4071**: rename fields to match Schema v1:
   - `strategy_type` → `asset_class` (look up from a ticker→asset_class map, or carry forward from universe)
   - `kraken_pair` → `venue_symbol` (keep same value, rename key)
   - `reasoning` → remove (not in Schema v1; if needed, add back in v2)
   - add `schema_version`, `cycle_id`, `timestamp`, `venue`, `asset_class` defaults in the normaliser (not in SignalAgent itself, to keep backtest compat).

3. **In `agent/risk_agent.py`**: rename existing return keys to match ApprovedOrder schema:
   - `var_contribution` → `var_contribution_pct` (value unchanged; name clarity)
   - add `order_id`, `cycle_id`, `schema_version`, `venue`, `venue_symbol`, `mode`, `risk_checks` sub-fields in the approved dict.
   - Remove `price_estimate` from the serialised order (internal only).

4. **In `agent/execution_agent.py`**: do not change order handling—receive ApprovedOrder v1, pass through.

5. **In `api/models/signal.py`**: replace the Pydantic `Signal` model with one matching Schema v1. Add a `from_legacy(cls, raw: dict) -> "Signal"` class method for incremental migration.

---

## Step 7: Versioning Guards

Add a small utility `common/versioning.py`:
- `MAX_SUPPORTED_SCHEMA_VERSION = 1`
- `validate_schema_version(version: int)` raises if `version > max`.
- Both `SignalAgent` and `RiskAgent` call this before serialising/deserialising.

---

## Step 8: Tests

### 8.1 Schema Validation Tests (`tests/test_schemas.py`)
- **happy-path**: build a fully valid Signal dict and valid ApprovedOrder dict; both validate.
- **regime enum**: pass an invalid regime (e.g., `"GoblinMarket"`) — rejected.
- **venue/asset cross-check**: Signal with `asset_class:"crypto"`, `venue:"ibkr"` — rejected.
- **hold-consistency**: Signal with `direction:"hold"` and `score:0.5` with threshold `0.2` — rejected.
- **ibkr-paper lock**: order with `venue:"ibkr"`, `mode:"live"` — rejected.
- **risk-check guard**: order with `risk_checks.position_pct_ok:false` — rejected.
- **version bump**: Signal with `schema_version:2` — rejected by `validate_schema_version`.
- **hold-consistency dynamic**: confirm that changing `FUSION_THRESHOLD` in `.env` affects validation outcome.

### 8.2 Replay Export Tests (`tests/test_replay_export.py`)
- **deterministic ordering**: export the same list twice → byte-identical files.
- **metadata line**: first line starts with `# META ` and decodes to valid JSON.
- **invalid signal abort**: inserting one invalid signal raises and no file is written.
- **round-trip**: load the file back, every line (after header) validates.

---

## Step 9: Documentation

Update `README.md` to reference:
- `docs/SCHEMA_POLICY.md` (canonical versioning rules)
- `schemas/signal_schema_v1.json` and `schemas/order_schema_v1.json` (JSON Schema sources)
- The new CLI flag `--export-replay` in backtest usage.

---

## Out of Scope for P0 (confirmed unchanged)
- RiskEngine / ExecutionEngine C++ implementations (P3+)
- C++ replay runner (P7)
- IBKR `venue_symbol` exchange/currency decomposition (v2 candidate)
- Backtest strategy logic / overlays (P1/P2)
- Any Redis pub/sub refactor for orchestrator

---

## Success Criteria (from p0.md Section## Feature 1/2/3/4)

| Criterion | How Verified |
|---|---|
| All 19 Signal fields defined with types/ranges | JSON Schema doc |
| venue/asset enums | JSON Schema `enum` |
| Score bounds [-1,1] | JSON Schema `minimum`/`maximum` |
| crypto≠ibkr cross-check | JSON Schema `if`/`then` |
| hold-consistency rule | Dynamic validation from config |
| Regime enum = 7 KG names | Derived from master.cypher |
| graph_path format | Confirmed against signal_agent.py |
| cycle_id UUID | Schema `format: uuid` |
| schema_version required | Schema `required` + versioning guard |
| ApprovedOrder data model + risk_checks | JSON Schema, ordered dict |
| ibkr→paper hard lock | JSON Schema `if`/`then` |
| Risk check failure = no order | Validator rejects if any sub-field false |
| Versioning policy document | `docs/SCHEMA_POLICY.md` |
| v2 IBKR candidate flagged | Documented in policy |
| Replay export file format | JSONL with metadata header |
| Deterministic export ordering | Sorted by (timestamp, cycle_id, strategy) |
| Byte-identical reruns | Tests |
| Inline per-signal validation | Export calls validator |

---

## Files to Create / Modify

| Action | Path |
|---|---|
| CREATE | `schemas/signal_schema_v1.json` |
| CREATE | `schemas/order_schema_v1.json` |
| CREATE | `common/schema_validator.py` |
| CREATE | `common/versioning.py` |
| CREATE | `backtest/replay_export.py` |
| CREATE | `tests/test_schemas.py` |
| CREATE | `tests/test_replay_export.py` |
| CREATE | `docs/SCHEMA_POLICY.md` |
| MODIFY | `agent/orchestrator.py` (+30 lines: normalise + cycle_id UUID) |
| MODIFY | `agent/signal_agent.py` (field renames, add defaults) |
| MODIFY | `agent/risk_agent.py` (key renames, schema v1 fields on approved orders) |
| MODIFY | `api/models/signal.py` (replace with Schema v1 Pydantic model) |
| MODIFY | `backtest/engine.py` (add `--export-replay` flag, call export) |
| MODIFY | `README.md` (references to new docs) |

---

## Order of Work (Suggested Sequence)

1. **Extract artifacts** (Step 1) — populate `artifacts/regimes.json`, `artifacts/graph_path_example.json`, `artifacts/config_values.json`
2. **Write schemas** (Step 2) — JSON Schema documents + `common/schema_validator.py`
3. **Write versioning policy** (Step 3) — `docs/SCHEMA_POLICY.md`
4. **Implement replay export** (Step 4+5) — `backtest/replay_export.py` + integrate into `engine.py`
5. **Minimal orchestrator/signal/risk touches** (Step 6+7) — renames + `schema_version`/`cycle_id` carry
6. **Tests** (Step 8)
7. **Docs** (Step 9)
8. **Run `make test` and lint** before marking P0 done

---

## Clarifying Questions for User (if any)

1. **Fusion threshold config key**: `docs/p0.md` Section## Feature 1 424 says "referenced from config, not hardcoded". Should we add a new `.env` key like `FUSION_THRESHOLD_BUY` / `FUSION_THRESHOLD_SELL` or reuse the existing sell threshold in `signal_agent.py` line 160 (`sell_threshold = strategy.get("sell_threshold") or 0.35`)?
2. **graph_path format confirmation**: `p0.md` expects "sequence of alternating Concept/Relationship names", but current code (`signal_agent.py:102`) emits only concept names `[r["concept"] for r in results]`. Should the schema enforce alternating (Concept, RELATIONSHIP, Concept, ...) or accept the current plain-concept list?
3. **`asset_class` source**: Currently `signal_agent.py` has no `asset_class` field. Should we add a hardcoded `TICKER_ASSET_CLASS` map in P0, or is it acceptable to leave it configurable and populated by P1's `universe.py` (with a `"unknown"` placeholder in P0)?
4. **`news_overlay` / `macro_overlay` / `kg_formula_contribution` bounds**: `p0.md` says all bounded to [-1,1]. Current overlay code applies ±20% adjustments—should we validate that overlay values themselves stay within [-1,1] before writing, or is that a P2/overlay concern?
