"""
Execution Agent
Submits approved orders to Alpaca (paper or live).
Legacy Kraken support retained for backward compatibility.
Paper mode: simulates fills using last price; all modes write immutable audit log.
Live mode: calls Alpaca REST API via alpaca-py.
"""

import json
import os
import time
import uuid
from datetime import datetime
from typing import Any

import httpx
import psycopg2
from loguru import logger

from alpaca_client import alpaca

TRADING_MODE = os.getenv("TRADING_MODE", os.getenv("KRAKEN_TRADING_MODE", "paper"))
DEFAULT_VENUE = os.getenv("DEFAULT_VENUE", "alpaca")

PAPER_FEE_PCT = 0.0026
PAPER_SLIP_PCT = 0.0005


class ExecutionAgent:
    def __init__(self, mode: str = TRADING_MODE, venue: str = DEFAULT_VENUE):
        self.mode = mode
        self.venue = venue
        self._db_conn_str = (
            f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
            f"dbname={os.getenv('POSTGRES_DB', 'graphalpha')} "
            f"user={os.getenv('POSTGRES_USER', 'graphalpha')} "
            f"password={os.getenv('POSTGRES_PASSWORD', '')}"
        )
        logger.info(f"ExecutionAgent initialised in [{self.mode}] mode on [{self.venue}]")

    async def run(self, orders: list[dict]) -> list[dict]:
        executed = []
        for order in orders:
            result = await self._execute_order(order)
            if result:
                self._write_audit(order, result)
                self._update_position(order, result)
                executed.append(result)
        return executed

    # ── Order dispatch ────────────────────────────────────────────────────────
    async def _execute_order(self, order: dict) -> dict | None:
        order_id = str(uuid.uuid4())
        venue = order.get("venue", self.venue)
        symbol = order.get("venue_symbol", order.get("ticker", ""))
        side = order["direction"]
        qty = order["quantity"]
        price_est = order.get("price_estimate", 0)

        try:
            if venue == "alpaca":
                return await self._alpaca_order(order_id, symbol, side, qty, price_est)
            elif venue == "kraken":
                return await self._kraken_order(order_id, order.get("kraken_pair", symbol), side, qty, price_est)
            else:
                logger.error(f"Unknown venue: {venue}")
                return None
        except Exception as e:
            logger.error(f"Execution error for {symbol} ({venue}): {e}")
            return None

    async def _alpaca_order(self, order_id: str, symbol: str, side: str,
                            qty: float, price_est: float) -> dict:
        if self.mode == "paper":
            return self._paper_fill(order_id, symbol, side, qty, price_est)
        result = await alpaca.place_order(symbol, side, qty)
        return {
            "order_id":    order_id,
            "alpaca_order_id": result.order_id,
            "symbol":      symbol,
            "side":        side,
            "quantity":    qty,
            "fill_price":  result.filled_avg_price or price_est,
            "fee_usd":     0.0,
            "mode":        "live",
            "venue":       "alpaca",
            "timestamp":   datetime.utcnow().isoformat(),
            "status":      result.status,
            "raw_response": result.raw,
        }

    async def _kraken_order(self, order_id: str, pair: str,
                            side: str, qty: float, price_est: float) -> dict:
        if self.mode == "paper":
            return self._paper_fill(order_id, pair, side, qty, price_est)
        import base64, hashlib, hmac, urllib.parse
        nonce = str(int(time.time() * 1000))
        data = {"nonce": nonce, "ordertype": "market", "type": side,
                "volume": str(qty), "pair": pair, "cl_ord_id": order_id}
        post_data = urllib.parse.urlencode(data)
        path = "/0/private/AddOrder"
        sha256 = hashlib.sha256((nonce + post_data).encode()).digest()
        msg = path.encode() + sha256
        mac = hmac.new(base64.b64decode(os.getenv("KRAKEN_API_SECRET", "")), msg, hashlib.sha512)
        sig = base64.b64encode(mac.digest()).decode()
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{os.getenv('KRAKEN_API_URL', 'https://api.kraken.com')}{path}",
                                  data=data, headers={"API-Key": os.getenv("KRAKEN_API_KEY", ""), "API-Sign": sig})
        resp = r.json()
        if resp.get("error"):
            raise RuntimeError(f"Kraken API error: {resp['error']}")
        txid = resp["result"]["txid"][0]
        return {"order_id": order_id, "kraken_txid": txid, "pair": pair,
                "side": side, "quantity": qty, "mode": "live", "venue": "kraken",
                "timestamp": datetime.utcnow().isoformat(), "status": "submitted"}

    def _paper_fill(self, order_id: str, symbol: str, side: str,
                    qty: float, price: float) -> dict:
        slip = price * PAPER_SLIP_PCT * (1 if side == "buy" else -1)
        fill_price = price + slip if price > 0 else 0
        fee = fill_price * qty * PAPER_FEE_PCT if fill_price > 0 else 0
        return {
            "order_id":    order_id,
            "symbol":      symbol,
            "side":        side,
            "quantity":    qty,
            "fill_price":  round(fill_price, 6),
            "fee_usd":     round(fee, 4),
            "mode":        "paper",
            "venue":       self.venue,
            "timestamp":   datetime.utcnow().isoformat(),
            "status":      "filled",
        }

    # ── Persistence ───────────────────────────────────────────────────────────
    def _write_audit(self, order: dict, result: dict):
        try:
            with psycopg2.connect(self._db_conn_str) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO order_audit
                          (order_id, strategy, ticker, venue_symbol, venue, direction,
                           quantity, fill_price, fee_usd, mode, signal_score,
                           kelly_fraction, var_contribution, created_at, raw_response)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s)
                    """, (
                        result["order_id"],
                        order.get("strategy"),
                        order.get("ticker"),
                        result.get("symbol", order.get("venue_symbol")),
                        result.get("venue", self.venue),
                        result["side"],
                        result["quantity"],
                        result.get("fill_price", 0),
                        result.get("fee_usd", 0),
                        result["mode"],
                        order.get("score"),
                        order.get("kelly_fraction"),
                        order.get("var_contribution"),
                        json.dumps(result),
                    ))
        except Exception as e:
            logger.error(f"Audit write failed: {e}")

    def _update_position(self, order: dict, result: dict):
        if result.get("status") not in ("filled", "submitted"):
            return
        try:
            ticker     = order["ticker"]
            side       = result["side"]
            qty        = result["quantity"]
            fill_price = result.get("fill_price", order.get("price_estimate", 0))
            venue      = result.get("venue", self.venue)

            with psycopg2.connect(self._db_conn_str) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT quantity, avg_entry_price FROM positions "
                        "WHERE ticker=%s AND venue=%s AND status='open'",
                        (ticker, venue)
                    )
                    row = cur.fetchone()
                    if row:
                        old_qty, old_avg = row
                        new_qty = old_qty + qty if side == "buy" else old_qty - qty
                        new_avg = (
                            (old_qty * old_avg + qty * fill_price) / new_qty
                            if side == "buy" and new_qty > 0 else old_avg
                        )
                        if new_qty <= 0:
                            cur.execute(
                                "UPDATE positions SET status='closed', quantity=0 "
                                "WHERE ticker=%s AND venue=%s AND status='open'",
                                (ticker, venue)
                            )
                        else:
                            cur.execute(
                                "UPDATE positions SET quantity=%s, avg_entry_price=%s, "
                                "current_price=%s WHERE ticker=%s AND venue=%s AND status='open'",
                                (new_qty, new_avg, fill_price, ticker, venue)
                            )
                    elif side == "buy":
                        cur.execute("""
                            INSERT INTO positions
                              (ticker, direction, quantity, avg_entry_price,
                               current_price, venue, status, opened_at)
                            VALUES (%s, %s, %s, %s, %s, %s, 'open', NOW())
                        """, (ticker, side, qty, fill_price, fill_price, venue))
        except Exception as e:
            logger.error(f"Position update failed: {e}")
