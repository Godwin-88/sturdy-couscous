from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from common.schema_validator import validate_signal

from .config import BacktestConfig, cfg
from .schemas import SCHEMA_VERSION


@dataclass(frozen=True)
class UniverseEntry:
    ticker: str
    asset_class: str
    venue: str
    venue_symbol: str
    sector: str


_GICS_SECTORS: Dict[str, str] = {
    "SPY": "Diversified ETF",
    "QQQ": "Technology",
    "TLT": "Rates / Treasuries",
    "GLD": "Commodities",
    "BTC-USD": "",
    "ETH-USD": "",
}

_CRYPTO_VENUE = "kraken"
_EQUITY_VENUE = "ibkr"


def _infer_venue_symbol(ticker: str, asset_class: str) -> str:
    if asset_class == "crypto":
        symbol = ticker.upper().replace("-", "").replace("USD", "")
        if symbol == "BTC":
            return "XBTUSD"
        return f"{symbol}USD"
    return ticker.upper()


def _create_universe_entry(ticker: str, asset_class: str = "equity_xstock") -> UniverseEntry:
    ticker = ticker.upper()
    is_crypto = asset_class == "crypto" or "-USD" in ticker
    ac = "crypto" if is_crypto else asset_class
    venue = _CRYPTO_VENUE if is_crypto else _EQUITY_VENUE
    return UniverseEntry(
        ticker=ticker,
        asset_class=ac,
        venue=venue,
        venue_symbol=_infer_venue_symbol(ticker, ac),
        sector=_GICS_SECTORS.get(ticker, ""),
    )


_DEFAULTS: tuple[UniverseEntry, ...] = (
    _create_universe_entry("SPY"),
    _create_universe_entry("QQQ"),
    _create_universe_entry("TLT", "macro_proxy"),
    _create_universe_entry("GLD", "macro_proxy"),
    _create_universe_entry("BTC-USD", "crypto"),
)

_entries: Dict[str, UniverseEntry] = {e.ticker: e for e in _DEFAULTS}

_UNIVERSE_PRESETS: Dict[str, List[str]] = {
    "default": ["SPY", "QQQ", "TLT", "GLD", "BTC-USD"],
    "crypto": ["BTC-USD", "ETH-USD"],
    "equity": ["SPY", "QQQ", "TLT", "GLD"],
    "macro": ["TLT", "GLD"],
}


def get_universe() -> List[UniverseEntry]:
    return list(_entries.values())


def lookup(ticker: str) -> UniverseEntry:
    ticker = ticker.upper()
    if ticker not in _entries:
        raise KeyError(f"Ticker {ticker!r} not in universe")
    return _entries[ticker]


def add(ticker: str, asset_class: str, venue: str, venue_symbol: str, sector: str = "") -> None:
    _validate_routing(asset_class, venue)
    _validate_ticker(ticker)
    _validate_symbol(venue_symbol)
    _validate_sector(sector)
    _entries[ticker] = UniverseEntry(
        ticker=ticker, asset_class=asset_class, venue=venue,
        venue_symbol=venue_symbol, sector=sector,
    )
    _run_schema_check(_entries[ticker])


def set_universe(tickers: List[str], asset_class: str = "equity_xstock") -> None:
    global _entries
    _entries = {}
    for ticker in tickers:
        _entries[ticker.upper()] = _create_universe_entry(ticker, asset_class)


def use_preset(preset: str) -> None:
    if preset not in _UNIVERSE_PRESETS:
        raise ValueError(f"Unknown preset {preset!r}. Available: {list(_UNIVERSE_PRESETS.keys())}")
    set_universe(_UNIVERSE_PRESETS[preset])


def _validate_routing(asset_class: str, venue: str) -> None:
    crypto_only = {_CRYPTO_VENUE}
    equity_macro_only = {_EQUITY_VENUE}
    if asset_class == "crypto" and venue not in crypto_only:
        raise ValueError(f"crypto asset_class must route via {crypto_only}, got {venue}")
    if asset_class in {"equity_xstock", "macro_proxy"} and venue not in equity_macro_only:
        raise ValueError(f"{asset_class} must route via {equity_macro_only}, got {venue}")


def _validate_ticker(name: str) -> None:
    if not re.fullmatch(r"[A-Z]{1,5}(-[A-Z]{2,4})?", name.upper()):
        raise ValueError(f"Ticker {name!r} not ASCII⁄uppercase")


def _validate_symbol(sym: str) -> None:
    if not re.fullmatch(r"[A-Z0-9]{1,20}", sym.upper()):
        raise ValueError(f"venue_symbol {sym!r} must be ASCII⁄uppercase")


def _validate_sector(sector: str) -> None:
    if not isinstance(sector, str):
        raise TypeError("sector must be str")


def _run_schema_check(entry: UniverseEntry) -> None:
    fake_signal = {
        "schema_version": SCHEMA_VERSION,
        "cycle_id": "00000000-0000-0000-0000-000000000000",
        "timestamp": "2024-01-01T00:00:00Z",
        "regime": "Trending",
        "strategy": "TestStrategy",
        "ticker": entry.ticker,
        "venue": entry.venue,
        "venue_symbol": entry.venue_symbol,
        "asset_class": entry.asset_class,
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
    validate_signal(fake_signal)