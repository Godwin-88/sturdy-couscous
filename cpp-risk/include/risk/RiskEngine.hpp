#pragma once

#include "risk/Signal.hpp"
#include "risk/ApprovedOrder.hpp"
#include "risk/Config.hpp"
#include <string>
#include <vector>
#include <optional>
#include <map>

namespace risk {

struct Position {
  std::string ticker;
  std::string venue;
  std::string asset_class;
  std::string sector;
  double notional = 0.0;
  double quantity = 0.0;
};

struct PortfolioState {
  double nav = 0.0;
  double cash = 0.0;
  double drawdown_from_peak = 0.0;
  bool halted = false;
  std::vector<Position> positions;
};

class RiskEngine {
public:
  explicit RiskEngine(const Config& cfg);

  ApprovedOrder evaluate(const Signal& signal, const PortfolioState& portfolio,
                         const std::optional<std::map<std::string, std::vector<double>>>& prices = std::nullopt);

  bool is_halted() const noexcept;
  void reset_halt();

private:
  Config cfg_;
  bool halted_ = false;

  double _compute_kelly(double score) const;
  bool _check_position_cap(const PortfolioState& pf, const Signal& sig, double target_notional) const;
  bool _check_sector_cap(const PortfolioState& pf, const Signal& sig, double target_notional) const;
  double _compute_var(const Signal& sig, const std::vector<double>& price_series, double notional) const;
  double _zscore(double confidence) const;
};

} // namespace risk
