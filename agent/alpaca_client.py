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


alpaca = AlpacaClient()
