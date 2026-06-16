#include "risk/RiskEngine.hpp"
#include "graphalpha/execution_engine.hpp"
#include "graphalpha/portfolio_state.hpp"
#include "graphalpha/audit_log.hpp"
#include "graphalpha/event_publisher.hpp"
#include <hiredis/hiredis.h>
#include <fstream>
#include <iostream>
#include <chrono>
#include <ctime>
#include <thread>
#include <vector>
#include <string>
#include <atomic>
#include <csignal>
#include <cmath>

using namespace risk;
using namespace graphalpha;

std::atomic<bool> g_running{true};

void signal_handler(int) { g_running = false; }

std::string now_iso() {
  auto t = std::chrono::system_clock::now();
  std::time_t tt = std::chrono::system_clock::to_time_t(t);
  char buf[32];
  std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&tt));
  return buf;
}

std::vector<Signal> load_signals(const std::string& path) {
  std::ifstream f(path);
  if (!f) {
    std::cerr << "Cannot open signal file: " << path << "\n";
    return {};
  }
  std::vector<Signal> out;
  std::string line;
  while (std::getline(f, line)) {
    if (line.empty()) continue;
    try {
      auto j = nlohmann::json::parse(line);
      auto sig = Signal::from_json(j);
      if (sig) out.push_back(*sig);
    } catch (const std::exception& e) {
      std::cerr << "Skip signal: " << e.what() << "\n";
    }
  }
  return out;
}

bool run_file_mode(const std::vector<Signal>& signals,
                   RiskEngine& risk_engine,
                   ExecutionEngine& exec_engine,
                   AuditLog& audit,
                   EventPublisher& publisher) {
  std::map<std::string, std::vector<double>> price_map;
  price_map["SPY"] = {100.0, 101.0, 102.0, 103.0, 104.0};
  price_map["QQQ"] = {300.0, 301.0, 302.0, 303.0, 304.0};
  price_map["BTC-USD"] = {20000.0, 20200.0, 20500.0, 20800.0, 21000.0};

  risk::PortfolioState pf;
  pf.nav = 10000.0;
  pf.cash = 10000.0;
  pf.drawdown_from_peak = 0.0;

  for (const auto& sig : signals) {
    auto order = risk_engine.evaluate(sig, pf,
                                      std::optional<std::map<std::string, std::vector<double>>>(price_map));

    if (order.risk_checks_all_passed) {
      double price = 100.0;
      if (!sig.ticker.empty() && price_map.count(sig.ticker)) {
        const auto& s = price_map.at(sig.ticker);
        if (!s.empty()) price = s.back();
      }
      std::string ts = now_iso();
      auto fill = exec_engine.execute(order, price, ts);

      update_position(pf, order, fill.fill_price, fill.fee_usd, fill.slippage_usd);
      double old_nav = pf.nav;
      pf.nav = update_nav(old_nav, order, fill.fill_price, fill.fee_usd, fill.slippage_usd);
      if (pf.nav > old_nav) {
        pf.drawdown_from_peak = compute_drawdown(pf.nav, pf.nav);
      } else {
        pf.drawdown_from_peak = compute_drawdown(pf.nav, std::max(pf.nav, old_nav));
      }

      audit.write_order(order);
      publisher.publish_order_approved(order);
      publisher.publish_order_filled(fill);

      if (risk_engine.is_halted()) {
        publisher.publish_halt(true);
      }
    } else {
      publisher.publish_order_rejected(sig.cycle_id, sig.ticker, order.rejection_reason);
      audit.write_rejection(sig.cycle_id, sig.strategy, sig.ticker, order.rejection_reason);
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  return true;
}

int run_subscriber_mode(const std::string& redis_host, int redis_port, EventPublisher& publisher) {
  std::signal(SIGINT, signal_handler);
  std::signal(SIGTERM, signal_handler);

  Config cfg;
  RiskEngine risk_engine(cfg);
  ExecutionEngine exec_engine(0.0026, 0.0005);

  std::string conn_str =
      "host=" + std::string(std::getenv("POSTGRES_HOST") ? std::getenv("POSTGRES_HOST") : "localhost") +
      " dbname=" + std::string(std::getenv("POSTGRES_DB") ? std::getenv("POSTGRES_DB") : "graphalpha") +
      " user=" + std::string(std::getenv("POSTGRES_USER") ? std::getenv("POSTGRES_USER") : "graphalpha") +
      " password=" + std::string(std::getenv("POSTGRES_PASSWORD") ? std::getenv("POSTGRES_PASSWORD") : "");

  AuditLog audit(conn_str);
  std::string channel = std::getenv("REDIS_SIGNALS_CHANNEL")
                        ? std::getenv("REDIS_SIGNALS_CHANNEL")
                        : "graphalpha:signals:v1";

  // Minimal portfolio for evaluation
  risk::PortfolioState pf;
  pf.nav = 10000.0;
  pf.cash = 10000.0;
  pf.drawdown_from_peak = 0.0;
  std::map<std::string, std::vector<double>> price_map;
  price_map["SPY"] = {100.0, 101.0, 102.0, 103.0, 104.0};
  price_map["QQQ"] = {300.0, 301.0, 302.0, 303.0, 304.0};
  price_map["BTC-USD"] = {20000.0, 20200.0, 20500.0, 20800.0, 21000.0};

  std::cerr << "[subscriber] Connecting Redis subscribe on " << redis_host << ":" << redis_port
            << " channel=" << channel << "\n";

  while (g_running) {
    redisContext* ctx = redisConnect(redis_host.c_str(), redis_port);
    if (ctx == nullptr || ctx->err) {
      std::cerr << "[subscriber] Redis connect failed: "
                << (ctx ? ctx->errstr : "null context") << "\n";
      if (ctx) redisFree(ctx);
      std::this_thread::sleep_for(std::chrono::seconds(2));
      continue;
    }

    if (redisCommand(ctx, "SUBSCRIBE %s", channel.c_str()) == nullptr) {
      std::cerr << "[subscriber] SUBSCRIBE failed: " << ctx->errstr << "\n";
      redisFree(ctx);
      std::this_thread::sleep_for(std::chrono::seconds(2));
      continue;
    }
    std::cerr << "[subscriber] Subscribed. Waiting for signals...\n";

    while (g_running) {
      redisReply* reply = nullptr;
      int rc = redisGetReply(ctx, (void**)&reply);
      if (rc != REDIS_OK || reply == nullptr) {
        std::cerr << "[subscriber] read error, reconnecting: " << (ctx ? ctx->errstr : "null") << "\n";
        if (reply) freeReplyObject(reply);
        break;
      }

      if (reply->type == REDIS_REPLY_ARRAY && reply->elements == 3) {
        std::string message_type = reply->element[0]->str;
        if (message_type == "message") {
          std::string payload = reply->element[2]->str;
          try {
            auto j = nlohmann::json::parse(payload);
            auto sig = Signal::from_json(j);
            if (!sig) {
              std::cerr << "[subscriber] invalid signal schema\n";
              freeReplyObject(reply);
              continue;
            }

            std::string ts = now_iso();
            auto order = risk_engine.evaluate(
                *sig, pf,
                std::optional<std::map<std::string, std::vector<double>>>(price_map));

            if (order.risk_checks_all_passed) {
              double price = 100.0;
              if (!sig->ticker.empty() && price_map.count(sig->ticker)) {
                const auto& s = price_map.at(sig->ticker);
                if (!s.empty()) price = s.back();
              }
              auto fill = exec_engine.execute(order, price, ts);

              update_position(pf, order, fill.fill_price, fill.fee_usd, fill.slippage_usd);
              double old_nav = pf.nav;
              pf.nav = update_nav(old_nav, order, fill.fill_price, fill.fee_usd, fill.slippage_usd);
              pf.drawdown_from_peak = compute_drawdown(pf.nav, std::max(pf.nav, old_nav));

              audit.write_order(order);
              publisher.publish_order_approved(order);
              publisher.publish_order_filled(fill);
            } else {
              publisher.publish_order_rejected(sig->cycle_id, sig->ticker, order.rejection_reason);
              audit.write_rejection(sig->cycle_id, sig->strategy, sig->ticker, order.rejection_reason);
            }
          } catch (const std::exception& e) {
            std::cerr << "[subscriber] process error: " << e.what() << "\n";
          }
        }
      }
      freeReplyObject(reply);
    }

    redisFree(ctx);
    if (g_running) {
      std::cerr << "[subscriber] reconnecting in 2s...\n";
      std::this_thread::sleep_for(std::chrono::seconds(2));
    }
  }

  std::cerr << "[subscriber] shutting down\n";
  return 0;
}

int main(int argc, char** argv) {
  const bool redis_subscribe = std::getenv("REDIS_SUBSCRIBE") != nullptr
                               && std::string(std::getenv("REDIS_SUBSCRIBE")) == "1";
  const std::string redis_host = std::getenv("REDIS_HOST") ? std::getenv("REDIS_HOST") : "localhost";
  const int redis_port = std::getenv("REDIS_PORT") ? std::stoi(std::getenv("REDIS_PORT")) : 6379;

  if (redis_subscribe) {
    if (argc >= 2) {
      std::cerr << "[main] REDIS_SUBSCRIBE=1 mode: ignoring file arg '" << argv[1] << "'\n";
    }
    EventPublisher publisher(redis_host, redis_port);
    return run_subscriber_mode(redis_host, redis_port, publisher);
  }

  if (argc < 2) {
    std::cerr << "Usage (file mode): risk-engine <signals.jsonl>\n"
              << "       (Redis mode): REDIS_SUBSCRIBE=1 risk-engine\n";
    return 1;
  }

  Config cfg;
  RiskEngine risk_engine(cfg);
  ExecutionEngine exec_engine(0.0026, 0.0005);

  std::string conn_str =
      "host=" + std::string(std::getenv("POSTGRES_HOST") ? std::getenv("POSTGRES_HOST") : "localhost") +
      " dbname=" + std::string(std::getenv("POSTGRES_DB") ? std::getenv("POSTGRES_DB") : "graphalpha") +
      " user=" + std::string(std::getenv("POSTGRES_USER") ? std::getenv("POSTGRES_USER") : "graphalpha") +
      " password=" + std::string(std::getenv("POSTGRES_PASSWORD") ? std::getenv("POSTGRES_PASSWORD") : "");

  AuditLog audit(conn_str);
  EventPublisher publisher(redis_host, redis_port);

  std::vector<Signal> signals = load_signals(argv[1]);
  return run_file_mode(signals, risk_engine, exec_engine, audit, publisher) ? 0 : 1;
}
