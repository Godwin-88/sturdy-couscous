#include "graphalpha/execution_engine.hpp"
#include <iostream>
#include <algorithm>

namespace graphalpha {

ExecutionEngine::ExecutionEngine() {
   std::cerr << "[ExecutionEngine] Initialised (venue-routed mode)\n";
}

void ExecutionEngine::register_adapter(std::unique_ptr<VenueAdapter> adapter) {
   std::string vid = adapter->venue_id();
   adapters_[vid] = std::move(adapter);
   std::cerr << "[ExecutionEngine] Registered adapter for venue: " << vid << "\n";
}

std::optional<FillResult> ExecutionEngine::execute(const risk::ApprovedOrder& order,
                                                  const std::string& timestamp) {
   auto it = adapters_.find(order.venue);
   if (it == adapters_.end()) {
     std::cerr << "[ExecutionEngine] No adapter registered for venue '"
               << order.venue << "' (ticker=" << order.ticker << ")\n";
     return std::nullopt;
   }

   VenueAdapter* adapter = it->second.get();
   if (!adapter->is_connected()) {
     std::cerr << "[ExecutionEngine] Adapter '" << order.venue
               << "' not connected, attempting reconnect...\n";
     if (!adapter->reconnect()) {
       std::cerr << "[ExecutionEngine] Reconnect failed for '" << order.venue
                 << "', rejecting order for " << order.ticker << "\n";
       return std::nullopt;
     }
   }

   return adapter->submit_order(order, timestamp);
}

std::vector<risk::Position> ExecutionEngine::get_all_positions() {
   std::vector<risk::Position> all;
   for (auto& kv : adapters_) {
     auto positions = kv.second->get_positions();
     all.insert(all.end(), positions.begin(), positions.end());
   }
   return all;
}

VenueAdapter* ExecutionEngine::get_adapter(const std::string& venue_id) {
   auto it = adapters_.find(venue_id);
   if (it == adapters_.end()) return nullptr;
   return it->second.get();
}

bool ExecutionEngine::all_connected() const {
   for (const auto& kv : adapters_) {
     if (!kv.second->is_connected()) return false;
   }
   return !adapters_.empty();
}

void ExecutionEngine::reconnect_all() {
   for (auto& kv : adapters_) {
     if (!kv.second->is_connected()) {
       kv.second->reconnect();
     }
   }
}

}  // namespace graphalpha