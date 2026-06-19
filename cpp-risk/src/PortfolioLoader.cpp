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
      "CASE WHEN direction = 'buy' THEN 'long' ELSE 'short' END AS side "
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
    p.venue = "kraken";  // P4 only supports kraken
    p.asset_class = "equity_xstock";
    p.sector = "";
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
    const char* posValues[7] = {
        pos.ticker.c_str(),
        side.c_str(),
        std::to_string(qty).c_str(),
        std::to_string(pos.notional / std::max(qty, 1e-9)).c_str(),
        std::to_string(pos.notional / std::max(qty, 1e-9)).c_str(),
        "open",
        "NOW()"};

    PGresult* pres = PQexecParams(conn,
        "INSERT INTO positions "
        "(ticker, direction, quantity, avg_entry_price, current_price, status, opened_at) "
        "VALUES ($1, $2, $3::numeric, $4::numeric, $5::numeric, $6, $7) "
        "ON CONFLICT (ticker) WHERE status = 'open' DO UPDATE SET "
        "quantity = EXCLUDED.quantity, "
        "current_price = EXCLUDED.current_price, "
        "avg_entry_price = EXCLUDED.avg_entry_price",
        7, NULL, posValues, NULL, NULL, 0);
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
