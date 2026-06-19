#pragma once

#include <string>
#include <optional>
#include <algorithm>
#include <regex>
#include <stdexcept>
#include <unordered_set>
#include "nlohmann/json.hpp"

namespace risk {

enum class Direction { Buy, Sell, Hold };

inline Direction direction_from_string(const std::string& s) {
  if (s == "buy") return Direction::Buy;
  if (s == "sell") return Direction::Sell;
  if (s == "hold") return Direction::Hold;
  throw std::invalid_argument("invalid direction: " + s);
}

inline std::string direction_to_string(Direction d) {
  switch (d) {
    case Direction::Buy: return "buy";
    case Direction::Sell: return "sell";
    case Direction::Hold: return "hold";
  }
  return "hold";
}

struct Signal {
  int schema_version = 1;
  std::string cycle_id;
  std::string timestamp;
  std::string regime;
  std::string strategy;
  std::string ticker;
  std::string venue;
  std::string venue_symbol;
  std::string asset_class;
  Direction direction = Direction::Hold;
  double score = 0.0;
  double quant_score = 0.0;
  double sentiment_score = 0.0;
  double news_overlay = 0.0;
  double macro_overlay = 0.0;
  double kg_formula_contribution = 0.0;
  bool contradiction_blocked = false;

  static std::optional<Signal> from_json(const nlohmann::json& j);
  nlohmann::json to_json() const;
};

// Schema v1 validation helpers matching Python side
inline void validate_range(const std::string& field, double value, double lo, double hi) {
  if (!(value >= lo && value <= hi)) {
    throw std::invalid_argument(field + " out of range [" + std::to_string(lo) + ", " + std::to_string(hi) + "]: " + std::to_string(value));
  }
}

inline void validate_regime(const std::string& regime) {
  static const std::unordered_set<std::string> valid = {
    "Trending", "MeanReverting", "HighVolatility", "LowVolatility",
    "Crisis", "SystemicStress", "Recovery", "Neutral"
  };
  if (!valid.contains(regime)) {
    throw std::invalid_argument("invalid regime: " + regime);
  }
}

inline void validate_schema_version(int v) {
  if (v != 1) {
    throw std::invalid_argument("unsupported schema version: " + std::to_string(v));
  }
}

inline std::string validate_uuid(const std::string& id) {
  static const std::regex uuid_regex(R"(^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$)", std::regex::icase);
  if (!std::regex_match(id, uuid_regex)) {
    throw std::invalid_argument("invalid cycle_id (expected UUID): " + id);
  }
  return id;
}

} // namespace risk
