"""
Enhanced FFT Pricing Tests

Tests for the improved FFT pricing engine with parameter optimization and stability checks.
These tests validate Requirements 1.1, 1.2, 1.3, 1.4, and 1.5 from the specification.
"""

import math
import pytest
import pricing_engine

# Test parameters
s, tau, r, sigma = 100.0, 1.0, 0.05, 0.2

class TestFFTEnhancedPricing:
    """Test suite for enhanced FFT pricing functionality"""
    
    def test_optimized_call_vs_bs_accuracy(self):
        """Test Requirement 1.1: FFT call prices within 1% of Black-Scholes"""
        # Test various strike prices
        strikes = [80, 90, 100, 110, 120]
        
        for k in strikes:
            bs_call = pricing_engine.price_call(s, k, tau, r, sigma)
            fft_call = pricing_engine.price_call_fft_optimized(s, k, tau, r, sigma)
            
            relative_error = abs(fft_call - bs_call) / bs_call
            assert relative_error < 0.01, f"Strike {k}: FFT call {fft_call:.6f} vs BS {bs_call:.6f}, error: {relative_error:.4%}"
    
    def test_optimized_put_vs_bs_accuracy(self):
        """Test Requirement 1.2: FFT put prices within 1% of Black-Scholes"""
        strikes = [80, 90, 100, 110, 120]
        
        for k in strikes:
            bs_put = pricing_engine.price_put(s, k, tau, r, sigma)
            fft_put = pricing_engine.price_put_fft_optimized(s, k, tau, r, sigma)
            
            relative_error = abs(fft_put - bs_put) / max(bs_put, 0.01)  # Avoid division by zero for very small puts
            assert relative_error < 0.01, f"Strike {k}: FFT put {fft_put:.6f} vs BS {bs_put:.6f}, error: {relative_error:.4%}"
    
    def test_parameter_optimization_stability(self):
        """Test Requirement 1.3: Parameter optimization produces stable results"""
        # Test various market conditions
        test_cases = [
            (100, 100, 0.25, 0.05, 0.15),  # Short-term, low vol
            (100, 100, 1.0, 0.05, 0.2),    # Medium-term, medium vol
            (100, 100, 2.0, 0.05, 0.4),    # Long-term, high vol
            (100, 80, 0.5, 0.03, 0.25),    # ITM call
            (100, 120, 0.5, 0.03, 0.25),   # OTM call
        ]
        
        for s_test, k_test, tau_test, r_test, sigma_test in test_cases:
            # Should not raise exceptions for valid parameters
            try:
                call_price = pricing_engine.price_call_fft_optimized(s_test, k_test, tau_test, r_test, sigma_test)
                put_price = pricing_engine.price_put_fft_optimized(s_test, k_test, tau_test, r_test, sigma_test)
                
                # Prices should be reasonable
                assert call_price >= 0, f"Call price negative: {call_price}"
                assert put_price >= 0, f"Put price negative: {put_price}"
                assert call_price <= s_test, f"Call price {call_price} exceeds spot {s_test}"
                
            except Exception as e:
                pytest.fail(f"Parameter optimization failed for case {test_cases.index((s_test, k_test, tau_test, r_test, sigma_test))}: {e}")
    
    def test_error_handling_invalid_parameters(self):
        """Test Requirement 1.4 & 1.5: Proper error handling for invalid parameters"""
        invalid_cases = [
            (-100, 100, 1.0, 0.05, 0.2),   # Negative spot
            (100, -100, 1.0, 0.05, 0.2),   # Negative strike
            (100, 100, -1.0, 0.05, 0.2),   # Negative time
            (100, 100, 1.0, 0.05, -0.2),   # Negative volatility
            (100, 100, 1.0, 0.05, 3.0),    # Extremely high volatility
        ]
        
        for s_test, k_test, tau_test, r_test, sigma_test in invalid_cases:
            with pytest.raises(ValueError) as exc_info:
                pricing_engine.price_call_fft_optimized(s_test, k_test, tau_test, r_test, sigma_test)
            
            # Error message should contain diagnostic information
            error_msg = str(exc_info.value)
            assert any(keyword in error_msg.lower() for keyword in ['parameter', 'positive', 'invalid', 'stability']), \
                f"Error message lacks diagnostic info: {error_msg}"
    
    def test_enhanced_vs_original_fft(self):
        """Compare enhanced FFT with original implementation"""
        # Use parameters that work with both implementations
        k_min = math.log(s) - 2.0
        delta_v = 0.01
        n = 4096
        delta_k = 2.0 * math.pi / (n * delta_v)
        alpha = 1.5
        
        # Original FFT
        original_calls = pricing_engine.price_call_fft(s, k_min, delta_v, delta_k, n, tau, r, sigma, alpha)
        original_puts = pricing_engine.price_put_fft(s, k_min, delta_v, delta_k, n, tau, r, sigma, alpha)
        
        # Enhanced FFT with same parameters
        enhanced_call = pricing_engine.price_call_fft_enhanced(s, k_min, delta_v, delta_k, n, tau, r, sigma, alpha)
        enhanced_put = pricing_engine.price_put_fft_enhanced(s, k_min, delta_v, delta_k, n, tau, r, sigma, alpha)
        
        # Find the ATM index
        target_k = math.log(100.0)
        idx = int(round((target_k - k_min) / delta_k))
        
        if 0 <= idx < len(original_calls):
            original_call = original_calls[idx]
            original_put = original_puts[idx]
            
            # Enhanced version should be at least as accurate
            bs_call = pricing_engine.price_call(s, 100, tau, r, sigma)
            bs_put = pricing_engine.price_put(s, 100, tau, r, sigma)
            
            original_call_error = abs(original_call - bs_call) / bs_call
            enhanced_call_error = abs(enhanced_call - bs_call) / bs_call
            
            original_put_error = abs(original_put - bs_put) / max(bs_put, 0.01)
            enhanced_put_error = abs(enhanced_put - bs_put) / max(bs_put, 0.01)
            
            # Enhanced should be at least as good as original
            assert enhanced_call_error <= original_call_error * 1.1, \
                f"Enhanced call error {enhanced_call_error:.4%} worse than original {original_call_error:.4%}"
            assert enhanced_put_error <= original_put_error * 1.1, \
                f"Enhanced put error {enhanced_put_error:.4%} worse than original {original_put_error:.4%}"
    
    def test_put_call_parity(self):
        """Test that enhanced FFT respects put-call parity"""
        strikes = [90, 100, 110]
        
        for k in strikes:
            call_price = pricing_engine.price_call_fft_optimized(s, k, tau, r, sigma)
            put_price = pricing_engine.price_put_fft_optimized(s, k, tau, r, sigma)
            
            # Put-call parity: C - P = S - K*e^(-r*T)
            parity_lhs = call_price - put_price
            parity_rhs = s - k * math.exp(-r * tau)
            
            parity_error = abs(parity_lhs - parity_rhs)
            assert parity_error < 0.01, f"Put-call parity violation for K={k}: {parity_error:.6f}"
    
    def test_monotonicity_properties(self):
        """Test that option prices behave monotonically as expected"""
        strikes = [90, 95, 100, 105, 110]
        call_prices = []
        put_prices = []
        
        for k in strikes:
            call_price = pricing_engine.price_call_fft_optimized(s, k, tau, r, sigma)
            put_price = pricing_engine.price_put_fft_optimized(s, k, tau, r, sigma)
            call_prices.append(call_price)
            put_prices.append(put_price)
        
        # Call prices should decrease with strike
        for i in range(1, len(call_prices)):
            assert call_prices[i] <= call_prices[i-1], \
                f"Call price monotonicity violated: K={strikes[i-1]} -> {strikes[i]}, prices: {call_prices[i-1]:.6f} -> {call_prices[i]:.6f}"
        
        # Put prices should increase with strike
        for i in range(1, len(put_prices)):
            assert put_prices[i] >= put_prices[i-1], \
                f"Put price monotonicity violated: K={strikes[i-1]} -> {strikes[i]}, prices: {put_prices[i-1]:.6f} -> {put_prices[i]:.6f}"
    
    def test_time_decay(self):
        """Test that option prices decrease with time (theta < 0)"""
        k = 100
        times = [0.1, 0.5, 1.0, 1.5]
        
        call_prices = []
        put_prices = []
        
        for t in times:
            call_price = pricing_engine.price_call_fft_optimized(s, k, t, r, sigma)
            put_price = pricing_engine.price_put_fft_optimized(s, k, t, r, sigma)
            call_prices.append(call_price)
            put_prices.append(put_price)
        
        # For ATM options, prices generally increase with time (positive time value)
        # This tests that the implementation captures time value correctly
        assert call_prices[-1] > call_prices[0], "Call price should increase with time for ATM option"
        assert put_prices[-1] > put_prices[0], "Put price should increase with time for ATM option"
    
    def test_volatility_sensitivity(self):
        """Test that option prices increase with volatility (vega > 0)"""
        k = 100
        volatilities = [0.1, 0.2, 0.3, 0.4]
        
        call_prices = []
        put_prices = []
        
        for vol in volatilities:
            call_price = pricing_engine.price_call_fft_optimized(s, k, tau, r, vol)
            put_price = pricing_engine.price_put_fft_optimized(s, k, tau, r, vol)
            call_prices.append(call_price)
            put_prices.append(put_price)
        
        # Prices should increase with volatility
        for i in range(1, len(call_prices)):
            assert call_prices[i] > call_prices[i-1], \
                f"Call vega should be positive: vol {volatilities[i-1]} -> {volatilities[i]}, prices: {call_prices[i-1]:.6f} -> {call_prices[i]:.6f}"
            assert put_prices[i] > put_prices[i-1], \
                f"Put vega should be positive: vol {volatilities[i-1]} -> {volatilities[i]}, prices: {put_prices[i-1]:.6f} -> {put_prices[i]:.6f}"


class TestFFTPerformance:
    """Performance and stress tests for FFT pricing"""
    
    def test_performance_benchmark(self):
        """Basic performance test - should complete quickly"""
        import time
        
        start_time = time.time()
        
        # Price 100 options
        for i in range(100):
            k = 90 + i * 0.2  # Strikes from 90 to 110
            pricing_engine.price_call_fft_optimized(s, k, tau, r, sigma)
        
        elapsed = time.time() - start_time
        
        # Should complete 100 calculations in reasonable time
        assert elapsed < 10.0, f"Performance test took too long: {elapsed:.2f} seconds"
    
    def test_extreme_parameters(self):
        """Test behavior with extreme but valid parameters"""
        extreme_cases = [
            (10, 10, 0.01, 0.001, 0.05),    # Very low values
            (1000, 1000, 5.0, 0.2, 1.0),    # High values
            (100, 100, 0.001, 0.15, 0.8),   # Very short time
        ]
        
        for s_test, k_test, tau_test, r_test, sigma_test in extreme_cases:
            try:
                call_price = pricing_engine.price_call_fft_optimized(s_test, k_test, tau_test, r_test, sigma_test)
                put_price = pricing_engine.price_put_fft_optimized(s_test, k_test, tau_test, r_test, sigma_test)
                
                # Should produce reasonable results
                assert not math.isnan(call_price), f"Call price is NaN for case {extreme_cases.index((s_test, k_test, tau_test, r_test, sigma_test))}"
                assert not math.isnan(put_price), f"Put price is NaN for case {extreme_cases.index((s_test, k_test, tau_test, r_test, sigma_test))}"
                assert call_price >= 0, f"Call price negative: {call_price}"
                assert put_price >= 0, f"Put price negative: {put_price}"
                
            except ValueError:
                # Some extreme cases may be rejected, which is acceptable
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])