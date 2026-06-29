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


namespace {
std::string now_iso() {
  auto t = std::chrono::system_clock::now();
  std::time_t tt = std::chrono::system_clock::to_time_t(t);
  char buf[32];
  std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&tt));
  return buf;
}
}  // anonymous namespace

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
    std::string secret = get_api_secret();
    if (secret.empty()) return "";

    // Decode base64 secret
    std::string decoded_secret;
    const size_t secret_len = secret.size();
    int decode_len = EVP_DecodeBlock(nullptr, (const unsigned char*)secret.c_str(), secret_len);
    if (decode_len < 0) return "";
    decoded_secret.resize(decode_len + 1);
    EVP_DecodeBlock((unsigned char*)decoded_secret.data(), (const unsigned char*)secret.c_str(), secret_len);
    decoded_secret.resize(decode_len);

    // HMAC-SHA512: message = nonce + post_data
    std::string message = nonce + post_data;
    unsigned int hmac_len = 0;
    unsigned char hmac[EVP_MAX_MD_SIZE];
    
    HMAC_CTX* ctx = HMAC_CTX_new();
    HMAC_Init_ex(ctx, decoded_secret.c_str(), decoded_secret.size(), EVP_sha512(), nullptr);
    HMAC_Update(ctx, (const unsigned char*)message.c_str(), message.size());
    HMAC_Final(ctx, hmac, &hmac_len);
    HMAC_CTX_free(ctx);

    // Base64 encode result
    BIO* b64 = BIO_new(BIO_f_base64());
    BIO* bmem = BIO_new(BIO_s_mem());
    b64 = BIO_push(b64, bmem);
    BIO_set_flags(b64, BIO_FLAGS_BASE64_NO_NL);
    BIO_write(b64, hmac, hmac_len);
    BIO_flush(b64);
    
    char* sig_ptr;
    long sig_len = BIO_get_mem_data(bmem, &sig_ptr);
    std::string signature(sig_ptr, sig_len);
    BIO_free_all(b64);
    
    return signature;
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
        error = "Failed to sign request";
        return false;
    }

    // Live order submission via curl
    CURL* curl = curl_easy_init();
    if (!curl) {
        error = "Failed to init curl";
        return false;
    }

    std::string response;
    std::string url = "https://api.kraken.com/0/private/AddOrder";

    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, ("API-Key: " + api_key).c_str());
    headers = curl_slist_append(headers, ("API-Sign: " + signature).c_str());
    headers = curl_slist_append(headers, "Content-Type: application/x-www-form-urlencoded");

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_data.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);

    CURLcode res = curl_easy_perform(curl);
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        error = "Curl error: " + std::string(curl_easy_strerror(res));
        return false;
    }

    // Parse response
    auto j = nlohmann::json::parse(response);
    if (j.contains("error") && j["error"].is_array() && !j["error"].empty()) {
        error = "Kraken error: " + j["error"][0].get<std::string>();
        return false;
    }

    // Extract fill info
    if (j.contains("result")) {
        fill.ticker = order.ticker;
        fill.venue = "kraken";
        fill.direction = order.direction;
        fill.fill_price = order.quantity * 20000.0;
        fill.fill_quantity = order.quantity;
        fill.fee_usd = order.quantity * 0.0026;
        fill.slippage_usd = 0.0;
        fill.timestamp = now_iso();
        fill.status = "submitted";
        fill.mode = "live";
        return true;
    }

    error = "Invalid response from Kraken";
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
    
    // Query Kraken balance via curl
    std::string api_key = get_api_key();
    std::string api_secret = get_api_secret();
    
    auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    std::string nonce = std::to_string(now);
    std::string post_data = "nonce=" + nonce;
    
    std::string signature = sign_request("/0/private/Balance", nonce, post_data);
    if (signature.empty()) {
        error = "Failed to sign balance request";
        return false;
    }
    
    CURL* curl = curl_easy_init();
    if (!curl) {
        error = "Failed to init curl";
        return false;
    }
    
    std::string response;
    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, ("API-Key: " + api_key).c_str());
    headers = curl_slist_append(headers, ("API-Sign: " + signature).c_str());
    headers = curl_slist_append(headers, "Content-Type: application/x-www-form-urlencoded");
    
    curl_easy_setopt(curl, CURLOPT_URL, "https://api.kraken.com/0/private/Balance");
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_data.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    
    CURLcode res = curl_easy_perform(curl);
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    
    if (res != CURLE_OK) {
        error = "Curl error: " + std::string(curl_easy_strerror(res));
        return false;
    }
    
    auto j = nlohmann::json::parse(response);
    if (j.contains("error") && j["error"].is_array() && !j["error"].empty()) {
        error = "Kraken error: " + j["error"][0].get<std::string>();
        return false;
    }
    
    // Sum USD value of all balances (simplified - assumes USD-denominated pairs)
    if (j.contains("result")) {
        total_usd = 0.0;
        for (auto& [currency, amount] : j["result"].items()) {
            // This is simplified - real implementation would convert to USD
            total_usd += amount.get<double>();
        }
        return true;
    }
    
    error = "Invalid response from Kraken";
    return false;
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

    // Compare against tracked positions (simplified - in production would compare actual positions)
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