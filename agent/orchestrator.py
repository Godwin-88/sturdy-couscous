"""
GraphAlpha Orchestrator
Runs the main agent loop: every AGENT_LOOP_INTERVAL_SECONDS it
coordinates all 5 sub-agents and enforces hard risk limits.
"""

import asyncio
import os
import time
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


class Orchestrator:
    def __init__(self):
        self.regime_agent    = RegimeAgent()
        self.signal_agent    = SignalAgent()
        self.risk_agent      = RiskAgent()
        self.execution_agent = ExecutionAgent(mode=TRADING_MODE)
        self.research_agent  = ResearchAgent()
        self.portfolio_peak  = 0.0
        self.halted          = False

    async def run_cycle(self) -> dict:
        """One full agent cycle. Returns a structured audit record."""
        cycle_start = time.time()
        audit = {"timestamp": datetime.utcnow().isoformat(), "steps": []}

        try:
            # ── Step 1: Regime classification ─────────────────────────────────
            regime_result = await self.regime_agent.run()
            audit["regime"] = regime_result["regime"]
            audit["regime_confidence"] = regime_result["confidence"]
            audit["steps"].append({"agent": "RegimeAgent", "status": "ok",
                                   "result": regime_result})
            logger.info(f"Regime: {regime_result['regime']} "
                        f"(confidence={regime_result['confidence']:.2f})")

            # ── Step 2: Signal generation ──────────────────────────────────────
            signals = await self.signal_agent.run(
                regime=regime_result["regime"],
                active_strategies=regime_result["active_strategies"]
            )
            audit["signals"] = signals
            audit["steps"].append({"agent": "SignalAgent", "status": "ok",
                                   "signal_count": len(signals)})
            SIGNAL_GAUGE.set(len(signals))
            logger.info(f"Generated {len(signals)} signals")

            # Cache signals for the API WebSocket
            await self._cache_signals(signals)

            # ── Step 3: Risk validation ────────────────────────────────────────
            approved_orders = await self.risk_agent.run(signals=signals)
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

            # ── Step 4: Execution ──────────────────────────────────────────────
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

            # ── Step 5: Circuit breaker check ─────────────────────────────────
            portfolio = await self.risk_agent.get_portfolio_state()
            pnl = portfolio.get("unrealised_pnl_usd", 0.0)
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

    async def run_research_cycle(self):
        """Runs less frequently — enriches the knowledge graph."""
        try:
            result = await self.research_agent.run()
            logger.info(f"Research cycle: {result.get('nodes_added', 0)} new nodes, "
                        f"{result.get('edges_added', 0)} new edges")
        except Exception as e:
            logger.exception(f"Research cycle error: {e}")

    async def _write_status(self, regime_result: dict, signals: list,
                             approved: list, duration: float):
        import json
        r = aioredis.from_url(
            f"redis://{os.getenv('REDIS_HOST', 'redis')}:"
            f"{os.getenv('REDIS_PORT', 6379)}"
        )
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
        import json
        r = aioredis.from_url(
            f"redis://{os.getenv('REDIS_HOST', 'redis')}:"
            f"{os.getenv('REDIS_PORT', 6379)}"
        )
        await r.set("graphalpha:latest_signals", json.dumps(signals), ex=600)
        await r.publish("graphalpha:events", json.dumps({
            "event": "signals_updated",
            "count": len(signals),
            "timestamp": datetime.utcnow().isoformat(),
        }))
        await r.aclose()

    async def _notify_halt(self, drawdown: float):
        """Publish halt event to Redis so the API can alert the frontend."""
        r = aioredis.from_url(
            f"redis://{os.getenv('REDIS_HOST', 'redis')}:"
            f"{os.getenv('REDIS_PORT', 6379)}"
        )
        await r.publish("graphalpha:events", f"HALT:drawdown={drawdown:.3f}")
        await r.aclose()

    async def main_loop(self):
        logger.info(f"Orchestrator starting | mode={TRADING_MODE} | "
                    f"interval={LOOP_INTERVAL}s | max_dd={MAX_DRAWDOWN:.0%}")
        start_http_server(8001)  # Prometheus metrics endpoint

        research_counter = 0
        while True:
            await self.run_cycle()

            # Run research agent every 12 trading cycles (~1 hour)
            research_counter += 1
            if research_counter % 12 == 0:
                await self.run_research_cycle()

            await asyncio.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    asyncio.run(Orchestrator().main_loop())
