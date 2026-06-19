#pragma once

#include <string>
#include <optional>
#include <vector>
#include "risk/RiskEngine.hpp"
#include "nlohmann/json.hpp"

namespace risk {

class PortfolioLoader {
 public:
  static std::optional<PortfolioState> load_from_postgres(const std::string& conn_str);
  static bool persist_portfolio(const std::string& conn_str,
                                const PortfolioState& pf);
  static std::string make_order_id();
};

}  // namespace risk
