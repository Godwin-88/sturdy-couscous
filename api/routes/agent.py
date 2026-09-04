import asyncio
import json
import logging
import os
from fastapi import APIRouter, HTTPException, Query
import redis
import psycopg2

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


def _redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


def _conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "graphalpha"),
        user=os.getenv("POSTGRES_USER", "graphalpha"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


@router.get("/status")
def agent_status():
    r = _redis()
    raw = r.get("graphalpha:agent_status")
    if raw:
        return json.loads(raw)
    return {
        "regime":            "LowVolatility",
        "regime_confidence": 0.65,
        "active_strategies": [],
        "signals_generated": 0,
        "orders_approved":   0,
        "last_cycle_at":     None,
        "halted":            False,
        "cycle_duration_s":  0.0,
    }


@router.get("/risk")
def agent_risk():
    """
    Returns pre-trade risk metrics: position concentration, gross/net exposure,
    drawdown vs limit, and Kelly fraction vs actual sizing.

    NAV is sourced from the live Alpaca paper account (authoritative broker
    equity) so the chat assistant never sees a phantom "discrepancy" between
    the risk engine and the brokerage. Falls back to the local
    ``portfolio_state`` table when Alpaca is unconfigured, and finally to
    ``INITIAL_CAPITAL_USD`` if both sources are missing.
    """
    r = _redis()
    raw_status = r.get("graphalpha:agent_status")
    status = json.loads(raw_status) if raw_status else {}

    # Pull positions and portfolio from Postgres
    positions = []
    portfolio = {"nav": 10000, "cash": 10000, "drawdown_pct": 0.0, "halted": False}
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ticker, direction, quantity, avg_entry_price, current_price,
                           quantity * (current_price - avg_entry_price) AS unrealised_pnl
                    FROM positions WHERE status = 'open'
                """)
                cols = ["ticker", "direction", "quantity", "avg_entry_price",
                         "current_price", "unrealised_pnl"]
                positions = [
                    {k: (float(v) if k not in ("ticker", "direction") else v)
                     for k, v in zip(cols, row)}
                    for row in cur.fetchall()
                ]

                cur.execute("""
                    SELECT cash_balance, nav, drawdown_pct, halted
                    FROM portfolio_state ORDER BY id DESC LIMIT 1
                """)
                row = cur.fetchone()
                if row:
                    portfolio = {"cash": float(row[0]), "nav": float(row[1]),
                                 "drawdown_pct": float(row[2]), "halted": row[3]}
    except Exception:
        pass

    # Authoritative NAV = live Alpaca account equity when configured. This
    # eliminates the "Risk Engine vs Brokerage discrepancy" that previously
    # showed up in every chat response on the dashboard. The Alpaca client is
    # async, so we run it in a one-shot event loop (the risk endpoint itself
    # is sync and called from the FastAPI threadpool).
    nav_source = "initial_capital"
    nav = portfolio.get("nav") or float(os.getenv("INITIAL_CAPITAL_USD", "10000"))
    broker_positions: list[dict] = []
    cash = portfolio.get("cash", 0)
    try:
        from agent.alpaca_client import alpaca
        import asyncio
        if alpaca is not None and alpaca.is_configured():
            try:
                loop = asyncio.new_event_loop()
                try:
                    acct = loop.run_until_complete(alpaca.get_account())
                    broker_positions = loop.run_until_complete(alpaca.get_positions())
                finally:
                    loop.close()
            except RuntimeError:
                # Already inside a running loop (e.g. when called from
                # another async route). Skip the live read; nav_source stays
                # at "initial_capital" rather than blocking the response.
                acct = None
            if isinstance(acct, dict):
                equity = float(acct.get("equity") or 0)
                if equity > 0:
                    nav = equity
                    cash = float(acct.get("cash") or 0)
                    nav_source = "alpaca"
                    portfolio["cash"] = cash
                    portfolio["nav"] = nav
    except Exception:
        pass

    # Concentration: % NAV per ticker
    concentration = []
    gross_exposure = 0.0
    net_exposure = 0.0
    option_book = []
    # Internal (Postgres) positions first — format as broker-style rows.
    internal_positions = [
        {
            "symbol": p["ticker"],
            "qty": float(p["quantity"]) * (1 if p["direction"] == "buy" else -1),
            "avg_entry_price": float(p["avg_entry_price"]),
            "current_price": float(p["current_price"]),
            "market_value": abs(float(p["quantity"]) * float(p["current_price"])),
            "side": p["direction"],
            "unrealised_pnl": float(p.get("unrealised_pnl") or 0),
        }
        for p in positions
    ]
    all_positions = internal_positions + [
        {
            "symbol": p.get("symbol"),
            "qty": float(p.get("qty") or 0),
            "avg_entry_price": float(p.get("avg_entry_price") or 0),
            "current_price": float(p.get("current_price") or 0),
            "market_value": abs(float(p.get("market_value") or 0)),
            "side": "buy" if float(p.get("qty") or 0) >= 0 else "sell",
            "unrealised_pnl": 0.0,
        }
        for p in broker_positions or []
        if p.get("symbol")
    ]
    # Dedup by symbol (broker truth wins over the internal ledger).
    _by_symbol: dict[str, dict] = {}
    for p in all_positions:
        _by_symbol[p["symbol"]] = p
    merged_positions = list(_by_symbol.values())

    try:
        from agent.risk_book import build_risk_metrics, _dte
        metrics = build_risk_metrics(merged_positions, nav)
        gross_exposure = metrics["gross_exposure"]
        net_exposure = metrics["net_exposure"]
        concentration = metrics["concentration"]
        option_book = metrics["option_book"]
        n_broker_positions = metrics["n_positions"]
        # surface the option book into the response for the chat/dashboard
        for leg in option_book:
            if leg.get("expiry") and leg.get("underlying"):
                leg["dte"] = _dte(leg.get("expiry"))
        # legacy fields from internal rows for P&L
        for c in concentration:
            sym = c["ticker"]
            if sym in _by_symbol:
                c["pnl"] = round(float(_by_symbol[sym].get("unrealised_pnl") or 0), 2)
    except Exception:
        # fall back to old internal-only aggregation (hermetic tests)
        for p in positions:
            mkt_val = abs(p["quantity"] * p["current_price"])
            pct_nav = mkt_val / nav if nav else 0
            sign = 1 if p["direction"] == "buy" else -1
            gross_exposure += mkt_val
            net_exposure += sign * mkt_val
            concentration.append({
                "ticker":   p["ticker"],
                "mkt_val":  round(mkt_val, 2),
                "pct_nav":  round(pct_nav, 4),
                "direction": p["direction"],
                "pnl":      round(p["unrealised_pnl"], 2),
            })
        concentration.sort(key=lambda x: x["pct_nav"], reverse=True)
        option_book = []

    # Drawdown limit (configurable via env, default 10%)
    dd_limit = float(os.getenv("DRAWDOWN_LIMIT", "0.10"))
    dd_current = portfolio.get("drawdown_pct", 0.0) or 0.0
    dd_remaining = max(0.0, dd_limit - dd_current)

    # Kelly criterion estimate from recent signals win rate
    kelly_fraction = None
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT AVG(CASE WHEN signal_score > 0 THEN 1.0 ELSE 0.0 END) AS win_rate,
                           AVG(ABS(signal_score)) AS avg_score
                    FROM order_audit
                    WHERE created_at > NOW() - INTERVAL '7 days'
                """)
                row = cur.fetchone()
                if row and row[0] is not None:
                    win_rate = float(row[0])
                    avg_score = float(row[1]) if row[1] else 1.0
                    # Simplified Kelly: f* = (bp - q) / b  where b=avg_score, p=win_rate, q=1-win_rate
                    b = avg_score
                    p = win_rate
                    q = 1 - win_rate
                    kelly_fraction = round(max(0.0, (b * p - q) / b), 4) if b > 0 else 0.0
    except Exception:
        pass

    return {
        "nav":              round(nav, 2),
        "nav_source":       nav_source,
        "gross_exposure":   round(gross_exposure, 2),
        "net_exposure":     round(net_exposure, 2),
        "gross_pct_nav":    round(gross_exposure / nav, 4) if nav else 0,
        "net_pct_nav":      round(net_exposure / nav, 4) if nav else 0,
        "drawdown_current": round(dd_current, 4),
        "drawdown_limit":   round(dd_limit, 4),
        "drawdown_remaining": round(dd_remaining, 4),
        "kelly_fraction":   kelly_fraction,
        "concentration":    concentration,
        "n_positions":      len(merged_positions) if 'merged_positions' in dir() else len(positions),
        "halted":           portfolio.get("halted", False),
        "option_book":      option_book,
        "exposure_source":  "broker_book" if broker_positions else "internal_ledger",
    }


# ── Regime override (UI-driven scenario planning) ──────────────────────────
#
# The dashboard's Market Regime card lets the user pick a regime from a
# dropdown; the consequence is that the live data points on the card
# (SPY-benchmarked option suggestions, eligible strategies, regime
# confidence) recompute under the *chosen* regime — i.e. a "what if the
# market were Trending right now?" view. The agent's real running regime
# (RegimeAgent) is NOT modified by this; the override is UI-only and
# in-memory for the duration of the session, stored in Redis so the FE
# can re-render consistently across polls.

import json as _json


_VALID_REGIMES = {"Trending", "MeanReverting", "LowVolatility", "HighVolatility",
                  "Recovery", "Crisis", "SystemicStress", "Neutral"}


def _regime_override_get() -> str | None:
    """Read the current regime override from Redis (or None if unset)."""
    try:
        r = _redis()
        return r.get("graphalpha:regime_override") or None
    except Exception:
        return None


@router.get("/regime-override")
def get_regime_override():
    """Returns the active UI regime override, or empty string if none."""
    return {"override": _regime_override_get() or ""}


@router.post("/regime-override")
def set_regime_override(regime: str = Query("", description="Regime label, or empty to clear")):
    """Set or clear the dashboard's regime override (UI-only, no agent impact).

    Empty string (or "auto") clears the override so the card reverts to
    the live RegimeAgent output. The value is stored in Redis under
    ``graphalpha:regime_override`` and read by ``/agent/regime-bench``
    and ``/options/suggestions`` callers that pass ``regime=override``.
    """
    regime = (regime or "").strip()
    if regime and regime not in _VALID_REGIMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown regime '{regime}'. Valid: {sorted(_VALID_REGIMES)}",
        )
    try:
        r = _redis()
        if regime:
            r.set("graphalpha:regime_override", regime)
        else:
            r.delete("graphalpha:regime_override")
    except Exception as e:
        logger.warning(f"regime-override redis set failed: {e}")
    return {"override": regime or ""}


@router.get("/regime-bench")
def regime_bench(regime: str = Query("", description="Override regime; empty = live"),
                 strategy: str = Query("", description="Optional strategy filter"),
                 underlying: str = Query("SPY", description="Benchmark underlying"),
                 contract_type: str = Query("", description="call|put|empty=auto"),
                 lens: str = Query("defensive")):
    """SPY-benchmarked scenario view: regime strategies + top SPY option card.

    Returns a single payload containing:
      * live SPY spot + 1d/5d price action
      * eligible strategies for the (override) regime
      * the top-ranked SPY option suggestion (option-signal engine output)
      * the regime name, confidence, and whether it's an override

    The dashboard card renders this as one cohesive panel.
    """
    _require_alpaca = None  # sentinel; we use the same gate as /options/suggestions
    # Use the same alpaca gate as options route
    try:
        from agent.alpaca_client import alpaca as _alpaca
        if not _alpaca.is_configured():
            raise HTTPException(status_code=503, detail="Alpaca not configured")
    except ImportError:
        raise HTTPException(status_code=503, detail="Alpaca client unavailable")

    effective_regime = (regime or "").strip() or _regime_override_get() or ""
    is_override = bool(effective_regime)

    # 1) SPY spot + 1d/5d
    spot_info = {"spot": None, "d1": None, "d5": None, "d1_pct": None, "d5_pct": None}
    try:
        from agent.alpaca_data import provider
        df = provider.get_ohlcv(underlying, days=10)
        if df is not None and not df.empty:
            last = float(df["Close"].iloc[-1])
            prev1 = float(df["Close"].iloc[-2]) if len(df) > 1 else last
            prev5 = float(df["Close"].iloc[-5]) if len(df) >= 5 else last
            spot_info = {
                "spot": round(last, 2),
                "d1":   round(last - prev1, 2),
                "d5":   round(last - prev5, 2),
                "d1_pct": round((last / prev1 - 1) * 100, 2) if prev1 else 0,
                "d5_pct": round((last / prev5 - 1) * 100, 2) if prev5 else 0,
            }
    except Exception as e:
        logger.warning(f"regime-bench spot fetch failed: {e}")

    # 2) Live regime (when no override)
    live_regime = ""
    live_confidence = 0.0
    if not is_override:
        try:
            from agent.regime_agent import RegimeAgent
            agent_obj = RegimeAgent()
            try:
                loop = asyncio.new_event_loop()
                try:
                    rs = loop.run_until_complete(agent_obj.run())
                finally:
                    loop.close()
            except RuntimeError:
                rs = None
            if isinstance(rs, dict):
                live_regime = rs.get("regime", "")
                live_confidence = float(rs.get("confidence", 0.0))
        except Exception:
            pass

    # 3) Eligible strategies for the *effective* regime
    eligible: list[dict] = []
    try:
        from agent.regime_agent import RegimeAgent
        eligible = RegimeAgent()._query_active_strategies(effective_regime or live_regime or "Neutral")
        # Normalize to {name, description}
        eligible = [
            {"name": s.get("name"), "description": s.get("description", "")}
            if isinstance(s, dict) else {"name": str(s), "description": ""}
            for s in (eligible or [])
        ]
    except Exception:
        try:
            from common.graph import get_db
            db = get_db()
            cypher = (
                "MATCH (r:Regime {name:$r})-[:ACTIVATES]->(s:Strategy) "
                "RETURN s.name AS name, s.description AS description "
                "ORDER BY s.name"
            )
            rows = list(db.execute_and_fetch(cypher, {"r": effective_regime or "Neutral"}))
            eligible = [{"name": r["name"], "description": r.get("description") or ""} for r in rows]
        except Exception as e:
            logger.warning(f"eligible strategies fallback failed: {e}")

    # 4) Top SPY option suggestion (filtered by strategy if supplied)
    top_suggestion = None
    rejected_summary: list[dict] = []
    try:
        from agent.option_signal import compute_suggestions
        out = compute_suggestions(
            underlying=underlying,
            expiration=None,
            contract_type=(contract_type or None),
            regime=effective_regime or None,
            lens=lens,
            nav=spot_info.get("spot") and None,  # let server use default NAV
        )
        suggs = out.get("suggestions", [])
        if strategy:
            suggs = [s for s in suggs if s.get("strategy", "").lower() == strategy.lower()]
        top_suggestion = suggs[0] if suggs else None
        rejected_summary = out.get("rejected", [])[:3]
    except Exception as e:
        logger.warning(f"regime-bench suggestion failed: {e}")

    return {
        "underlying":       underlying,
        "spot":             spot_info,
        "regime":           effective_regime or live_regime or "Neutral",
        "confidence":       live_confidence if not is_override else 1.0,
        "is_override":      is_override,
        "live_regime":      live_regime,
        "live_confidence":  live_confidence,
        "eligible":         eligible,
        "eligible_count":   len(eligible),
        "top_suggestion":   top_suggestion,
        "rejected":         rejected_summary,
    }
