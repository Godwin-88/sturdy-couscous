#pragma once

#include <string>
#include <optional>
#include <vector>
#include <map>
#include <nlohmann/json.hpp>
#include "risk/ApprovedOrder.hpp"
#include "graphalpha/paper_fill.hpp"

namespace graphalpha {

class EventPublisher {
 public:
  EventPublisher(const std::string& redis_host,
                 int redis_port,
                 const std::string& channel = "graphalpha:events");
  ~EventPublisher();

  bool publish(const std::string& event_type,
               const std::string& ticker,
               const std::string& detail);
  bool publish_order_approved(const risk::ApprovedOrder& order);
  bool publish_order_filled(const FillResult& fill);
  bool publish_order_rejected(const std::string& cycle_id,
                               const std::string& ticker,
                               const std::string& reason);
  bool publish_halt(bool halted);
  bool subscribe(const std::string& channel);
  void set_subscriber_callback(std::function<void(const std::string&)> cb);

  private:
  bool _publish_json(const std::string& message);
  std::string redis_host_;
  int redis_port_;
  std::string channel_;
};

}  // namespace graphalpha
