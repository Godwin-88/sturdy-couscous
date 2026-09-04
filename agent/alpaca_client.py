"""
Alpaca Trading Client — GraphAlpha
Wraps alpaca-py for paper trading on Alpaca.
Falls back to simulation if alpaca-py is not installed or keys are missing.
"""

import os
from dataclasses import dataclass
from typing import Any

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, OrderSide, OrderType, TimeInForce
    from alpaca.trading.enums import OrderSide as OrderSideEnum
    from alpaca.common.enums import Sort
    from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame
    _ALPACA_AVAILABLE = True
except ImportError:
    _ALPACA_AVAILABLE = False

from loguru import logger


@dataclass
class AlpacaOrderResult:
    order_id: str
    symbol: str
    side: str
    qty: float
    filled_qty: float
    filled_avg_price: float | None
    status: str
    raw: dict
    http_status: int = 502  # hint to the route layer (502 transient, 403 account-level, 400 validation)


class AlpacaClient:
    def __init__(self):
        self.key_id = os.getenv("ALPACA_API_KEY_ID", "")
        self.secret_key = os.getenv("ALPACA_API_SECRET_KEY", "")
        self.base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        self.data_url = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")
        self.paper = self.base_url.startswith("https://paper-api")
        self._client = None
        self._data_client = None

    @property
    def client(self):
        if not self._client and _ALPACA_AVAILABLE and self.key_id:
            self._client = TradingClient(
                api_key=self.key_id,
                secret_key=self.secret_key,
                paper=self.paper,
                url_override=self.base_url,
            )
        return self._client

    @property
    def data_client(self):
        if not self._data_client and _ALPACA_AVAILABLE and self.key_id:
            self._data_client = StockHistoricalDataClient(
                api_key=self.key_id,
                secret_key=self.secret_key,
            )
        return self._data_client

    def is_configured(self) -> bool:
        return bool(self.key_id and self.secret_key and _ALPACA_AVAILABLE)

    def configure(self, key_id: str, secret_key: str, base_url: str | None = None,
                  paper: bool | None = None) -> None:
        """Swap the active credentials at runtime (per-user settings vault).

        Invalidates cached trading/data clients so the next call uses the new
        account without a process restart.
        """
        self.key_id = key_id or ""
        self.secret_key = secret_key or ""
        if base_url:
            self.base_url = base_url
        if paper is not None:
            self.paper = paper
        else:
            self.paper = self.base_url.startswith("https://paper-api")
        self._client = None
        self._data_client = None

    async def place_order(self, symbol: str, side: str, qty: float,
                          order_type: str = "market") -> AlpacaOrderResult:
        if not self.is_configured():
            return AlpacaOrderResult(
                order_id="simulated", symbol=symbol, side=side, qty=qty,
                filled_qty=qty, filled_avg_price=0.0, status="simulated", raw={}
            )

        try:
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
            )
            order = self.client.submit_order(req)
            return AlpacaOrderResult(
                order_id=order.id or "",
                symbol=order.symbol or symbol,
                side=side,
                qty=float(order.qty or qty),
                filled_qty=float(order.filled_qty or 0),
                filled_avg_price=float(order.filled_avg_price or 0),
                status=order.status.value if order.status else "unknown",
                raw=order.model_dump() if hasattr(order, "model_dump") else {},
            )
        except Exception as e:
            logger.error(f"Alpaca order failed for {symbol}: {e}")
            return AlpacaOrderResult(
                order_id="error", symbol=symbol, side=side, qty=qty,
                filled_qty=0, filled_avg_price=0.0, status="error", raw={"error": str(e)}
            )

    async def place_crypto_order(self, symbol: str, side: str, qty: float,
                                  order_type: str = "market",
                                  limit_price: float | None = None) -> AlpacaOrderResult:
        """Place a spot crypto order on Alpaca paper (24/7 market).

        Accepts "BTC/USD" (canonical), "BTC-USD", or "BTC" (mapped via
        ``agent.alpaca_data.CRYPTO_MAP``. Crypto orders require time_in_force
        IOC (market) / GTC (limit) — DAY (equities) is rejected for crypto.

        """
        sym = str(symbol or "").strip().upper()
        if "/" not in sym:
            try:
                from agent.alpaca_data import CRYPTO_MAP
            except Exception:
                CRYPTO_MAP = {}
            sym = CRYPTO_MAP.get(sym, sym)
        if not self.is_configured():
            return AlpacaOrderResult(
                order_id="simulated", symbol=sym, side=side, qty=qty,
                filled_qty=qty, filled_avg_price=0.0, status="simulated", raw={}, http_status=200
            )
        try:
            side_enum = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            tif = TimeInForce.IOC if order_type == "market" else TimeInForce.GTC
            if order_type == "limit" and limit_price is not None:
                req = LimitOrderRequest(
                    symbol=sym, qty=qty, side=side_enum, type=OrderType.LIMIT,
                    time_in_force=tif, limit_price=limit_price,
                )
            else:
                req = MarketOrderRequest(
                    symbol=sym, qty=qty, side=side_enum, type=OrderType.MARKET,
                    time_in_force=tif,
                )
            order = self.client.submit_order(req)
            return AlpacaOrderResult(
                order_id=order.id or "",
                symbol=sym,
                side=side,
                qty=float(order.qty or qty),
                filled_qty=float(order.filled_qty or 0),
                filled_avg_price=float(order.filled_avg_price or 0),
                status=order.status.value if order.status else "unknown",
                raw=order.model_dump() if hasattr(order, "model_dump") else {},
                http_status=200,
            )
        except Exception as e:
            logger.error(f"Alpaca crypto order failed for {sym}: {e}")
            return AlpacaOrderResult(
                order_id="error", symbol=sym, side=side, qty=qty,
                filled_qty=0, filled_avg_price=0.0, status="error",
                raw={"error": str(e)}, http_status=502,
            )

    def search_crypto_assets(self, query: str = "") -> list[dict]:
        """Search the FULL tradable Alpaca crypto universe (no hardcoded set.

        Returns pair symbols ("BTC/USD") so any listed pair is tradable/spawnable
        from the UI —the universe == Alpaca's crypto asset list.

        """
        if not self.is_configured():
            return []
        try:
            from alpaca.trading.requests import GetAssetsRequest
            from alpaca.trading.enums import AssetClass
            req = GetAssetsRequest(asset_class=AssetClass.CRYPTO, status="active")
            assets = self.client.get_all_assets(req)
            q = query.strip().upper()
            out = []
            for a in (assets or []):
                if getattr(a, "tradable", True) is False:
                    continue
                sym = str(getattr(a, "symbol", "") or "")
                pair = sym.replace("-", "/").upper()
                name = str(getattr(a, "name", "") or "")
                if not q or q in sym.upper() or q in pair or q in name.upper():
                    out.append({
                        "symbol": sym,
                        "pair": pair,
                        "name": name,
                        "tradable": True,
                        "exchange": getattr(a, "exchange", None),
                        "asset_class": getattr(a, "class_", None),
                    })
            # De-dup by pair, keep first
            seen = set()
            dedup = []
            for e in out:
                p = e["pair"]
                if p in seen:
                    continue
                seen.add(p)
                dedup.append(e)
            return dedup[:250]
        except Exception as e:
            logger.error(f"search_crypto_assets failed: {e}")
            return []

    async def get_positions(self) -> list[dict]:
        if not self.is_configured():
            return []
        try:
            positions = self.client.get_all_positions()
            return [
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "avg_entry_price": float(p.avg_entry_price),
                    "current_price": float(p.current_price or 0),
                    "market_value": float(p.market_value or 0),
                    "side": "buy" if float(p.qty) > 0 else "sell",
                }
                for p in positions
            ]
        except Exception as e:
            logger.error(f"Alpaca get_positions failed: {e}")
            return []

    async def get_account(self) -> dict:
        if not self.is_configured():
            return {"status": "unconfigured", "cash": 0, "equity": 0}
        try:
            account = self.client.get_account()
            return {
                "status": account.status,
                "cash": float(account.cash or 0),
                "equity": float(account.equity or 0),
                "buying_power": float(account.buying_power or 0),
            }
        except Exception as e:
            logger.error(f"Alpaca get_account failed: {e}")
            return {"status": "error", "error": str(e)}

    async def portfolio_history(self, days: int = 30) -> dict:
        """Return the broker's real equity curve (NAV) over the trailing window.

        Uses Alpaca's portfolio-history endpoint so the frontend NAV chart shows
        the authoritative account equity — never a fabricated running balance.
        """
        if not self.is_configured():
            return {"source": "unconfigured"}
        try:
            from alpaca.trading.requests import GetPortfolioHistoryRequest
            req = GetPortfolioHistoryRequest(period="1M", timeframe="1D", extended_hours=False)
            hist = self.client.get_portfolio_history(req)
            # Historically a model; guard against a plain dict shape too.
            timestamps = getattr(hist, "timestamp", None) or (hist.get("timestamp") if isinstance(hist, dict) else None)
            equity = getattr(hist, "equity", None) or (hist.get("equity") if isinstance(hist, dict) else None)
            base_value = getattr(hist, "base_value", None) or (hist.get("base_value") if isinstance(hist, dict) else None)
            if timestamps is None or equity is None:
                return {"source": "error", "error": "unexpected portfolio-history shape"}
            nav_history = [
                {"t": ts.isoformat() if hasattr(ts, "isoformat") else str(ts), "equity": float(e)}
                for ts, e in zip(timestamps, equity)
            ]
            return {
                "source": "alpaca",
                "nav_history": nav_history,
                "base_value": float(base_value or 0),
            }
        except Exception as e:
            logger.error(f"Alpaca portfolio_history failed: {e}")
            return {"source": "error", "error": str(e)}

    async def get_bars(self, symbol: str, timeframe: str = "1Day",
                       limit: int = 252) -> list[dict]:
        if not self.is_configured():
            return []
        try:
            tf = TimeFrame.Day
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                limit=limit,
            )
            bars = self.data_client.get_stock_bars(req)
            return [
                {
                    "t": bar.timestamp.isoformat(),
                    "o": float(bar.open),
                    "h": float(bar.high),
                    "l": float(bar.low),
                    "c": float(bar.close),
                    "v": float(bar.volume),
                }
                for bar in (bars[symbol] or [])
            ]
        except Exception as e:
            logger.warning(f"Alpaca get_bars failed for {symbol}: {e}")
            return []

# ── Options ────────────────────────────────────────────────────────────────
    async def get_option_contracts(self, underlying: str, expiration: str | None = None,
                             contract_type: str | None = None,
                             strike_gte: float | None = None,
                             strike_lte: float | None = None,
                             limit: int = 1000) -> list[dict]:
        """Look up option contracts via the Alpaca contract master."""
        if not self.is_configured():
            return []
        try:
            from alpaca.trading.requests import GetOptionContractsRequest
            from alpaca.trading.enums import ContractType
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
            resp = self.client.get_option_contracts(req)
            return [c.model_dump() for c in resp.option_contracts] if hasattr(resp, "option_contracts") else []
        except Exception as e:
            logger.error(f"Alpaca get_option_contracts failed for {underlying}: {e}")
            return []

    def search_assets(self, query: str, asset_class: str | None = None) -> list[dict]:
        """Search Alpaca tradable assets (stocks, ETFs) for option underlyings."""
        if not self.is_configured():
            return []
        try:
            from alpaca.trading.requests import GetAssetsRequest
            from alpaca.trading.enums import AssetClass
            req = GetAssetsRequest(asset_class=asset_class)
            assets = self.client.get_all_assets(req)
            q = query.upper().strip()
            out = []
            for a in assets:
                sym = a.symbol
                if not q or q in sym or (a.name and q in (a.name or "").upper()):
                    out.append({
                        "symbol": sym,
                        "name": a.name,
                        "asset_class": a.class_ if hasattr(a, "class_") else None,
                        "tradable": a.tradable,
                    })
            return out[:100]
        except Exception as e:
            logger.error(f"search_assets failed: {e}")
            return []

    async def place_option_order(self, contract_symbol: str, qty: int, side: str,
                                 position_intent: str = "buy_to_open",
                                 order_type: str = "market",
                                 limit_price: float | None = None,
                                 order_class: str = "simple",
                                 legs: list[dict] | None = None) -> AlpacaOrderResult:
        """Place an options order (single contract or multi-leg spread)."""
        if not self.is_configured():
            return AlpacaOrderResult(
                order_id="simulated", symbol=contract_symbol or "OPT", side=side, qty=qty,
                filled_qty=qty, filled_avg_price=0.0, status="simulated", raw={},
                http_status=200,
            )
        try:
            from alpaca.trading.requests import (MarketOrderRequest, LimitOrderRequest,
                                                 OrderRequest, OptionLegRequest)
            from alpaca.trading.enums import (OrderSide, OrderType, TimeInForce,
                                              OrderClass, PositionIntent)
            side_enum = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            pi = PositionIntent(position_intent)
            # Alpaca-py OrderClass has no 'vertical' member: normalize to 'mleg'
            # (multi-leg). 'simple' stays simple.
            oc_raw = "mleg" if order_class in ("vertical", "mleg") else "simple"
            common = dict(
                qty=qty, side=side_enum, time_in_force=TimeInForce.DAY,
                position_intent=pi, order_class=OrderClass(oc_raw),
            )
            if oc_raw == "simple":
                if order_type == "limit" and limit_price is not None:
                    req = LimitOrderRequest(symbol=contract_symbol, limit_price=limit_price, **common)
                else:
                    req = MarketOrderRequest(symbol=contract_symbol, **common)
            else:
                # Accept 1-leg MLEG as a way to bypass single-leg market-hours
                # restrictions on Alpaca (the broker allows MLEG market orders
                # outside hours even with a single option leg).
                if not legs or len(legs) < 1:
                    raise ValueError(
                        "MLEG orders require at least 1 leg; "
                        f"got {len(legs) if legs else 0}."
                    )
                # Belt-and-suspenders: collapse duplicate (symbol, side,
                # position_intent) legs by summing qty, in case the caller
                # didn't consolidate. This is what ratio structures
                # (butterfly/strip/strap) need — Alpaca rejects duplicate
                # symbols, so 2x K2 must be one leg with ratio_qty=2.
                consolidated: dict[tuple, dict] = {}
                for l in legs:
                    key = (
                        str(l.get("symbol")),
                        str(l.get("side", "buy")).lower(),
                        str(l.get("position_intent", "buy_to_open")),
                    )
                    qty = int(l.get("qty", 1) or 1)
                    if key in consolidated:
                        consolidated[key]["qty"] = int(consolidated[key].get("qty", 1) or 1) + qty
                    else:
                        consolidated[key] = dict(l)
                if len(consolidated) < 1:
                    raise ValueError(
                        "MLEG orders require at least 1 leg after "
                        f"consolidation; got {len(consolidated)}."
                    )
                symbols = [str(l.get("symbol")) for l in consolidated.values()]
                if len(set(symbols)) != len(symbols):
                    raise ValueError(
                        "All legs must have unique symbols; "
                        f"got duplicates in {symbols}."
                    )
                leg_objs = [
                    OptionLegRequest(
                        symbol=str(l["symbol"]),
                        ratio_qty=int(l.get("qty", 1)),
                        side=OrderSide.BUY if str(l.get("side", "buy")).lower() == "buy" else OrderSide.SELL,
                        position_intent=PositionIntent(l.get("position_intent", "buy_to_open")),
                    ) for l in consolidated.values()
                ]
                # Alpaca rejects MLEG orders with < 2 unique legs after
                # consolidation. When the caller asked for mleg/vertical but the
                # payload collapsed to a single leg (e.g. the route's market-hour
                # auto-wrap of a simple order), downgrade to a SIMPLE order on
                # that one leg instead of submitting an invalid 1-leg MLEG.
                if len(consolidated) == 1:
                    sole = consolidated[next(iter(consolidated))]
                    sole_symbol = str(sole["symbol"])
                    sole_side = OrderSide.BUY if str(sole.get("side", "buy")).lower() == "buy" else OrderSide.SELL
                    sole_qty = int(sole.get("qty", 1) or 1)
                    if order_type == "limit" and limit_price is not None:
                        req = LimitOrderRequest(
                            symbol=sole_symbol, limit_price=limit_price,
                            qty=sole_qty, side=sole_side, time_in_force=TimeInForce.DAY,
                            position_intent=PositionIntent(sole.get("position_intent", position_intent)),
                            order_class=OrderClass.SIMPLE,
                        )
                    else:
                        req = MarketOrderRequest(
                            symbol=sole_symbol,
                            qty=sole_qty, side=sole_side, time_in_force=TimeInForce.DAY,
                            position_intent=PositionIntent(sole.get("position_intent", position_intent)),
                            order_class=OrderClass.SIMPLE,
                        )
                else:
                    mleg_common = dict(
                        symbol=None,  # alpaca-py: symbol must NOT be set for MLEG orders
                        qty=qty, side=side_enum, time_in_force=TimeInForce.DAY,
                        order_class=OrderClass.MLEG, legs=leg_objs or None,
                        position_intent=pi,
                    )
                    if order_type == "limit" and limit_price is not None:
                        req = LimitOrderRequest(
                            limit_price=limit_price,
                            type=OrderType.LIMIT,
                            **mleg_common,
                        )
                    else:
                        req = MarketOrderRequest(
                            type=OrderType.MARKET,
                            **mleg_common,
                        )
            order = self.client.submit_order(req)
            return AlpacaOrderResult(
                order_id=order.id or "",
                symbol=contract_symbol,
                side=side,
                qty=float(getattr(order, "qty", qty) or qty),
                filled_qty=float(getattr(order, "filled_qty", 0) or 0),
                filled_avg_price=float(getattr(order, "filled_avg_price", 0) or 0),
                status=order.status.value if getattr(order, "status", None) else "unknown",
                raw=order.model_dump() if hasattr(order, "model_dump") else {},
            )
        except Exception as e:
            logger.error(f"Alpaca option order failed for {contract_symbol}: {e}")
            err_text = str(e)
            # Distinguish account-eligibility / validation errors from
            # transient transport failures so the route can return 4xx vs 5xx
            # and the UI can surface a clear message instead of "Bad Gateway".
            http_status = 502
            if "40310000" in err_text or "not eligible" in err_text.lower() \
                    or "forbidden" in err_text.lower() or "permission" in err_text.lower():
                http_status = 403
            elif "validation" in err_text.lower() or "missing" in err_text.lower() \
                    or "invalid" in err_text.lower() or "value error" in err_text.lower():
                http_status = 400
            return AlpacaOrderResult(
                order_id="error", symbol=contract_symbol, side=side, qty=qty,
                filled_qty=0, filled_avg_price=0.0, status="error",
                raw={"error": err_text}, http_status=http_status,
            )


alpaca = AlpacaClient()
