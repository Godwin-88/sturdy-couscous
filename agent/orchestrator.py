"""
GraphAlpha Orchestrator
Runs the main agent loop: every AGENT_LOOP_INTERVAL_SECONDS it
coordinates all sub-agents and enforces hard risk limits.

Signal sources per cycle:
  1. RegimeAgent    — market regime classification
  2. SignalAgent    — price/vol-based technical signals
  3. NewsAgent      — RSS sentiment → ticker & concept scores
  4. MacroCalendar  — upcoming events → pre-event size modifiers
  5. KGSignalGen    — KG Formula node evaluation
  6. RiskAgent      — validates and sizes approved orders
  7. ExecutionAgent — submits approved orders (paper or live)
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime

import redis.asyncio as aioredis
from dotenv import load_dotenv
from loguru import logger
from prometheus_client import Counter, Gauge, start_http_server

from regime_agent import RegimeAgent
from signal_agent import SignalAgent
from risk_agent import RiskAgent
from execution_agent import ExecutionAgent
from research_agent import ResearchAgent
from news_agent import NewsAgent
from macro_calendar import MacroCalendarAgent
from kg_signal_generator import KGSignalGenerator
from common.schema_validator import validate_signal
from common.versioning import validate_schema_version
from common.redis_publisher import publish_signal_batch, publish_heartbeat

load_dotenv()

# ── Metrics ───────────────────────────────────────────────────────────────────
LOOP_COUNTER    = Counter("agent_loop_total", "Number of completed agent loops")
SIGNAL_GAUGE    = Gauge("active_signals", "Number of active signals this cycle")
PNL_GAUGE       = Gauge("portfolio_pnl_usd", "Current unrealised PnL in USD")
DRAWDOWN_GAUGE  = Gauge("portfolio_drawdown_pct", "Current drawdown from peak")

# ── Config ────────────────────────────────────────────────────────────────────
LOOP_INTERVAL   = int(os.getenv("AGENT_LOOP_INTERVAL_SECONDS", 300))
MAX_DRAWDOWN    = float(os.getenv("AGENT_MAX_DRAWDOWN_HALT", 0.10))
TRADING_MODE    = os.getenv("KRAKEN_TRADING_MODE", "paper")

# How often to run each slower sub-cycle (in main loop ticks)
NEWS_EVERY      = int(os.getenv("NEWS_CYCLE_TICKS", 1))       # every tick (~5 min)
MACRO_EVERY     = int(os.getenv("MACRO_CYCLE_TICKS", 12))     # every ~1 hour
RESEARCH_EVERY  = int(os.getenv("RESEARCH_CYCLE_TICKS", 12))  # every ~1 hour

# Tickers that KGSignalGenerator evaluates formulas against
KG_SIGNAL_TICKERS = os.getenv(
    "KG_SIGNAL_TICKERS", "SPY,QQQ,TLT,GLD,BTC-USD"
).split(",")


class Orchestrator:
    def __init__(self):
        self.regime_agent    = RegimeAgent()
        self.signal_agent    = SignalAgent()
        self.risk_agent      = RiskAgent()
        self.execution_agent = ExecutionAgent(mode=TRADING_MODE)
        self.research_agent  = ResearchAgent()
        self.news_agent      = NewsAgent()
        self.macro_agent     = MacroCalendarAgent()
        self.kg_signals      = KGSignalGenerator()
        self.portfolio_peak  = 0.0
        self.halted          = False
        self._tick           = 0

    async def run_cycle(self) -> dict:
        """One full agent cycle. Returns a structured audit record."""
        cycle_start = time.time()
        self._tick += 1
        audit = {"timestamp": datetime.utcnow().isoformat(), "steps": [], "tick": self._tick}

        try:
            # ── Step 1: Regime classification ─────────────────────────────────
            regime_result = await self.regime_agent.run()
            regime        = regime_result["regime"]
            audit["regime"]            = regime
            audit["regime_confidence"] = regime_result["confidence"]
            audit["steps"].append({"agent": "RegimeAgent", "status": "ok",
                                   "result": regime_result})
            logger.info(f"Regime: {regime} (confidence={regime_result['confidence']:.2f})")

            # ── Step 2a: News sentiment ────────────────────────────────────────
            news_result: dict = {}
            if self._tick % NEWS_EVERY == 0:
                try:
                    news_result = await self.news_agent.run(max_articles=40)
                    await self._cache_news(news_result)
                    audit["steps"].append({"agent": "NewsAgent", "status": "ok",
                                           "articles": news_result.get("articles", 0)})
                    logger.info(f"NewsAgent: {news_result.get('articles', 0)} articles")
                except Exception as e:
                    logger.warning(f"NewsAgent failed: {e}")

            # ── Step 2b: Macro calendar (slower cycle) ─────────────────────────
            macro_result: dict = {}
            if self._tick % MACRO_EVERY == 0:
                try:
                    macro_result = await self.macro_agent.run(lookahead_days=7)
                    await self._cache_macro(macro_result)
                    audit["steps"].append({"agent": "MacroCalendarAgent", "status": "ok",
                                           "events": macro_result.get("events", 0)})
                    logger.info(f"MacroCalendarAgent: {macro_result.get('events', 0)} events ahead")
                except Exception as e:
                    logger.warning(f"MacroCalendarAgent failed: {e}")

            # ── Step 2c: KG Formula signals ────────────────────────────────────
            kg_signals: list[dict] = []
            try:
                kg_signals = await self.kg_signals.run(
                    regime=regime, tickers=KG_SIGNAL_TICKERS
                )
                audit["steps"].append({"agent": "KGSignalGenerator", "status": "ok",
                                       "signals": len(kg_signals)})
            except Exception as e:
                logger.warning(f"KGSignalGenerator failed: {e}")

            # ── Step 3: Price/vol signal generation ───────────────────────────
            cycle_id = str(uuid.uuid4())
            timestamp = datetime.utcnow().isoformat()
            signals = await self.signal_agent.run(
                regime=regime,
                active_strategies=regime_result["active_strategies"]
            )

            # Merge KG formula signals into the main signal list
            signals = signals + kg_signals

            # Schema v1 injection: stamp every signal with canonical fields
            signals = self._inject_schema_v1(signals, cycle_id, timestamp)

            # Apply news sentiment boost/penalty to overlapping tickers
            if news_result.get("ticker_sentiment"):
                signals = self._apply_news_overlay(signals, news_result["ticker_sentiment"])

            # Apply pre-event size reduction if macro event is imminent
            if macro_result.get("pre_event_signals"):
                signals = self._apply_macro_overlay(signals, macro_result["pre_event_signals"])

            # Schema v1 injection (final): stamp canonical fields before RiskAgent
            signals = self._inject_schema_v1(signals, cycle_id, timestamp)

            audit["signals"] = signals
            audit["steps"].append({"agent": "SignalAgent", "status": "ok",
                                   "signal_count": len(signals)})
            SIGNAL_GAUGE.set(len(signals))
            logger.info(f"Total signals this cycle: {len(signals)}")

            # Cache signals for the API WebSocket
            await self._cache_signals(signals)

            # ── Step 4: Risk validation ────────────────────────────────────────
            approved_orders = await self.risk_agent.run(signals=signals, cycle_id=cycle_id)
            audit["approved_orders"] = approved_orders
            audit["steps"].append({"agent": "RiskAgent", "status": "ok",
                                   "approved": len(approved_orders),
                                   "rejected": len(signals) - len(approved_orders)})
            logger.info(f"Risk: {len(approved_orders)}/{len(signals)} signals approved")

            # Persist cycle status for the /agent/status API endpoint
            await self._write_status(
                regime_result, signals, approved_orders,
                time.time() - cycle_start
            )

            # Publish validated signals to C++ risk engine (fire-and-forget)
            asyncio.create_task(self._publish_signals(signals, cycle_id))

            # Publish heartbeat so ops can distinguish quiet cycles from stalls
            asyncio.create_task(publish_heartbeat(
                cycle_id,
                f"cycle_complete:{len(signals)}_signals:{len(approved_orders)}_orders"
            ))

            # ── Step 5: Execution ──────────────────────────────────────────────
            if not self.halted and approved_orders:
                executed = await self.execution_agent.run(orders=approved_orders)
                audit["executed"] = executed
                audit["steps"].append({"agent": "ExecutionAgent", "status": "ok",
                                       "executed_count": len(executed)})
                logger.info(f"Executed {len(executed)} orders [{TRADING_MODE} mode]")
            else:
                audit["executed"] = []
                if self.halted:
                    logger.warning("Agent HALTED — drawdown limit exceeded")

            # ── Step 6: Circuit breaker check ─────────────────────────────────
            portfolio = await self.risk_agent.get_portfolio_state()
            pnl       = portfolio.get("unrealised_pnl_usd", 0.0)
            PNL_GAUGE.set(pnl)

            if portfolio["nav"] > self.portfolio_peak:
                self.portfolio_peak = portfolio["nav"]
            drawdown = (self.portfolio_peak - portfolio["nav"]) / max(self.portfolio_peak, 1)
            DRAWDOWN_GAUGE.set(drawdown)

            if drawdown > MAX_DRAWDOWN and not self.halted:
                self.halted = True
                logger.critical(f"HALT: drawdown {drawdown:.1%} > {MAX_DRAWDOWN:.1%} limit")
                await self._notify_halt(drawdown)

        except Exception as e:
            logger.exception(f"Cycle error: {e}")
            audit["error"] = str(e)

        audit["cycle_duration_s"] = round(time.time() - cycle_start, 2)
        LOOP_COUNTER.inc()
        return audit

    def _inject_schema_v1(self, signals, cycle_id, timestamp):
        from backtest.universe import lookup as _lookup
        from common.versioning import validate_schema_version
        validate_schema_version(1)
        out = []
        for sig in signals:
            ticker = sig.get("ticker", "")
            try:
                u = _lookup(ticker)
            except KeyError:
                continue
            payload = {
                "schema_version": 1,
                "cycle_id": cycle_id,
                "timestamp": timestamp,
                "regime": sig.get("regime", ""),
                "strategy": sig.get("strategy", ""),
                "ticker": ticker,
                "venue": u.venue,
                "venue_symbol": u.venue_symbol,
                "asset_class": u.asset_class,
                "direction": sig.get("direction", "hold"),
                "score": float(sig.get("score", 0.0)),
                "quant_score": float(sig.get("quant_score", 0.0)),
                "sentiment_score": float(sig.get("sentiment_score", 0.0)),
                "news_overlay": float(sig.get("news_sentiment", sig.get("news_overlay", 0.0))),
                "macro_overlay": float(sig.get("macro_reduction", sig.get("macro_overlay", 0.0))),
                "kg_formula_contribution": float(sig.get("kg_formula_contribution", 0.0)),
                "graph_path": sig.get("graph_path", []),
                "contradiction_blocked": bool(sig.get("contradiction_blocked", False)),
            }
            try:
                validate_signal(payload)
            except ValueError:
                payload["score"] = 0.0
                payload["direction"] = "hold"
                payload["contradiction_blocked"] = True
            out.append(payload)
        return out


    # ── Signal overlay helpers ─────────────────────────────────────────────────

    def _apply_news_overlay(
        self, signals: list[dict], ticker_sentiment: dict[str, float]
    ) -> list[dict]:
        """Boost or penalise signal scores based on news sentiment alignment."""
        out = []
        for sig in signals:
            tk   = sig.get("ticker", "")
            sent = ticker_sentiment.get(tk, 0.0)
            if sent == 0.0:
                out.append(sig)
                continue
            direction_sign = 1 if sig.get("direction") == "long" else -1
            # Aligned sentiment amplifies; opposing sentiment dampens
            alignment = sent * direction_sign
            boost     = round(alignment * 0.20, 3)   # up to ±20% adjustment
            new_sig   = dict(sig)
            new_sig["signal_score"] = round(
                max(-1.0, min(1.0, sig.get("signal_score", 0.0) + boost)), 3
            )
            new_sig["news_sentiment"] = round(sent, 3)
            out.append(new_sig)
        return out

    def _apply_macro_overlay(
        self, signals: list[dict], pre_event_signals: dict[str, float]
    ) -> list[dict]:
        """Reduce position sizing for signals exposed to imminent macro events."""
        if not pre_event_signals:
            return signals
        # Take most restrictive modifier across all pre-event concepts
        max_reduction = min(pre_event_signals.values())   # most negative value
        if max_reduction >= 0:
            return signals
        out = []
        for sig in signals:
            new_sig = dict(sig)
            new_sig["signal_score"] = round(
                sig.get("signal_score", 0.0) * (1 + max_reduction), 3
            )
            new_sig["macro_reduction"] = round(max_reduction, 3)
            out.append(new_sig)
        logger.info(f"MacroOverlay: applied {max_reduction:.0%} size reduction")
        return out

    # ── Background cycles ──────────────────────────────────────────────────────

    async def run_research_cycle(self):
        try:
            result = await self.research_agent.run()
            logger.info(f"Research cycle: {result.get('nodes_added', 0)} new nodes, "
                        f"{result.get('edges_added', 0)} new edges")
        except Exception as e:
            logger.exception(f"Research cycle error: {e}")

    # ── Redis helpers ──────────────────────────────────────────────────────────

    def _redis_url(self) -> str:
        return (f"redis://{os.getenv('REDIS_HOST', 'redis')}:"
                f"{os.getenv('REDIS_PORT', 6379)}")

    async def _publish_signals(self, signals: list[dict], cycle_id: str) -> None:
        published = await publish_signal_batch(signals)
        logger.debug(f"Redis publish: {published}/{len(signals)} signals written to "
                     f"{os.getenv('REDIS_SIGNALS_CHANNEL', 'graphalpha:signals:v1')}")

    async def _write_status(self, regime_result: dict, signals: list,
                             approved: list, duration: float, cycle_id: str = ""):
        r = aioredis.from_url(self._redis_url())
        status = {
            "regime":            regime_result["regime"],
            "regime_confidence": regime_result["confidence"],
            "active_strategies": [s["name"] if isinstance(s, dict) else str(s)
                                  for s in regime_result.get("active_strategies", [])],
            "signals_generated": len(signals),
            "orders_approved":   len(approved),
            "last_cycle_at":     datetime.utcnow().isoformat(),
            "halted":            self.halted,
            "cycle_duration_s":  round(duration, 2),
        }
        await r.set("graphalpha:agent_status", json.dumps(status), ex=3600)
        await r.aclose()

    async def _cache_signals(self, signals: list):
        r = aioredis.from_url(self._redis_url())
        await r.set("graphalpha:latest_signals", json.dumps(signals), ex=600)
        await r.publish("graphalpha:events", json.dumps({
            "event":     "signals_updated",
            "count":     len(signals),
            "timestamp": datetime.utcnow().isoformat(),
        }))
        await r.aclose()

    async def _cache_news(self, news_result: dict):
        r = aioredis.from_url(self._redis_url())
        await r.set("graphalpha:news_latest", json.dumps(news_result), ex=1800)
        await r.publish("graphalpha:events", json.dumps({
            "event":     "news_updated",
            "articles":  news_result.get("articles", 0),
            "timestamp": datetime.utcnow().isoformat(),
        }))
        await r.aclose()

    async def _cache_macro(self, macro_result: dict):
        r = aioredis.from_url(self._redis_url())
        await r.set("graphalpha:macro_calendar", json.dumps(macro_result), ex=3600)
        await r.aclose()

    async def _notify_halt(self, drawdown: float):
        r = aioredis.from_url(self._redis_url())
        await r.publish("graphalpha:events", f"HALT:drawdown={drawdown:.3f}")
        await r.aclose()

    async def main_loop(self):
        logger.info(f"Orchestrator starting | mode={TRADING_MODE} | "
                    f"interval={LOOP_INTERVAL}s | max_dd={MAX_DRAWDOWN:.0%}")
        start_http_server(8001)  # Prometheus metrics endpoint

        while True:
            await self.run_cycle()

            if self._tick % RESEARCH_EVERY == 0:
                await self.run_research_cycle()

            await asyncio.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    asyncio.run(Orchestrator().main_loop())
