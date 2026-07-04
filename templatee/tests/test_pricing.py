import pytest
import pricing_engine

# Known Black-Scholes values for S=100, K=100, T=1, r=0.05, sigma=0.2:
EXPECTED_CALL = 10.4506
EXPECTED_PUT  = 5.5735

def approx(a, b, tol=1e-4):
    assert abs(a - b) < tol


def test_call():
    c = pricing_engine.price_call(100, 100, 1.0, 0.05, 0.2)
    approx(c, EXPECTED_CALL)


def test_put():
    p = pricing_engine.price_put(100, 100, 1.0, 0.05, 0.2)
    approx(p, EXPECTED_PUT)