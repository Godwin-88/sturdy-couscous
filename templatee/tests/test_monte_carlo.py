import pytest
import pricing_engine

# Monte Carlo should approximate Black-Scholes value within tolerance
def test_call_mc():
    bs = pricing_engine.price_call(100, 100, 1.0, 0.05, 0.2)
    mc = pricing_engine.price_call_mc(100, 100, 1.0, 0.05, 0.2, 100_000)
    assert abs(mc - bs) < 0.5

def test_put_mc():
    bs_put = pricing_engine.price_put(100, 100, 1.0, 0.05, 0.2)
    mc_put = pricing_engine.price_put_mc(100, 100, 1.0, 0.05, 0.2, 100_000)
    assert abs(mc_put - bs_put) < 0.5
