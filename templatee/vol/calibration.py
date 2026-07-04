"""Heston calibration and IV surface - DPE extension"""
import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm
from typing import Optional
from dataclasses import dataclass

try:
    import pricing_engine
    HAS_PRICING = True
except ImportError:
    try:
        import pricing_engine_mock as pricing_engine
        HAS_PRICING = True
    except ImportError:
        HAS_PRICING = False


@dataclass
class HestonCalibResult:
    v0: float
    kappa: float
    theta: float
    xi: float
    rho: float
    rmse: float
    feller_ok: bool


def _heston_call(s: float, k: float, v0: float, r: float, kappa: float, theta: float, xi: float, rho: float, tau: float) -> float:
    if not HAS_PRICING:
        return 0.0
    try:
        return float(pricing_engine.price_heston_call(s, k, v0, r, kappa, theta, xi, rho, tau))
    except Exception:
        return 0.0


def heston_calibrate(
    s: float,
    r: float,
    strikes: np.ndarray,
    expiries: np.ndarray,
    market_prices: np.ndarray,
) -> HestonCalibResult:
    """
    Calibrate Heston to market option prices.
    strikes, expiries, market_prices: same length, each (K_i, tau_i, C_i).
    """
    def obj(x):
        v0, kappa, theta, xi, rho = x[0], x[1], x[2], x[3], np.clip(x[4], -0.99, 0.99)
        if v0 <= 0 or kappa <= 0 or theta <= 0 or xi <= 0:
            return 1e12
        if 2 * kappa * theta <= xi * xi:
            return 1e12
        err = 0.0
        for i in range(len(strikes)):
            model = _heston_call(s, strikes[i], v0, r, kappa, theta, xi, rho, expiries[i])
            err += (model - market_prices[i]) ** 2
        return np.sqrt(err / len(strikes))

    x0 = [0.04, 2.0, 0.04, 0.3, -0.5]
    bounds = [(0.001, 1), (0.1, 10), (0.001, 1), (0.01, 2), (-0.99, 0.99)]
    res = minimize(obj, x0, method="L-BFGS-B", bounds=bounds)
    v0    = float(res.x[0])
    kappa = float(res.x[1])
    theta = float(res.x[2])
    xi    = float(res.x[3])
    rho   = float(np.clip(res.x[4], -0.99, 0.99))
    feller = bool(2 * kappa * theta > xi * xi)
    return HestonCalibResult(v0=v0, kappa=kappa, theta=theta, xi=xi, rho=rho, rmse=float(res.fun), feller_ok=feller)


def implied_vol_bs(c: float, s: float, k: float, r: float, tau: float, option_type: str = "call") -> float:
    """Newton-Raphson IV inversion of Black-Scholes."""
    def bs_call(sig):
        d1 = (np.log(s / k) + (r + 0.5 * sig ** 2) * tau) / (sig * np.sqrt(tau))
        d2 = d1 - sig * np.sqrt(tau)
        return s * norm.cdf(d1) - k * np.exp(-r * tau) * norm.cdf(d2)

    def vega(sig):
        d1 = (np.log(s / k) + (r + 0.5 * sig ** 2) * tau) / (sig * np.sqrt(tau))
        return s * norm.pdf(d1) * np.sqrt(tau)

    price = c
    if option_type == "put":
        price = c - s + k * np.exp(-r * tau)
    sig = 0.3
    for _ in range(50):
        f = bs_call(sig) - price
        if abs(f) < 1e-8:
            return float(sig)
        sig = sig - f / vega(sig)
        sig = float(np.clip(sig, 0.01, 5.0))
    return float(sig)
