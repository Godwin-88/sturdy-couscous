#include "graphalpha/audit_log.hpp"
#include <libpq-fe.h>
#include <sstream>
#include <stdexcept>
#include <cstdlib>
#include <string>
#include <algorithm>

namespace graphalpha {

AuditLog::AuditLog(const std::string& conn_str) : conn_str_(conn_str) {}

AuditLog::~AuditLog() = default;

bool AuditLog::write_order(const std::string& order_id,
                           const risk::ApprovedOrder& order,
                           const FillResult& fill) {
  PGconn* conn = PQconnectdb(conn_str_.c_str());
  if (PQstatus(conn) != CONNECTION_OK) {
    PQfinish(conn);
    return false;
  }

  nlohmann::json order_json = order.to_json();
  if (fill.fill_price > 0.0) {
    order_json["fill_price"] = fill.fill_price;
    order_json["fee_usd"] = fill.fee_usd;
    order_json["slippage_usd"] = fill.slippage_usd;
    order_json["fill_timestamp"] = fill.timestamp;
    order_json["fill_quantity"] = fill.fill_quantity;
  }

  std::string json_str = order_json.dump();
  std::string order_id_copy = order_id;
  std::string qty_str = std::to_string(order.quantity);
  std::string fill_price_str = std::to_string(fill.fill_price);
  std::string fee_str = std::to_string(fill.fee_usd);
  std::string ts_str = order.signal_timestamp;
  const char* paramValues[9] = {
      order_id_copy.c_str(),
      order.ticker.c_str(),
      order.direction.c_str(),
      qty_str.c_str(),
      fill_price_str.c_str(),
      fee_str.c_str(),
      order.mode.empty() ? "paper" : order.mode.c_str(),
      ts_str.c_str(),
      json_str.c_str()};

  const char* sql =
      "INSERT INTO order_audit "
      "(order_id, ticker, direction, quantity, fill_price, "
      "fee_usd, mode, signal_score, created_at, raw_response) "
      "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, "
      "COALESCE(NULLIF($8, '')::numeric, 0), NOW(), $9::jsonb)";

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

bool AuditLog::write_shadow_comparison(const std::string& cycle_id,
                                        const std::string& ticker,
                                        const std::string& strategy,
                                        const nlohmann::json& signal,
                                        const nlohmann::json& decision) {
  PGconn* conn = PQconnectdb(conn_str_.c_str());
  if (PQstatus(conn) != CONNECTION_OK) {
    PQfinish(conn);
    return false;
  }

  std::string signal_str = signal.dump();
  std::string decision_str = decision.dump();
  const char* paramValues[5] = {
      cycle_id.c_str(),
      ticker.c_str(),
      strategy.c_str(),
      signal_str.c_str(),
      decision_str.c_str()};

  const char* sql =
      "INSERT INTO shadow_comparison "
      "(cycle_id, ticker, strategy, signal, cpp_decision) "
      "VALUES ($1::uuid, $2, $3, $4::jsonb, $5::jsonb) "
      "ON CONFLICT (cycle_id, ticker, strategy) DO UPDATE SET "
      "cpp_decision = EXCLUDED.cpp_decision, "
      "signal = EXCLUDED.signal";

  PGresult* res = PQexecParams(conn, sql, 5, NULL, paramValues, NULL, NULL, 0);
  bool ok = (PQresultStatus(res) == PGRES_COMMAND_OK);
  PQclear(res);
  PQfinish(conn);
  return ok;
}

}  // namespace graphalpha

bool AuditLog::write_live_validation_discrepancy(const std::string& cycle_id,
                                                const std::string& ticker,
                                                const std::string& strategy,
                                                double paper_price,
                                                double live_price,
                                                double paper_fee,
                                                double live_fee,
                                                double paper_slippage,
                                                double live_slippage,
                                                const std::string& discrepancy_type,
                                                const nlohmann::json& detail) {
  PGconn* conn = PQconnectdb(conn_str_.c_str());
  if (PQstatus(conn) != CONNECTION_OK) {
    PQfinish(conn);
    return false;
  }

  std::string detail_str = detail.dump();
  const char* paramValues[10] = {
      cycle_id.c_str(),
      ticker.c_str(),
      strategy.c_str(),
      std::to_string(paper_price).c_str(),
      std::to_string(live_price).c_str(),
      std::to_string(paper_fee).c_str(),
      std::to_string(live_fee).c_str(),
      std::to_string(paper_slippage).c_str(),
      std::to_string(live_slippage).c_str(),
      detail_str.c_str()};

  const char* sql =
      "INSERT INTO live_validation_discrepancy "
      "(cycle_id, ticker, strategy, paper_price, live_price, "
      "paper_fee, live_fee, paper_slippage, live_slippage, discrepancy_type, detail) "
      "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)";

  PGresult* res = PQexecParams(conn, sql, 11, NULL, paramValues, NULL, NULL, 0);
  bool ok = (PQresultStatus(res) == PGRES_COMMAND_OK);
  PQclear(res);
  PQfinish(conn);
  return ok;
}

