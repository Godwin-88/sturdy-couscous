#include "risk/Config.hpp"
#include <cstdlib>
#include <stdexcept>
#include <string>

namespace risk {

Config::Config() {
  kelly_fraction = std::stod(std::getenv("AGENT_KELLY_FRACTION") ? std::getenv("AGENT_KELLY_FRACTION") : "0.5");
  max_position_pct = std::stod(std::getenv("AGENT_MAX_POSITION_PCT") ? std::getenv("AGENT_MAX_POSITION_PCT") : "0.20");
  max_sector_pct = std::stod(std::getenv("RISK_MAX_SECTOR_PCT") ? std::getenv("RISK_MAX_SECTOR_PCT") : "0.40");
  var_confidence = std::stod(std::getenv("RISK_VAR_CONFIDENCE") ? std::getenv("RISK_VAR_CONFIDENCE") : "0.99");
  max_var_pct = std::stod(std::getenv("RISK_MAX_VAR_PCT") ? std::getenv("RISK_MAX_VAR_PCT") : "0.05");
  max_drawdown_halt = std::stod(std::getenv("AGENT_MAX_DRAWDOWN_HALT") ? std::getenv("AGENT_MAX_DRAWDOWN_HALT") : "0.10");
}

} // namespace risk
