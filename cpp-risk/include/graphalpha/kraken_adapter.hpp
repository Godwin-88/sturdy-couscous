#pragma once

#include <string>
#include <vector>
#include "graphalpha/venue_adapter.hpp"
#include "graphalpha/paper_fill.hpp"

namespace graphalpha {

/**
 * KrakenAdapter — execution venue connector for Kraken (crypto).
 *
 * Supports both paper and live trading modes.
 * Live mode requires KRAKEN_TRADING_MODE=live and explicit confirmation.
 * API keys are read from .env and never logged.
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

   /** P7 Feature 2: Reconcile positions against live Kraken account */
   bool reconcile_positions(double tolerance_pct, std::string& mismatch_detail);

   /** P7 Feature 2: Query live Kraken balance */
   bool query_kraken_balance(double& total_usd, std::string& error);

   /** P7 Feature 2: Get last reconciliation mismatch */
   std::string last_reconciliation_mismatch() const { return last_reconcile_mismatch_; }

   /** P7 Feature 2: Clear reconciliation halt state */
   void clear_reconciliation_halt() { kraken_live_halt_ = false; }

   /** P7 Feature 2: Check if Kraken live trading is halted due to reconciliation */
   bool is_kraken_live_halted() const { return kraken_live_halt_; }

  private:
   bool connected_ = true;
   bool kraken_live_halt_ = false;
   std::string last_reconcile_mismatch_;

   /** P7 Feature 1: Live mode REST client */
   bool submit_live_order(const risk::ApprovedOrder& order, FillResult& fill, std::string& error);
   std::string nonce_;
   std::string sign_request(const std::string& path, const std::string& nonce, const std::string& post_data);

   /** P7 Feature 1: Get API credentials (never stored in logs) */
   std::string get_api_key() const;
   std::string get_api_secret() const;
   std::string get_trading_mode() const;

   /** P7 Feature 2: Query open orders from Kraken */
   bool query_open_orders(nlohmann::json& orders, std::string& error);
};

}  // namespace graphalpha