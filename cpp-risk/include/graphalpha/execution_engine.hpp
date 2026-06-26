#pragma once

#include <string>
#include <optional>
#include <vector>
#include <memory>
#include <map>
#include "risk/ApprovedOrder.hpp"
#include "graphalpha/portfolio_state.hpp"
#include "graphalpha/paper_fill.hpp"
#include "graphalpha/venue_adapter.hpp"

namespace graphalpha {

class ExecutionEngine {
  public:
   ExecutionEngine();

   /// Register a venue adapter (e.g. KrakenAdapter, IBKRAdapter)
   void register_adapter(std::unique_ptr<VenueAdapter> adapter);

   /// Route an approved order to the correct venue adapter based on order.venue
   /// Returns a FillResult on success, std::nullopt on rejection/failure
   std::optional<FillResult> execute(const risk::ApprovedOrder& order,
                                     const std::string& timestamp);

   /// Get aggregated positions from all registered adapters
   std::vector<risk::Position> get_all_positions();

   /// Check if all configured adapters are connected
   bool all_connected() const;

   /// Attempt to reconnect all adapters
   void reconnect_all();

  private:
   std::map<std::string, std::unique_ptr<VenueAdapter>> adapters_;
};

}  // namespace graphalpha
