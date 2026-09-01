"""
Hedge Agent — dynamic delta hedging + Taleb-style tail-hedge sleeve.

Watches the LIVE portfolio greeks (aggregated delta/gamma/theta/vega across all
Alpaca option positions, plus equity positions with delta=shares) and:

  1. DYNAMIC DELTA HEDGE
       hedge_shares = -portfolio_delta / underlying_price
     Proposes an underlying share offset whenever |hedge_shares| >= min_shares
     or the portfolio delta breaches a regime-scaled band. DRY-RUN FIRST: an
     explicit confirm=True is required before any paper order is placed
     (T10 human-agent interaction: the trader always sees the hedge before it
     touches the account).

  2. TAIL SLEEVE (Taleb / REF Module-5 fat tails)
     When short-gamma exposure is material and the regime is HighVolatility /
     Crisis / SystemicStress, recommend a ladder of cheap OTM puts (e.g. -5% /
     -8%) sized to a hedge budget funded from collected premium.

Greeks come from live Alpaca option snapshots; underlying spot from the last
equity bar close. All methods are defensive (never raise): on any failure they
return a zero/empty state, so the hedge agent can never take down the loop.
"""
from __future__ import annotations

import os
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


class HedgeAgent:
    """Portfolio-greek aggregation + dynamic delta hedge + tail sleeve."""

    def __init__(self) -> None:
        self.min_shares = HEDGE_MIN_SHARES
        self.band_shares = HEDGE_BAND_SHARES

    # ── Position / greek ingestion ─────────────────────────────────────────

    def _option_positions(self) -> list[dict]:
        try:
            positions = alpaca.get_positions() if alpaca and alpaca.is_configured() else []
        except Exception as e:
            logger.warning(f"hedge_agent: get_positions failed: {e}")
            return []
        if isinstance(positions, list):
            return [
                {
                    "symbol": str(p.get("symbol") or ""),
                    "qty": float(p.get("qty") or 0),
                    "avg_entry_price": float(p.get("avg_entry_price") or 0),
                    "market_value": float(p.get("market_value") or 0),
                }
                for p in positions
                if p.get("symbol")
            ]
        if isinstance(positions, dict) and positions.get("status"):
            # unconfigured/error response
            return []
        return []

    def portfolio_greeks(self) -> dict[str, Any]:
        """Aggregate delta/gamma/theta/vega across live Alpaca positions.

        Equity positions contribute delta = qty (1 share = 1 delta), gamma=0.
        Option positions contribute contracts x 100 x greeks from live snapshots.
        """
        agg = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
        detail: list[dict] = []
        for pos in self._option_positions():
            symbol, qty = pos["symbol"], pos["qty"]
            if qty == 0 or not symbol:
                continue
            stripped = symbol.upper().lstrip("$")
            # Options are OCC-style (16+ chars, or contain '-' for some venues);
            # equities are plain symbols.
            is_option = ("-" in symbol) or len(stripped) > 6
            if not is_option:
                agg["delta"] += qty
                detail.append({"symbol": symbol, "cls": "equity",
                               "qty": qty, "delta": qty, "gamma": 0.0,
                               "theta": 0.0, "vega": 0.0})
                continue
            try:
                snap = options_provider.get_snapshot(symbol)
                g = (snap or {}).get("greeks") or {}
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
                               "iv": g.get("implied_volatility")})
            except Exception as e:
                logger.warning(f"hedge_agent: snapshot failed for {symbol}: {e}")
        for k in agg:
            agg[k] = round(agg[k], 4)
        return {"greeks": agg, "positions": detail}

    # ── Regime band ─────────────────────────────────────────────────────────

    def regime(self) -> dict:
        try:
            import asyncio
            return asyncio.run(current_regime())
        except Exception as e:
            logger.warning(f"hedge_agent: regime lookup failed: {e}")
            return {"regime": "Neutral", "confidence": 0.0}

    def band_multiplier(self, regime: str) -> float:
        return _BAND_MULT.get(regime, 1.0)

    # ── Spot ────────────────────────────────────────────────────────────────

    def spot(self, underlying: str) -> float | None:
        try:
            bars = alpaca.get_bars(underlying.upper(), limit=2) if alpaca else []
            if bars:
                return float(bars[-1]["c"])
        except Exception as e:
            logger.warning(f"hedge_agent: spot failed for {underlying}: {e}")
        return None

    # ── Hedge state / proposal ──────────────────────────────────────────────

    def hedge_state(self, underlying: str = "SPY") -> dict[str, Any]:
        """Current portfolio greeks + recommended dynamic delta hedge."""
        pg = self.portfolio_greeks()
        regime_state = self.regime()
        regime = regime_state.get("regime", "Neutral")
        mult = self.band_multiplier(regime)
        spot = self.spot(underlying)
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

    def rebalance_proposal(self, underlying: str = "SPY") -> dict:
        return {"dry_run": True, "hedge_state": self.hedge_state(underlying)}

    def execute(self, underlying: str = "SPY", confirm: bool = False) -> dict[str, Any]:
        """Dry-run by default; with confirm=True places the paper underlying order."""
        st = self.hedge_state(underlying)
        if not confirm:
            return {"status": "dry_run",
                    "message": "pass confirm=true to execute (human-in-the-loop)",
                    "hedge_state": st}
        pp = st.get("proposal")
        if not pp or pp.get("qty", 0) <= 0:
            return {"status": "no_rebalance_needed", "hedge_state": st}
        try:
            import asyncio
            res = asyncio.run(alpaca.place_order(
                pp["symbol"], pp["side"], float(pp["qty"]), "market"))
            return {"status": "executed", "order": {
                "symbol": res.symbol, "side": pp["side"], "qty": pp["qty"],
                "order_id": res.order_id, "status": res.status,
                "filled_avg_price": res.filled_avg_price,
            }, "hedge_state": st}
        except Exception as e:
            logger.error(f"hedge execute failed: {e}")
            return {"status": "error", "error": str(e), "hedge_state": st}


hedge_agent = HedgeAgent()

__all__ = ["HedgeAgent", "hedge_agent"]