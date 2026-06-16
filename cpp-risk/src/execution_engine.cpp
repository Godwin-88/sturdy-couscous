#include "graphalpha/execution_engine.hpp"
#include "graphalpha/paper_fill.hpp"

namespace graphalpha {

FillResult ExecutionEngine::execute(const risk::ApprovedOrder& order,
                                    double current_price,
                                    const std::string& timestamp) {
  return PaperFillSimulator::simulate(order, current_price, fee_pct_, slip_pct_, timestamp);
}

}  // namespace graphalpha
