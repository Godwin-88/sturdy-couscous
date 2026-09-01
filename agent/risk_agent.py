"""
Risk Agent
Validates signals, sizes positions (half-Kelly), checks VaR, enforces
concentration limits, and returns only risk-approved orders.
"""

from common.schema_validator import validate_order

import os
from typing import Any

import numpy as np
import pandas as pd
import psycopg2
from alpaca_data import provider
from loguru import logger


MAX_POSITION_PCT   = float(os.getenv("AGENT_MAX_POSITION_PCT",  "0.20"))
MAX_SECTOR_PCT     = float(os.getenv("RISK_MAX_SECTOR_PCT",     "0.40"))
VAR_CONFIDENCE     = float(os.getenv("RISK_VAR_CONFIDENCE",     "0.99"))
MAX_VAR_PCT        = float(os.getenv("RISK_MAX_VAR_PCT",        "0.05"))
INITIAL_CAPITAL    = float(os.getenv("INITIAL_CAPITAL_USD", 10000))
SHADOW_MODE        = os.getenv("SHADOW_MODE", "false").lower() == "true"

SECTOR_MAP = {
    "SPY": "equity_broad",
    "QQQ": "equity_tech",
    "XLF": "equity_financials",
    "XLE": "equity_energy",
    "GLD": "commodities",
    "TLT": "macro_rates",
    "BTC-USD": "crypto",
    "ETH-USD": "crypto",
}

# Correlation-breakdown universe (REF: cross-asset correlations -> 1 in stress).
CORR_UNIVERSE = ["SPY", "QQQ", "XLF", "XLE", "GLD"]

# When the mean pairwise correlation breaches this level the market is in a
# breakdown regime (REF 'Model Failure & Crises' + 'Liquidity & Regulation'
# feedback loops): tighten both the sector and per-position caps.
CORR_BREAKDOWN_THRESHOLD = 0.70
STRESS_SECTOR_CAP_PCT     = 0.25
STRESS_POSITION_CAP_PCT   = 0.10


class RiskAgent:
    def __init__(self):
        self._db_conn_str = (
            f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
            f"dbname={os.getenv('POSTGRES_DB', 'graphalpha')} "
            f"user={os.getenv('POSTGRES_USER', 'graphalpha')} "
            f"password={os.getenv('POSTGRES_PASSWORD', '')}"
        )

    async def run(self, signals: list[dict], cycle_id: str = "") -> list[dict]:
        """Validate and size each signal. Returns approved orders only."""
        portfolio = await self.get_portfolio_state()
        nav       = portfolio["nav"]
        positions = portfolio["positions"]

        prices_cache = self._fetch_recent_prices()
        corr_breakdown = self._corr_breakdown(prices_cache)
        stress_mode = corr_breakdown >= CORR_BREAKDOWN_THRESHOLD
        sector_cap_pct = STRESS_SECTOR_CAP_PCT if stress_mode else MAX_SECTOR_PCT
        position_cap_pct = STRESS_POSITION_CAP_PCT if stress_mode else MAX_POSITION_PCT
        if stress_mode:
            logger.warning(
                f"Correlation breakdown {corr_breakdown:.2f}>=0.70 — tightened "
                f"sector cap to {sector_cap_pct:.0%}, position cap to {position_cap_pct:.0%}"
            )
        approved = []

        for sig in signals:
            ticker = sig["ticker"]

            kelly_fraction = self._kelly_fraction(sig)
            target_notional = nav * kelly_fraction * position_cap_pct

            sector = SECTOR_MAP.get(ticker, "other")
            sector_exposure = sum(
                p["notional"] for p in positions.values()
                if SECTOR_MAP.get(p["ticker"], "other") == sector
            )
            if sector_exposure + target_notional > nav * sector_cap_pct:
                logger.warning(f"Rejected {ticker}: sector {sector} concentration limit")
                self._write_shadow(cycle_id, sig, {"action": "reject", "reason": "sector_cap"}, nav)
                continue

            var_contrib = self._marginal_var(ticker, target_notional, nav, prices_cache)
            if var_contrib > nav * MAX_VAR_PCT:
                logger.warning(f"Rejected {ticker}: VaR contribution {var_contrib:.2f} "
                               f"> limit {nav * MAX_VAR_PCT:.2f}")
                self._write_shadow(cycle_id, sig, {"action": "reject", "reason": "var_cap"}, nav)
                continue

            price = self._get_price(ticker, prices_cache)
            if price <= 0:
                logger.warning(f"Rejected {ticker}: no valid price")
                self._write_shadow(cycle_id, sig, {"action": "reject", "reason": "no_price"}, nav)
                continue

            qty = target_notional / price
            if qty < 0.0001:
                continue

            decision = {
                "action": "approve",
                "quantity": round(qty, 6),
                "notional_usd": round(target_notional, 2),
                "kelly_fraction": round(kelly_fraction, 4),
                "var_contribution_pct": round(var_contrib / max(nav, 1e-9), 4),
                "price_estimate": round(price, 4),
            }

            order = {
                **sig,
                "order_id":        str(__import__("uuid").uuid4()),
                "cycle_id":        sig.get("cycle_id", cycle_id),
                "quantity":        decision["quantity"],
                "notional_usd":    decision["notional_usd"],
                "kelly_fraction":  decision["kelly_fraction"],
                "var_contribution": round(var_contrib, 2),
                "var_contribution_pct": decision["var_contribution_pct"],
                "price_estimate":  decision["price_estimate"],
                "risk_checks": {
                    "position_pct_ok": sector_exposure + target_notional <= nav * sector_cap_pct,
                    "sector_pct_ok": sector_exposure + target_notional <= nav * sector_cap_pct,
                    "var_ok": var_contrib <= nav * MAX_VAR_PCT,
                },
                "mode": os.getenv("KRAKEN_TRADING_MODE", "paper"),
            }
            try:
                validate_order(order)
            except ValueError:
                self._write_shadow(cycle_id, sig, {"action": "reject", "reason": "schema_validation"}, nav)
                continue

            self._write_shadow(cycle_id, sig, decision, nav)
            approved.append(order)

        logger.info(f"Risk: {len(approved)}/{len(signals)} signals approved")
        return approved

    def _write_shadow(self, cycle_id: str, signal: dict, decision: dict, nav: float) -> None:
        if not SHADOW_MODE:
            return
        if not cycle_id:
            return
        try:
            import json
            import psycopg2.extras
            conn = psycopg2.connect(self._db_conn_str)
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO shadow_comparison
                  (cycle_id, ticker, strategy, signal, python_decision)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
                ON CONFLICT (cycle_id, ticker, strategy) DO UPDATE SET
                  python_decision = EXCLUDED.python_decision,
                  signal = EXCLUDED.signal
                """,
                (
                    cycle_id,
                    signal.get("ticker", ""),
                    signal.get("strategy", ""),
                    json.dumps(signal),
                    json.dumps(decision),
                ),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as exc:
            logger.debug(f"shadow_comparison write skipped: {exc}")

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
        p_win = 0.5 + 0.25 * score
        p_lose = 1 - p_win
        b = 1.5
        kelly = (p_win * b - p_lose) / b
        half_kelly = max(0.0, kelly / 2)
        # KG `risk_weight` scales sizing (single source of truth in Neo4j).
        rw = signal.get("risk_weight")
        if isinstance(rw, (int, float)) and 0.0 < rw <= 1.0:
            half_kelly *= rw
        return min(half_kelly, 1.0)

    # ── Correlation breakdown ────────────────────────────────────────────────
    def _corr_breakdown(self, prices: dict) -> float:
        """Mean pairwise 60d rolling correlation over the equity+gold universe."""
        frame = pd.DataFrame(
            {t: prices[t] for t in CORR_UNIVERSE if t in prices}
        )
        if frame.shape[1] < 3 or frame.empty:
            return 0.5
        rets = frame.pct_change().dropna().tail(60)
        if len(rets) < 21:
            return 0.5
        cmat = rets.corr().values
        tri = cmat[np.triu_indices(n=len(rets.columns), k=1)]
        if not tri.size:
            return 0.5
        val = float(np.nanmean(tri))
        return 0.5 if np.isnan(val) else val

    # ── Marginal VaR ──────────────────────────────────────────────────────────
    def _marginal_var(self, ticker: str, notional: float,
                      nav: float, prices: dict) -> float:
        """Parametric VaR contribution using 60-day daily returns."""
        series = prices.get(ticker)
        if series is None or len(series) < 20:
            return notional * 0.03
        rets   = series.pct_change().dropna().tail(60)
        sigma  = rets.std()
        z      = 2.326 if VAR_CONFIDENCE >= 0.99 else 1.645
        return notional * sigma * z

    # ── Price helpers ─────────────────────────────────────────────────────────
    def _fetch_recent_prices(self) -> dict:
        tickers = list(SECTOR_MAP.keys())
        close = provider.get_close_series_many(tickers, days=90)
        if close.empty:
            logger.warning("RiskAgent: no price data available")
            return {}
        return {t: close[t].dropna() for t in tickers if t in close.columns}

    def _get_price(self, ticker: str, prices: dict) -> float:
        series = prices.get(ticker)
        if series is not None and not series.empty:
            return float(series.iloc[-1])
        return 0.0
