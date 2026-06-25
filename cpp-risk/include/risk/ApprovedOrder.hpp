#pragma once

#include "risk/Signal.hpp"
#include <string>
#include <optional>
#include "nlohmann/json.hpp"

namespace risk {

struct RiskChecks {
  bool position_pct_ok = false;
  bool sector_pct_ok = false;
  bool var_ok = false;

  nlohmann::json to_json() const {
    return {
      {"position_pct_ok", position_pct_ok},
      {"sector_pct_ok", sector_pct_ok},
      {"var_ok", var_ok}
    };
  }

  static RiskChecks from_json(const nlohmann::json& j) {
    RiskChecks rc;
    rc.position_pct_ok = j.value("position_pct_ok", false);
    rc.sector_pct_ok = j.value("sector_pct_ok", false);
    rc.var_ok = j.value("var_ok", false);
    return rc;
  }
};

struct ApprovedOrder {
  int schema_version = 1;
  std::string order_id;
  std::string cycle_id;
  std::string ticker;
  std::string venue;
  std::string venue_symbol;
  std::string direction;
  double quantity = 0.0;
  double notional_usd = 0.0;
  double kelly_fraction = 0.0;
  double var_contribution_pct = 0.0;
  std::string mode = "paper";
  RiskChecks risk_checks;

// Internal fields (not in schema)
   bool risk_checks_all_passed = false;
   std::string rejection_reason;
   std::string signal_timestamp;
   std::string order_timestamp;

   // Convenience accessors matching test expectations
   bool sector_pct_ok() const { return risk_checks.sector_pct_ok; }
   bool position_pct_ok() const { return risk_checks.position_pct_ok; }

   // Factory: only creates a real order when checks pass (mirrors P0)
  static ApprovedOrder create(const Signal& signal, double quantity, double notional,
                               double kelly, bool pos_ok, bool sec_ok,
                               bool var_ok_val, double var_pct,
                               const std::string& ts, const std::string& order_id = "") {
    ApprovedOrder o;
    o.schema_version = 1;
    o.order_id = order_id;
    o.cycle_id = signal.cycle_id;
    o.ticker = signal.ticker;
    o.venue = signal.venue;
    o.venue_symbol = signal.venue_symbol;
    o.direction = direction_to_string(signal.direction);
    o.quantity = quantity;
    o.notional_usd = notional;
    o.kelly_fraction = kelly;
    o.var_contribution_pct = var_pct;
    o.mode = "paper";
    o.risk_checks.position_pct_ok = pos_ok;
    o.risk_checks.sector_pct_ok = sec_ok;
    o.risk_checks.var_ok = var_ok_val;
    o.risk_checks_all_passed = pos_ok && sec_ok && var_ok_val;
    o.signal_timestamp = signal.timestamp;
    o.order_timestamp = ts;

    if (!o.risk_checks_all_passed) {
      if (!pos_ok) o.rejection_reason = "position_cap";
      else if (!sec_ok) o.rejection_reason = "sector_cap";
      else if (!var_ok_val) o.rejection_reason = "var_cap";
    }
    return o;
  }

  static ApprovedOrder rejection(const Signal& signal, const std::string& reason, const std::string& ts) {
    ApprovedOrder o;
    o.schema_version = 1;
    o.cycle_id = signal.cycle_id;
    o.ticker = signal.ticker;
    o.venue = signal.venue;
    o.venue_symbol = signal.venue_symbol;
    o.direction = direction_to_string(signal.direction);
    o.rejection_reason = reason;
    o.risk_checks_all_passed = false;
    o.mode = "paper";
    o.signal_timestamp = signal.timestamp;
    o.order_timestamp = ts;
    return o;
  }

  static std::optional<ApprovedOrder> from_json(const nlohmann::json& j);
  nlohmann::json to_json() const;
};

} // namespace risk
