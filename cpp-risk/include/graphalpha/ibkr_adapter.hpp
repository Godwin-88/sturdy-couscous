#pragma once

#include <string>
#include <vector>
#include <memory>
#include <atomic>
#include <thread>
#include <mutex>
#include "graphalpha/venue_adapter.hpp"

namespace graphalpha {

/**
 * IBKRAdapter — execution venue connector for Interactive Brokers.
 *
 * Connects to IB Gateway over its native TWS socket API (port 4002 for paper).
 * P6 scope: paper-only. A hard code-level check prevents any live order.
 * Fills are reported from the Gateway's simulated fill engine (not GraphAlpha's).
 *
 * Contract resolution: venue_symbol is decomposed into symbol/exchange/currency.
 * If the venue_symbol doesn't decompose cleanly, the order is rejected with a clear error.
 */
class IBKRAdapter : public VenueAdapter {
 public:
  /**
   * @param host IB Gateway hostname (default: "ib-gateway")
   * @param port IB Gateway paper trading port (default: 4002)
   * @param client_id Unique client ID for this connection
   */
  IBKRAdapter(const std::string& host = "ib-gateway",
              int port = 4002,
              int client_id = 1);
  ~IBKRAdapter() override;

  std::optional<FillResult> submit_order(const risk::ApprovedOrder& order,
                                          const std::string& timestamp) override;

  std::vector<risk::Position> get_positions() override;

  bool is_connected() const override;

  bool reconnect() override;

  std::string venue_id() const override { return "ibkr"; }

 private:
  std::string host_;
  int port_;
  int client_id_;
  int sock_fd_ = -1;
  mutable std::mutex mutex_;
  std::atomic<bool> connected_{false};
  int next_order_id_ = 1;
  std::unique_ptr<std::thread> reader_thread_;
  std::atomic<bool> running_{true};

  // Connect to IB Gateway
  bool connect_socket();

  // Send a raw message over the socket
  bool send_message(const std::string& msg);

  // Read and dispatch incoming messages (runs in reader thread)
  void reader_loop();

  // Disconnect
  void disconnect();

  // Decompose venue_symbol into contract parts: symbol, exchange, currency
  // Returns true if decomposition succeeded
  static bool decompose_contract(const std::string& ticker,
                                  const std::string& venue_symbol,
                                  std::string& out_symbol,
                                  std::string& out_exchange,
                                  std::string& out_currency);

  // Build an IBKR order message (paper-only)
  std::string build_order_message(const risk::ApprovedOrder& order,
                                   const std::string& symbol,
                                   const std::string& exchange,
                                   const std::string& currency);
};

}  // namespace graphalpha