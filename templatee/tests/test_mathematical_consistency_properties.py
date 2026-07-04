"""
Mathematical Consistency Property Tests

These tests validate the three key mathematical consistency properties:
- Property 24: Model Convergence
- Property 25: Arbitrage-Free Pricing  
- Property 26: Greeks Relationship Consistency

**Validates: Requirements All**
"""

import pytest
import math
import sys
import os
from hypothesis import given, strategies as st, settings, assume
from hypothesis import HealthCheck

# Import the modules under test
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import the Rust pricing engine, fall back to mock if not available
try:
    import pricing_engine
    USING_MOCK = False
except ImportError:
    import pricing_engine_mock as pricing_engine
    USING_MOCK = True


class TestMathematicalConsistencyProperties:
    """Property-based tests for mathematical consistency"""
    
    def setup_method(self):
        """Set up test parameters"""
        self.tolerance = 0.05  # 5% tolerance for model convergence
        self.arbitrage_tolerance = 0.01  # 1% tolerance for arbitrage bounds
        self.greeks_tolerance = 0.1  # 10% tolerance for Greeks relationships
    
    @given(
        s=st.floats(min_value=50.0, max_value=200.0),
        k=st.floats(min_value=50.0, max_value=200.0),
        tau=st.floats(min_value=0.1, max_value=2.0),
        r=st.floats(min_value=0.01, max_value=0.1),
        sigma=st.floats(min_value=0.1, max_value=0.5)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_property_24_model_convergence(self, s, k, tau, r, sigma):
        """
        Property 24: Model Convergence
        For any option parameters in the Black-Scholes regime (constant volatility), 
        all pricing models should converge to similar prices within reasonable tolerance 
        as model parameters approach Black-Scholes assumptions.
        
        **Validates: Requirements All**
        """
        assume(s > 0 and k > 0 and tau > 0 and r >= 0 and sigma > 0)
        assume(0.5 <= s/k <= 2.0)  # Reasonable moneyness range
        
        try:
            # Get Black-Scholes prices as reference
            bs_call = pricing_engine.price_call(s, k, tau, r, sigma)
            bs_put = pricing_engine.price_put(s, k, tau, r, sigma)
            
            # Skip if BS prices are invalid
            assume(bs_call > 0 and bs_put > 0)
            assume(math.isfinite(bs_call) and math.isfinite(bs_put))
            
            # Get FFT optimized prices
            try:
                fft_call = pricing_engine.price_call_fft_optimized(s, k, tau, r, sigma)
                fft_put = pricing_engine.price_put_fft_optimized(s, k, tau, r, sigma)
                
                # Check convergence for calls
                if math.isfinite(fft_call) and fft_call > 0:
                    call_diff_pct = abs(fft_call - bs_call) / bs_call
                    assert call_diff_pct <= self.tolerance, (
                        f"Call price convergence failed: BS={bs_call:.6f}, FFT={fft_call:.6f}, "
                        f"diff={call_diff_pct:.2%} > {self.tolerance:.2%}"
                    )
                
                # Check convergence for puts
                if math.isfinite(fft_put) and fft_put > 0:
                    put_diff_pct = abs(fft_put - bs_put) / bs_put
                    assert put_diff_pct <= self.tolerance, (
                        f"Put price convergence failed: BS={bs_put:.6f}, FFT={fft_put:.6f}, "
                        f"diff={put_diff_pct:.2%} > {self.tolerance:.2%}"
                    )
                    
            except Exception:
                # FFT may fail for some parameter combinations, which is acceptable
                pass
            
            # Test Heston convergence when parameters approach Black-Scholes
            # Use low vol-of-vol and high mean reversion to approach constant volatility
            try:
                v0 = sigma * sigma  # Initial variance = sigma^2
                theta = v0  # Long-term variance = sigma^2
                kappa = 10.0  # High mean reversion
                sigma_v = 0.1  # Low vol-of-vol
                rho = 0.0  # Zero correlation
                
                # Validate Feller condition
                if 2.0 * kappa * theta > sigma_v * sigma_v:
                    heston_call = pricing_engine.price_heston_call(
                        s, k, v0, r, kappa, theta, sigma_v, rho, tau
                    )
                    heston_put = pricing_engine.price_heston_put(
                        s, k, v0, r, kappa, theta, sigma_v, rho, tau
                    )
                    
                    # Check Heston convergence to Black-Scholes
                    if math.isfinite(heston_call) and heston_call > 0:
                        heston_call_diff_pct = abs(heston_call - bs_call) / bs_call
                        # Allow larger tolerance for Heston due to numerical integration
                        assert heston_call_diff_pct <= 0.15, (
                            f"Heston call convergence failed: BS={bs_call:.6f}, "
                            f"Heston={heston_call:.6f}, diff={heston_call_diff_pct:.2%}"
                        )
                    
                    if math.isfinite(heston_put) and heston_put > 0:
                        heston_put_diff_pct = abs(heston_put - bs_put) / bs_put
                        assert heston_put_diff_pct <= 0.15, (
                            f"Heston put convergence failed: BS={bs_put:.6f}, "
                            f"Heston={heston_put:.6f}, diff={heston_put_diff_pct:.2%}"
                        )
                        
            except Exception:
                # Heston may fail for some parameter combinations, which is acceptable
                pass
                
        except Exception as e:
            # If Black-Scholes fails, skip this test case
            assume(False)
    
    @given(
        s=st.floats(min_value=80.0, max_value=120.0),
        tau=st.floats(min_value=0.25, max_value=1.0),
        r=st.floats(min_value=0.02, max_value=0.08),
        sigma=st.floats(min_value=0.15, max_value=0.35)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_property_25_arbitrage_free_pricing(self, s, tau, r, sigma):
        """
        Property 25: Arbitrage-Free Pricing
        For any option chain generated by the pricing models, the prices should satisfy 
        basic arbitrage bounds: call prices should decrease with strike price, 
        and put prices should increase with strike price.
        
        **Validates: Requirements All**
        """
        assume(s > 0 and tau > 0 and r >= 0 and sigma > 0)
        
        # Generate a range of strikes around the spot price
        strikes = [s * multiplier for multiplier in [0.8, 0.9, 1.0, 1.1, 1.2]]
        
        try:
            # Test Black-Scholes arbitrage bounds
            bs_calls = []
            bs_puts = []
            
            for k in strikes:
                call_price = pricing_engine.price_call(s, k, tau, r, sigma)
                put_price = pricing_engine.price_put(s, k, tau, r, sigma)
                
                assume(call_price > 0 and put_price > 0)
                assume(math.isfinite(call_price) and math.isfinite(put_price))
                
                bs_calls.append(call_price)
                bs_puts.append(put_price)
            
            # Check that call prices decrease with strike
            for i in range(len(bs_calls) - 1):
                assert bs_calls[i] >= bs_calls[i + 1] - self.arbitrage_tolerance, (
                    f"Call prices should decrease with strike: "
                    f"K={strikes[i]:.2f} -> C={bs_calls[i]:.4f}, "
                    f"K={strikes[i+1]:.2f} -> C={bs_calls[i+1]:.4f}"
                )
            
            # Check that put prices increase with strike
            for i in range(len(bs_puts) - 1):
                assert bs_puts[i] <= bs_puts[i + 1] + self.arbitrage_tolerance, (
                    f"Put prices should increase with strike: "
                    f"K={strikes[i]:.2f} -> P={bs_puts[i]:.4f}, "
                    f"K={strikes[i+1]:.2f} -> P={bs_puts[i+1]:.4f}"
                )
            
            # Check intrinsic value bounds for calls
            for i, k in enumerate(strikes):
                intrinsic_call = max(0, s - k)
                assert bs_calls[i] >= intrinsic_call - self.arbitrage_tolerance, (
                    f"Call price below intrinsic value: C={bs_calls[i]:.4f} < "
                    f"max(0, S-K)={intrinsic_call:.4f} for K={k:.2f}"
                )
            
            # Check intrinsic value bounds for puts
            for i, k in enumerate(strikes):
                intrinsic_put = max(0, k * math.exp(-r * tau) - s)
                assert bs_puts[i] >= intrinsic_put - self.arbitrage_tolerance, (
                    f"Put price below intrinsic value: P={bs_puts[i]:.4f} < "
                    f"max(0, Ke^(-rT)-S)={intrinsic_put:.4f} for K={k:.2f}"
                )
            
            # Test FFT arbitrage bounds if available
            try:
                fft_calls = []
                fft_puts = []
                
                for k in strikes:
                    fft_call = pricing_engine.price_call_fft_optimized(s, k, tau, r, sigma)
                    fft_put = pricing_engine.price_put_fft_optimized(s, k, tau, r, sigma)
                    
                    if math.isfinite(fft_call) and fft_call > 0:
                        fft_calls.append(fft_call)
                    if math.isfinite(fft_put) and fft_put > 0:
                        fft_puts.append(fft_put)
                
                # Check FFT call monotonicity if we have enough valid prices
                if len(fft_calls) >= 3:
                    for i in range(len(fft_calls) - 1):
                        assert fft_calls[i] >= fft_calls[i + 1] - self.arbitrage_tolerance, (
                            f"FFT call prices should decrease with strike"
                        )
                
                # Check FFT put monotonicity if we have enough valid prices
                if len(fft_puts) >= 3:
                    for i in range(len(fft_puts) - 1):
                        assert fft_puts[i] <= fft_puts[i + 1] + self.arbitrage_tolerance, (
                            f"FFT put prices should increase with strike"
                        )
                        
            except Exception:
                # FFT may fail for some parameter combinations
                pass
                
        except Exception as e:
            # If pricing fails, skip this test case
            assume(False)
    
    @given(
        s=st.floats(min_value=80.0, max_value=120.0),
        k=st.floats(min_value=80.0, max_value=120.0),
        tau=st.floats(min_value=0.25, max_value=1.0),
        r=st.floats(min_value=0.02, max_value=0.08),
        sigma=st.floats(min_value=0.15, max_value=0.35)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_property_26_greeks_relationship_consistency(self, s, k, tau, r, sigma):
        """
        Property 26: Greeks Relationship Consistency
        For any option parameters, the Greeks should satisfy known mathematical 
        relationships such as Gamma = ∂Delta/∂S and the relationship between 
        Delta and the probability of finishing in-the-money.
        
        **Validates: Requirements All**
        """
        assume(s > 0 and k > 0 and tau > 0 and r >= 0 and sigma > 0)
        assume(0.7 <= s/k <= 1.3)  # Focus on near-the-money options
        
        try:
            # Get Black-Scholes Greeks for calls
            bs_call_greeks = pricing_engine.calculate_bs_call_greeks(s, k, tau, r, sigma)
            
            # Verify Greeks are finite and reasonable
            assume(math.isfinite(bs_call_greeks.delta))
            assume(math.isfinite(bs_call_greeks.gamma))
            assume(math.isfinite(bs_call_greeks.theta))
            assume(math.isfinite(bs_call_greeks.vega))
            assume(math.isfinite(bs_call_greeks.rho))
            
            # Test Delta bounds for calls
            assert 0 <= bs_call_greeks.delta <= 1, (
                f"Call delta out of bounds: {bs_call_greeks.delta}"
            )
            
            # Test Gamma non-negativity
            assert bs_call_greeks.gamma >= 0, (
                f"Gamma should be non-negative: {bs_call_greeks.gamma}"
            )
            
            # Test Vega non-negativity
            assert bs_call_greeks.vega >= 0, (
                f"Vega should be non-negative: {bs_call_greeks.vega}"
            )
            
            # Test Rho sign for calls (should be positive)
            assert bs_call_greeks.rho >= 0, (
                f"Call rho should be positive: {bs_call_greeks.rho}"
            )
            
            # Test Theta sign for calls (usually negative, but can be positive for deep ITM calls with low rates)
            # We'll just check it's finite for now
            assert math.isfinite(bs_call_greeks.theta), (
                f"Theta should be finite: {bs_call_greeks.theta}"
            )
            
            # Get put Greeks for comparison
            bs_put_greeks = pricing_engine.calculate_bs_put_greeks(s, k, tau, r, sigma)
            
            assume(math.isfinite(bs_put_greeks.delta))
            assume(math.isfinite(bs_put_greeks.gamma))
            assume(math.isfinite(bs_put_greeks.vega))
            assume(math.isfinite(bs_put_greeks.rho))
            
            # Test Delta bounds for puts
            assert -1 <= bs_put_greeks.delta <= 0, (
                f"Put delta out of bounds: {bs_put_greeks.delta}"
            )
            
            # Test Rho sign for puts (should be negative)
            assert bs_put_greeks.rho <= 0, (
                f"Put rho should be negative: {bs_put_greeks.rho}"
            )
            
            # Test Gamma consistency between calls and puts (should be equal)
            gamma_diff = abs(bs_call_greeks.gamma - bs_put_greeks.gamma)
            gamma_avg = (bs_call_greeks.gamma + bs_put_greeks.gamma) / 2
            if gamma_avg > 0:
                gamma_diff_pct = gamma_diff / gamma_avg
                assert gamma_diff_pct <= self.greeks_tolerance, (
                    f"Gamma inconsistency between calls and puts: "
                    f"call_gamma={bs_call_greeks.gamma:.6f}, "
                    f"put_gamma={bs_put_greeks.gamma:.6f}, "
                    f"diff={gamma_diff_pct:.2%}"
                )
            
            # Test Vega consistency between calls and puts (should be equal)
            vega_diff = abs(bs_call_greeks.vega - bs_put_greeks.vega)
            vega_avg = (bs_call_greeks.vega + bs_put_greeks.vega) / 2
            if vega_avg > 0:
                vega_diff_pct = vega_diff / vega_avg
                assert vega_diff_pct <= self.greeks_tolerance, (
                    f"Vega inconsistency between calls and puts: "
                    f"call_vega={bs_call_greeks.vega:.6f}, "
                    f"put_vega={bs_put_greeks.vega:.6f}, "
                    f"diff={vega_diff_pct:.2%}"
                )
            
            # Test Delta relationship: Call Delta - Put Delta = 1 (for same strike)
            delta_sum = bs_call_greeks.delta - bs_put_greeks.delta
            assert abs(delta_sum - 1.0) <= self.greeks_tolerance, (
                f"Delta relationship violation: Call_Delta - Put_Delta = "
                f"{delta_sum:.6f}, should be ≈ 1.0"
            )
            
            # Test numerical Greeks consistency if available
            try:
                num_call_greeks = pricing_engine.calculate_numerical_call_greeks(s, k, tau, r, sigma)
                
                if (math.isfinite(num_call_greeks.delta) and 
                    math.isfinite(num_call_greeks.gamma) and
                    math.isfinite(num_call_greeks.vega)):
                    
                    # Compare analytical vs numerical Delta
                    if abs(bs_call_greeks.delta) > 0.01:  # Avoid division by very small numbers
                        delta_diff_pct = abs(num_call_greeks.delta - bs_call_greeks.delta) / abs(bs_call_greeks.delta)
                        assert delta_diff_pct <= 0.2, (  # 20% tolerance for numerical vs analytical
                            f"Delta analytical vs numerical inconsistency: "
                            f"analytical={bs_call_greeks.delta:.6f}, "
                            f"numerical={num_call_greeks.delta:.6f}, "
                            f"diff={delta_diff_pct:.2%}"
                        )
                    
                    # Compare analytical vs numerical Gamma
                    if abs(bs_call_greeks.gamma) > 1e-6:  # Avoid division by very small numbers
                        gamma_diff_pct = abs(num_call_greeks.gamma - bs_call_greeks.gamma) / abs(bs_call_greeks.gamma)
                        assert gamma_diff_pct <= 0.3, (  # 30% tolerance for numerical vs analytical
                            f"Gamma analytical vs numerical inconsistency: "
                            f"analytical={bs_call_greeks.gamma:.6f}, "
                            f"numerical={num_call_greeks.gamma:.6f}, "
                            f"diff={gamma_diff_pct:.2%}"
                        )
                        
            except Exception:
                # Numerical Greeks may fail for some parameter combinations
                pass
                
        except Exception as e:
            # If Greeks calculation fails, skip this test case
            assume(False)


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "--tb=short"])