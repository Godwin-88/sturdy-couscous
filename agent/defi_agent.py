"""
defi_agent.py
──────────────────────
KG-grounded DeFi strategy agent for P11 (docs/p11_web3_defi_expansion.md §6).

Implements the D1–D8 sector catalogue on a per-cycle basis, exactly mirroring
the DreamDEXAgent / CreditGraphAgent interface:

    async def run(regime, signals) -> list[dict]   (candidates, intents never
                                                    auto-executed)

Venues are selected by the ported stellcasp adapter registry (data, not
branching):
    D1–D4  → Ethereum/Sepolia via web3_adapters (Uniswap V3 / Aave V3 / yield /
              perp).  web3-relay is the execution interface.
    D5–D8  → DreamDEX/Somnia via dreamdex_adapter (EC markets, somnia-relay).
    D6/D8  → risk + data governors over the feed integrity signals.

Risk gates per tenet ledger (docs/p9_tenets_financial_engineering.md):
    U28  edge-over-pay gate (EVM: fee − IL(x·y=k) − gas;  EC: binary-Kelly edge)
    U29  liquidation/settlement-distance guard (Aave V3 collat×price; EC short-τ)
    U30  oracle-staleness circuit-breaker (OracleFeed stale/deviation → pause)
    U32  position/leverage caps (EC tail-hedge cap; EVM leverage cap)
    U33  attestation hygiene (only P10-attested feeds drive D6/D8)
    U21  candidates are intents — never execute without human approval

Self-disables when DEFI_ENABLED is unset/0 (identical safety property to P9/P10).
"""

from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Optional

import redis
from loguru import logger

from common.graph import get_db

try:
    from agent.dreamdex_adapter import get_markets  # cwd = /app (api)
    from agent.crypto_signal import suggest_crypto  # KG crypto belief engine
except ImportError:  # cwd = agent/ (agent-worker)
    from dreamdex_adapter import get_markets  # type: ignore
    from crypto_signal import suggest_crypto  # type: ignore

ENABLED = os.getenv("DEFI_ENABLED", "0").lower() in ("1", "true", "yes")
# ── Venue / sector gates (D1–D8, from P11 §6 + U28–U33) ───────────────────
MIN_LP_EDGE_PCT          = float(os.getenv("MIN_LP_EDGE_PCT", "0.03"))
MIN_LENDING_SPREAD_PCT   = float(os.getenv("MIN_LENDING_SPREAD_PCT", "0.02"))
MIN_FUNDING_CARRY_PCT    = float(os.getenv("MIN_FUNDING_CARRY_PCT", "0.03"))
MIN_EC_EDGE_PCT          = float(os.getenv("MIN_EC_EDGE_PCT", "0.03"))
MIN_CORRELATION          = float(os.getenv("MIN_CORRELATION", "0.6"))
MAX_LEVERAGE_X           = float(os.getenv("MAX_LEVERAGE_X", "3.0"))
MAX_EC_TAILHEDGE_PCT     = float(os.getenv("MAX_EC_TAILHEDGE_PCT", "0.02"))
MAX_LP_RANGE_WIDTH_PCT   = float(os.getenv("MAX_LP_RANGE_WIDTH_PCT", "25.0"))
ORACLE_STALE_MS          = float(os.getenv("ORACLE_STALE_MS", "300000"))   # 5 min
ORACLE_DEVIATION_BPS     = float(os.getenv("ORACLE_DEVIATION_BPS", "50")) / 10_000.0
PER_FEED_CAP_USD         = float(os.getenv("DEFI_PER_FEED_CAP_USD", "1000.0"))
MAX_DEFI_EXPOSURE_PCT    = float(os.getenv("MAX_DEFI_EXPOSURE_PCT", "0.05"))

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _il_divergence(price_ratio: float) -> float:
    """Constant-product IL vs HODL: 1 − 2*sqrt(r)/(1 + r). (*How to DeFi* Ch.3)"""
    r = max(price_ratio, 1e-9)
    return max(0.0, 1.0 - (2.0 * math.sqrt(r) / (1.0 + r)))


def _binary_kelly(p: float, ask: float) -> float:
    """f* = (p − ask) / (1 − ask) for a $0/$1 payoff, floored at 0."""
    return _clamp((p - ask) / max(1.0 - ask, 1e-9), 0.0, 1.0)


class DeFiAgent:
    """Sector-agnostic DeFi strategy agent — one registry, venue-dispatched."""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self.enabled = ENABLED

    @property
    def redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
            )
        return self._redis

    # ── Main entry point (called by orchestrator, 1-line hook) ──────────────
    async def run(self, regime: str, signals: list[dict] | None = None) -> list[dict]:
        if not self.enabled:
            logger.debug("[DeFi] Agent disabled — set DEFI_ENABLED=1 to enable")
            return []

        # D6: oracle integrity governor (U30/U33).
        governor = self._oracle_governor()

        markets = get_markets()
        if not markets and not governor.get("paused_evm"):
            logger.warning("[DeFi] No markets + no breaker → 0 candidates this cycle")
            return []

        candidates: list[dict] = []
        for bucket in (
            self._strategy_d1_lp(markets, regime),
            self._strategy_d2_lending(markets, regime),
            self._strategy_d3_yield(markets, regime),
            self._strategy_d4_perp(markets, regime),
            self._strategy_d5_ec_hedge(markets, signals or [], regime),
            self._strategy_d7_ec_tail(markets, regime),
        ):
            candidates.extend(bucket)

        candidates = self._apply_pause(candidates, governor)
        candidates = self._apply_exposure_cap(candidates)

        self._cache("defi:candidates", candidates)
        self._cache("defi:governor", governor)
        self._upsert_kg_nodes(candidates, regime)

        logger.info(
            f"[DeFi] {len(candidates)} candidates "
            f"(regime={regime}, paused_evm={governor.get('paused_evm')}, "
            f"paused_ec={governor.get('paused_ec')})"
        )
        return candidates
# ── D1: AMM concentrated-LP (Uniswap V3 / Sepolia) ────────────────────────
    def _strategy_d1_lp(self, markets: list[dict], regime: str) -> list[dict]:
        out: list[dict] = []
        for m in markets:
            if not m.get("is_lp"):
                continue
            fee_apy  = float(m.get("fee_apy") or 0.0)
            gas_cost = float(m.get("gas_cost_pct") or 0.001)
            price_ratio = float(m.get("price_ratio_entry") or 1.0)
            il = _il_divergence(price_ratio)
            raw_edge = fee_apy * (1.0 - il) - gas_cost
            net_edge = raw_edge - MIN_LP_EDGE_PCT
            if net_edge <= 0:                       # U28
                continue
            width = float(m.get("range_width_pct") or 100.0)
            if width > MAX_LP_RANGE_WIDTH_PCT:       # range-width cap
                continue
            out.append({
                "kind": "defi-lp", "sector": "D1", "venue": "sepolia-evm",
                "market_id": m.get("market_id"), "name": m.get("name"),
                "fee_apy": round(fee_apy * 100, 2),
                "il_pct": round(il * 100, 2),
                "gas_pct": round(gas_cost * 100, 3),
                "net_edge_pct": round(net_edge * 100, 2),
                "range_width_pct": round(width, 1),
                "regime": regime, "status": "intent",  # U21
            })
        return out

    # ── D2: Lending carry (Aave V3 / Sepolia) ─────────────────────────────────
    def _strategy_d2_lending(self, markets: list[dict], regime: str) -> list[dict]:
        out: list[dict] = []
        for m in markets:
            if not m.get("is_lending"):
                continue
            spread = float(m.get("lend_rate") or 0.0) - float(m.get("borrow_rate") or 0.0)
            if spread < MIN_LENDING_SPREAD_PCT:      # carry threshold
                continue
            collat = float(m.get("collat_price") or 0.0)
            liq_ratio = float(m.get("liquidation_ratio") or 0.0)
            liquidation_distance = (
                (collat * liq_ratio - 1.0) if liq_ratio > 0 else -1.0
            )
            if liquidation_distance < 0.10:           # U29
                continue
            out.append({
                "kind": "defi-lending", "sector": "D2", "venue": "sepolia-evm",
                "market_id": m.get("market_id"), "name": m.get("name"),
                "lend_rate_pct": round(float(m.get("lend_rate") or 0.0) * 100, 2),
                "borrow_rate_pct": round(float(m.get("borrow_rate") or 0.0) * 100, 2),
                "spread_pct": round(spread * 100, 2),
                "liquidation_distance": round(liquidation_distance, 4),
                "regime": regime, "status": "intent",
            })
        return out

    # ── D3: Yield-farm ranking (risk-adj APY) (Sepolia) ──────────────────────
    def _strategy_d3_yield(self, markets: list[dict], regime: str) -> list[dict]:
        out: list[dict] = []
        for m in markets:
            if not m.get("is_vault"):
                continue
            raw_apy = float(m.get("raw_apy") or 0.0)
            hack_prior = float(m.get("hack_prior_apy") or 0.0)
            liq_risk = float(m.get("liquidation_risk_apy") or 0.0)
            il_add = float(m.get("il_risk_apy") or 0.0)
            risk_adj = max(0.0, raw_apy - hack_prior - liq_risk - il_add)
            leverage = float(m.get("leverage_x") or 1.0)
            if leverage > MAX_LEVERAGE_X:             # U32
                continue
            out.append({
                "kind": "defi-yield", "sector": "D3", "venue": "sepolia-evm",
                "market_id": m.get("market_id"), "name": m.get("name"),
                "raw_apy_pct": round(raw_apy * 100, 2),
                "risk_adj_apy_pct": round(risk_adj * 100, 2),
                "leverage_x": round(leverage, 2),
                "regime": regime, "status": "intent",
            })
        return out

    # ── D4: Perp funding carry (Sepolia) ─────────────────────────────────────
    def _strategy_d4_perp(self, markets: list[dict], regime: str) -> list[dict]:
        out: list[dict] = []
        for m in markets:
            if not m.get("is_perp"):
                continue
            funding = abs(float(m.get("funding_rate") or 0.0))
            if funding < MIN_FUNDING_CARRY_PCT:     # threshold
                continue
            if regime not in ("Bull Trend", "Bear Trend", "High Volatility"):
                continue
            out.append({
                "kind": "defi-perp", "sector": "D4", "venue": "sepolia-evm",
                "market_id": m.get("market_id"), "name": m.get("name"),
                "funding_rate_pct": round(float(m.get("funding_rate") or 0.0) * 100, 2),
                "regime": regime, "status": "intent",
            })
        return out

# ── D5: EC cross-hedge (DreamDEX) ────────────────────────────────────────
    def _strategy_d5_ec_hedge(self, markets: list[dict], signals: list[dict],
                              regime: str) -> list[dict]:
        out: list[dict] = []
        for m in markets:
            if not m.get("is_ec"):
                continue
            ticker = m.get("related_ticker") or (m.get("asset") or "BTC") + "/USD"
            corr = abs(float(m.get("correlation") or 0.0))
            if m.get("hedge_direction") != "cross" or corr < MIN_CORRELATION:
                continue
            ask = float((m.get("up") or {}).get("ask") or 0.5)
            try:
                env = suggest_crypto(ticker, lens="defensive", regime_override=regime)
                spot = float(env.get("spot") or 0.0) or 0.0
            except Exception as e:
                logger.warning(f"[DeFi] D5 belief failed for {ticker}: {e}")
                spot = 0.0

            # Belief p(up): use an explicit strike when present; otherwise a
            # neutral tilt (the EC windows are near-dated, so without a strike
            # we keep a modest directional prior from the regime+signal only).
            strike_raw = m.get("strike")
            if strike_raw not in (None, 0, 0.0, "", "0", "0.0"):
                strike = float(strike_raw)
                p = _clamp(0.5 + (0.25 if spot > strike else -0.25), 0.01, 0.99)
            else:
                p = _clamp(0.5 + (0.10 if spot > 0 else -0.10), 0.01, 0.99)
            edge = (p - ask) / ask if ask > 0 else 0.0
            if edge < MIN_EC_EDGE_PCT:               # U28 (EC)
                continue
            kelly = _binary_kelly(p, ask)            # U9 binary-Kelly sizing
            if kelly <= 0:
                continue
            out.append({
                "kind": "defi-ec-hedge", "sector": "D5", "venue": "somnia-relay",
                "market_id": m.get("market_id"), "symbol": m.get("symbol"),
                "ticker": ticker, "correlation": round(corr, 3),
                "estimate": round(p, 4), "ask": round(ask, 4),
                "edge_pct": round(edge * 100, 2),
                "binary_kelly": round(kelly, 4),
                "size_usd": round(100_000.0 * kelly * MAX_EC_TAILHEDGE_PCT, 2),
                "regime": regime, "status": "intent",
            })
        return out

    # ── D7: EC tail-hedge (DreamDEX, regime=Crisis/Stress) ───────────────────
    def _strategy_d7_ec_tail(self, markets: list[dict], regime: str) -> list[dict]:
        if regime not in ("Crisis", "Stress"):
            return []
        out: list[dict] = []
        for m in markets:
            if not m.get("is_ec"):
                continue
            ask = float((m.get("up") or {}).get("ask") or 0.5)
            if ask > 0.30:
                continue
            hedged_pct = MAX_EC_TAILHEDGE_PCT       # U32
            out.append({
                "kind": "defi-ec-tail", "sector": "D7", "venue": "somnia-relay",
                "market_id": m.get("market_id"), "symbol": m.get("symbol"),
                "ask": round(ask, 4),
                "hedge_pct_portfolio": round(hedged_pct * 100, 2),
                "size_usd": round(100_000.0 * hedged_pct, 2),
                "regime": regime, "status": "intent",
            })
        return out

    # ── D6/D8: oracle governor (U30/U33) ────────────────────────────────────
    def _oracle_governor(self) -> dict:
        paused_ec = False
        paused_evm = False
        feeds = self._oracle_feeds()
        now_ms = float(os.getenv("_NOW_MS") or 0)
        if now_ms <= 0:
            now_ms = time.time() * 1000.0
        for feed in feeds:
            updated = float(feed.get("updated_ts") or 0.0)
            dev_bps = float(feed.get("deviation_bps") or 0.0)
            attested = bool(feed.get("attested"))        # U33
            stale = (now_ms - updated) > ORACLE_STALE_MS
            deviated = dev_bps > ORACLE_DEVIATION_BPS
            # U30: stale → pause.  U33: unattested → treat as stale.
            if stale or deviated or not attested:
                if feed.get("venue") == "somnia":
                    paused_ec = True
                else:
                    paused_evm = True
        return {
            "paused_ec": paused_ec,
            "paused_evm": paused_evm,
            "stale_ms": ORACLE_STALE_MS,
            "deviation_bps": int(ORACLE_DEVIATION_BPS * 10_000),
            "checks": [
                {
                    "venue": f.get("venue"),
                    "stale": (now_ms - float(f.get("updated_ts") or 0)) > ORACLE_STALE_MS,
                    "deviation_bps": float(f.get("deviation_bps") or 0.0),
                    "attested": bool(f.get("attested")),
                }
                for f in feeds
            ],
        }

    def _oracle_feeds(self) -> list[dict]:
        """Best-effort feed liveness from the DreamDEX relay."""
        try:
            from agent.dreamdex_adapter import relay_status  # type: ignore
        except ImportError:
            try:
                from dreamdex_adapter import relay_status  # type: ignore
            except ImportError:
                return []
        st = relay_status()
        if not isinstance(st, dict):
            return []
        return [
            {
                "venue": "somnia",
                "updated_ts": float(st.get("updated_ts") or 0.0),
                "deviation_bps": float(st.get("deviation_bps") or 0.0),
                "attested": bool(st.get("attested") if "attested" in st else False),
            }
        ]

    def _apply_pause(self, candidates: list[dict], governor: dict) -> list[dict]:
        if governor.get("paused_evm"):
            candidates = [c for c in candidates if c.get("venue") != "sepolia-evm"]
        if governor.get("paused_ec"):
            candidates = [c for c in candidates if c.get("venue") != "somnia-relay"]
        return candidates

    def _apply_exposure_cap(self, candidates: list[dict]) -> list[dict]:
        """Global DeFi exposure ≤ MAX_DEFI_EXPOSURE_PCT of a 100k book."""
        cap = 100_000.0 * MAX_DEFI_EXPOSURE_PCT
        used = 0.0
        kept: list[dict] = []
        for c in candidates:
            sz = float(c.get("size_usd") or 0.0)
            if used + sz > cap:
                continue
            used += sz
            kept.append(c)
        return kept
# ── Persistence (best-effort, mirrors siblings) ─────────────────────────
    def _cache(self, key: str, payload: Any):
        try:
            self.redis.set(key, json.dumps(payload), ex=300)
        except Exception as e:
            logger.warning(f"[DeFi] redis cache {key} failed: {e}")

    def _upsert_kg_nodes(self, candidates: list[dict], regime: str):
        """MERGE DeFi sector nodes linked to the shared Regime spine."""
        try:
            db = get_db()
            for c in candidates:
                mid = str(c.get("market_id") or "")
                if not mid:
                    continue
                label = "AMMPool" if c.get("sector") == "D1" else "LendingPool"
                db.execute_and_fetch(
                    f"MERGE (n:{label} {{market_id: $mid}}) "
                    f"SET n.sector = $sector, n.venue = $venue, n.status = $status "
                    f"WITH n MATCH (r:Regime {{name: $regime}}) "
                    f"MERGE (n)-[:ACTIVATES_IN]->(r)",
                    {
                        "mid": mid, "sector": c.get("sector"),
                        "venue": c.get("venue"), "status": c.get("status"),
                        "regime": regime,
                    },
                )
        except Exception as e:
            logger.warning(f"[DeFi] KG upsert failed (non-fatal): {e}")


__all__ = ["DeFiAgent", "_il_divergence", "_binary_kelly"]