#pragma once

#include <string>
#include <optional>
#include "risk/ApprovedOrder.hpp"
#include "graphalpha/paper_fill.hpp"

namespace graphalpha {

class AuditLog {
 public:
  AuditLog(const std::string& conn_str);
  ~AuditLog();

  bool write_order(const risk::ApprovedOrder& order);
  bool write_rejection(const std::string& cycle_id,
                       const std::string& strategy,
                       const std::string& ticker,
                       const std::string& reason);
  bool write_fill(const std::string& order_id, const FillResult& fill);

 private:
  std::string conn_str_;
};

}  // namespace graphalpha
