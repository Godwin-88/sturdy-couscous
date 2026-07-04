
import math
import pytest
import pricing_engine

# Shared parameters
s, tau, r, sigma = 100.0, 1.0, 0.05, 0.2
alpha = 1.5  # More stable damping factor
n = 4096     # Smaller grid for faster computation

# FFT parameters - more conservative for stability
delta_v = 0.01
delta_k = 2.0 * math.pi / (n * delta_v)
k_min = math.log(s) - (n / 2.0) * delta_k

def test_call_fft_vs_bs_call():
    bs_call = pricing_engine.price_call(s, 100, tau, r, sigma)
    fft_calls = pricing_engine.price_call_fft(s, k_min, delta_v, delta_k, n, tau, r, sigma, alpha)

    idx = int(round((math.log(100.0) - k_min) / delta_k))
    fft_call = fft_calls[idx]

    assert abs(fft_call - bs_call) < 1e-1, f"FFT call {fft_call} vs BS {bs_call}"

def test_put_fft_vs_bs_put():
    bs_put = pricing_engine.price_put(s, 100, tau, r, sigma)
    fft_puts = pricing_engine.price_put_fft(s, k_min, delta_v, delta_k, n, tau, r, sigma, alpha)

    idx = int(round((math.log(100.0) - k_min) / delta_k))
    fft_put = fft_puts[idx]

    assert abs(fft_put - bs_put) < 1e-1, f"FFT put {fft_put} vs BS {bs_put}"
