#include "risk/ApprovedOrder.hpp"
#include "risk/Signal.hpp"
#include <stdexcept>

namespace risk {

std::optional<ApprovedOrder> ApprovedOrder::from_json(const nlohmann::json& j) {
  if (!j.contains("schema_version")) throw std::invalid_argument("missing schema_version");
  std::string ver = j["schema_version"].get<std::string>();
  if (ver != "1") throw std::invalid_argument("unsupported schema version: " + ver);
  ApprovedOrder o;
  o.schema_version = ver;
  if (!j.contains("cycle_id")) throw std::invalid_argument("missing cycle_id");
  o.cycle_id = j["cycle_id"].get<std::string>();
  if (!j.contains("signal_timestamp")) throw std::invalid_argument("missing signal_timestamp");
  o.signal_timestamp = j["signal_timestamp"].get<std::string>();
  if (!j.contains("order_timestamp")) throw std::invalid_argument("missing order_timestamp");
  o.order_timestamp = j["order_timestamp"].get<std::string>();
  if (!j.contains("ticker")) throw std::invalid_argument("missing ticker");
  o.ticker = j["ticker"].get<std::string>();
  if (!j.contains("venue")) throw std::invalid_argument("missing venue");
  o.venue = j["venue"].get<std::string>();
  if (!j.contains("direction")) throw std::invalid_argument("missing direction");
  o.direction = j["direction"].get<std::string>();
  o.quantity = j.value("quantity", 0.0);
  o.notional_usd = j.value("notional_usd", 0.0);
  o.kelly_fraction = j.value("kelly_fraction", 0.0);
  o.position_pct_ok = j.value("position_pct_ok", false);
  o.sector_pct_ok = j.value("sector_pct_ok", false);
  o.var_ok = j.value("var_ok", false);
  o.var_contribution_pct = j.value("var_contribution_pct", 0.0);
  o.risk_checks_all_passed = j.value("risk_checks_all_passed", false);
  o.rejection_reason = j.value("rejection_reason", "");
  return o;
}

nlohmann::json ApprovedOrder::to_json() const {
  nlohmann::json j;
  j["schema_version"] = schema_version;
  j["cycle_id"] = cycle_id;
  j["signal_timestamp"] = signal_timestamp;
  j["order_timestamp"] = order_timestamp;
  j["ticker"] = ticker;
  j["venue"] = venue;
  j["direction"] = direction;
  j["quantity"] = quantity;
  j["notional_usd"] = notional_usd;
  j["kelly_fraction"] = kelly_fraction;
  j["position_pct_ok"] = position_pct_ok;
  j["sector_pct_ok"] = sector_pct_ok;
  j["var_ok"] = var_ok;
  j["var_contribution_pct"] = var_contribution_pct;
  j["risk_checks_all_passed"] = risk_checks_all_passed;
  j["rejection_reason"] = rejection_reason;
  return j;
}

} // namespace risk
