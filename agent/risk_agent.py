"""
Risk Agent
Validates signals, sizes positions (half-Kelly), checks VaR, enforces
concentration limits, and returns only risk-approved orders.
"""

import os
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
import psycopg2
from loguru import logger


MAX_POSITION_PCT   = float(os.getenv("RISK_MAX_POSITION_PCT", 0.15))   # 15% per position
MAX_SECTOR_PCT     = float(os.getenv("RISK_MAX_SECTOR_PCT", 0.40))      # 40% per sector
VAR_CONFIDENCE     = float(os.getenv("RISK_VAR_CONFIDENCE", 0.99))
MAX_VAR_PCT        = float(os.getenv("RISK_MAX_VAR_PCT", 0.05))         # 5% daily VaR limit
INITIAL_CAPITAL    = float(os.getenv("INITIAL_CAPITAL_USD", 10000))

SECTOR_MAP = {
    "SPY": "equity_broad",
    "QQQ": "equity_tech",
    "XLF": "equity_financials",
    "XLE": "equity_energy",
    "BTC": "crypto",
    "ETH": "crypto",
}


class RiskAgent:
    def __init__(self):
        self._db_conn_str = (
            f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
            f"dbname={os.getenv('POSTGRES_DB', 'graphalpha')} "
            f"user={os.getenv('POSTGRES_USER', 'graphalpha')} "
            f"password={os.getenv('POSTGRES_PASSWORD', '')}"
        )

    async def run(self, signals: list[dict]) -> list[dict]:
        """Validate and size each signal. Returns approved orders only."""
        portfolio = await self.get_portfolio_state()
        nav       = portfolio["nav"]
        positions = portfolio["positions"]

        prices_cache = self._fetch_recent_prices()
        approved = []

        for sig in signals:
            ticker = sig["ticker"]

            # ── Kelly sizing ──────────────────────────────────────────────────
            kelly_fraction = self._kelly_fraction(sig)
            target_notional = nav * kelly_fraction * MAX_POSITION_PCT

            # ── Concentration check ───────────────────────────────────────────
            sector = SECTOR_MAP.get(ticker, "other")
            sector_exposure = sum(
                p["notional"] for p in positions.values()
                if SECTOR_MAP.get(p["ticker"], "other") == sector
            )
            if sector_exposure + target_notional > nav * MAX_SECTOR_PCT:
                logger.warning(f"Rejected {ticker}: sector {sector} concentration limit")
                continue

            # ── VaR contribution check ────────────────────────────────────────
            var_contrib = self._marginal_var(ticker, target_notional, nav, prices_cache)
            if var_contrib > nav * MAX_VAR_PCT:
                logger.warning(f"Rejected {ticker}: VaR contribution {var_contrib:.2f} "
                               f"> limit {nav * MAX_VAR_PCT:.2f}")
                continue

            # ── Compute order quantity ────────────────────────────────────────
            price = self._get_price(ticker, prices_cache)
            if price <= 0:
                logger.warning(f"Rejected {ticker}: no valid price")
                continue

            qty = target_notional / price
            if qty < 0.0001:
                continue

            approved.append({
                **sig,
                "quantity":        round(qty, 6),
                "notional_usd":    round(target_notional, 2),
                "kelly_fraction":  round(kelly_fraction, 4),
                "var_contribution": round(var_contrib, 2),
                "price_estimate":  round(price, 4),
            })

        logger.info(f"Risk: {len(approved)}/{len(signals)} signals approved")
        return approved

    # ── Portfolio state ───────────────────────────────────────────────────────
    async def get_portfolio_state(self) -> dict:
        """Read open positions and NAV from PostgreSQL."""
        try:
            with psycopg2.connect(self._db_conn_str) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT ticker, direction, quantity, avg_entry_price,
                               current_price, (quantity * current_price) AS notional
                        FROM positions WHERE status = 'open'
                    """)
                    rows = cur.fetchall()
                    cols = ["ticker", "direction", "quantity",
                            "avg_entry_price", "current_price", "notional"]
                    positions = {
                        r[0]: dict(zip(cols, r)) for r in rows
                    }
                    total_notional = sum(p["notional"] for p in positions.values())

                    cur.execute("SELECT cash_balance FROM portfolio_state ORDER BY id DESC LIMIT 1")
                    row = cur.fetchone()
                    cash = row[0] if row else INITIAL_CAPITAL

                    nav = cash + total_notional
                    pnl = sum(
                        p["quantity"] * (p["current_price"] - p["avg_entry_price"])
                        * (1 if p["direction"] == "buy" else -1)
                        for p in positions.values()
                    )
                    return {
                        "nav":               nav,
                        "cash":              cash,
                        "positions":         positions,
                        "unrealised_pnl_usd": pnl,
                    }
        except Exception as e:
            logger.error(f"Portfolio state error: {e}")
            return {
                "nav":               INITIAL_CAPITAL,
                "cash":              INITIAL_CAPITAL,
                "positions":         {},
                "unrealised_pnl_usd": 0.0,
            }

    # ── Kelly criterion ───────────────────────────────────────────────────────
    def _kelly_fraction(self, signal: dict) -> float:
        """
        Half-Kelly: f* = (p*b - q) / b, halved for conservatism.
        Maps fused_score to a win-probability estimate.
        """
        score = abs(signal["score"])
        p_win = 0.5 + 0.25 * score          # score=1 → p=0.75, score=0.2 → p=0.55
        p_lose = 1 - p_win
        b = 1.5                              # assumed payoff ratio (reward:risk = 1.5)
        kelly = (p_win * b - p_lose) / b
        half_kelly = max(0.0, kelly / 2)
        return min(half_kelly, 1.0)

    # ── Marginal VaR ──────────────────────────────────────────────────────────
    def _marginal_var(self, ticker: str, notional: float,
                      nav: float, prices: dict[str, pd.Series]) -> float:
        """Parametric VaR contribution using 60-day daily returns."""
        series = prices.get(ticker)
        if series is None or len(series) < 20:
            return notional * 0.03   # conservative 3% fallback
        rets   = series.pct_change().dropna().tail(60)
        sigma  = rets.std()
        z      = 2.326 if VAR_CONFIDENCE >= 0.99 else 1.645
        return notional * sigma * z

    # ── Price helpers ─────────────────────────────────────────────────────────
    def _fetch_recent_prices(self) -> dict[str, pd.Series]:
        tickers = list(SECTOR_MAP.keys())
        try:
            raw = yf.download(tickers, period="3mo", auto_adjust=True, progress=False)
            close = raw["Close"]
            return {t: close[t].dropna() for t in tickers if t in close.columns}
        except Exception as e:
            logger.error(f"Price fetch error: {e}")
            return {}

    def _get_price(self, ticker: str, prices: dict[str, pd.Series]) -> float:
        series = prices.get(ticker)
        if series is not None and not series.empty:
            return float(series.iloc[-1])
        return 0.0
