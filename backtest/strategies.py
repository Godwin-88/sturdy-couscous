from __future__ import annotations

from typing import Any, Dict

import numpy as np

from .schemas import make_signal


_REGISTRY: Dict[str, Any] = {}


def _register(name: str):
    def decorator(cls):
        _REGISTRY[name] = cls
        _REGISTRY[name.lower()] = cls
        return cls
    return decorator


@_register("MomentumOverlay")
class MomentumOverlay:
    name = "MomentumOverlay"

    def generate_signal(self, bar: Dict[str, Any], kg_context: Dict[str, Any]) -> Dict[str, Any]:
        for ticker, tkbar in bar.items():
            if ticker in {"ticker", "close", "vix", "^VIX"}:
                continue
            close = float(tkbar.get("close", 0))
            ma21 = tkbar.get("ma21")
            if ma21 is None or np.isnan(ma21) or close <= 0:
                return _empty(ticker, self.name)
            score = float(np.clip((close - ma21) / (ma21 + 1e-10) * 25, -1.0, 1.0))
            out = _empty(ticker, self.name)
            out["quant_score"] = score
            out["score"] = score
            return out
        out = _empty("SPY", self.name)
        return out


@_register("GARCHVolatility")
class GARCHVolStrategy:
    name = "GARCHVolatility"

    def generate_signal(self, bar: Dict[str, Any], kg_context: Dict[str, Any]) -> Dict[str, Any]:
        for ticker, tkbar in bar.items():
            if ticker in {"ticker", "close", "vix", "^VIX"}:
                continue
            av = tkbar.get("annual_vol")
            if av is None or np.isnan(av):
                return _empty(ticker, self.name)
            score = float(np.clip(-((float(av) - 0.15) / 0.30), -1.0, 1.0))
            out = _empty(ticker, self.name)
            out["quant_score"] = score
            out["score"] = score
            return out
        out = _empty("SPY", self.name)
        return out


@_register("BayesianNetworkProxy")
class BayesianNetworkProxy:
    name = "BayesianNetworkProxy"

    def generate_signal(self, bar: Dict[str, Any], kg_context: Dict[str, Any]) -> Dict[str, Any]:
        for ticker, tkbar in bar.items():
            if ticker in {"ticker", "close", "vix", "^VIX"}:
                continue
            ret21 = tkbar.get("return_21")
            vol21 = tkbar.get("vol_21")
            if ret21 is None or vol21 is None or np.isnan(ret21) or np.isnan(vol21):
                return _empty(ticker, self.name)
            score = float(np.clip(float(ret21) / (float(vol21) + 1e-10) * 3, -1.0, 1.0))
            out = _empty(ticker, self.name)
            out["quant_score"] = score
            out["score"] = score
            return out
        out = _empty("SPY", self.name)
        return out


@_register("ValueMeanReversion")
class ValueMeanReversion:
    name = "ValueMeanReversion"

    def generate_signal(self, bar: Dict[str, Any], kg_context: Dict[str, Any]) -> Dict[str, Any]:
        for ticker, tkbar in bar.items():
            if ticker in {"ticker", "close", "vix", "^VIX"}:
                continue
            close = float(tkbar.get("close", 0))
            ma200 = tkbar.get("ma200")
            if ma200 is None or np.isnan(ma200) or float(ma200) <= 0:
                return _empty(ticker, self.name)
            score = float(np.clip((float(ma200) - close) / (float(ma200) + 1e-10) * 10, -1.0, 1.0))
            out = _empty(ticker, self.name)
            out["quant_score"] = score
            out["score"] = score
            return out
        out = _empty("SPY", self.name)
        return out


@_register("CrisisAlpha")
class CrisisAlpha:
    name = "CrisisAlpha"

    def generate_signal(self, bar: Dict[str, Any], kg_context: Dict[str, Any]) -> Dict[str, Any]:
        vix = float(bar.get("vix", 20.0) or 20.0)
        score = float(np.clip((vix - 25.0) / 20.0, 0.0, 1.0))
        out = _empty("SPY", self.name)
        out["quant_score"] = score
        out["score"] = score
        return out


def get_strategy(name: str):
    if name not in _REGISTRY:
        raise KeyError(f"Unknown strategy {name!r}")
    return _REGISTRY[name]()


def _empty(ticker: str, strategy_name: str = "") -> Dict[str, Any]:
    return {
        "ticker": ticker,
        "asset_class": "",
        "venue": "",
        "venue_symbol": "",
        "strategy": strategy_name,
        "direction": "hold",
        "score": 0.0,
        "quant_score": 0.0,
        "sentiment_score": 0.0,
        "news_overlay": 0.0,
        "macro_overlay": 0.0,
        "kg_formula_contribution": 0.0,
        "graph_path": [],
        "contradiction_blocked": False,
    }
