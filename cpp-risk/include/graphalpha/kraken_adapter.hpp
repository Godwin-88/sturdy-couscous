#pragma once

#include <string>
#include <vector>
#include "graphalpha/venue_adapter.hpp"
#include "graphalpha/paper_fill.hpp"

namespace graphalpha {

/**
 * KrakenAdapter — execution venue connector for Kraken (crypto).
 *
 * In P4/P5/P6, Kraken operates exclusively in paper mode.
 * This adapter wraps the PaperFillSimulator for fills and enforces
 * the paper-only constraint at the adapter level (defense in depth).
 */
class KrakenAdapter : public VenueAdapter {
 public:
  KrakenAdapter();
  ~KrakenAdapter() override = default;

  std::optional<FillResult> submit_order(const risk::ApprovedOrder& order,
                                          const std::string& timestamp) override;

  std::vector<risk::Position> get_positions() override;

  bool is_connected() const override;

  bool reconnect() override;

  std::string venue_id() const override { return "kraken"; }

 private:
  bool connected_ = true;  // Paper mode — always "connected"
};

}  // namespace graphalpha