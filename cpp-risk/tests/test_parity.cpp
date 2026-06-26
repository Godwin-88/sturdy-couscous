#define CATCH_CONFIG_MAIN
#include <catch2/catch_test_macros.hpp>
#include "risk/Config.hpp"
#include "risk/Signal.hpp"
#include "risk/ApprovedOrder.hpp"
#include "risk/RiskEngine.hpp"
#include <fstream>
#include <sstream>
#include <string>
#include <map>
#include <vector>

using namespace risk;

static std::string slurp(const std::string& path) {
  std::ifstream f(path);
  if (!f) throw std::runtime_error("cannot open " + path);
  std::ostringstream ss;
  ss << f.rdbuf();
  return ss.str();
}

static nlohmann::json load_json(const std::string& absolute_path) {
  std::ifstream f(absolute_path);
  if (!f) throw std::runtime_error("cannot open " + absolute_path);
  nlohmann::json j;
  f >> j;
  return j;
}

TEST_CASE("parity: baseline buy", "[parity]") {
  auto fixture = load_json("/workspace/tests/fixtures/baseline_portfolio.json");
  auto sig_opt = Signal::from_json(fixture["signal"]);
  REQUIRE(sig_opt.has_value());
  Signal sig = *sig_opt;
  PortfolioState pf;
  pf.nav = fixture["portfolio"]["nav"].get<double>();
  pf.cash = fixture["portfolio"]["cash"].get<double>();
  pf.drawdown_from_peak = fixture["portfolio"]["drawdown_from_peak"].get<double>();
  std::map<std::string, std::vector<double>> prices;
  for (auto& [k, v] : fixture["prices"].items()) {
    prices[k] = v.get<std::vector<double>>();
  }
  Config cfg;
  RiskEngine engine(cfg);
  auto order = engine.evaluate(sig, pf, prices);
  CHECK(order.risk_checks_all_passed == fixture["expected"]["risk_checks_all_passed"].get<bool>());
  CHECK(order.rejection_reason == fixture["expected"]["rejection_reason"].get<std::string>());
}

TEST_CASE("parity: hold/no-signal", "[parity]") {
  auto fixture = load_json("/workspace/tests/fixtures/signal_hold.json");
  auto sig_opt = Signal::from_json(fixture["signal"]);
  REQUIRE(sig_opt.has_value());
  Signal sig = *sig_opt;
  PortfolioState pf;
  pf.nav = fixture["portfolio"]["nav"].get<double>();
  pf.cash = fixture["portfolio"]["cash"].get<double>();
  pf.drawdown_from_peak = fixture["portfolio"]["drawdown_from_peak"].get<double>();
  std::map<std::string, std::vector<double>> prices;
  for (auto& [k, v] : fixture["prices"].items()) {
    prices[k] = v.get<std::vector<double>>();
  }
  Config cfg;
  RiskEngine engine(cfg);
  auto order = engine.evaluate(sig, pf, prices);
  CHECK(order.rejection_reason == "no_signal");
  CHECK(!order.risk_checks_all_passed);
}

TEST_CASE("parity: position cap breach", "[parity]") {
  auto fixture = load_json("/workspace/tests/fixtures/position_cap_breach.json");
  auto sig_opt = Signal::from_json(fixture["signal"]);
  REQUIRE(sig_opt.has_value());
  Signal sig = *sig_opt;
  PortfolioState pf;
  pf.nav = fixture["portfolio"]["nav"].get<double>();
  pf.cash = fixture["portfolio"]["cash"].get<double>();
  pf.drawdown_from_peak = fixture["portfolio"]["drawdown_from_peak"].get<double>();
  for (auto& p : fixture["portfolio"]["positions"]) {
    pf.positions.push_back(Position{
      p["ticker"].get<std::string>(),
      p["venue"].get<std::string>(),
      p["asset_class"].get<std::string>(),
      p["sector"].get<std::string>(),
      p["quantity"].get<double>(),
      p["notional"].get<double>()
    });
  }
  std::map<std::string, std::vector<double>> prices;
  for (auto& [k, v] : fixture["prices"].items()) {
    prices[k] = v.get<std::vector<double>>();
  }
  Config cfg;
  RiskEngine engine(cfg);
  auto order = engine.evaluate(sig, pf, prices);
  CHECK(order.rejection_reason == "position_cap");
  CHECK(!order.position_pct_ok());
}

TEST_CASE("parity: sector cap breach", "[parity]") {
  auto fixture = load_json("/workspace/tests/fixtures/sector_cap_breach.json");
  auto sig_opt = Signal::from_json(fixture["signal"]);
  REQUIRE(sig_opt.has_value());
  Signal sig = *sig_opt;
  PortfolioState pf;
  pf.nav = fixture["portfolio"]["nav"].get<double>();
  pf.cash = fixture["portfolio"]["cash"].get<double>();
  pf.drawdown_from_peak = fixture["portfolio"]["drawdown_from_peak"].get<double>();
  for (auto& p : fixture["portfolio"]["positions"]) {
    pf.positions.push_back(Position{
      p["ticker"].get<std::string>(),
      p["venue"].get<std::string>(),
      p["asset_class"].get<std::string>(),
      p["sector"].get<std::string>(),
      p["quantity"].get<double>(),
      p["notional"].get<double>()
    });
  }
  std::map<std::string, std::vector<double>> prices;
  for (auto& [k, v] : fixture["prices"].items()) {
    prices[k] = v.get<std::vector<double>>();
  }
  Config cfg;
  RiskEngine engine(cfg);
  auto order = engine.evaluate(sig, pf, prices);
  CHECK(order.rejection_reason == "sector_cap");
  CHECK(!order.sector_pct_ok());
}

TEST_CASE("parity: drawdown halt", "[parity]") {
  auto fixture = load_json("/workspace/tests/fixtures/drawdown_halt.json");
  auto sig_opt = Signal::from_json(fixture["signal"]);
  REQUIRE(sig_opt.has_value());
  Signal sig = *sig_opt;
  PortfolioState pf;
  pf.nav = fixture["portfolio"]["nav"].get<double>();
  pf.cash = fixture["portfolio"]["cash"].get<double>();
  pf.drawdown_from_peak = fixture["portfolio"]["drawdown_from_peak"].get<double>();
  std::map<std::string, std::vector<double>> prices;
  for (auto& [k, v] : fixture["prices"].items()) {
    prices[k] = v.get<std::vector<double>>();
  }
  Config cfg;
  RiskEngine engine(cfg);
  auto order = engine.evaluate(sig, pf, prices);
  CHECK(order.rejection_reason == "halted");
  CHECK(engine.is_halted());
}

TEST_CASE("parity: crypto ignores sector cap", "[parity]") {
  auto fixture = load_json("/workspace/tests/fixtures/crypto_ignore_sector.json");
  auto sig_opt = Signal::from_json(fixture["signal"]);
  REQUIRE(sig_opt.has_value());
  Signal sig = *sig_opt;
  PortfolioState pf;
  pf.nav = fixture["portfolio"]["nav"].get<double>();
  pf.cash = fixture["portfolio"]["cash"].get<double>();
  pf.drawdown_from_peak = fixture["portfolio"]["drawdown_from_peak"].get<double>();
  std::map<std::string, std::vector<double>> prices;
  for (auto& [k, v] : fixture["prices"].items()) {
    prices[k] = v.get<std::vector<double>>();
  }
  Config cfg;
  RiskEngine engine(cfg);
  auto order = engine.evaluate(sig, pf, prices);
  CHECK(order.risk_checks_all_passed);
  CHECK(order.sector_pct_ok());
}

TEST_CASE("parity: cross-venue sector ok", "[parity]") {
  auto fixture = load_json("/workspace/tests/fixtures/cross_venue_sector_ok.json");
  auto sig_opt = Signal::from_json(fixture["signal"]);
  REQUIRE(sig_opt.has_value());
  Signal sig = *sig_opt;
  PortfolioState pf;
  pf.nav = fixture["portfolio"]["nav"].get<double>();
  pf.cash = fixture["portfolio"]["cash"].get<double>();
  pf.drawdown_from_peak = fixture["portfolio"]["drawdown_from_peak"].get<double>();
  for (auto& p : fixture["portfolio"]["positions"]) {
    pf.positions.push_back(Position{
      p["ticker"].get<std::string>(),
      p["venue"].get<std::string>(),
      p["asset_class"].get<std::string>(),
      p["sector"].get<std::string>(),
      p["quantity"].get<double>(),
      p["notional"].get<double>()
    });
  }
  std::map<std::string, std::vector<double>> prices;
  for (auto& [k, v] : fixture["prices"].items()) {
    prices[k] = v.get<std::vector<double>>();
  }
  Config cfg;
  RiskEngine engine(cfg);
  auto order = engine.evaluate(sig, pf, prices);
  CHECK(order.risk_checks_all_passed);
  CHECK(order.sector_pct_ok());
}

TEST_CASE("parity: cross-venue sector breach", "[parity]") {
  auto fixture = load_json("/workspace/tests/fixtures/cross_venue_sector_breach.json");
  auto sig_opt = Signal::from_json(fixture["signal"]);
  REQUIRE(sig_opt.has_value());
  Signal sig = *sig_opt;
  PortfolioState pf;
  pf.nav = fixture["portfolio"]["nav"].get<double>();
  pf.cash = fixture["portfolio"]["cash"].get<double>();
  pf.drawdown_from_peak = fixture["portfolio"]["drawdown_from_peak"].get<double>();
  for (auto& p : fixture["portfolio"]["positions"]) {
    pf.positions.push_back(Position{
      p["ticker"].get<std::string>(),
      p["venue"].get<std::string>(),
      p["asset_class"].get<std::string>(),
      p["sector"].get<std::string>(),
      p["quantity"].get<double>(),
      p["notional"].get<double>()
    });
  }
  std::map<std::string, std::vector<double>> prices;
  for (auto& [k, v] : fixture["prices"].items()) {
    prices[k] = v.get<std::vector<double>>();
  }
  Config cfg;
  RiskEngine engine(cfg);
  auto order = engine.evaluate(sig, pf, prices);
  CHECK(order.rejection_reason == "sector_cap");
  CHECK(!order.sector_pct_ok());
}
