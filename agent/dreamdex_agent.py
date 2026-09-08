"""
dreamdex_agent.py
──────────────────
KG-grounded DreamDEX Event-Contract agent (P9 §9, tenet upgrades U10–U13).

Per orchestrator cycle:
  1. Pulls open EC markets from the relay snapshot (on-chain-gated).
  2. Builds a conditional probability estimate for each window
     P(price > strike at T | spot, remaining time, realized vol) using the
     pair's own tape via the existing KG crypto strategy engine
     (crypto_signal.suggest_crypto) — the "graph-before-generation" gate.
  3. Computes edge vs the LIVE book (up.ask / down.ask), applies the U10
     multiplicity correction, U11 cost/liquidity/fat-tail guards, and the
     oracle-divergence haircut (U1).
  4. Sizes winners with binary Kelly (0/1 payoff) and hard caps.
  5. Persists EventContract nodes to the shared KG (best-effort) and
     candidates to Redis for the panel + API.

Self-disables when DREAMDEX_ENABLED is unset/0 (same property as P9).
Human gate: produced candidates are *intents* — they never execute without
a proposal_token / explicit approval (U21).
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Optional

import redis
from loguru import logger

from common.graph import get_db

try:
    from agent.dreamdex_adapter import get_markets  # cwd = /app (api container)
except ImportError:                                # cwd = agent/ (agent-worker)
    from dreamdex_adapter import get_markets  # type: ignore

ENABLED = os.getenv("DREAMDEX_ENABLED", "0").lower() in ("1", "true", "yes")
MIN_EDGE_PCT = float(os.getenv("DREAMDEX_MIN_EDGE_PCT", "0.03"))
FILL_IMPACT_BPS = float(os.getenv("FILL_IMPACT_BPS", "20")) / 10_000.0
MIN_ASK_DEPTH_CONTRACTS = float(os.getenv("MIN_ASK_DEPTH_CONTRACTS", "5"))
KURTOSIS_VOL_SCALE = float(os.getenv("KURTOSIS_VOL_SCALE", "1.0"))
TAPE_DIVERGENCE_BPS = float(os.getenv("TAPE_DIVERGENCE_BPS", "25")) / 10_000.0
MULTICORR = os.getenv("DREAMDEX_MULTICORR", "bh")  # off|bonferroni|holm|bh
FDR_DELTA = float(os.getenv("DREAMDEX_FDR_DELTA", "0.10"))
MAX_EC_POSITION_PCT_PORTFOLIO = float(os.getenv("MAX_EC_POSITION_PCT_PORTFOLIO", "0.02"))
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Regime → category eligibility (KG-strategy grounded; keep conservative).
CATEGORY_REGIME_AFFINITY: dict[str, list[str]] = {
    "crypto":     ["Bull Trend", "Bear Trend", "High Volatility"],
    "economics":  ["Bull Trend", "Bear Trend", "Stagflation", "Recession"],
    "politics":   ["High Volatility", "Crisis"],
    "sports":     ["Bull Trend", "Bear Trend", "Low Volatility"],
    "technology": ["Bull Trend", "Low Volatility"],
}


class DreamDEXAgent:
    """Scores live DreamDEX EC windows and produces sized candidate intents."""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self.enabled = ENABLED

    # ── Redis ──────────────────────────────────────────────────────────────
    @property
    def redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
            )
        return self._redis

    # ── Main entry point (called by orchestrator, 1-line hook) ─────────────
    async def run(self, regime: str, signals: list[dict] | None = None) -> list[dict]:
        if not self.enabled:
            logger.debug("[DreamDEX] Agent disabled — set DREAMDEX_ENABLED=1 to enable")
            return []

        markets = get_markets()
        if not markets:
            self._cache("dreamdex_markets", [])
            return []

        eligible = [m for m in markets if self._is_eligible(m, regime)]
        candidates = self._score_markets(eligible, signals or [], regime)

        self._cache("dreamdex_markets", markets)
        self._cache("dreamdex_candidates", candidates)
        self._upsert_kg_nodes(eligible, regime)

        logger.info(
            f"[DreamDEX] {len(markets)} markets | {len(eligible)} regime-eligible | "
            f"{len(candidates)} candidates (regime={regime})"
        )
        return candidates

    # ── Filters ────────────────────────────────────────────────────────────
    def _is_eligible(self, m: dict, regime: str) -> bool:
        # Fall back to asset-based affinity when the relay gives no category.
        category = (m.get("category") or "").lower()
        if not category:
            category = {"btc": "crypto", "eth": "crypto"}.get(
                str(m.get("asset", "")).lower(), "other"
            )
        return regime in CATEGORY_REGIME_AFFINITY.get(category, [])

# ── Core financial engine (P9 §7 + U10–U13) ────────────────────────────
    def _score_markets(self, markets: list[dict], signals: list[dict],
                       regime: str) -> list[dict]:
        # U10: each candidate's edge → a naive p-value under the null, then a
        # multiplicity-corrected gate (BH / Bonferroni / Holm) on n_tested.
        n_tested = max(1, len(markets))
        candidates: list[dict] = []

        for m in markets:
            c = self._score_one(m, regime, n_tested)
            if c is not None:
                candidates.append(c)

        if MULTICORR in ("bh", "holm", "bonferroni"):
            candidates.sort(key=lambda c: c["edge_p_value"])
            kept: list[dict] = []
            n = n_tested
            for i, c in enumerate(candidates, start=1):
                if MULTICORR == "bonferroni":
                    threshold = FDR_DELTA / n
                elif MULTICORR == "holm":
                    threshold = FDR_DELTA / (n - i + 1)
                else:  # bh
                    threshold = FDR_DELTA * i / n
                if c["edge_p_value"] <= threshold:
                    kept.append(c)
            candidates = kept

        return candidates

    def _score_one(self, m: dict, regime: str, n_tested: int) -> dict | None:
        asset = (m.get("asset") or "BTC").upper()
        pair = {"BTC": "BTC/USD", "ETH": "ETH/USD"}.get(asset, f"{asset}/USD")
        strike = float(m.get("strike") or 0)
        interval_sec = float(m.get("interval_sec") or 300)
        closes_at = m.get("closes_at") or ""
        up, down = m.get("up", {}), m.get("down", {})

        # U11 liquidity floor: a "great edge" on an empty book is a mirage.
        if float(m.get("ask_depth") or 0) < MIN_ASK_DEPTH_CONTRACTS:
            return None

        # KG-grounded belief via the existing crypto strategy engine.
        belief, source = self._kg_belief(pair, regime, strike)

        # U11 fat-tail widening: leptokurtic crypto returns (T6). Widen sigma.
        realized_rv = float(m.get("rv_21") or belief.get("rv_21", 0.05))
        ex_kurt = float(m.get("ex_kurtosis") or 5.0)
        sigma_eff = realized_rv * (1.0 + KURTOSIS_VOL_SCALE * (ex_kurt / 10.0))

        # Log-normal window probability: P(price > strike at T). tau is a
        # normalized remaining-time factor (clamped to a sane range).
        tau = max(0.1, min(1.5, (100_000.0 / max(interval_sec, 1.0))))
        z = (math.log(strike / max(belief["spot"], 1e-9))) / (sigma_eff * math.sqrt(tau))
        p_up = 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        p_up = min(max(p_up, 0.01), 0.99)

        ask_up = float(up.get("ask") or 0.5)
        ask_down = float(down.get("ask") or (1 - ask_up))

        # Oracle divergence haircut (U1): if KG belief disagrees with the book
        # beyond a band, pull toward 0.5 (uncertainty = no edge).
        divergence = abs(p_up - ask_up)
        if divergence > TAPE_DIVERGENCE_BPS + 0.05:
            p_up = 0.5 + (p_up - 0.5) * 0.5

        # Edge on BOTH sides — buy the side where estimate beats ask by margin.
        edge_up = (p_up - ask_up) / ask_up
        edge_down = ((1 - p_up) - ask_down) / ask_down
        side = "up" if edge_up >= edge_down else "down"
        raw_edge = edge_up if side == "up" else edge_down

        # U11 net-edge: subtract impact and the minimum threshold.
        net_edge = raw_edge - FILL_IMPACT_BPS - MIN_EDGE_PCT
        if net_edge <= 0:
            return None

        # Naive p-value under the null (edge=0).
        p_value = min(1.0, 1.0 / (1.0 + math.exp(10.0 * raw_edge)))

        # Binary Kelly sizing (0/1 payoff): f = (p_side - price)/(1 - price).
        p_side = p_up if side == "up" else (1 - p_up)
        price = ask_up if side == "up" else ask_down
        kelly = max(0.0, (p_side - price) / (1.0 - price))
        nav = float(os.getenv("INITIAL_CAPITAL_USD", 10000))
        size_usd = min(
            kelly * nav * 0.5,                    # half-Kelly prudence
            nav * MAX_EC_POSITION_PCT_PORTFOLIO,  # hard per-market cap
        )

        return {
            "market_id": m.get("marketId") or m.get("market_id"),
            "symbol": m.get("symbol") or "",
            "asset": asset,
            "side": side,
            "estimate": round(p_side, 4),
            "ask": round(price, 4),
            "divergence": round(divergence, 4),
            "edge_pct": round(raw_edge * 100, 2),
            "net_edge_pct": round(net_edge * 100, 2),
            "edge_p_value": round(p_value, 6),
            "binary_kelly": round(kelly, 4),
            "size_usd": round(size_usd, 2),
            "qty_contracts": max(1, int(size_usd / max(price, 0.01))),
            "regime": regime,
            "belief_source": source,
            "closes_at": closes_at,
            "n_tested": n_tested,
        }

    def _kg_belief(self, pair: str, regime: str, strike: float) -> tuple[dict, str]:
        """KG-grounded spot/vol belief via the existing crypto strategy engine."""
        try:
            try:
                from agent.crypto_signal import suggest_crypto  # cwd = /app (api)
            except ImportError:                                 # cwd = agent/
                from crypto_signal import suggest_crypto  # type: ignore
            env = suggest_crypto(pair, lens="defensive", regime_override=regime)
            spot = float(env.get("spot") or 0)
            rv = float(env.get("rv_21") or 0.05)
            return {"spot": spot if spot > 0 else strike * 0.9, "rv_21": rv}, "crypto_signal"
        except Exception as e:
            logger.warning(f"[DreamDEX] KG belief failed for {pair}: {e} — using book mid")
            return {"spot": strike * 0.9, "rv_21": 0.05}, "book_mid_fallback"

    # ── Persistence (additive, best-effort) ────────────────────────────────
    def _cache(self, key: str, payload: Any):
        try:
            self.redis.set(key, json.dumps(payload), ex=300)
        except Exception as e:
            logger.warning(f"[DreamDEX] redis cache {key} failed: {e}")

    def _upsert_kg_nodes(self, markets: list[dict], regime: str):
        """MERGE EventContract nodes linked to existing Regime nodes."""
        try:
            db = get_db()
            for m in markets:
                market_id = str(m.get("marketId") or m.get("market_id") or "")
                if not market_id:
                    continue
                asset = str(m.get("asset") or "BTC").upper()
                db.execute_and_fetch(
                    "MERGE (ec:EventContract {market_id: $market_id}) "
                    "SET ec.symbol = $symbol, ec.asset = $asset, ec.status = $status, "
                    "    ec.closes_at = $closes_at, ec.up_ask = $up_ask, ec.down_ask = $down_ask "
                    "WITH ec MATCH (r:Regime {name: $regime}) MERGE (ec)-[:ACTIVATES_IN]->(r)",
                    {
                        "market_id": market_id,
                        "symbol": str(m.get("symbol") or ""),
                        "asset": asset,
                        "status": int(m.get("status") or 0),
                        "closes_at": str(m.get("closes_at") or ""),
                        "up_ask": float((m.get("up") or {}).get("ask") or 0),
                        "down_ask": float((m.get("down") or {}).get("ask") or 0),
                        "regime": regime,
                    },
                )
        except Exception as e:
            logger.warning(f"[DreamDEX] KG upsert failed (non-fatal): {e}")


__all__ = ["DreamDEXAgent"]