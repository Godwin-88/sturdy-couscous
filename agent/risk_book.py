"""
Risk book aggregation \u2014 broker-true exposure metrics.

Builds portfolio risk metrics from *broker* positions (equity + option +
crypto legs as Alpaca reports them) so the risk engine / /agent/risk never
reports gross_exposure:0 while the brokerage holds live option legs.

Pure functions; every caller passes in already-fetched positions + NAV.
"""
from __future__ import annotations

import os
from datetime import datetime

RISK_FREE_RATE = float(os.getenv("OPTION_RISK_FREE_RATE", "0.05"))
IV_FALLBACK = float(os.getenv("OPTION_IV_FALLBACK", "0.40"))
MULT = 100


def _is_option_symbol(symbol: str) -> bool:
    s = str(symbol or "").upper().lstrip("$")
    return ("-" in s) or len(s) > 6


def _is_crypto(symbol: str) -> bool:
    s = str(symbol or "").upper()
    return "/" in s or s in {"BTC-USD", "ETH-USD", "BTCUSD", "ETHUSD"}


def _d1(S: float, K: float, T: float, sig: float, r: float) -> float:
    from math import log, sqrt
    if S <= 0 or K <= 0 or T <= 0 or sig <= 0:
        return 0.0
    return (log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * sqrt(T))


def black_scholes_greeks(S: float, K: float, T: float, sig: float,
                         r: float = RISK_FREE_RATE, right: str = "C") -> dict:
    """Black-Scholes greeks for one leg. Returns zero-safe values."""
    from math import exp, log, sqrt, pi, erfc
    out = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    S = S or 0.0
    K = K or 0.0
    T = T or 0.0
    sig = sig or 0.0
    if S <= 0 or K <= 0 or T <= 0 or sig <= 0:
        return out
    d1 = (log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * sqrt(T))
    d2 = d1 - sig * sqrt(T)

    def N(x: float) -> float:
        return 0.5 * erfc(-x / sqrt(2.0))

    def nprime(x: float) -> float:
        return exp(-0.5 * x * x) / sqrt(2.0 * pi)

    sign = 1.0 if right.upper() == "C" else -1.0
    out["delta"] = sign * N(sign * d1)
    out["gamma"] = nprime(d1) / (S * sig * sqrt(T))
    out["theta"] = (-sign * S * nprime(d1) * sig / (2.0 * sqrt(T))) / 365.0
    if right.upper() == "C":
        out["theta"] -= r * K * exp(-r * T) * N(d2) / 365.0
    else:
        out["theta"] += r * K * exp(-r * T) * N(-d2) / 365.0
    out["vega"] = S * nprime(d1) * sqrt(T) / 100.0
    out["rho"] = (K * T * exp(-r * T) * N(d2) / 100.0) if right.upper() == "C" else (-K * T * exp(-r * T) * N(-d2) / 100.0)
    return out


def _dte(expiry) -> int:
    try:
        d = expiry.date() if hasattr(expiry, "date") else expiry
        return max(0, (datetime.strptime(str(d), "%Y-%m-%d").date() - datetime.utcnow().date()).days)
    except Exception:
        return 0


def build_risk_metrics(positions: list[dict], nav: float,
                       spot_map: dict[str, float] | None = None) -> dict:
    """Broker-true gross/net exposure, concentration, option book."""
    nav = float(nav or 0)
    gross = 0.0
    net = 0.0
    concentration: dict[str, dict] = {}
    option_book: list[dict] = []
    n_positions = 0

    for p in positions or []:
        symbol = str(p.get("symbol") or "")
        qty = float(p.get("qty") or 0)
        if not symbol or qty == 0:
            continue
        n_positions += 1
        mval = abs(float(p.get("market_value") or 0))
        if mval == 0:
            mval = abs(float(p.get("current_price") or 0) * qty)
        sign = -1.0 if (qty < 0 or str(p.get("side") or "").lower() in ("sell", "short")) else 1.0
        gross += mval
        net += sign * mval

        root = symbol
        detail = {"symbol": symbol, "qty": qty, "mkt_val": round(mval, 2),
                  "side": "Long" if sign > 0 else "Short"}
        if _is_option_symbol(symbol):
            try:
                from agent.option_utils import parse_contract_symbol
                root, expiry, right, strike = parse_contract_symbol(symbol)
            except Exception:
                root = symbol
                expiry, right, strike = None, None, None
            dte = _dte(expiry) if expiry else 0
            spot = (spot_map or {}).get(root)
            iv = None
            greeks = None
            try:
                from agent.options_market import options_provider
                snap = options_provider.get_snapshot(symbol) or {}
                iv = snap.get("implied_volatility")
                greeks = snap.get("greeks")
            except Exception:
                pass
            if spot and spot > 0 and (greeks is None or greeks.get("delta") is None):
                T = dte / 365.0 if dte else 1 / 365.0
                bs = black_scholes_greeks(spot, strike or 0, T, iv or IV_FALLBACK, RISK_FREE_RATE, str(right or "C"))
                greeks = bs if greeks is None else {**bs, **{k: greeks.get(k) for k in bs if greeks.get(k) is not None}}
                iv = iv or IV_FALLBACK
            detail.update({"underlying": root, "expiry": str(expiry),
                           "right": right, "strike": strike,
                           "iv": iv, "greeks": greeks, "dte": dte,
                           "greeks_source": "bs_local" if (greeks and not (snap or {}).get("greeks")) else "snapshot"})
            option_book.append(detail)
        elif _is_crypto(symbol):
            root = symbol
            detail["cls"] = "crypto"
            detail["spot"] = (spot_map or {}).get(symbol)

        if root not in concentration:
            concentration[root] = {"ticker": root, "mkt_val": 0.0, "pct_nav": 0.0,
                                   "direction": "buy" if sign > 0 else "sell", "pnl": 0.0}
        concentration[root]["mkt_val"] += mval
        concentration[root]["direction"] = "buy" if concentration[root]["mkt_val"] >= 0 or sign > 0 else "sell"

    conc = sorted(concentration.values(), key=lambda x: x["mkt_val"], reverse=True)
    for c in conc:
        c["mkt_val"] = round(c["mkt_val"], 2)
        c["pct_nav"] = round(c["mkt_val"] / nav, 4) if nav else 0.0

    return {
        "gross_exposure": round(gross, 2),
        "net_exposure": round(net, 2),
        "gross_pct_nav": round(gross / nav, 4) if nav else 0.0,
        "net_pct_nav": round(net / nav, 4) if nav else 0.0,
        "n_positions": n_positions,
        "concentration": conc,
        "option_book": option_book,
        "option_notional": round(sum(float(o.get("mkt_val") or 0) for o in option_book), 2),
        "exposure_source": "broker_book",
    }


__all__ = ["build_risk_metrics", "black_scholes_greeks"]
