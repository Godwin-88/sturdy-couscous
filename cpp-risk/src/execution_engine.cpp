#include "graphalpha/execution_engine.hpp"
#include "graphalpha/paper_fill.hpp"
#include <algorithm>

namespace graphalpha {

static double infer_fee_pct(const std::string& ticker) {
  if (ticker.find("-USD") != std::string::npos || 
      ticker == "BTC" || ticker == "ETH" || ticker == "XBT") {
    return 0.0026;
  }
  return 0.0010;
}

static double infer_slip_pct(const std::string& ticker) {
  if (ticker.find("-USD") != std::string::npos || 
      ticker == "BTC" || ticker == "ETH" || ticker == "XBT") {
    return 0.0010;
  }
  return 0.0005;
}

FillResult ExecutionEngine::execute(const risk::ApprovedOrder& order,
                                    double current_price,
                                    const std::string& timestamp) {
  double fee = infer_fee_pct(order.ticker);
  double slip = infer_slip_pct(order.ticker);
  return PaperFillSimulator::simulate(order, current_price, fee, slip, timestamp);
}

}  // namespace graphalpha
