#include "risk/PortfolioLoader.hpp"
#include <libpq-fe.h>
#include <sstream>
#include <stdexcept>
#include <cstdlib>
#include <string>
#include <algorithm>
#include <random>
#include <chrono>

namespace risk {

static std::string infer_asset_class(const std::string& ticker) {
  if (ticker.find("-USD") != std::string::npos || 
      ticker == "BTC" || ticker == "ETH" || ticker == "XBT") {
    return "crypto";
  }
  return "equity_xstock";
}

static std::string infer_sector(const std::string& ticker) {
  std::string t = ticker;
  for (char& c : t) c = std::toupper(c);
  if (t == "SPY") return "equity_broad";
  if (t == "QQQ") return "equity_tech";
  if (t == "XLF") return "equity_financials";
  if (t == "XLE") return "equity_energy";
  if (t.find("-USD") != std::string::npos) return "";
  return "equity_broad";
}

static std::string infer_venue(const std::string& ticker) {
  if (ticker.find("-USD") != std::string::npos || 
      ticker == "BTC" || ticker == "ETH" || ticker == "XBT") {
    return "kraken";
  }
  return "ibkr";
}

std::optional<PortfolioState> PortfolioLoader::load_from_postgres(const std::string& conn_str) {
  PGconn* conn = PQconnectdb(conn_str.c_str());
  if (PQstatus(conn) != CONNECTION_OK) {
    PQfinish(conn);
    return std::nullopt;
  }

  PortfolioState pf;

PGresult* res = PQexec(conn,
       "SELECT ticker, direction, quantity, avg_entry_price, "
       "current_price, (quantity * current_price) AS notional, "
       "venue, asset_class "
       "FROM positions WHERE status = 'open'");
  
  if (PQresultStatus(res) != PGRES_TUPLES_OK) {
    PQclear(res);
    PQfinish(conn);
    return std::nullopt;
  }

  int rows = PQntuples(res);
  for (int i = 0; i < rows; ++i) {
    Position p;
    p.ticker = PQgetvalue(res, i, 0);
    p.venue = (PQgetisnull(res, i, 6) ? infer_venue(p.ticker) : PQgetvalue(res, i, 6));
    p.asset_class = (PQgetisnull(res, i, 7) ? infer_asset_class(p.ticker) : PQgetvalue(res, i, 7));
    p.sector = infer_sector(p.ticker);
    p.quantity = std::stod(PQgetvalue(res, i, 2));
    p.notional = std::stod(PQgetvalue(res, i, 5));
    pf.positions.push_back(p);
  }
  PQclear(res);

  res = PQexec(conn,
      "SELECT cash_balance, nav, drawdown_pct, halted "
      "FROM portfolio_state ORDER BY id DESC LIMIT 1");
  if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) > 0) {
    pf.cash = std::stod(PQgetvalue(res, 0, 0));
    pf.nav = std::stod(PQgetvalue(res, 0, 1));
    pf.drawdown_from_peak = std::stod(PQgetvalue(res, 0, 2));
    pf.halted = (std::string(PQgetvalue(res, 0, 3)) == "t" ||
                 std::string(PQgetvalue(res, 0, 3)) == "true");
  } else {
    pf.cash = 10000.0;
    pf.nav = 10000.0;
  }
  PQclear(res);

  PQfinish(conn);
  return pf;
}

bool PortfolioLoader::persist_portfolio(const std::string& conn_str,
                                         const PortfolioState& pf) {
  PGconn* conn = PQconnectdb(conn_str.c_str());
  if (PQstatus(conn) != CONNECTION_OK) {
    PQfinish(conn);
    return false;
  }

  const char* paramValues[4] = {
      std::to_string(pf.cash).c_str(),
      std::to_string(pf.nav).c_str(),
      std::to_string(pf.drawdown_from_peak).c_str(),
      pf.halted ? "true" : "false"};

  PGresult* res = PQexecParams(conn,
      "INSERT INTO portfolio_state (cash_balance, nav, drawdown_pct, halted) "
      "VALUES ($1::numeric, $2::numeric, $3::numeric, $4::bool)",
      4, NULL, paramValues, NULL, NULL, 0);
  bool ok = (PQresultStatus(res) == PGRES_COMMAND_OK);
  PQclear(res);

  for (const auto& pos : pf.positions) {
    std::string side = (pos.quantity >= 0) ? "buy" : "sell";
    double qty = std::abs(pos.quantity);
    std::string venue = pos.venue.empty() ? infer_venue(pos.ticker) : pos.venue;
    std::string ac = pos.asset_class.empty() ? infer_asset_class(pos.ticker) : pos.asset_class;
    const char* posValues[8] = {
        pos.ticker.c_str(),
        side.c_str(),
        std::to_string(qty).c_str(),
        std::to_string(pos.notional / std::max(qty, 1e-9)).c_str(),
        std::to_string(pos.notional / std::max(qty, 1e-9)).c_str(),
        venue.c_str(),
        ac.c_str(),
        "open"};

    PGresult* pres = PQexecParams(conn,
        "INSERT INTO positions "
        "(ticker, direction, quantity, avg_entry_price, current_price, venue, asset_class, status) "
        "VALUES ($1, $2, $3::numeric, $4::numeric, $5::numeric, $6, $7, $8) "
        "ON CONFLICT (ticker) WHERE status = 'open' DO UPDATE SET "
        "quantity = EXCLUDED.quantity, "
        "current_price = EXCLUDED.current_price, "
        "avg_entry_price = EXCLUDED.avg_entry_price, "
        "venue = EXCLUDED.venue, "
        "asset_class = EXCLUDED.asset_class",
        8, NULL, posValues, NULL, NULL, 0);
    PQclear(pres);
  }

  PQfinish(conn);
  return ok;
}

std::string PortfolioLoader::make_order_id() {
  using u64 = unsigned long long;
  static std::random_device rd;
  static std::mt19937_64 gen(rd());
  static std::uniform_int_distribution<u64> dist;
  u64 a = dist(gen);
  u64 b = dist(gen);
  char buf[37];
  std::snprintf(buf, sizeof(buf),
      "%08llx-%04llx-%04llx-%04llx-%012llx",
      (u64)(a >> 32), (u64)((a >> 16) & 0xFFFFULL),
      (u64)(a & 0xFFFFULL), (u64)(b >> 48),
      b & 0xFFFFFFFFFFFFULL);
  return std::string(buf);
}

}  // namespace risk
