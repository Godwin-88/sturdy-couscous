#pragma once

#include <string>
#include <optional>
#include <vector>
#include "risk/ApprovedOrder.hpp"
#include "risk/RiskEngine.hpp"
#include "graphalpha/paper_fill.hpp"

namespace graphalpha {

/**
 * VenueAdapter — common interface for execution venue connectors.
 *
 * Both KrakenAdapter and IBKRAdapter implement this interface so that
 * ExecutionEngine can route orders without venue-specific branching.
 */
class VenueAdapter {
 public:
  virtual ~VenueAdapter() = default;

  /**
   * Submit an approved order to the venue.
   * Returns a FillResult on success, std::nullopt on rejection/failure.
   * The adapter is responsible for:
   *   - enforcing mode constraints (paper-only checks)
   *   - converting ApprovedOrder to venue-native format
   *   - receiving fill confirmation from the venue
   *   - reporting fill_price / fee / slippage from the venue's response
   */
  virtual std::optional<FillResult> submit_order(const risk::ApprovedOrder& order,
                                                  const std::string& timestamp) = 0;

  /**
   * Report current open positions from this venue.
   * Used by PortfolioState aggregation on restart/reconnect.
   */
  virtual std::vector<risk::Position> get_positions() = 0;

  /**
   * Health check: is the venue connection alive?
   */
  virtual bool is_connected() const = 0;

  /**
   * Attempt reconnection. Returns true if connection was (re)established.
   */
  virtual bool reconnect() = 0;

  /**
   * Venue identifier string, e.g. "kraken" or "ibkr".
   */
  virtual std::string venue_id() const = 0;
};

}  // namespace graphalpha