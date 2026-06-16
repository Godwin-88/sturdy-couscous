#include "graphalpha/audit_log.hpp"

#include <libpq-fe.h>
#include <sstream>
#include <stdexcept>
#include <cstdlib>
#include <string>

namespace graphalpha {

AuditLog::AuditLog(const std::string& conn_str) : conn_str_(conn_str) {}

AuditLog::~AuditLog() = default;

bool AuditLog::write_order(const risk::ApprovedOrder& order) {
  PGconn* conn = PQconnectdb(conn_str_.c_str());
  if (PQstatus(conn) != CONNECTION_OK) {
    PQfinish(conn);
    return false;
  }

  std::string s_qty = std::to_string(order.quantity);
  std::string s_not = std::to_string(order.notional_usd);
  std::string s_kelly = std::to_string(order.kelly_fraction);
  std::string s_var = std::to_string(order.var_contribution_pct);

  const char* paramValues[9] = {
      order.cycle_id.c_str(),
      order.ticker.c_str(),
      order.direction.c_str(),
      s_qty.c_str(),
      s_not.c_str(),
      s_kelly.c_str(),
      s_var.c_str(),
      "paper",
      "{}"};

  const char* sql =
      "INSERT INTO order_audit "
      "(order_id, ticker, direction, quantity, fill_price, "
      "fee_usd, mode, signal_score, created_at, raw_response) "
      "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, NOW(), $9::jsonb)";

  PGresult* res = PQexecParams(conn, sql, 9, NULL, paramValues, NULL, NULL, 0);
  bool ok = (PQresultStatus(res) == PGRES_COMMAND_OK);
  PQclear(res);
  PQfinish(conn);
  return ok;
}

bool AuditLog::write_rejection(const std::string& cycle_id,
                                const std::string& strategy,
                                const std::string& ticker,
                                const std::string& reason) {
  PGconn* conn = PQconnectdb(conn_str_.c_str());
  if (PQstatus(conn) != CONNECTION_OK) {
    PQfinish(conn);
    return false;
  }

  std::string safe_reason = reason.empty() ? "unknown" : reason;
  const char* paramValues[4] = {
      cycle_id.c_str(),
      strategy.empty() ? NULL : strategy.c_str(),
      ticker.c_str(),
      safe_reason.c_str()};

  PGresult* res = PQexecParams(conn,
                               "INSERT INTO order_audit "
                               "(order_id, strategy, ticker, direction, "
                               "quantity, fill_price, fee_usd, mode, signal_score, "
                               "created_at, raw_response) "
                               "VALUES ($1::uuid, $2, $3, 'hold', 0, 0, 0, 'paper', 0, "
                               "NOW(), jsonb_build_object('rejection_reason', $4))",
                               4, NULL, paramValues, NULL, NULL, 0);

  bool ok = (PQresultStatus(res) == PGRES_COMMAND_OK);
  PQclear(res);
  PQfinish(conn);
  return ok;
}

bool AuditLog::write_fill(const std::string& order_id, const FillResult& fill) {
  return true;
}

}  // namespace graphalpha
