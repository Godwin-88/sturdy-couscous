"""
Hedge Agent — dynamic delta hedging + Taleb-style tail-hedge sleeve.

Watches the LIVE portfolio greeks (aggregated delta/gamma/theta/vega across
all Alpaca positions — equities contribute delta=shares, options contribute
contracts x 100 x greeks from live snapshots) and:

  1. DYNAMIC DELTA HEDGE
        hedge_shares = -portfolio_delta / underlying_price
     Proposes an underlying share offset whenever |hedge_shares| >= min_shares
     or the portfolio delta breaches a regime-scaled band. DRY-RUN FIRST: an
     explicit confirm=True is required before any paper order is placed
     (T10 human-agent interaction).

  2. TAIL SLEEVE (Taleb / REF Model Failure and Crises)
     When short-gamma is material and regime is HighVolatility / Crisis /
     SystemicStress, recommend a ladder of cheap OTM puts (-5% / -8%) funded
     from collected premium.

  3. OPTION P&L (income vs hedge cost)
     option_pnl() reports collected premium on short options, debit paid on
     long options, mark-to-market P&L, and the equity hedge-sleeve notional.

All methods are async-safe (they await the Alpaca coroutines) and defensive
(never raise): on failure they return a zero/empty state so the hedge agent
can never take down the agent loop.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from loguru import logger

try:
    from agent.alpaca_client import alpaca
    from agent.options_market import options_provider
except ImportError:  # pragma: no cover
    from alpaca_client import alpaca  # type: ignore
    from options_market import options_provider  # type: ignore

try:
    from agent.option_signal import current_regime
except ImportError:  # pragma: no cover
    from option_signal import current_regime  # type: ignore

MULT = 100  # option multiplier (1 contract = 100 shares of underlying)

HEDGE_MIN_SHARES = float(os.getenv("OPTION_HEDGE_MIN_SHARES", "1"))
# Rebalance when |portfolio_delta| in SHARES exceeds this regime-scaled band.
HEDGE_BAND_SHARES = float(os.getenv("OPTION_HEDGE_BAND_SHARES", "20"))
# Regime multipliers tighten the band (more hedging) in stress regimes.
_BAND_MULT = {
    "Neutral": 1.5,
    "LowVolatility": 2.0,
    "MeanReverting": 1.0,
    "Trending": 1.0,
    "Recovery": 1.0,
    "HighVolatility": 0.5,
    "Crisis": 0.25,
    "SystemicStress": 0.2,
}
# Tail sleeve budget as a fraction of the current long-premium/income pool.
TAIL_BUDGET_PCT = float(os.getenv("OPTION_TAIL_BUDGET_PCT", "0.02"))


def _is_option_symbol(symbol: str) -> bool:
    """OCC option symbols are 16+ chars (or contain '-' for some venues)."""
    stripped = str(symbol or "").upper().lstrip("$")
    return ("-" in symbol) or len(stripped) > 6


class HedgeAgent:
    """Portfolio-greek aggregation + dynamic delta hedge + tail sleeve + P&L."""

    def __init__(self) -> None:
        self.min_shares = HEDGE_MIN_SHARES
        self.band_shares = HEDGE_BAND_SHARES

    # ── Position ingestion ─────────────────────────────────────────────────

    async def _fetch_positions(self) -> list[dict]:
        """Await live Alpaca positions; normalise to a flat dict list."""
        if not (alpaca and alpaca.is_configured()):
            return []
        try:
            positions = await alpaca.get_positions()
        except Exception as e:
            logger.warning(f"hedge_agent: get_positions failed: {e}")
            return []
        if not isinstance(positions, list):
            return []
        return [
            {
                "symbol": str(p.get("symbol") or ""),
                "qty": float(p.get("qty") or 0),
                "avg_entry_price": float(p.get("avg_entry_price") or 0),
                "current_price": float(p.get("current_price") or 0),
                "market_value": float(p.get("market_value") or 0),
            }
            for p in positions
            if p.get("symbol")
        ]

    # ── Portfolio greeks ───────────────────────────────────────────────────

    async def portfolio_greeks(self) -> dict[str, Any]:
        """Aggregate delta/gamma/theta/vega across live Alpaca positions.

        Equity positions contribute delta=qty (1 share = 1 delta), gamma=0.
        Option positions contribute contracts x 100 x greeks from snapshots.
        """
        agg = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
        detail: list[dict] = []
        for pos in await self._fetch_positions():
            symbol, qty = pos["symbol"], pos["qty"]
            if qty == 0 or not symbol:
                continue
            if not _is_option_symbol(symbol):
                agg["delta"] += qty
                detail.append({"symbol": symbol, "cls": "equity",
                               "qty": qty, "delta": qty, "gamma": 0.0,
                               "theta": 0.0, "vega": 0.0})
                continue
            try:
                snap = options_provider.get_snapshot(symbol)
                g = (snap or {}).get("greeks") or {}
                greeks_source = "snapshot"
                # Near-expiry / stale-quote contracts sometimes return None
                # greeks from the broker — fill with local Black-Scholes so the
                # portfolio hedge state is real (not zeroed) for the book.
                def _zeroed(gg: dict) -> bool:
                    return all(
                        gg.get(k) is None or float(gg.get(k) or 0) == 0.0
                        for k in ("delta", "gamma", "theta", "vega")
                    )
                if not g or _zeroed(g):
                    try:
                        from agent.option_utils import parse_contract_symbol
                        root, expiry, right, strike = parse_contract_symbol(symbol)
                        spot = await self.spot(root)
                        if spot and spot > 0 and strike and strike > 0:
                            dte = max(0, (expiry - datetime.utcnow().date()).days) if hasattr(expiry, "strftime") else 0
                            T = dte / 365.0 if dte else 1.0 / 365.0
                            from agent.risk_book import black_scholes_greeks
                            iv = (snap or {}).get("implied_volatility") or 0.40
                            bs = black_scholes_greeks(spot, float(strike), T, float(iv), right=str(right or "C"))
                            if not g:
                                g = bs
                            else:
                                g = {**bs, **{k: g.get(k) for k in bs if g.get(k) is not None}}
                            greeks_source = "bs_local"
                    except Exception as e:
                        logger.debug(f"hedge_agent: BS fill failed for {symbol}: {e}")
                contracts = abs(qty)
                d = float(g.get("delta") or 0.0) * MULT * contracts
                gm = float(g.get("gamma") or 0.0) * MULT * contracts
                th = float(g.get("theta") or 0.0) * MULT * contracts
                v = float(g.get("vega") or 0.0) * MULT * contracts
                if qty < 0:
                    d, gm, th, v = -d, -gm, -th, -v
                for k, val in (("delta", d), ("gamma", gm), ("theta", th), ("vega", v)):
                    agg[k] += val
                detail.append({"symbol": symbol, "cls": "option", "qty": qty,
                               "delta": round(d, 2), "gamma": round(gm, 4),
                               "theta": round(th, 2), "vega": round(v, 2),
                               "iv": g.get("implied_volatility"),
                               "greeks_source": greeks_source})
            except Exception as e:
                logger.warning(f"hedge_agent: snapshot failed for {symbol}: {e}")
        for k in agg:
            agg[k] = round(agg[k], 4)
        return {"greeks": agg, "positions": detail}

    # ── Regime band ────────────────────────────────────────────────────────

    async def regime(self) -> dict:
        try:
            return await current_regime()
        except Exception as e:
            logger.warning(f"hedge_agent: regime lookup failed: {e}")
            return {"regime": "Neutral", "confidence": 0.0}

    def band_multiplier(self, regime: str) -> float:
        return _BAND_MULT.get(regime, 1.0)

    # ── Spot ───────────────────────────────────────────────────────────────

    async def spot(self, underlying: str) -> float | None:
        try:
            # Primary: the AlpacaDataProvider (proven to return real bars — the
            # bare StockHistoricalDataClient instance returns empty data.keys()).
            from agent.alpaca_data import provider
            df = provider.get_ohlcv(underlying.upper(), days=4)
            if df is not None and not getattr(df, "empty", True) and "Close" in df.columns:
                return float(df["Close"].iloc[-1])
        except Exception as e:
            logger.debug(f"hedge_agent: provider spot failed for {underlying}: {e}")
        try:
            bars = await alpaca.get_bars(underlying.upper(), limit=2) if alpaca else []
            if bars:
                return float(bars[-1]["c"])
            # get_bars may have failed on key mismatch — try the Alpaca client directly
            if alpaca and alpaca.is_configured():
                from alpaca.data.requests import StockBarsRequest
                from alpaca.data.timeframe import TimeFrame
                req = StockBarsRequest(
                    symbol_or_symbols=underlying.upper(), timeframe=TimeFrame.Day, limit=2
                )
                resp = alpaca.data_client.get_stock_bars(req)
                # Alpaca keys by the requested symbol, but be tolerant of case/format
                for key in (underlying.upper(), underlying, underlying.upper().replace("/", "-")):
                    if key in resp:
                        rows = resp[key] or []
                        if rows:
                            return float(rows[-1].close)
                # fall back to the only series present
                if hasattr(resp, "data"):
                    for rows in resp.data.values():
                        if rows:
                            return float(rows[-1].close)
        except Exception as e:
            logger.warning(f"hedge_agent: spot failed for {underlying}: {e}")
        return None

    # ── Hedge state / proposal ─────────────────────────────────────────────

    async def hedge_state(self, underlying: str = "SPY") -> dict[str, Any]:
        """Current portfolio greeks + recommended dynamic delta hedge."""
        pg = await self.portfolio_greeks()
        regime_state = await self.regime()
        regime = regime_state.get("regime", "Neutral")
        mult = self.band_multiplier(regime)
        spot = await self.spot(underlying)
        net_delta = pg["greeks"]["delta"]
        hedge_shares = -net_delta / spot if spot else 0.0
        band = self.band_shares * mult
        needs = False
        reason = ""
        if abs(hedge_shares) >= self.min_shares:
            needs = True
            reason = f"|delta|={abs(net_delta):.1f} shares > band {band:.1f} " \
                     f"(regime {regime}, x{mult:.2f})"
        proposal = None
        if needs:
            proposal = {
                "symbol": underlying.upper(),
                "side": "buy" if hedge_shares > 0 else "sell",
                "qty": int(abs(hedge_shares)),
            }
        return {
            "underlying": underlying.upper(),
            "regime": regime,
            "confidence": float(regime_state.get("confidence", 0.0)),
            "greeks": pg["greeks"],
            "positions": pg["positions"],
            "spot": spot,
            "hedge_shares": round(hedge_shares, 2),
            "band_shares": round(band, 2),
            "needs_rebalance": needs,
            "reason": reason,
            "proposal": proposal,
            "tail_sleeve": self.tail_sleeve(pg["greeks"], regime, spot),
        }

    def tail_sleeve(self, greeks: dict, regime: str, spot: float | None) -> dict:
        """Taleb short-gamma tail sleeve: recommend cheap OTM puts on stress."""
        short_gamma = float(greeks.get("gamma", 0.0)) < -50
        if not short_gamma and regime not in ("HighVolatility", "Crisis", "SystemicStress"):
            return {"recommended": False,
                    "reason": "no material short gamma / no stress regime"}
        budget = 25.0
        theta = abs(float(greeks.get("theta", 0.0)))
        if theta > 0:
            budget = max(theta * TAIL_BUDGET_PCT, 25.0)
        spot_str = f"around {spot:.2f}" if spot else "ATM-reference"
        return {
            "recommended": True,
            "budget_usd": round(budget, 2),
            "suggest": f"buy ~${budget:.0f} of OTM puts near {spot_str} (-5%/-8% ladders)",
            "note": "fund hedge from collected premium; never keep un-hedged short gamma "
                    "overnight in crisis (REF: Model Failure and Crises)",
        }

    async def rebalance_proposal(self, underlying: str = "SPY") -> dict:
        return {"dry_run": True, "hedge_state": await self.hedge_state(underlying)}

    async def execute(self, underlying: str = "SPY", confirm: bool = False) -> dict[str, Any]:
        """Dry-run by default; with confirm=True places the paper underlying order."""
        st = await self.hedge_state(underlying)
        if not confirm:
            return {"status": "dry_run",
                    "message": "pass confirm=true to execute (human-in-the-loop)",
                    "hedge_state": st}
        pp = st.get("proposal")
        if not pp or pp.get("qty", 0) <= 0:
            return {"status": "no_rebalance_needed", "hedge_state": st}
        try:
            res = await alpaca.place_order(
                pp["symbol"], pp["side"], float(pp["qty"]), "market")
            return {"status": "executed", "order": {
                "symbol": res.symbol, "side": pp["side"], "qty": pp["qty"],
                "order_id": res.order_id, "status": res.status,
                "filled_avg_price": res.filled_avg_price,
            }, "hedge_state": st}
        except Exception as e:
            logger.error(f"hedge execute failed: {e}")
            return {"status": "error", "error": str(e), "hedge_state": st}

    # ── Option P&L (income vs hedge cost) ──────────────────────────────────

    async def option_pnl(self, underlying: str = "SPY") -> dict[str, Any]:
        """Live option P&L: premium income vs debit cost, mark, hedge sleeve."""
        positions = await self._fetch_positions()
        options = [p for p in positions if _is_option_symbol(p["symbol"])]
        equities = [p for p in positions if not _is_option_symbol(p["symbol"])]

        premium_income = 0.0   # credit collected on short options
        premium_cost = 0.0     # debit paid on long options
        unrealized_pnl = 0.0   # mark-to-market on option positions
        contracts = 0
        underlyings: set[str] = set()

        for p in options:
            qty, entry = p["qty"], p["avg_entry_price"]
            cur = p["current_price"]
            notional = qty * entry * MULT
            if qty < 0:
                premium_income += abs(qty) * entry * MULT       # sold premium
                unrealized_pnl += (entry - cur) * abs(qty) * MULT
            else:
                premium_cost += qty * entry * MULT
                unrealized_pnl += (cur - entry) * qty * MULT
            contracts += abs(qty)
            try:
                from agent.option_utils import parse_contract_symbol
                root, _, _, _ = parse_contract_symbol(p["symbol"])
                underlyings.add(str(root))
            except Exception:
                pass

        # Equity hedge sleeve notional (the delta-hedge shares held).
        hedge_sleeve_mv = sum(p["market_value"] for p in equities if p["market_value"] > 0)

        return {
            "underlying": underlying.upper(),
            "option_positions": len(options),
            "equity_positions": len(equities),
            "contracts": contracts,
            "underlyings": sorted(underlyings),
            "premium_income_usd": round(premium_income, 2),
            "premium_cost_usd": round(premium_cost, 2),
            "net_premium_usd": round(premium_income - premium_cost, 2),
            "unrealized_pnl_usd": round(unrealized_pnl, 2),
            "hedge_sleeve_mv_usd": round(hedge_sleeve_mv, 2),
            "net_option_pnl_usd": round(premium_income - premium_cost + unrealized_pnl, 2),
        }


hedge_agent = HedgeAgent()

__all__ = ["HedgeAgent", "hedge_agent"]
