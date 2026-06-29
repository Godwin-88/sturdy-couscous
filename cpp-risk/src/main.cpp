#include "risk/RiskEngine.hpp"
#include "risk/Config.hpp"
#include "risk/PortfolioLoader.hpp"
#include "graphalpha/execution_engine.hpp"
#include "graphalpha/kraken_adapter.hpp"
#include "graphalpha/ibkr_adapter.hpp"
#include "graphalpha/portfolio_state.hpp"
#include "graphalpha/audit_log.hpp"
#include "graphalpha/event_publisher.hpp"
#include <nlohmann/json.hpp>
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
#include <iomanip>

using namespace risk;
using namespace graphalpha;

namespace {
std::atomic<bool> g_running{true};
std::atomic<bool> g_kill_switch_active{false};

void signal_handler(int) { g_running = false; }

std::string now_iso() {
  auto t = std::chrono::system_clock::now();
  std::time_t tt = std::chrono::system_clock::to_time_t(t);
  char buf[32];
  std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&tt));
  return buf;
}

double now_epoch_ms() {
  return std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::system_clock::now().time_since_epoch()).count();
}

std::string build_conn_str() {
  const char* pg_host = std::getenv("POSTGRES_HOST") ? std::getenv("POSTGRES_HOST") : "localhost";
  const char* pg_db   = std::getenv("POSTGRES_DB")   ? std::getenv("POSTGRES_DB")   : "graphalpha";
  const char* pg_user = std::getenv("POSTGRES_USER") ? std::getenv("POSTGRES_USER") : "graphalpha";
  const char* pg_pass = std::getenv("POSTGRES_PASSWORD") ? std::getenv("POSTGRES_PASSWORD") : "";
  return std::string("host=") + pg_host +
         " dbname=" + pg_db +
         " user=" + pg_user +
         " password=" + pg_pass;
}

bool should_shadow_compare() {
   const char* v = std::getenv("SHADOW_COMPARE");
   return v && std::string(v) == "1";
}

bool check_kill_switch() {
   const char* v = std::getenv("KILL_SWITCH");
   return v && std::string(v) == "1";
}

bool check_live_validation_scale() {
   const char* v = std::getenv("LIVE_VALIDATION_SCALE_PCT");
   return v != nullptr;
}

double get_live_validation_scale() {
   const char* v = std::getenv("LIVE_VALIDATION_SCALE_PCT");
   if (!v) return 1.0;
   try {
      return std::stod(v) / 100.0;
   } catch (...) {
      return 1.0;
   }
}

int get_reconcile_interval_seconds() {
   const char* v = std::getenv("KRAKEN_RECONCILE_INTERVAL_SECONDS");
   return v ? std::stoi(v) : 300;
}
}  // anonymous namespace

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
                   EventPublisher& publisher,
                   const std::string& conn_str) {
  std::map<std::string, std::vector<double>> price_map;
  price_map["SPY"] = {100.0, 101.0, 102.0, 103.0, 104.0};
  price_map["QQQ"] = {300.0, 301.0, 302.0, 303.0, 304.0};
  price_map["BTC-USD"] = {20000.0, 20200.0, 20500.0, 20800.0, 21000.0};

  auto pf_opt = PortfolioLoader::load_from_postgres(conn_str);
  risk::PortfolioState pf = pf_opt.value_or(risk::PortfolioState{});
  if (pf.nav <= 0.0) {
    pf.nav = 10000.0;
    pf.cash = 10000.0;
  }
  double peak = std::max(pf.nav, pf.drawdown_from_peak * pf.nav + pf.nav);

  double t_total_start = now_epoch_ms();

  for (const auto& sig : signals) {
    double t0 = now_epoch_ms();
    auto order = risk_engine.evaluate(sig, pf,
                                        std::optional<std::map<std::string, std::vector<double>>>(price_map));

    std::string order_id = PortfolioLoader::make_order_id();

    if (order.risk_checks_all_passed) {
      std::string ts = now_iso();
      auto fill_opt = exec_engine.execute(order, ts);
      if (!fill_opt) {
        std::cerr << "[file] execute failed for " << order.ticker << " at venue " << order.venue << "\n";
        continue;
      }
      auto fill = *fill_opt;

      update_position(pf, order, fill.fill_price, fill.fee_usd, fill.slippage_usd);
      double old_nav = pf.nav;
      pf.nav = update_nav(old_nav, order, fill.fill_price, fill.fee_usd, fill.slippage_usd);
      if (pf.nav > peak) peak = pf.nav;
      pf.drawdown_from_peak = compute_drawdown(pf.nav, peak);

      audit.write_order(order_id, order, fill);
      publisher.publish_order_approved(order);
      publisher.publish_order_filled(fill);

      if (should_shadow_compare()) {
        nlohmann::json sig_j = sig.to_json();
        nlohmann::json dec_j = nlohmann::json{
            {"action", "approve"},
            {"quantity", order.quantity},
            {"notional_usd", order.notional_usd},
            {"kelly_fraction", order.kelly_fraction},
            {"var_contribution_pct", order.var_contribution_pct},
        };
        audit.write_shadow_comparison(sig.cycle_id, sig.ticker, sig.strategy, sig_j, dec_j);
      }

      if (risk_engine.is_halted()) {
        publisher.publish_halt(true);
      }
    } else {
      publisher.publish_order_rejected(sig.cycle_id, sig.ticker, order.rejection_reason);
      audit.write_rejection(sig.cycle_id, sig.strategy, sig.ticker, order.rejection_reason);

      if (should_shadow_compare()) {
        nlohmann::json sig_j = sig.to_json();
        nlohmann::json dec_j = nlohmann::json{
            {"action", "reject"},
            {"reason", order.rejection_reason},
        };
        audit.write_shadow_comparison(sig.cycle_id, sig.ticker, sig.strategy, sig_j, dec_j);
      }
    }

    double t1 = now_epoch_ms();
    if ((t1 - t0) > 100.0) {
      std::cerr << "[latency] signal ticker=" << sig.ticker
                << " engine_ms=" << std::fixed << std::setprecision(1) << (t1 - t0) << "\n";
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }

  PortfolioLoader::persist_portfolio(conn_str, pf);

  double t_total_end = now_epoch_ms();
  std::cerr << "[latency] total_cycle_ms=" << std::fixed << std::setprecision(1)
            << (t_total_end - t_total_start) << " signals=" << signals.size() << "\n";

  return true;
}

int run_subscriber_mode(const std::string& redis_host, int redis_port, EventPublisher& publisher) {
   std::signal(SIGINT, signal_handler);
   std::signal(SIGTERM, signal_handler);

    Config cfg;
    RiskEngine risk_engine(cfg);
    ExecutionEngine exec_engine;

    // P6: Register venue adapters
    std::string ibkr_host = std::getenv("IBKR_HOST") ? std::getenv("IBKR_HOST") : "ib-gateway";
    int ibkr_port = std::getenv("IBKR_PORT") ? std::stoi(std::getenv("IBKR_PORT")) : 4002;
    int ibkr_client_id = std::getenv("IBKR_CLIENT_ID") ? std::stoi(std::getenv("IBKR_CLIENT_ID")) : 1;
    exec_engine.register_adapter(std::make_unique<KrakenAdapter>());
    exec_engine.register_adapter(std::make_unique<IBKRAdapter>(ibkr_host, ibkr_port, ibkr_client_id));

  std::string conn_str = build_conn_str();
  AuditLog audit(conn_str);
  std::string channel = std::getenv("REDIS_SIGNALS_CHANNEL")
                        ? std::getenv("REDIS_SIGNALS_CHANNEL")
                        : "graphalpha:signals:v1";

  auto pf_opt = PortfolioLoader::load_from_postgres(conn_str);
  risk::PortfolioState pf = pf_opt.value_or(risk::PortfolioState{});
  if (pf.nav <= 0.0) {
    pf.nav = 10000.0;
    pf.cash = 10000.0;
  }
  double peak = std::max(pf.nav, pf.drawdown_from_peak * pf.nav + pf.nav);

  std::map<std::string, std::vector<double>> price_map;
  price_map["SPY"] = {100.0, 101.0, 102.0, 103.0, 104.0};
  price_map["QQQ"] = {300.0, 301.0, 302.0, 303.0, 304.0};
  price_map["BTC-USD"] = {20000.0, 20200.0, 20500.0, 20800.0, 21000.0};

  int reconcile_interval = get_reconcile_interval_seconds();
  double last_reconcile = now_epoch_ms();

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
      // P7 Feature 4: Kill switch check - halts Kraken live orders
      if (check_kill_switch()) {
        std::cerr << "[subscriber] KILL_SWITCH active - halting Kraken live orders\n";
        g_kill_switch_active = true;
        publisher.publish_halt(true);
        // Continue processing but Kraken live orders should be blocked
      }

      // P7 Feature 2: Reconciliation interval polling
      double now = now_epoch_ms();
      if ((now - last_reconcile) / 1000.0 >= reconcile_interval) {
        if (auto* kraken = dynamic_cast<KrakenAdapter*>(exec_engine.get_adapter("kraken"))) {
          std::string mismatch;
          if (!kraken->reconcile_positions(0.01, mismatch)) {
            std::cerr << "[subscriber] Kraken reconciliation mismatch: " << mismatch << "\n";
            publisher.publish_kraken_halt(mismatch);
          }
        }
        last_reconcile = now;
      }

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
          std::cerr << "[subscriber] received payload len=" << payload.size() << "\n";
          double t0 = now_epoch_ms();
          std::optional<Signal> sig_opt;
          ApprovedOrder order;
          std::string outcome = "error";
          try {
            auto j = nlohmann::json::parse(payload);
            sig_opt = Signal::from_json(j);
            if (!sig_opt) {
              std::cerr << "[subscriber] invalid signal schema\n";
              freeReplyObject(reply);
              continue;
            }

            order = risk_engine.evaluate(
                *sig_opt, pf,
                std::optional<std::map<std::string, std::vector<double>>>(price_map));

            std::string order_id = PortfolioLoader::make_order_id();

// P7 Feature 2: Check if Kraken live trading is halted due to reconciliation or kill switch
             bool kraken_halted = false;
             if (order.venue == "kraken") {
               const char* reenable = std::getenv("KRAKEN_REENABLE");
               if (reenable && std::string(reenable) == "1") {
                 if (auto* kraken = dynamic_cast<KrakenAdapter*>(exec_engine.get_adapter("kraken"))) {
                   kraken->clear_reconciliation_halt();
                   std::cerr << "[subscriber] KRAKEN_REENABLE=1 - clearing halt\n";
                 }
               } else if (auto* kraken = dynamic_cast<KrakenAdapter*>(exec_engine.get_adapter("kraken"))) {
                 kraken_halted = kraken->is_kraken_live_halted() || g_kill_switch_active;
               }
               if (kraken_halted) {
                 std::cerr << "[subscriber] Skipping order - Kraken halted\n";
                 outcome = "skipped_kraken_halt";
                 freeReplyObject(reply);
                 continue;
               }
             }

            // P7 Feature 3: Live validation scaling
            if (order.venue == "kraken" && check_live_validation_scale()) {
               double scale = get_live_validation_scale();
               if (scale > 0.0 && scale < 1.0) {
                  order.notional_usd *= scale;
                  order.quantity = order.notional_usd / (price_map.count(order.ticker) ? price_map.at(order.ticker).back() : 100.0);
               }
            }

            if (order.risk_checks_all_passed) {
               outcome = "approve";

               auto fill_opt = exec_engine.execute(order, now_iso());
             if (!fill_opt) {
               std::cerr << "[subscriber] execute failed for " << order.ticker << " at venue " << order.venue << "\n";
               continue;
             }
             auto fill = *fill_opt;

             update_position(pf, order, fill.fill_price, fill.fee_usd, fill.slippage_usd);
             double old_nav = pf.nav;
             pf.nav = update_nav(old_nav, order, fill.fill_price, fill.fee_usd, fill.slippage_usd);
             if (pf.nav > peak) peak = pf.nav;
             pf.drawdown_from_peak = compute_drawdown(pf.nav, peak);

             audit.write_order(order_id, order, fill);
             publisher.publish_order_approved(order);
             publisher.publish_order_filled(fill);

             if (should_shadow_compare()) {
               nlohmann::json sig_j = sig_opt->to_json();
               nlohmann::json dec_j = nlohmann::json{
                   {"action", "approve"},
                   {"quantity", order.quantity},
                   {"notional_usd", order.notional_usd},
                   {"kelly_fraction", order.kelly_fraction},
                   {"var_contribution_pct", order.var_contribution_pct},
               };
               audit.write_shadow_comparison(sig_opt->cycle_id, sig_opt->ticker, sig_opt->strategy, sig_j, dec_j);
             }

             if (risk_engine.is_halted()) {
               publisher.publish_halt(true);
             }
           } else {
             outcome = "reject";
             publisher.publish_order_rejected(sig_opt->cycle_id, sig_opt->ticker, order.rejection_reason);
             audit.write_rejection(sig_opt->cycle_id, sig_opt->strategy, sig_opt->ticker, order.rejection_reason);

             if (should_shadow_compare()) {
               nlohmann::json sig_j = sig_opt->to_json();
               nlohmann::json dec_j = nlohmann::json{
                   {"action", "reject"},
                   {"reason", order.rejection_reason},
               };
               audit.write_shadow_comparison(sig_opt->cycle_id, sig_opt->ticker, sig_opt->strategy, sig_j, dec_j);
             }
           }
            // P5: Persist portfolio state after each signal
            PortfolioLoader::persist_portfolio(conn_str, pf);
          } catch (const std::exception& e) {
            std::cerr << "[subscriber] process error: " << e.what() << "\n";
          }
          // P5: Per-signal latency baseline (Feature 3 AC)
          double t1 = now_epoch_ms();
          double latency_ms = t1 - t0;
          std::cerr << "[latency]"
                    << " ticker=" << (sig_opt ? sig_opt->ticker : "???")
                    << " strategy=" << (sig_opt ? sig_opt->strategy : "???")
                    << " direction=" << (sig_opt ? direction_to_string(sig_opt->direction) : "???")
                    << " engine_ms=" << std::fixed << std::setprecision(1) << latency_ms
                    << " outcome=" << outcome
                    << "\n";
        }
      }
      freeReplyObject(reply);
    }

    redisFree(ctx);
    PortfolioLoader::persist_portfolio(conn_str, pf);
    if (g_running) {
      std::cerr << "[subscriber] reconnecting in 2s...\n";
      std::this_thread::sleep_for(std::chrono::seconds(2));
    }
  }

  PortfolioLoader::persist_portfolio(conn_str, pf);
  std::cerr << "[subscriber] shutting down\n";
  return 0;
}

int main(int argc, char** argv) {
  const bool redis_subscribe = std::getenv("REDIS_SUBSCRIBE") != nullptr
                                && std::string(std::getenv("REDIS_SUBSCRIBE")) == "1";
  const char* redis_host_c = std::getenv("REDIS_HOST") ? std::getenv("REDIS_HOST") : "localhost";
  const int redis_port = std::getenv("REDIS_PORT") ? std::stoi(std::getenv("REDIS_PORT")) : 6379;

  std::string conn_str = build_conn_str();

  if (redis_subscribe) {
    if (argc >= 2) {
      std::cerr << "[main] REDIS_SUBSCRIBE=1 mode: ignoring file arg '" << argv[1] << "'\n";
    }
    EventPublisher publisher(redis_host_c, redis_port, "graphalpha:events");
    return run_subscriber_mode(redis_host_c, redis_port, publisher);
  }

  if (argc < 2) {
    std::cerr << "Usage (file mode): risk-engine <signals.jsonl>\n"
              << "       (Redis mode): REDIS_SUBSCRIBE=1 risk-engine\n";
    return 1;
  }

  Config cfg;
  RiskEngine risk_engine(cfg);
  ExecutionEngine exec_engine;

  AuditLog audit(conn_str);
  EventPublisher publisher(redis_host_c, redis_port);

  std::vector<Signal> signals = load_signals(argv[1]);
  return run_file_mode(signals, risk_engine, exec_engine, audit, publisher, conn_str) ? 0 : 1;
}
