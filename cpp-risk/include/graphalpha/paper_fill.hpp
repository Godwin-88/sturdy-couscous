#pragma once

#include <string>
#include <optional>
#include <map>
#include <vector>
#include <nlohmann/json.hpp>

namespace graphalpha {

struct FillResult {
  std::string order_id;
  std::string ticker;
  std::string venue;
  std::string direction;
  double fill_price = 0.0;
  double fill_quantity = 0.0;
  double fee_usd = 0.0;
  double slippage_usd = 0.0;
  std::string timestamp;
  std::string mode = "paper";
  std::string status = "filled";
};

class PaperFillSimulator {
 public:
  static FillResult simulate(const risk::ApprovedOrder& order,
                             double current_price,
                             double fee_pct,
                             double slip_pct,
                             const std::string& timestamp) {
    FillResult fr;
    fr.order_id = order.cycle_id;
    fr.ticker = order.ticker;
    fr.venue = order.venue;
    fr.direction = order.direction;
    fr.fill_quantity = order.quantity;

    double slip = current_price * slip_pct * (order.direction == "buy" ? 1.0 : -1.0);
    fr.fill_price = current_price + slip;
    double notional = order.quantity * fr.fill_price;
    fr.fee_usd = notional * fee_pct;
    fr.slippage_usd = std::abs(slip * order.quantity);
    fr.timestamp = timestamp;
    return fr;
  }
};

}  // namespace graphalpha
