#pragma once

#include <string>

namespace risk {

struct Config {
  double kelly_fraction = 0.5;
  double max_position_pct = 0.20;
  double max_sector_pct = 0.40;
  double var_confidence = 0.99;
  double max_var_pct = 0.05;
  double max_drawdown_halt = 0.10;
  double nav = 0.0;  // set from portfolio at evaluation time

  Config();
};

} // namespace risk
