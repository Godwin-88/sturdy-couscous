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
   ExecutionEngine() = default;

   void set_fee_slippage(double fee_pct, double slip_pct) {
     fee_pct_ = fee_pct;
     slip_pct_ = slip_pct;
   }

   FillResult execute(const risk::ApprovedOrder& order,
                      double current_price,
                      const std::string& timestamp);

  private:
   double fee_pct_ = 0.0026;  // crypto default
   double slip_pct_ = 0.0005;
};

}  // namespace graphalpha
