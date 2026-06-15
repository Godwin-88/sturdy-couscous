# Schema Versioning Policy — GraphAlpha

**Applies to:** `Signal` (Schema v1) and `ApprovedOrder` (Schema v1)  
**Status:** Active since P0 completion  
**Owner:** GraphAlpha maintainers

---

## 1. Purpose

The `Signal` and `ApprovedOrder` JSON contracts are the seam between the Python research/agent layer and the C++ risk/execution layer. This policy ensures that schema evolution does not silently drift, and that both sides can reliably detect incompatibilities before they manifest as incorrect risk decisions or lost audit trails.

---

## 2. Version Bump Rules

Every breaking or semantically meaningful change to either schema **must** increment `schema_version`. The following changes require a version bump, even if they are "only additive":

| Change Type | Version Bump Required? |
|---|---|
| Adding a new required field | Yes |
| Adding a new optional field with a safe default | **Yes**, if the field affects risk, routing, or sizing logic |
| Changing an enum's valid values (add or remove) | Yes |
| Changing a numeric range (min/max) | Yes |
| Changing a field from optional to required (or vice versa) | Yes |
| Renaming or removing a field | Yes |
| Adding a new optional field that is purely informational (e.g., debug metadata) | No — but document it in the changelog |

**Rationale:** Optional fields with safe defaults can still change downstream behaviour if a consumer starts relying on them. The conservative rule prevents accidental semantic drift.

---

## 3. Consumer Behaviour — Reject, Don't Guess

Both the Python and C++ sides must declare the maximum schema version they support:

```python
MAX_SUPPORTED_SCHEMA_VERSION = 1  # bump when implementing new schema
```

When a message arrives with `schema_version > MAX_SUPPORTED_SCHEMA_VERSION`:

1. **Reject** the message outright.
2. **Log** the rejection with the offending version and message identifier.
3. **Do not** attempt to parse with guessed defaults or "best-effort" field mapping.

Accepting a message with an unknown schema version is a bug, not a feature.

---

## 4. v2 Candidate: IBKR `venue_symbol` Decomposition

**Flagged change:** The current `venue_symbol` field holds a single string (e.g., `"XLEUSD"` for Kraken, `"XLE"` for IBKR). For IBKR integration, the contract will likely need to decompose this into `(symbol, exchange, currency)` — e.g., `"XLE/SMART/USD"`.

**Impact:**
- `venue_symbol` will change type from `string` to `object` or become a structured string.
- This affects both `Signal` and `ApprovedOrder` schemas.
- A version bump to `2` is required.

**Decision deadline:** Before P6 (IBKR adapter implementation).

---

## 5. Changelog

| Version | Date | Summary |
|---|---|---|
| 1 | P0 | Initial schema: Signal + ApprovedOrder + versioning policy. 7-regime enum from master.cypher. IBKR paper-only hard lock. |

---

## 6. Related Documents

- `schemas/signal_schema_v1.json` — canonical Signal JSON Schema
- `schemas/approved_order_schema_v1.json` — canonical ApprovedOrder JSON Schema
- `common/schema_validator.py` — Python validation implementation used by both engines
- `common/versioning.py` — `MAX_SUPPORTED_SCHEMA_VERSION` constant and guard
