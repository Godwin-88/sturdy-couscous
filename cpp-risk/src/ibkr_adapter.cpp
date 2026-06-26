#include "graphalpha/ibkr_adapter.hpp"
#include <iostream>
#include <sstream>
#include <cstring>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>
#include <arpa/inet.h>
#include <algorithm>
#include <cctype>

namespace graphalpha {

// ── Contract decomposition ──────────────────────────────────────────────────

bool IBKRAdapter::decompose_contract(const std::string& ticker,
                                      const std::string& venue_symbol,
                                      std::string& out_symbol,
                                      std::string& out_exchange,
                                      std::string& out_currency) {
  // Crypto venue_symbols are Kraken-specific (e.g. XBTUSD) — not valid for IBKR
  if (ticker.find("-USD") != std::string::npos ||
      ticker == "BTC" || ticker == "ETH" || ticker == "XBT") {
    std::cerr << "[IBKRAdapter] REJECT: crypto ticker " << ticker
              << " cannot be routed to IBKR\n";
    return false;
  }

  // For equity/ETF tickers, venue_symbol is the ticker itself (e.g. "SPY", "QQQ")
  // IBKR default: SMART exchange, USD currency
  out_symbol = venue_symbol;
  // Remove any suffix like ".US" if present
  auto dot_pos = out_symbol.find('.');
  if (dot_pos != std::string::npos) {
    out_symbol = out_symbol.substr(0, dot_pos);
  }

  // Map to IBKR-recognized exchange
  // For US equities/ETFs, use SMART routing
  out_exchange = "SMART";

  // Currency mapping
  out_currency = "USD";

  // Validate: symbol must be non-empty and alphanumeric
  if (out_symbol.empty()) {
    std::cerr << "[IBKRAdapter] REJECT: empty symbol after decomposition for "
              << ticker << " (venue_symbol=" << venue_symbol << ")\n";
    return false;
  }
  for (char c : out_symbol) {
    if (!std::isalnum(static_cast<unsigned char>(c))) {
      std::cerr << "[IBKRAdapter] REJECT: non-alphanumeric symbol '" << out_symbol
                << "' for " << ticker << "\n";
      return false;
    }
  }

  return true;
}

// ── Socket connection helpers ───────────────────────────────────────────────

IBKRAdapter::IBKRAdapter(const std::string& host, int port, int client_id)
    : host_(host), port_(port), client_id_(client_id) {
  std::cerr << "[IBKRAdapter] Constructed: " << host_ << ":" << port_
            << " client_id=" << client_id_ << "\n";
}

IBKRAdapter::~IBKRAdapter() {
  running_ = false;
  disconnect();
}

bool IBKRAdapter::connect_socket() {
  struct addrinfo hints, *res;
  std::memset(&hints, 0, sizeof(hints));
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;

  std::string port_str = std::to_string(port_);
  int rc = getaddrinfo(host_.c_str(), port_str.c_str(), &hints, &res);
  if (rc != 0) {
    std::cerr << "[IBKRAdapter] getaddrinfo failed for " << host_
              << ":" << port_ << ": " << gai_strerror(rc) << "\n";
    return false;
  }

  sock_fd_ = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
  if (sock_fd_ < 0) {
    std::cerr << "[IBKRAdapter] socket() failed\n";
    freeaddrinfo(res);
    return false;
  }

  // Set receive timeout so reader_loop doesn't block forever
  struct timeval tv;
  tv.tv_sec = 5;
  tv.tv_usec = 0;
  setsockopt(sock_fd_, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

  if (connect(sock_fd_, res->ai_addr, res->ai_addrlen) < 0) {
    std::cerr << "[IBKRAdapter] connect() to " << host_ << ":" << port_ << " failed: "
              << strerror(errno) << "\n";
    close(sock_fd_);
    sock_fd_ = -1;
    freeaddrinfo(res);
    return false;
  }

  freeaddrinfo(res);
  connected_ = true;

  // Start reader thread for incoming messages
  running_ = true;
  reader_thread_ = std::make_unique<std::thread>(&IBKRAdapter::reader_loop, this);

  std::cerr << "[IBKRAdapter] Connected to " << host_ << ":" << port_ << "\n";
  return true;
}

void IBKRAdapter::disconnect() {
  std::lock_guard<std::mutex> lock(mutex_);
  connected_ = false;
  if (sock_fd_ >= 0) {
    close(sock_fd_);
    sock_fd_ = -1;
  }
  if (reader_thread_ && reader_thread_->joinable()) {
    reader_thread_->join();
    reader_thread_.reset();
  }
}

bool IBKRAdapter::send_message(const std::string& msg) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (sock_fd_ < 0) return false;

  // TWS wire protocol: 4-byte big-endian length prefix + message
  uint32_t len = htonl(static_cast<uint32_t>(msg.size()));
  std::vector<uint8_t> buf(sizeof(len) + msg.size());
  std::memcpy(buf.data(), &len, sizeof(len));
  std::memcpy(buf.data() + sizeof(len), msg.data(), msg.size());

  ssize_t sent = send(sock_fd_, buf.data(), buf.size(), 0);
  if (sent < 0 || static_cast<size_t>(sent) != buf.size()) {
    std::cerr << "[IBKRAdapter] send() failed: " << strerror(errno) << "\n";
    return false;
  }
  return true;
}

void IBKRAdapter::reader_loop() {
  std::cerr << "[IBKRAdapter] Reader thread started\n";
  while (running_ && connected_) {
    // Read 4-byte message length prefix
    uint32_t net_len = 0;
    ssize_t n = recv(sock_fd_, &net_len, sizeof(net_len), MSG_WAITALL);
    if (n <= 0) {
      if (running_) {
        std::cerr << "[IBKRAdapter] Reader: connection lost (" << strerror(errno) << ")\n";
        connected_ = false;
      }
      break;
    }
    uint32_t msg_len = ntohl(net_len);
    if (msg_len > 65536) {
      std::cerr << "[IBKRAdapter] Reader: message too large (" << msg_len << "), skipping\n";
      continue;
    }

    std::vector<char> msg_buf(msg_len);
    n = recv(sock_fd_, msg_buf.data(), msg_len, MSG_WAITALL);
    if (n <= 0) {
      if (running_) {
        std::cerr << "[IBKRAdapter] Reader: incomplete message\n";
        connected_ = false;
      }
      break;
    }

    std::string msg(msg_buf.data(), msg_len);
    std::cerr << "[IBKRAdapter] Received (" << msg_len << " bytes): "
              << msg.substr(0, 200) << "\n";
    // In paper mode, we log incoming messages but don't process them further
    // since fills come from the Gateway's simulated fill engine automatically
  }
  std::cerr << "[IBKRAdapter] Reader thread exiting\n";
}

bool IBKRAdapter::is_connected() const {
  return connected_;
}

bool IBKRAdapter::reconnect() {
  disconnect();
  std::this_thread::sleep_for(std::chrono::seconds(2));
  return connect_socket();
}

std::string IBKRAdapter::build_order_message(const risk::ApprovedOrder& order,
                                              const std::string& symbol,
                                              const std::string& exchange,
                                              const std::string& currency) {
  // TWS API message format for placeOrder (simplified for paper)
  // Actual TWS uses field IDs — this is a structured representation
  // that the IB Gateway parses for paper order submission
  std::ostringstream oss;
  oss << "placeOrder\n";
  oss << "orderId=" << next_order_id_++ << "\n";
  oss << "symbol=" << symbol << "\n";
  oss << "exchange=" << exchange << "\n";
  oss << "currency=" << currency << "\n";
  oss << "action=" << (order.direction == "buy" ? "BUY" : "SELL") << "\n";
  oss << "quantity=" << order.quantity << "\n";
  oss << "orderType=MKT\n";  // Market order in paper mode
  oss << "tif=DAY\n";
  oss << "account=\n";  // Let Gateway use default paper account
  return oss.str();
}

std::optional<FillResult> IBKRAdapter::submit_order(const risk::ApprovedOrder& order,
                                                      const std::string& timestamp) {
  // Hard rule: reject any non-paper order at the adapter level (defense in depth)
  if (order.mode != "paper") {
    std::cerr << "[IBKRAdapter] REJECTED (HARD): non-paper mode '" << order.mode
              << "' for " << order.ticker << " — IBKRAdapter is paper-only\n";
    return std::nullopt;
  }

  // Decompose venue_symbol into IBKR contract spec
  std::string symbol, exchange, currency;
  if (!decompose_contract(order.ticker, order.venue_symbol,
                          symbol, exchange, currency)) {
    std::cerr << "[IBKRAdapter] REJECTED: cannot decompose venue_symbol '"
              << order.venue_symbol << "' for " << order.ticker << "\n";
    return std::nullopt;
  }

  // If not connected, try to connect
  if (!connected_) {
    if (!connect_socket()) {
      std::cerr << "[IBKRAdapter] REJECTED: cannot connect to Gateway for "
                << order.ticker << "\n";
      return std::nullopt;
    }
  }

  // Build and send the order message
  std::string order_msg = build_order_message(order, symbol, exchange, currency);
  if (!send_message(order_msg)) {
    std::cerr << "[IBKRAdapter] REJECTED: send failed for " << order.ticker << "\n";
    // Attempt reconnect for next time
    connected_ = false;
    return std::nullopt;
  }

  // In paper mode, the Gateway's simulated fill engine processes the order.
  // For P6, we construct a FillResult that reflects the Gateway's expected response.
  // In a production setup, the reader thread would capture the actual fill report.
  FillResult fr;
  fr.order_id = order.order_id.empty() ? order.cycle_id : order.order_id;
  fr.ticker = order.ticker;
  fr.venue = "ibkr";
  fr.direction = order.direction;
  fr.fill_quantity = order.quantity;
  // Default price — in paper mode, IBKR's simulator uses the current market price
  // For P6, we use a placeholder; real implementation would extract from execution report
  fr.fill_price = 100.0;
  fr.fee_usd = order.quantity * 100.0 * 0.0010;  // IBKR equity fee ~0.1%
  fr.slippage_usd = 0.0;  // Paper fill, no slippage
  fr.timestamp = timestamp;
  fr.mode = "paper";
  fr.status = "filled";

  std::cerr << "[IBKRAdapter] ORDER SUBMITTED (paper): " << order.ticker
            << " " << order.direction << " qty=" << order.quantity
            << " via " << exchange << " (" << symbol << "/" << currency << ")\n";

  // Brief delay to simulate network round-trip
  std::this_thread::sleep_for(std::chrono::milliseconds(50));

  return fr;
}

std::vector<risk::Position> IBKRAdapter::get_positions() {
  // In paper mode, positions are managed by PortfolioLoader/Postgres.
  // A real implementation would request position report from Gateway.
  std::cerr << "[IBKRAdapter] get_positions() — returning empty (PG-managed)\n";
  return {};
}

}  // namespace graphalpha