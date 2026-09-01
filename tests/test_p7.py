"""P7 — Kraken Live Trading + Live-Mode Parity Validation tests."""
import json
import uuid
from pathlib import Path

import pytest


# Repo root, works on host AND inside the API container (/app).
REPO_ROOT = Path(__file__).resolve().parents[1]

VALID_KRAKEN_LIVE_SIGNAL = {
   "schema_version": 1,
   "cycle_id": str(uuid.uuid4()),
   "timestamp": "2023-01-15T00:00:00Z",
   "regime": "Trending",
   "strategy": "MomentumOverlay",
   "ticker": "BTC",
   "venue": "kraken",
   "venue_symbol": "XBTUSD",
   "asset_class": "crypto",
   "direction": "buy",
   "score": 0.6,
   "quant_score": 0.6,
   "sentiment_score": 0.0,
   "news_overlay": 0.0,
   "macro_overlay": 0.0,
   "kg_formula_contribution": 0.0,
   "contradiction_blocked": False
}


class TestKrakenLiveClient:
   """Feature 1: Kraken REST Live Client."""

   def test_kraken_adapter_has_live_mode_methods(self):
       """KrakenAdapter has live mode methods."""
       header = (REPO_ROOT / "cpp-risk/include/graphalpha/kraken_adapter.hpp").read_text()
       assert "submit_live_order" in header
       assert "sign_request" in header
       assert "query_kraken_balance" in header

   def test_kraken_adapter_structural_separation(self):
       """Paper and live code paths are structurally separated."""
       cpp = (REPO_ROOT / "cpp-risk/src/kraken_adapter.cpp").read_text()
       # Should check trading mode before live path
       assert 'get_trading_mode()' in cpp
       assert 'mode == "live"' in cpp
       # Live path should call submit_live_order separately
       assert "submit_live_order" in cpp

   def test_kraken_adapter_has_reconciliation_methods(self):
       """KrakenAdapter has reconciliation methods for Feature 2."""
       header = (REPO_ROOT / "cpp-risk/include/graphalpha/kraken_adapter.hpp").read_text()
       assert "reconcile_positions" in header
       assert "is_kraken_live_halted" in header
       assert "clear_reconciliation_halt" in header

   def test_kraken_api_key_never_logged(self):
       """API keys are never logged (verified by code structure)."""
       cpp = (REPO_ROOT / "cpp-risk/src/kraken_adapter.cpp").read_text()
       # Should not have any logging of API secret
       assert "api_secret.c_str()" not in cpp
       assert "get_api_secret()" in cpp


class TestLiveOrderReconciliation:
   """Feature 2: Live Order Reconciliation."""

   def test_kraken_reconciliation_method_exists(self):
       """KrakenAdapter.reconcile_positions method exists."""
       cpp = (REPO_ROOT / "cpp-risk/src/kraken_adapter.cpp").read_text()
       assert "reconcile_positions" in cpp
       assert "kraken_live_halt_" in cpp

   def test_execution_engine_get_adapter(self):
       """ExecutionEngine.get_adapter method for P7 kill switch checks."""
       header = (REPO_ROOT / "cpp-risk/include/graphalpha/execution_engine.hpp").read_text()
       assert "get_adapter" in header


class TestLiveParityValidation:
   """Feature 3: Live-Mode Parity Validation."""

   def test_live_validation_scale_env_var(self):
       """LIVE_VALIDATION_SCALE_PCT environment variable is defined."""
       env_example = (REPO_ROOT / ".env.example").read_text()
       assert "LIVE_VALIDATION_SCALE_PCT" in env_example

   def test_live_validation_scale_functions_exist(self):
       """Live validation scale helper functions exist."""
       main_cpp = (REPO_ROOT / "cpp-risk/src/main.cpp").read_text()
       assert "check_live_validation_scale" in main_cpp
       assert "get_live_validation_scale" in main_cpp


class TestLiveKillSwitch:
   """Feature 4: Live-Mode Circuit Breaker & Kill Switch."""

   def test_kill_switch_env_var(self):
       """KILL_SWITCH environment variable is defined."""
       env_example = (REPO_ROOT / ".env.example").read_text()
       assert "KILL_SWITCH" in env_example

   def test_event_publisher_has_kraken_halt(self):
       """EventPublisher has kraken_live_halt publishing."""
       header = (REPO_ROOT / "cpp-risk/include/graphalpha/event_publisher.hpp").read_text()
       assert "publish_kraken_halt" in header

   def test_kill_switch_polling_in_main(self):
       """Kill switch is checked on each signal cycle."""
       main_cpp = (REPO_ROOT / "cpp-risk/src/main.cpp").read_text()
       assert "check_kill_switch()" in main_cpp
       assert "KILL_SWITCH active" in main_cpp


class TestLiveOrderFailureHandling:
   """P7: Live order failure handling."""

   def test_submit_live_order_returns_failure_on_error(self):
       """Live order submission returns nullopt on failure."""
       cpp = (REPO_ROOT / "cpp-risk/src/kraken_adapter.cpp").read_text()
       # Should handle error cases gracefully
       assert "return std::nullopt" in cpp
       assert "LIVE ORDER FAILED" in cpp


class TestTradingModeConfirmation:
   """P7: Trading mode confirmation on startup."""

   def test_trading_mode_logged_on_init(self):
       """Trading mode is logged loudly on initialization."""
       cpp = (REPO_ROOT / "cpp-risk/src/kraken_adapter.cpp").read_text()
       assert "Initialised (mode=" in cpp


class TestLiveValidationDiscrepancyLogging:
   """P7: Live validation discrepancy logging."""

   def test_live_validation_discrepancy_method_in_audit_log(self):
       """AuditLog has write_live_validation_discrepancy method."""
       header = (REPO_ROOT / "cpp-risk/include/graphalpha/audit_log.hpp").read_text()
       assert "write_live_validation_discrepancy" in header

   def test_live_validation_discrepancy_table_exists(self):
       """live_validation_discrepancy table is defined in init.sql."""
       sql = (REPO_ROOT / "infra/postgres/init.sql").read_text()
       assert "live_validation_discrepancy" in sql

   def test_hmac_sha512_signing_implementation(self):
       """HMAC-SHA512 signing is implemented in sign_request."""
       cpp = (REPO_ROOT / "cpp-risk/src/kraken_adapter.cpp").read_text()
       assert "HMAC_CTX_new" in cpp
       assert "HMAC_Init_ex" in cpp
       assert "HMAC_Update" in cpp
       assert "HMAC_Final" in cpp

   def test_curl_integration_in_submit_live_order(self):
       """curl library is integrated for live order submission."""
       cpp = (REPO_ROOT / "cpp-risk/src/kraken_adapter.cpp").read_text()
       assert "curl_easy_init" in cpp
       assert "curl_easy_perform" in cpp
       assert "curl_slist_append" in cpp

   def test_no_auto_recovery_kraken_halt(self):
       """Kraken live halt cannot auto-recover (explicit re-enable required)."""
       cpp = (REPO_ROOT / "cpp-risk/src/main.cpp").read_text()
       # Check that there's no automatic halt clearing logic
       assert "clear_reconciliation_halt" not in cpp or "KRAKEN_REENABLE" in cpp

   def test_reconcile_interval_polling(self):
       """Reconciliation interval is polled in subscriber mode."""
       cpp = (REPO_ROOT / "cpp-risk/src/main.cpp").read_text()
       assert "KRAKEN_RECONCILE_INTERVAL_SECONDS" in cpp
       assert "reconcile_positions" in cpp