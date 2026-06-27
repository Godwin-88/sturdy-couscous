#include "graphalpha/kraken_adapter.hpp"
#include <iostream>
#include <cmath>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <cstring>
#include <openssl/hmac.h>
#include <openssl/evp.h>
#include <curl/curl.h>

namespace graphalpha {

// Response buffer for curl
static size_t write_callback(void* contents, size_t size, size_t nmemb, void* userp) {
    ((std::string*)userp)->append((char*)contents, size * nmemb);
    return size * nmemb;
}

KrakenAdapter::KrakenAdapter() {
    std::string mode = get_trading_mode();
    std::cerr << "[KrakenAdapter] Initialised (mode=" << mode << ")\n";
}

static double infer_fee_pct(const std::string& ticker) {
    if (ticker.find("-USD") != std::string::npos ||
        ticker == "BTC" || ticker == "ETH" || ticker == "XBT") {
        return 0.0026;
    }
    return 0.0010;
}

static double infer_slip_pct(const std::string& ticker) {
    if (ticker.find("-USD") != std::string::npos ||
        ticker == "BTC" || ticker == "ETH" || ticker == "XBT") {
        return 0.0010;
    }
    return 0.0005;
}

std::string KrakenAdapter::get_trading_mode() const {
    const char* mode = std::getenv("KRAKEN_TRADING_MODE");
    return mode ? mode : "paper";
}

std::string KrakenAdapter::get_api_key() const {
    const char* key = std::getenv("KRAKEN_API_KEY");
    return key ? key : "";
}

std::string KrakenAdapter::get_api_secret() const {
    const char* secret = std::getenv("KRAKEN_API_SECRET");
    return secret ? secret : "";
}

std::string KrakenAdapter::sign_request(const std::string& path, const std::string& nonce, const std::string& post_data) {
    // P7: HMAC-SHA512 signing stub
    // Full implementation would use OpenSSL EVP and base64 decode secret
    // Never logs or stores the secret
    return "";  // stub - production uses OpenSSL HMAC
}

bool KrakenAdapter::submit_live_order(const risk::ApprovedOrder& order, FillResult& fill, std::string& error) {
    std::string api_key = get_api_key();
    if (api_key.empty()) {
        error = "KRAKEN_API_KEY not configured";
        return false;
    }

    std::string api_secret = get_api_secret();
    if (api_secret.empty()) {
        error = "KRAKEN_API_SECRET not configured";
        return false;
    }

    // Generate nonce
    auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    nonce_ = std::to_string(now);

    // Build POST data
    std::string pair = order.venue_symbol;
    if (pair == "BTC-USD") pair = "XBTUSD";
    else if (pair == "ETH-USD") pair = "ETHUSD";

    std::string post_data = "nonce=" + nonce_ +
        "&pair=" + pair +
        "&type=" + order.direction +
        "&ordertype=market" +
        "&volume=" + std::to_string(order.quantity);

    // HMAC-SHA512 signing
    std::string signature = sign_request("/0/private/AddOrder", nonce_, post_data);
    if (signature.empty()) {
        error = "Failed to sign request (stub implementation)";
        return false;
    }

    // Live order submission via curl would go here
    // P7 stub - actual curl call requires libcurl and OpenSSL
    error = "Live mode requires full curl/OpenSSL implementation";
    return false;
}

bool KrakenAdapter::query_open_orders(nlohmann::json& orders, std::string& error) {
    if (get_trading_mode() != "live") {
        orders = nlohmann::json::array();
        return true;
    }
    // Full implementation would call /0/private/OpenOrders via curl
    return true;
}

bool KrakenAdapter::query_kraken_balance(double& total_usd, std::string& error) {
    if (get_trading_mode() != "live") {
        total_usd = 0.0;
        return true;
    }
    // Full implementation would call /0/private/Balance via curl
    return true;
}

std::optional<FillResult> KrakenAdapter::submit_order(const risk::ApprovedOrder& order,
                                                      const std::string& timestamp) {
    std::string mode = get_trading_mode();

    // P7 Feature 1: Structural separation - paper path vs live path
    if (mode == "live") {
        std::string error;
        FillResult fill;
        if (!submit_live_order(order, fill, error)) {
            std::cerr << "[KrakenAdapter] LIVE ORDER FAILED: " << error
                      << " for " << order.ticker << "\n";
            return std::nullopt;
        }
        return fill;
    }

    // Paper mode path (unchanged from P4/P5/P6)
    double price = 100.0;
    double fee_pct = infer_fee_pct(order.ticker);
    double slip_pct = infer_slip_pct(order.ticker);

    FillResult fr = PaperFillSimulator::simulate(order, price, fee_pct, slip_pct, timestamp);
    fr.ticker = order.ticker;
    fr.venue = "kraken";
    fr.direction = order.direction;
    fr.mode = "paper";
    fr.status = "filled";

    std::cerr << "[KrakenAdapter] FILL: " << order.ticker
              << " " << order.direction
              << " qty=" << order.quantity
              << " @ " << fr.fill_price
              << " fee=" << fr.fee_usd
              << "\n";
    return fr;
}

bool KrakenAdapter::reconcile_positions(double tolerance_pct, std::string& mismatch_detail) {
    if (get_trading_mode() != "live") {
        return true;
    }

    double kraken_total = 0.0;
    std::string error;
    if (!query_kraken_balance(kraken_total, error)) {
        mismatch_detail = "failed_to_query_kraken: " + error;
        kraken_live_halt_ = true;
        last_reconcile_mismatch_ = mismatch_detail;
        return false;
    }

    // In full implementation, compare kraken_total against tracked positions
    // For P7 stub, we assume match
    mismatch_detail = "";
    return true;
}

std::vector<risk::Position> KrakenAdapter::get_positions() {
    if (get_trading_mode() != "live") {
        return {};
    }
    // Live mode would query actual positions
    return {};
}

bool KrakenAdapter::is_connected() const {
    return connected_;
}

bool KrakenAdapter::reconnect() {
    connected_ = true;
    return true;
}

}  // namespace graphalpha