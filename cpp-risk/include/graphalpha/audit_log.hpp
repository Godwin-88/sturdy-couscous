#pragma once

#include <string>
#include <optional>
#include <vector>
#include "risk/ApprovedOrder.hpp"
#include "graphalpha/paper_fill.hpp"
#include "nlohmann/json.hpp"

namespace graphalpha {

class AuditLog {
 public:
  AuditLog(const std::string& conn_str);
  ~AuditLog();

  bool write_order(const std::string& order_id, const risk::ApprovedOrder& order, const FillResult& fill);
  bool write_rejection(const std::string& cycle_id,
                       const std::string& strategy,
                       const std::string& ticker,
                       const std::string& reason);
  bool write_shadow_comparison(const std::string& cycle_id,
                               const std::string& ticker,
                               const std::string& strategy,
                               const nlohmann::json& signal,
                               const nlohmann::json& decision);
  bool write_fill(const std::string& order_id, const FillResult& fill);

 private:
  std::string conn_str_;
};

}  // namespace graphalpha
