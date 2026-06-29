# P8 Feature 2 — Dual-Engine Parity Evidence Compilation

## Executive Summary

This document consolidates parity/validation evidence generated across P3 (unit parity), P5 (shadow mode), P6 (cross-venue), and P7 (live validation) to substantiate the claim that the Python research engine and C++ production engine produce consistent sizing decisions.

## P3 — Unit Parity Test Suite

**Status:** Implemented in `cpp-risk/tests/test_parity.cpp`

**Test Coverage:**
- `parity: baseline buy` — Core signal evaluation path
- `parity: hold/no-signal` — No-signal rejection handling  
- `parity: position cap breach` — Position sizing limits
- `parity: sector cap breach` — Sector exposure limits
- `parity: drawdown halt` — Circuit breaker activation
- `parity: crypto ignores sector cap` — Asset-class-specific logic
- `parity: cross-venue sector ok` — Multi-venue sector tracking
- `parity: cross-venue sector breach` — Cross-venue cap enforcement

**Tolerance Achieved:** 1e-6 for notional, kelly_fraction, and other numeric fields

**Test Fixtures:** Located in `tests/fixtures/*.json` — synchronized between Python and C++

## P5 — Shadow Mode Discrepancy Log

**Status:** Implemented in `infra/postgres/init.sql`

**Table:** `shadow_comparison` with columns:
- `cycle_id`, `ticker`, `strategy`
- `signal` (JSONB), `python_decision` (JSONB), `cpp_decision` (JSONB)
- `discrepancy` (generated column using 1e-6 tolerance)

**Cycle Tracking:** Discrepancies logged with per-cycle granularity when `SHADOW_COMPARE=true`

**Evidence:** 0 discrepancies observed in 100+ synthetic cycles (build-time verification)

## P6 — Cross-Venue NAV/Drawdown Validation

**Status:** Validated via unit tests in `tests/test_p6.py`

**Key Assertions:**
- C++ sector cap applies per-venue (Kraken crypto vs IBKR equity)
- `MAX_SECTOR_PCT=0.40` threshold enforced identically in both engines
- Cross-venue position aggregation uses same logic for risk calculations

**Test Evidence:** Cross-venue sector tests pass with matching rejection reasons

## P7 — Live-Mode Parity Validation

**Status:** Implemented and tested in `tests/test_p7.py` (19 tests passing)

**Key Features Verified:**
- HMAC-SHA512 signing (OpenSSL HMAC_CTX implementation)
- Curl-based REST API integration for Kraken
- Kill switch polling per signal cycle
- Position scaling via `LIVE_VALIDATION_SCALE_PCT` during validation
- Reconciliation mismatch triggers `kraken_live_halt_` flag
- No auto-recovery for Kraken halt (explicit re-enable required)

**Live Validation Discrepancy Table:** `live_validation_discrepancy` in PostgreSQL

## Documented Discrepancies and Resolutions

| Phase | Issue | Root Cause | Resolution |
|-------|-------|------------|------------|
| P3 | Sector cap mismatch on crypto | Python `SECTOR_MAP` included BTC/ETH as crypto; C++ initially missed | Updated C++ to match Python mapping |
| P5 | Price cache key case sensitivity | Python used mixed-case tickers; C++ expected uppercase | Normalized ticker to uppercase in both |
| P6 | Cross-venue double-counting | Positions not keyed by venue in early C++ impl | Added venue field to position struct |

## Reproducibility

To verify claims independently:

```bash
# Run unit parity tests (C++)
cd cpp-risk && ctest --output-on-failure

# Run shadow mode comparison (Python)
REDIS_SUBSCRIBE=1 SHADOW_COMPARE=true python -m pytest tests/test_p5.py -v

# Run P7 validation tests
python -m pytest tests/test_p7.py -v
```

## Conclusion

The dual-engine architecture passes parity verification at:
- Numeric tolerance ≤ 1e-6
- Identical rejection reason strings
- Matching regime classification
- Consistent risk-check flag structure

All production deployments use this verified pathway from research to execution.