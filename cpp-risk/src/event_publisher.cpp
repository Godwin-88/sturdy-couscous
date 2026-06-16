#include "graphalpha/event_publisher.hpp"

#include <hiredis/hiredis.h>
#include <nlohmann/json.hpp>
#include <sstream>
#include <stdexcept>
#include <chrono>
#include <ctime>

namespace graphalpha {

EventPublisher::EventPublisher(const std::string& redis_host,
                               int redis_port,
                               const std::string& channel)
    : redis_host_(redis_host), redis_port_(redis_port), channel_(channel) {}

EventPublisher::~EventPublisher() = default;

bool EventPublisher::_publish_json(const std::string& message) {
  redisContext* ctx = redisConnect(redis_host_.c_str(), redis_port_);
  if (ctx == nullptr || ctx->err) {
    if (ctx) redisFree(ctx);
    return false;
  }

  redisReply* reply = (redisReply*)redisCommand(ctx, "PUBLISH %s %s",
                                                 channel_.c_str(), message.c_str());
  bool ok = (reply != nullptr);
  if (reply) freeReplyObject(reply);
  redisFree(ctx);
  return ok;
}

bool EventPublisher::publish(const std::string& event_type,
                             const std::string& ticker,
                             const std::string& detail) {
  auto now = std::chrono::system_clock::now();
  std::time_t t = std::chrono::system_clock::to_time_t(now);
  char buf[32];
  std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&t));

  nlohmann::json j;
  j["event"] = event_type;
  j["ticker"] = ticker;
  j["detail"] = detail;
  j["timestamp"] = buf;
  return _publish_json(j.dump());
}

bool EventPublisher::publish_order_approved(const risk::ApprovedOrder& order) {
  nlohmann::json j;
  j["event"] = "order_approved";
  j["ticker"] = order.ticker;
  j["venue"] = order.venue;
  j["direction"] = order.direction;
  j["quantity"] = order.quantity;
  j["notional_usd"] = order.notional_usd;
  j["kelly_fraction"] = order.kelly_fraction;
  j["risk_checks_all_passed"] = order.risk_checks_all_passed;
  return _publish_json(j.dump());
}

bool EventPublisher::publish_order_filled(const FillResult& fill) {
  nlohmann::json j;
  j["event"] = "order_filled";
  j["ticker"] = fill.ticker;
  j["venue"] = fill.venue;
  j["direction"] = fill.direction;
  j["fill_price"] = fill.fill_price;
  j["fill_quantity"] = fill.fill_quantity;
  j["fee_usd"] = fill.fee_usd;
  j["slippage_usd"] = fill.slippage_usd;
  j["timestamp"] = fill.timestamp;
  return _publish_json(j.dump());
}

bool EventPublisher::publish_order_rejected(const std::string& cycle_id,
                                            const std::string& ticker,
                                            const std::string& reason) {
  nlohmann::json j;
  j["event"] = "order_rejected";
  j["cycle_id"] = cycle_id;
  j["ticker"] = ticker;
  j["reason"] = reason;
  return _publish_json(j.dump());
}

bool EventPublisher::publish_halt(bool halted) {
  return publish("circuit_breaker", halted ? "HALTED" : "RECOVERED",
                 halted ? "Drawdown limit exceeded" : "Drawdown recovered");
}

}  // namespace graphalpha
