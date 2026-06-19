#include "risk/ApprovedOrder.hpp"
#include "risk/Signal.hpp"
#include <stdexcept>

namespace risk {

std::optional<ApprovedOrder> ApprovedOrder::from_json(const nlohmann::json& j) {
  if (!j.contains("schema_version")) throw std::invalid_argument("missing schema_version");
  int ver = j["schema_version"].get<int>();
  if (ver != 1) throw std::invalid_argument("unsupported schema version: " + std::to_string(ver));
  ApprovedOrder o;
  o.schema_version = ver;
  o.order_id = j.value("order_id", "");
  o.cycle_id = j.value("cycle_id", "");
  o.ticker = j.value("ticker", "");
  o.venue = j.value("venue", "");
  o.venue_symbol = j.value("venue_symbol", "");
  o.direction = j.value("direction", "");
  o.quantity = j.value("quantity", 0.0);
  o.notional_usd = j.value("notional_usd", 0.0);
  o.kelly_fraction = j.value("kelly_fraction", 0.0);
  o.var_contribution_pct = j.value("var_contribution_pct", 0.0);
  o.mode = j.value("mode", "paper");

  if (j.contains("risk_checks")) {
    o.risk_checks = RiskChecks::from_json(j["risk_checks"]);
    o.risk_checks_all_passed = o.risk_checks.position_pct_ok &&
                               o.risk_checks.sector_pct_ok &&
                               o.risk_checks.var_ok;
  }
  o.rejection_reason = j.value("rejection_reason", "");
  return o;
}

nlohmann::json ApprovedOrder::to_json() const {
  nlohmann::json j;
  j["schema_version"] = schema_version;
  j["order_id"] = order_id;
  j["cycle_id"] = cycle_id;
  j["ticker"] = ticker;
  j["venue"] = venue;
  j["venue_symbol"] = venue_symbol;
  j["direction"] = direction;
  j["quantity"] = quantity;
  j["notional_usd"] = notional_usd;
  j["kelly_fraction"] = kelly_fraction;
  j["var_contribution_pct"] = var_contribution_pct;
  j["mode"] = mode;
  j["risk_checks"] = risk_checks.to_json();
  return j;
}

} // namespace risk
