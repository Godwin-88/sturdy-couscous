#pragma once

#include <string>
#include <optional>
#include <vector>
#include "risk/ApprovedOrder.hpp"
#include "graphalpha/portfolio_state.hpp"
#include "graphalpha/paper_fill.hpp"

namespace graphalpha {

class ExecutionEngine {
 public:
  ExecutionEngine(double fee_pct = 0.0026, double slip_pct = 0.0005)
      : fee_pct_(fee_pct), slip_pct_(slip_pct) {}

  void set_fee_slippage(double fee_pct, double slip_pct) {
    fee_pct_ = fee_pct;
    slip_pct_ = slip_pct;
  }

  FillResult execute(const risk::ApprovedOrder& order,
                     double current_price,
                     const std::string& timestamp);

 private:
  double fee_pct_;
  double slip_pct_;
};

}  // namespace graphalpha
