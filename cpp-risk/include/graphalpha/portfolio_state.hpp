#pragma once

#include <string>
#include <vector>
#include <algorithm>
#include "risk/RiskEngine.hpp"

namespace graphalpha {

struct Position {
  std::string ticker;
  std::string venue;
  std::string asset_class;
  std::string sector;
  double quantity = 0.0;
  double notional = 0.0;
};

inline void update_position(risk::PortfolioState& pf,
                            const risk::ApprovedOrder& order,
                            double fill_price,
                            double fee_usd,
                            double slippage_usd) {
  std::string ticker = order.ticker;
  std::string venue = order.venue;
  std::string dir = order.direction;
  auto it = std::find_if(pf.positions.begin(), pf.positions.end(),
                         [&](const risk::Position& p) {
                           return p.ticker == ticker && p.venue == venue;
                         });
  if (dir == "buy") {
    if (it != pf.positions.end()) {
      double old_qty = it->quantity;
      double old_not = it->notional;
      double new_qty = old_qty + order.quantity;
      double new_not = old_not + order.notional_usd;
      it->quantity = new_qty;
      it->notional = new_not;
    } else {
      pf.positions.push_back(risk::Position{
          ticker, venue, "", "", order.quantity, order.notional_usd});
    }
  } else if (dir == "sell") {
    if (it != pf.positions.end()) {
      it->quantity -= order.quantity;
      it->notional -= order.notional_usd;
      if (it->quantity <= 1e-9) {
        pf.positions.erase(it);
      }
    }
  }
}

inline double compute_drawdown(double nav, double peak) {
  if (peak <= 0.0) return 0.0;
  return (peak - nav) / std::max(peak, 1.0);
}

inline double update_nav(double old_nav,
                         const risk::ApprovedOrder& order,
                         double fill_price,
                         double fee_usd,
                         double slippage_usd) {
  double pnl = 0.0;
  if (order.direction == "sell" && order.quantity > 0) {
    pnl = order.quantity * (fill_price - order.notional_usd / std::max(order.quantity, 1e-9))
          - fee_usd - slippage_usd;
  }
  return old_nav + pnl;
}

}  // namespace graphalpha
