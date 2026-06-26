#include "risk/RiskEngine.hpp"
#include "risk/Signal.hpp"
#include <cmath>
#include <algorithm>
#include <stdexcept>
#include <numeric>
#include <random>

namespace risk {

RiskEngine::RiskEngine(const Config& cfg) : cfg_(cfg) {}

bool RiskEngine::is_halted() const noexcept { return halted_; }
void RiskEngine::reset_halt() { halted_ = false; }

double RiskEngine::_compute_kelly(double score) const {
  double abs_score = std::abs(score);
  if (abs_score < 1e-12) return 0.0;
  double p_win = 0.5 + 0.25 * abs_score;
  double kelly = (p_win * 1.5 - (1.0 - p_win)) / 1.5;
  kelly = std::max(0.0, kelly) / 2.0; // half-Kelly
  return std::min(kelly, cfg_.kelly_fraction);
}

bool RiskEngine::_check_position_cap(const PortfolioState& pf, const Signal& sig, double target_notional) const {
  double existing = 0.0;
  for (const auto& p : pf.positions) {
    if (p.ticker == sig.ticker) existing += p.notional;
  }
  return (existing + target_notional) / pf.nav <= cfg_.max_position_pct + 1e-12;
}

static std::string ticker_to_sector(const std::string& ticker) {
  std::string t = ticker;
  for (char& c : t) c = std::toupper(c);
  if (t == "QQQ") return "equity_tech";
  if (t == "SPY") return "equity_broad";
  if (t == "XLF") return "equity_financials";
  if (t == "XLE") return "equity_energy";
  if (t.find("-USD") != std::string::npos) return "";
  return "equity_broad";
}

bool RiskEngine::_check_sector_cap(const PortfolioState& pf, const Signal& sig, double target_notional) const {
   std::string sector = ticker_to_sector(sig.ticker);
   if (sector.empty()) return true;
   double existing = 0.0;
   for (const auto& p : pf.positions) {
     std::string pos_sector = p.sector.empty() ? ticker_to_sector(p.ticker) : p.sector;
     if (pos_sector == sector) existing += p.notional;
   }
   return (existing + target_notional) / pf.nav <= cfg_.max_sector_pct + 1e-12;
 }

double RiskEngine::_zscore(double confidence) const {
  // Approximate inverse normal CDF using rational approximation (Abramowitz & Stegun)
  if (confidence <= 0.0 || confidence >= 1.0) return 1e12;
  if (confidence > 0.5) return _zscore(1.0 - confidence);
  double t = std::sqrt(-2.0 * std::log(confidence));
  double c0 = 2.515517, c1 = 0.802853, c2 = 0.010328;
  double d1 = 1.432788, d2 = 0.189269, d3 = 0.001308;
  return t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t);
}

double RiskEngine::_compute_var(const Signal& sig, const std::vector<double>& prices, double notional) const {
  if (prices.size() < 2) return 0.0;
  std::vector<double> rets;
  rets.reserve(prices.size() - 1);
  for (size_t i = 1; i < prices.size(); ++i) {
    if (prices[i - 1] != 0.0) rets.push_back((prices[i] - prices[i - 1]) / prices[i - 1]);
  }
  if (rets.empty()) return 0.0;
  double mean = std::accumulate(rets.begin(), rets.end(), 0.0) / rets.size();
  double var = 0.0;
  for (double r : rets) {
    double d = r - mean;
    var += d * d;
  }
  var /= rets.size();
  double stdev = std::sqrt(var);
  double z = _zscore(cfg_.var_confidence);
  double var_abs = z * stdev * notional;
  return (cfg_.nav > 0.0) ? std::abs(var_abs) / cfg_.nav : 0.0;
}

ApprovedOrder RiskEngine::evaluate(const Signal& signal, const PortfolioState& portfolio,
                                   const std::optional<std::map<std::string, std::vector<double>>>& prices) {
  // Use portfolio nav as reference for caps
  Config mutable_cfg = cfg_;
  mutable_cfg.nav = portfolio.nav;

  // Hold / zero score => no order
  if (signal.direction == Direction::Hold || std::abs(signal.score) < 1e-12) {
    return ApprovedOrder::rejection(signal, "no_signal", "1970-01-01T00:00:00Z");
  }

  // Circuit breaker
  if (portfolio.drawdown_from_peak >= mutable_cfg.max_drawdown_halt - 1e-12) {
    halted_ = true;
    return ApprovedOrder::rejection(signal, "halted", "1970-01-01T00:00:00Z");
  }

  double kelly = _compute_kelly(signal.score);
  if (kelly <= 0.0) {
    return ApprovedOrder::rejection(signal, "kelly_zero", "1970-01-01T00:00:00Z");
  }

  // Price needed for sizing/VAR
  double price = 100.0; // default placeholder if no prices provided
  if (prices && prices->contains(signal.ticker)) {
    const auto& series = (*prices).at(signal.ticker);
    if (!series.empty()) price = series.back();
  }
  if (price <= 0.0) {
    return ApprovedOrder::rejection(signal, "no_price", "1970-01-01T00:00:00Z");
  }

  double target_notional = portfolio.nav * kelly * mutable_cfg.max_position_pct;
  double quantity = target_notional / price;

  bool pos_ok = _check_position_cap(portfolio, signal, target_notional);
  bool sec_ok = _check_sector_cap(portfolio, signal, target_notional);

  double var_pct = 0.0;
  if (prices && prices->contains(signal.ticker)) {
    var_pct = _compute_var(signal, (*prices).at(signal.ticker), target_notional);
  }
  bool var_ok = var_pct <= mutable_cfg.max_var_pct + 1e-12;

  std::string ts = "1970-01-01T00:00:00Z";
  return ApprovedOrder::create(signal, quantity, target_notional, kelly, pos_ok, sec_ok, var_ok, var_pct, ts);
}

} // namespace risk