#include "risk/Signal.hpp"
#include <sstream>

namespace risk {

std::optional<Signal> Signal::from_json(const nlohmann::json& j) {
  Signal sig;
  if (!j.contains("schema_version")) throw std::invalid_argument("missing schema_version");
  sig.schema_version = j["schema_version"].get<int>();
  validate_schema_version(sig.schema_version);
  if (!j.contains("cycle_id")) throw std::invalid_argument("missing cycle_id");
  sig.cycle_id = validate_uuid(j["cycle_id"].get<std::string>());
  if (!j.contains("timestamp")) throw std::invalid_argument("missing timestamp");
  sig.timestamp = j["timestamp"].get<std::string>();
  if (!j.contains("regime")) throw std::invalid_argument("missing regime");
  sig.regime = j["regime"].get<std::string>();
  validate_regime(sig.regime);
  if (!j.contains("strategy")) throw std::invalid_argument("missing strategy");
  sig.strategy = j["strategy"].get<std::string>();
  if (!j.contains("ticker")) throw std::invalid_argument("missing ticker");
  sig.ticker = j["ticker"].get<std::string>();
  if (!j.contains("venue")) throw std::invalid_argument("missing venue");
  sig.venue = j["venue"].get<std::string>();
  if (!j.contains("venue_symbol")) throw std::invalid_argument("missing venue_symbol");
  sig.venue_symbol = j["venue_symbol"].get<std::string>();
  if (!j.contains("asset_class")) throw std::invalid_argument("missing asset_class");
  sig.asset_class = j["asset_class"].get<std::string>();
  if (!j.contains("direction")) throw std::invalid_argument("missing direction");
  sig.direction = direction_from_string(j["direction"].get<std::string>());
  if (!j.contains("score")) throw std::invalid_argument("missing score");
  sig.score = j["score"].get<double>();
  validate_range("score", sig.score, -1.0, 1.0);
  sig.quant_score = j.value("quant_score", 0.0);
  validate_range("quant_score", sig.quant_score, -1.0, 1.0);
  sig.sentiment_score = j.value("sentiment_score", 0.0);
  validate_range("sentiment_score", sig.sentiment_score, -1.0, 1.0);
  sig.news_overlay = j.value("news_overlay", 0.0);
  validate_range("news_overlay", sig.news_overlay, -1.0, 1.0);
  sig.macro_overlay = j.value("macro_overlay", 0.0);
  validate_range("macro_overlay", sig.macro_overlay, -1.0, 1.0);
  sig.kg_formula_contribution = j.value("kg_formula_contribution", 0.0);
  validate_range("kg_formula_contribution", sig.kg_formula_contribution, -1.0, 1.0);
  sig.contradiction_blocked = j.value("contradiction_blocked", false);
  return sig;
}

nlohmann::json Signal::to_json() const {
  nlohmann::json j;
  j["schema_version"] = schema_version;
  j["cycle_id"] = cycle_id;
  j["timestamp"] = timestamp;
  j["regime"] = regime;
  j["strategy"] = strategy;
  j["ticker"] = ticker;
  j["venue"] = venue;
  j["venue_symbol"] = venue_symbol;
  j["asset_class"] = asset_class;
  j["direction"] = direction_to_string(direction);
  j["score"] = score;
  j["quant_score"] = quant_score;
  j["sentiment_score"] = sentiment_score;
  j["news_overlay"] = news_overlay;
  j["macro_overlay"] = macro_overlay;
  j["kg_formula_contribution"] = kg_formula_contribution;
  j["contradiction_blocked"] = contradiction_blocked;
  return j;
}

} // namespace risk
