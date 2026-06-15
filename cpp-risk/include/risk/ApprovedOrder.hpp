#pragma once

#include "risk/Signal.hpp"
#include <string>
#include <optional>
#include "nlohmann/json.hpp"

namespace risk {

struct ApprovedOrder {
  std::string schema_version = "1";
  std::string cycle_id;
  std::string signal_timestamp;
  std::string order_timestamp;
  std::string ticker;
  std::string venue;
  std::string direction;
  double quantity = 0.0;
  double notional_usd = 0.0;
  double kelly_fraction = 0.0;
  bool position_pct_ok = false;
  bool sector_pct_ok = false;
  bool var_ok = false;
  double var_contribution_pct = 0.0;
  bool risk_checks_all_passed = false;
  std::string rejection_reason;

  // Factory: only creates a real order when checks pass (mirrors P0)
  static ApprovedOrder create(const Signal& signal, double quantity, double notional,
                              double kelly, bool pos_ok, bool sec_ok,
                              bool var_ok_val, double var_pct,
                              const std::string& ts) {
    ApprovedOrder o;
    o.schema_version = "1";
    o.cycle_id = signal.cycle_id;
    o.signal_timestamp = signal.timestamp;
    o.order_timestamp = ts;
    o.ticker = signal.ticker;
    o.venue = signal.venue;
    o.direction = direction_to_string(signal.direction);
    o.quantity = quantity;
    o.notional_usd = notional;
    o.kelly_fraction = kelly;
    o.position_pct_ok = pos_ok;
    o.sector_pct_ok = sec_ok;
    o.var_ok = var_ok_val;
    o.var_contribution_pct = var_pct;
    o.risk_checks_all_passed = pos_ok && sec_ok && var_ok_val;
    if (!o.risk_checks_all_passed) {
      if (!pos_ok) o.rejection_reason = "position_cap";
      else if (!sec_ok) o.rejection_reason = "sector_cap";
      else if (!var_ok_val) o.rejection_reason = "var_cap";
    }
    return o;
  }

  static ApprovedOrder rejection(const Signal& signal, const std::string& reason, const std::string& ts) {
    ApprovedOrder o;
    o.schema_version = "1";
    o.cycle_id = signal.cycle_id;
    o.signal_timestamp = signal.timestamp;
    o.order_timestamp = ts;
    o.ticker = signal.ticker;
    o.venue = signal.venue;
    o.direction = direction_to_string(signal.direction);
    o.rejection_reason = reason;
    o.risk_checks_all_passed = false;
    return o;
  }

  static std::optional<ApprovedOrder> from_json(const nlohmann::json& j);
  nlohmann::json to_json() const;
};

} // namespace risk
