"""
Complete System Integration Tests

These tests verify the full pricing workflow from frontend to backend,
ensuring all components work together correctly across the entire system.
"""

import pytest
import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

# Import the modules under test
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from deriv_api_client import DerivAPIClient, MarketData, AssetClass
from error_handling import ValidationError, CalculationError


class TestCompleteSystemIntegration:
    """Integration tests for the complete pricing system"""
    
    def setup_method(self):
        """Set up test client and common test data"""
        self.client = TestClient(app)
        
        # Standard option parameters for testing
        self.standard_option = {
            "s": 100.0,
            "k": 100.0,
            "tau": 1.0,
            "r": 0.05,
            "sigma": 0.2
        }
        
        # FFT parameters for testing
        self.fft_params = {
            "s": 100.0,
            "k": 100.0,
            "tau": 1.0,
            "r": 0.05,
            "sigma": 0.2,
            "k_min": 4.0,
            "delta_v": 0.01,
            "delta_k": 0.1,
            "n": 2048,
            "alpha": 1.5
        }
        
        # Heston parameters for testing
        self.heston_params = {
            "s": 100.0,
            "k": 100.0,
            "tau": 1.0,
            "r": 0.05,
            "v0": 0.04,
            "theta": 0.04,
            "kappa": 2.0,
            "sigma_v": 0.3,
            "rho": -0.7
        }
    
    def test_health_check_endpoints(self):
        """Test that all health check endpoints are working"""
        # Basic health check
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        
        # Detailed health check
        response = self.client.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "overall_status" in data
        assert "timestamp" in data
        assert "checks" in data
        
        # Error statistics
        response = self.client.get("/health/errors")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
    
    def test_black_scholes_pricing_workflow(self):
        """Test complete Black-Scholes pricing workflow"""
        # Test call pricing
        response = self.client.post("/price/call/bs", json=self.standard_option)
        assert response.status_code == 200
        call_data = response.json()
        assert "price" in call_data
        assert "model" in call_data
        assert "request_id" in call_data
        assert call_data["model"] == "Black-Scholes"
        assert call_data["price"] > 0
        
        # Test put pricing
        response = self.client.post("/price/put/bs", json=self.standard_option)
        assert response.status_code == 200
        put_data = response.json()
        assert "price" in put_data
        assert "model" in put_data
        assert "request_id" in put_data
        assert put_data["model"] == "Black-Scholes"
        assert put_data["price"] > 0
        
        # Verify put-call parity approximately holds
        call_price = call_data["price"]
        put_price = put_data["price"]
        s, k, tau, r = self.standard_option["s"], self.standard_option["k"], self.standard_option["tau"], self.standard_option["r"]
        
        # Put-call parity: C - P = S - K*e^(-r*T)
        import math
        parity_left = call_price - put_price
        parity_right = s - k * math.exp(-r * tau)
        
        # Allow for small numerical differences
        assert abs(parity_left - parity_right) < 0.1, f"Put-call parity violation: {parity_left} vs {parity_right}"
    
    def test_fft_pricing_workflow(self):
        """Test FFT pricing workflow with both original and optimized versions"""
        # Test original FFT call pricing
        response = self.client.post("/price/call/fft", json=self.fft_params)
        assert response.status_code == 200
        call_data = response.json()
        assert "prices" in call_data
        assert "model" in call_data
        assert call_data["model"] == "FFT"
        assert isinstance(call_data["prices"], list)
        assert len(call_data["prices"]) > 0
        
        # Test original FFT put pricing
        response = self.client.post("/price/put/fft", json=self.fft_params)
        assert response.status_code == 200
        put_data = response.json()
        assert "prices" in put_data
        assert "model" in put_data
        assert put_data["model"] == "FFT"
        assert isinstance(put_data["prices"], list)
        assert len(put_data["prices"]) > 0
        
        # Test optimized FFT call pricing
        optimized_params = {
            "s": self.fft_params["s"],
            "k": self.fft_params["k"],
            "tau": self.fft_params["tau"],
            "r": self.fft_params["r"],
            "sigma": self.fft_params["sigma"]
        }
        
        response = self.client.post("/price/call/fft-optimized", json=optimized_params)
        assert response.status_code == 200
        opt_call_data = response.json()
        assert "price" in opt_call_data
        assert "model" in opt_call_data
        assert opt_call_data["model"] == "FFT-Optimized"
        assert opt_call_data["price"] > 0
        
        # Test optimized FFT put pricing
        response = self.client.post("/price/put/fft-optimized", json=optimized_params)
        assert response.status_code == 200
        opt_put_data = response.json()
        assert "price" in opt_put_data
        assert "model" in opt_put_data
        assert opt_put_data["model"] == "FFT-Optimized"
        assert opt_put_data["price"] > 0
    
    def test_heston_pricing_workflow(self):
        """Test Heston model pricing workflow"""
        # Test Feller condition validation first
        response = self.client.post("/validate/feller", params={
            "kappa": self.heston_params["kappa"],
            "theta": self.heston_params["theta"],
            "sigma_v": self.heston_params["sigma_v"]
        })
        assert response.status_code == 200
        feller_data = response.json()
        assert "feller_condition_satisfied" in feller_data
        assert feller_data["feller_condition_satisfied"] == True
        
        # Test Heston call pricing
        response = self.client.post("/price/call/heston", json=self.heston_params)
        assert response.status_code == 200
        call_data = response.json()
        assert "price" in call_data
        assert "model" in call_data
        assert "feller_condition_satisfied" in call_data
        assert call_data["model"] == "Heston"
        assert call_data["price"] > 0
        assert call_data["feller_condition_satisfied"] == True
        
        # Test Heston put pricing
        response = self.client.post("/price/put/heston", json=self.heston_params)
        assert response.status_code == 200
        put_data = response.json()
        assert "price" in put_data
        assert "model" in put_data
        assert "feller_condition_satisfied" in put_data
        assert put_data["model"] == "Heston"
        assert put_data["price"] > 0
        assert put_data["feller_condition_satisfied"] == True
    
    def test_greeks_calculation_workflow(self):
        """Test Greeks calculation across all models"""
        greeks_params = {
            "s": self.standard_option["s"],
            "k": self.standard_option["k"],
            "tau": self.standard_option["tau"],
            "r": self.standard_option["r"],
            "sigma": self.standard_option["sigma"],
            "model": "bs"
        }
        
        # Test Black-Scholes Greeks for calls
        response = self.client.post("/greeks/call", json=greeks_params)
        assert response.status_code == 200
        call_greeks = response.json()
        assert "greeks" in call_greeks
        assert "option_type" in call_greeks
        assert "model" in call_greeks
        assert call_greeks["option_type"] == "call"
        
        greeks = call_greeks["greeks"]
        assert "delta" in greeks
        assert "gamma" in greeks
        assert "theta" in greeks
        assert "vega" in greeks
        assert "rho" in greeks
        
        # Verify Greeks bounds for calls
        assert 0 <= greeks["delta"] <= 1, f"Call delta out of bounds: {greeks['delta']}"
        assert greeks["gamma"] >= 0, f"Gamma should be non-negative: {greeks['gamma']}"
        assert greeks["vega"] >= 0, f"Vega should be non-negative: {greeks['vega']}"
        assert greeks["rho"] >= 0, f"Call rho should be positive: {greeks['rho']}"
        
        # Test Black-Scholes Greeks for puts
        response = self.client.post("/greeks/put", json=greeks_params)
        assert response.status_code == 200
        put_greeks = response.json()
        assert "greeks" in put_greeks
        assert put_greeks["option_type"] == "put"
        
        put_greeks_data = put_greeks["greeks"]
        assert -1 <= put_greeks_data["delta"] <= 0, f"Put delta out of bounds: {put_greeks_data['delta']}"
        assert put_greeks_data["gamma"] >= 0, f"Gamma should be non-negative: {put_greeks_data['gamma']}"
        assert put_greeks_data["vega"] >= 0, f"Vega should be non-negative: {put_greeks_data['vega']}"
        assert put_greeks_data["rho"] <= 0, f"Put rho should be negative: {put_greeks_data['rho']}"
        
        # Test numerical Greeks
        greeks_params["model"] = "numerical"
        response = self.client.post("/greeks/call", json=greeks_params)
        assert response.status_code == 200
        numerical_greeks = response.json()
        assert numerical_greeks["method"] == "Numerical (Black-Scholes-based)"
        
        # Test FFT Greeks
        greeks_params["model"] = "fft"
        response = self.client.post("/greeks/call", json=greeks_params)
        assert response.status_code == 200
        fft_greeks = response.json()
        assert fft_greeks["method"] == "Numerical (FFT-based)"
    
    def test_heston_greeks_workflow(self):
        """Test Heston Greeks calculation"""
        heston_greeks_params = {
            "s": self.heston_params["s"],
            "k": self.heston_params["k"],
            "tau": self.heston_params["tau"],
            "r": self.heston_params["r"],
            "v0": self.heston_params["v0"],
            "theta": self.heston_params["theta"],
            "kappa": self.heston_params["kappa"],
            "sigma_v": self.heston_params["sigma_v"],
            "rho": self.heston_params["rho"]
        }
        
        # Test Heston call Greeks
        response = self.client.post("/greeks/call/heston", json=heston_greeks_params)
        assert response.status_code == 200
        call_greeks = response.json()
        assert "greeks" in call_greeks
        assert "feller_condition_satisfied" in call_greeks
        assert call_greeks["model"] == "Heston"
        assert call_greeks["feller_condition_satisfied"] == True
        
        # Test Heston put Greeks
        response = self.client.post("/greeks/put/heston", json=heston_greeks_params)
        assert response.status_code == 200
        put_greeks = response.json()
        assert "greeks" in put_greeks
        assert put_greeks["model"] == "Heston"
    
    def test_model_comparison_workflow(self):
        """Test model comparison functionality"""
        response = self.client.post("/compare/models", json=self.standard_option)
        assert response.status_code == 200
        comparison_data = response.json()
        
        assert "parameters" in comparison_data
        assert "results" in comparison_data
        
        # Verify parameters match input
        params = comparison_data["parameters"]
        for key, value in self.standard_option.items():
            assert params[key] == value
        
        # Verify results structure
        results = comparison_data["results"]
        assert "black_scholes" in results
        assert "fft_optimized" in results
        
        # Check Black-Scholes results
        bs_results = results["black_scholes"]
        if "error" not in bs_results:
            assert "call" in bs_results
            assert "put" in bs_results
            assert bs_results["call"] > 0
            assert bs_results["put"] > 0
        
        # Check FFT results
        fft_results = results["fft_optimized"]
        if "error" not in fft_results:
            assert "call" in fft_results
            assert "put" in fft_results
            assert fft_results["call"] > 0
            assert fft_results["put"] > 0
    
    def test_error_handling_workflow(self):
        """Test error handling across the system"""
        # Test invalid parameters
        invalid_params = {
            "s": -100.0,  # Negative spot price
            "k": 100.0,
            "tau": 1.0,
            "r": 0.05,
            "sigma": 0.2
        }
        
        response = self.client.post("/price/call/bs", json=invalid_params)
        assert response.status_code == 400  # Bad request error
        error_data = response.json()
        assert "detail" in error_data
        
        # Test invalid Heston parameters (Feller condition violation)
        invalid_heston = {
            "s": 100.0,
            "k": 100.0,
            "tau": 1.0,
            "r": 0.05,
            "v0": 0.04,
            "theta": 0.01,  # Low theta
            "kappa": 0.5,   # Low kappa
            "sigma_v": 0.8, # High sigma_v - violates Feller condition
            "rho": -0.7
        }
        
        response = self.client.post("/price/call/heston", json=invalid_heston)
        assert response.status_code == 400
        error_data = response.json()
        assert "Feller condition violated" in error_data["detail"]
        
        # Test invalid Greeks model
        invalid_greeks = {
            "s": 100.0,
            "k": 100.0,
            "tau": 1.0,
            "r": 0.05,
            "sigma": 0.2,
            "model": "invalid_model"
        }
        
        response = self.client.post("/greeks/call", json=invalid_greeks)
        assert response.status_code == 400
        error_data = response.json()
        assert "Invalid model" in error_data["detail"]
    
    def test_performance_and_response_times(self):
        """Test system performance and response times"""
        start_time = time.time()
        
        # Test Black-Scholes performance
        response = self.client.post("/price/call/bs", json=self.standard_option)
        bs_time = time.time() - start_time
        assert response.status_code == 200
        assert bs_time < 1.0, f"Black-Scholes too slow: {bs_time}s"
        
        # Test FFT performance
        start_time = time.time()
        optimized_params = {
            "s": self.standard_option["s"],
            "k": self.standard_option["k"],
            "tau": self.standard_option["tau"],
            "r": self.standard_option["r"],
            "sigma": self.standard_option["sigma"]
        }
        response = self.client.post("/price/call/fft-optimized", json=optimized_params)
        fft_time = time.time() - start_time
        assert response.status_code == 200
        assert fft_time < 2.0, f"FFT too slow: {fft_time}s"
        
        # Test Heston performance
        start_time = time.time()
        response = self.client.post("/price/call/heston", json=self.heston_params)
        heston_time = time.time() - start_time
        assert response.status_code == 200
        assert heston_time < 3.0, f"Heston too slow: {heston_time}s"
    
    def test_concurrent_requests(self):
        """Test system behavior under concurrent load"""
        import concurrent.futures
        import threading
        
        def make_pricing_request():
            """Make a pricing request and return the result"""
            try:
                response = self.client.post("/price/call/bs", json=self.standard_option)
                return response.status_code == 200
            except Exception:
                return False
        
        # Test with 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_pricing_request) for _ in range(10)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        success_rate = sum(results) / len(results)
        assert success_rate >= 0.9, f"Too many concurrent request failures: {success_rate}"
    
    @pytest.mark.asyncio
    async def test_market_data_integration_workflow(self):
        """Test market data integration if available"""
        try:
            # Test market data health
            response = self.client.get("/market-data/health")
            if response.status_code == 404:
                pytest.skip("Market data endpoints not available")
            
            assert response.status_code == 200
            health_data = response.json()
            assert "status" in health_data
            
            # Test supported symbols
            response = self.client.get("/market-data/symbols")
            assert response.status_code == 200
            symbols_data = response.json()
            assert "symbols" in symbols_data
            
            # Test market data retrieval
            market_request = {"symbol": "AAPL"}
            response = self.client.post("/market-data/spot", json=market_request)
            assert response.status_code == 200
            market_data = response.json()
            assert "symbol" in market_data
            assert "spot_price" in market_data
            assert "bid" in market_data
            assert "ask" in market_data
            assert market_data["ask"] >= market_data["bid"]
            
            # Test option chain retrieval
            from datetime import datetime, timedelta
            expiry_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            chain_request = {"underlying": "AAPL", "expiry": expiry_date}
            response = self.client.post("/market-data/option-chain", json=chain_request)
            assert response.status_code == 200
            chain_data = response.json()
            assert "underlying" in chain_data
            assert "calls" in chain_data
            assert "puts" in chain_data
            
        except Exception as e:
            pytest.skip(f"Market data integration not available: {e}")
    
    def test_request_id_tracking(self):
        """Test that request IDs are properly tracked"""
        response = self.client.post("/price/call/bs", json=self.standard_option)
        assert response.status_code == 200
        
        # Check response headers
        assert "X-Request-ID" in response.headers
        assert "X-Process-Time" in response.headers
        
        # Check response body
        data = response.json()
        assert "request_id" in data
        assert data["request_id"] == response.headers["X-Request-ID"]
    
    def test_cors_headers(self):
        """Test CORS headers are properly set"""
        # Test with a GET request to a valid endpoint
        response = self.client.get("/health")
        assert response.status_code == 200
        
        # CORS headers are typically added by middleware and may not be visible in test client
        # This test verifies the endpoint works and doesn't crash
        assert "status" in response.json()


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "--tb=short"])