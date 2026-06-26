#include "graphalpha/kraken_adapter.hpp"
#include <iostream>
#include <cmath>

namespace graphalpha {

KrakenAdapter::KrakenAdapter() {
  std::cerr << "[KrakenAdapter] Initialised (paper mode)\n";
}

static double infer_fee_pct(const std::string& ticker) {
  if (ticker.find("-USD") != std::string::npos || 
      ticker == "BTC" || ticker == "ETH" || ticker == "XBT") {
    return 0.0026;
  }
  return 0.0010;
}

static double infer_slip_pct(const std::string& ticker) {
  if (ticker.find("-USD") != std::string::npos || 
      ticker == "BTC" || ticker == "ETH" || ticker == "XBT") {
    return 0.0010;
  }
  return 0.0005;
}

std::optional<FillResult> KrakenAdapter::submit_order(const risk::ApprovedOrder& order,
                                                        const std::string& timestamp) {
  // Defense in depth: reject any non-paper order at the adapter level
  if (order.mode != "paper") {
    std::cerr << "[KrakenAdapter] REJECTED: non-paper mode '" << order.mode
              << "' for " << order.ticker << "\n";
    return std::nullopt;
  }

  // Use a default price of 100.0 for simulation (no live price feed in paper mode)
  double price = 100.0;
  double fee_pct = infer_fee_pct(order.ticker);
  double slip_pct = infer_slip_pct(order.ticker);

  FillResult fr = PaperFillSimulator::simulate(order, price, fee_pct, slip_pct, timestamp);
  fr.ticker = order.ticker;
  fr.venue = "kraken";
  fr.direction = order.direction;
  fr.mode = "paper";
  fr.status = "filled";

  std::cerr << "[KrakenAdapter] FILL: " << order.ticker
            << " " << order.direction
            << " qty=" << order.quantity
            << " @ " << fr.fill_price
            << " fee=" << fr.fee_usd
            << "\n";
  return fr;
}

std::vector<risk::Position> KrakenAdapter::get_positions() {
  // Paper mode: no real positions to report; the PortfolioLoader/PG handles state
  return {};
}

bool KrakenAdapter::is_connected() const {
  return connected_;
}

bool KrakenAdapter::reconnect() {
  connected_ = true;
  return true;
}

}  // namespace graphalpha