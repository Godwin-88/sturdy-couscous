"""
Options Market Data Provider — GraphAlpha perception layer (T1/T8).

Full options capability for the Alpaca paper-trading UI:
  * get_contracts / get_expirations / get_strikes  — chain discovery (any underlying)
  * get_chain                                    — contracts merged with live snapshots
  * get_snapshot                                 — bid/ask/last, implied vol, greeks, OI
  * get_bars                                     — historical OHLCV for backtesting

No hard-coded restriction on underlyings/strikes/expirations — the user can
browse and trade any Alpaca-listed US equity option from the UI. Caching + a
degrade-to-empty rule mirror agent/alpaca_data.py (never raises into the loop).
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from loguru import logger

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOptionContractsRequest
    from alpaca.trading.enums import ContractType
    from alpaca.data.historical import OptionHistoricalDataClient
    from alpaca.data.requests import OptionSnapshotRequest, OptionBarsRequest, OptionChainRequest
    from alpaca.data.timeframe import TimeFrame
    _ALPACA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ALPACA_AVAILABLE = False

try:
    from option_utils import build_contract_symbol, parse_contract_symbol  # noqa: E402
except ImportError:  # pragma: no cover - api container mounts agent/ as a package
    from agent.option_utils import build_contract_symbol, parse_contract_symbol  # type: ignore  # noqa: E402

CONTRACT_CACHE_TTL = float(os.getenv("ALPACA_DATA_CACHE_TTL", 240))


class OptionsDataProvider:
    def __init__(self):
        self.key_id = os.getenv("ALPACA_API_KEY_ID", "")
        self.secret_key = os.getenv("ALPACA_API_SECRET_KEY", "")
        self._trading_client = None
        self._data_client = None
        self._cache: dict = {}

    def is_configured(self) -> bool:
        if self.key_id.startswith("your_") or self.secret_key.startswith("your_") or not _ALPACA_AVAILABLE:
            return False
        return bool(self.key_id and self.secret_key)

    @property
    def trading_client(self):
        if self._trading_client is None and self.is_configured():
            self._trading_client = TradingClient(
                api_key=self.key_id,
                secret_key=self.secret_key,
                paper=True,
            )
        return self._trading_client

    @property
    def data_client(self):
        if self._data_client is None and self.is_configured():
            self._data_client = OptionHistoricalDataClient(
                api_key=self.key_id,
                secret_key=self.secret_key,
            )
        return self._data_client

    def _cache_get(self, key):
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < CONTRACT_CACHE_TTL:
            return hit[1]
        return None

    def _cache_set(self, key, value):
        self._cache[key] = (time.time(), value)

    def get_contracts(self, underlying: str, expiration: str | None = None,
                      contract_type: str | None = None,
                      strike_gte: float | None = None, strike_lte: float | None = None,
                      limit: int = 1000) -> list[dict]:
        """List tradable option contracts for an underlying (Alpaca contract master)."""
        k = ("contracts", underlying.upper(), expiration, contract_type, strike_gte, strike_lte, limit)
        cached = self._cache_get(k)
        if cached is not None:
            return cached
        if not self.is_configured() or self.trading_client is None:
            return []

        t = None
        if contract_type:
            tl = str(contract_type).lower()
            if tl.startswith("c"):
                t = ContractType.CALL
            elif tl.startswith("p"):
                t = ContractType.PUT
        req = GetOptionContractsRequest(
            underlying_symbols=[underlying.upper()],
            status="active",
            expiration_date=expiration,
            type=t,
            strike_price_gte=str(strike_gte) if strike_gte is not None else None,
            strike_price_lte=str(strike_lte) if strike_lte is not None else None,
            limit=limit,
        )
        try:
            resp = self.trading_client.get_option_contracts(req)
            rows = [c.model_dump() for c in resp.option_contracts] if hasattr(resp, "option_contracts") else []
            self._cache_set(k, rows)
            return rows
        except Exception as e:
            logger.warning(f"get_option_contracts failed for {underlying}: {e}")
            return []

    def get_expirations(self, underlying: str) -> list[str]:
        """Distinct available option expirations for an underlying (ISO dates, sorted)."""
        contracts = self.get_contracts(underlying, limit=2000)
        return sorted({str(c.get("expiration_date")) for c in contracts if c.get("expiration_date")})

    def get_strikes(self, underlying, expiration=None, contract_type=None):
        contracts = self.get_contracts(underlying, expiration=expiration,
                                       contract_type=contract_type, limit=2000)
        return sorted({float(c["strike_price"]) for c in contracts
                       if c.get("strike_price") is not None})

    # ── Snapshots (quotes + greeks) ────────────────────────────────────────────
    def get_snapshot(self, contract_symbol: str) -> dict:
        k = ("snapshot", str(contract_symbol).upper())
        cached = self._cache_get(k)
        if cached is not None:
            return cached
        if not self.is_configured() or self.data_client is None:
            return {}
        try:
            resp = self.data_client.get_option_snapshot(
                OptionSnapshotRequest(symbol_or_symbols=[contract_symbol.upper()])
            )
            raw = resp.get(contract_symbol.upper(), {}) if isinstance(resp, dict) else {}
            out = self._snapshot_to_dict(raw) if raw else {}
            self._cache_set(k, out)
            return out
        except Exception as e:
            logger.warning(f"get_option_snapshot failed for {contract_symbol}: {e}")
            return {}

    def get_chain(self, underlying: str, expiration: str | None = None,
                  contract_type: str | None = None,
                  strike_gte: float | None = None, strike_lte: float | None = None,
                  with_snapshots: bool = True,
                  snapshot_batch: int = 100) -> list[dict]:
        """Merge contract master with live snapshots into a browsable chain.

        Snapshots are fetched in **batches** (one API call per `snapshot_batch`
        contracts) — never one call per contract — so a full 1000-contract chain
        resolves in ~10 requests instead of minutes (fixes UI timeouts).
        """
        contracts = self.get_contracts(underlying, expiration=expiration,
                                       contract_type=contract_type,
                                       strike_gte=strike_gte, strike_lte=strike_lte,
                                       limit=1000)
        rows = [self._contract_brief(c) for c in contracts]

        if not with_snapshots or not contracts or not self.is_configured() or self.data_client is None:
            return rows

        snaps = {}
        symbols = [c.get("symbol") for c in contracts if c.get("symbol")]
        try:
            for i in range(0, len(symbols), snapshot_batch):
                chunk = symbols[i:i + snapshot_batch]
                resp = self.data_client.get_option_snapshot(
                    OptionSnapshotRequest(symbol_or_symbols=chunk)
                )
                if isinstance(resp, dict):
                    snaps.update(resp)
        except Exception as e:
            logger.warning(f"batch chain snapshots failed for {underlying}: {e}")

        for brief in rows:
            sym = brief.get("symbol")
            if not sym or sym not in snaps:
                continue
            snap = self._snapshot_to_dict(snaps[sym])
            if not snap:
                continue
            brief.update({
                "bid": snap.get("bid"), "ask": snap.get("ask"),
                "last": snap.get("last"), "volume": snap.get("volume"),
                "open_interest": snap.get("open_interest"),
                "implied_volatility": snap.get("implied_volatility"),
                "greeks": snap.get("greeks"),
            })
            if snap.get("ask") and snap.get("bid") and snap["ask"] > snap["bid"]:
                brief["spread_pct"] = (snap["ask"] - snap["bid"]) / ((snap["ask"] + snap["bid"]) / 2)
        return rows

    @staticmethod
    def _contract_brief(c: dict) -> dict:
        return {
            "symbol": c.get("symbol"),
            "underlying_symbol": c.get("underlying_symbol"),
            "root_symbol": c.get("root_symbol"),
            "expiration_date": c.get("expiration_date"),
            "contract_type": c.get("type"),
            "strike_price": c.get("strike_price"),
            "multiplier": c.get("size", 100),
            "style": c.get("style"),
            "tradable": c.get("tradable"),
            "status": c.get("status"),
            "open_interest": c.get("open_interest"),
        }

    @staticmethod
    def _snapshot_to_dict(raw: Any) -> dict:
        try:
            q = getattr(raw, "latest_quote", None)
            bid = float(getattr(q, "bid_price", 0)) if q else None
            ask = float(getattr(q, "ask_price", 0)) if q else None
            last = getattr(getattr(raw, "latest_trade", None), "price", None)
            vol = getattr(getattr(raw, "latest_trade", None), "size", None)
            iv = getattr(raw, "implied_volatility", None)
            oi = getattr(raw, "open_interest", None)
            g = getattr(raw, "greeks", None)
            greeks = None
            if g is not None:
                greeks = {
                    "delta": getattr(g, "delta", None),
                    "gamma": getattr(g, "gamma", None),
                    "theta": getattr(g, "theta", None),
                    "vega": getattr(g, "vega", None),
                    "rho": getattr(g, "rho", None),
                }
            return {
                "bid": bid, "ask": ask, "last": float(last) if last is not None else None,
                "volume": float(vol) if vol is not None else None,
                "open_interest": float(oi) if oi is not None else None,
                "implied_volatility": float(iv) if iv is not None else None,
                "greeks": greeks,
            }
        except Exception as e:
            logger.debug(f"snapshot parse failed: {e}")
            return {}

    # ── Historical bars (backtest) ─────────────────────────────────────────────
    def get_bars(self, contract_symbol: str, days: int = 90) -> pd.DataFrame:
        k = ("bars", contract_symbol.upper(), days)
        cached = self._cache_get(k)
        if cached is not None:
            return cached
        empty = pd.DataFrame()
        if not self.is_configured() or self.data_client is None:
            return empty
        start = datetime.utcnow() - timedelta(days=days + 5)
        try:
            resp = self.data_client.get_option_bars(
                OptionBarsRequest(
                    symbol_or_symbols=[contract_symbol.upper()],
                    timeframe=TimeFrame.Day,
                    start=start,
                )
            )
            df = getattr(resp, "df", None)
            if df is None or df.empty:
                return empty
            if contract_symbol.upper() in df.index.get_level_values(0):
                df = df.xs(contract_symbol.upper(), level=0)
            df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                    "close": "Close", "volume": "Volume"})
            keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
            if not keep:
                return empty
            df = df[keep].dropna()
            if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
                df = df.tz_localize(None)
            df = df[~df.index.duplicated(keep="last")].sort_index()
            self._cache_set(k, df)
            return df
        except Exception as e:
            logger.warning(f"option bars failed for {contract_symbol}: {e}")
            return empty


options_provider = OptionsDataProvider()