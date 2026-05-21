"""
Research Agent
Runs on a slower cadence (~1 hour). Three responsibilities:
  1. Transcribe earnings calls via Speechmatics → extract entities → add graph nodes
  2. Refit VARLiNGAM on fresh price data → update TRANSMITS_TO edge weights
  3. Pull FRED macro data → update Regime node properties
"""

import os
from datetime import datetime, timedelta
from typing import Any

import httpx
import numpy as np
import pandas as pd
import yfinance as yf
from gqlalchemy import Memgraph
from lingam import VARLiNGAM
from loguru import logger

SPEECHMATICS_KEY  = os.getenv("SPEECHMATICS_API_KEY", "")
FEATHERLESS_URL   = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
FEATHERLESS_KEY   = os.getenv("FEATHERLESS_API_KEY", "")
FEATHERLESS_MODEL = os.getenv("FEATHERLESS_MODEL", "")
FRED_API_KEY      = os.getenv("FRED_API_KEY", "")

VARLINGAM_TICKERS = ["SPY", "XLF", "XLE", "QQQ", "BTC-USD", "ETH-USD"]
VARLINGAM_LAG     = 4


class ResearchAgent:
    def __init__(self):
        self.db = Memgraph(
            host=os.getenv("MEMGRAPH_HOST", "memgraph"),
            port=int(os.getenv("MEMGRAPH_PORT", 7687))
        )

    async def run(self) -> dict[str, Any]:
        nodes_added = 0
        edges_added = 0

        # ── 1. VARLiNGAM causal graph refit ──────────────────────────────────
        try:
            causal_edges = self._refit_varlingam()
            edges_added += self._update_transmits_edges(causal_edges)
            logger.info(f"VARLiNGAM refit: {edges_added} TRANSMITS_TO edges updated")
        except Exception as e:
            logger.error(f"VARLiNGAM refit failed: {e}")

        # ── 2. FRED macro data → Regime node properties ───────────────────────
        try:
            self._update_regime_macro()
            logger.info("FRED macro update complete")
        except Exception as e:
            logger.error(f"FRED update failed: {e}")

        # ── 3. Earnings transcription (if Speechmatics key present) ──────────
        if SPEECHMATICS_KEY:
            try:
                n, e = await self._process_earnings_queue()
                nodes_added += n
                edges_added += e
            except Exception as ex:
                logger.error(f"Earnings processing failed: {ex}")

        return {"nodes_added": nodes_added, "edges_added": edges_added}

    # ── VARLiNGAM ─────────────────────────────────────────────────────────────
    def _refit_varlingam(self) -> list[dict]:
        """
        Fit VARLiNGAM on 1y daily returns. Return list of significant
        causal edges: {source, target, lag, coefficient}.
        """
        raw = yf.download(VARLINGAM_TICKERS, period="1y",
                          auto_adjust=True, progress=False)["Close"].dropna()
        rets = raw.pct_change().dropna().values

        model  = VARLiNGAM(lags=VARLINGAM_LAG)
        result = model.fit(rets)

        edges = []
        for lag_idx, matrix in enumerate(result.adjacency_matrices_):
            lag = lag_idx + 1
            for i, row in enumerate(matrix):
                for j, coef in enumerate(row):
                    if abs(coef) > 0.05 and i != j:
                        edges.append({
                            "source":      VARLINGAM_TICKERS[j].replace("-USD", ""),
                            "target":      VARLINGAM_TICKERS[i].replace("-USD", ""),
                            "lag":         lag,
                            "coefficient": round(float(coef), 4),
                        })
        return edges

    def _update_transmits_edges(self, edges: list[dict]) -> int:
        count = 0
        for e in edges:
            query = f"""
            MATCH (a:Ticker {{symbol: '{e["source"]}'}})
            MATCH (b:Ticker {{symbol: '{e["target"]}'}})
            MERGE (a)-[r:TRANSMITS_TO]->(b)
            SET r.lag = {e["lag"]},
                r.coefficient = {e["coefficient"]},
                r.last_fit = '{datetime.utcnow().date()}'
            """
            try:
                self.db.execute(query)
                count += 1
            except Exception as ex:
                logger.warning(f"Edge update failed {e}: {ex}")
        return count

    # ── FRED macro ────────────────────────────────────────────────────────────
    def _update_regime_macro(self):
        if not FRED_API_KEY:
            return
        series_map = {
            "FEDFUNDS":  "fed_funds_rate",
            "UNRATE":    "unemployment_rate",
            "CPIAUCSL":  "cpi_yoy",
            "GS10":      "yield_10y",
        }
        values = {}
        for series_id, prop in series_map.items():
            try:
                url = (f"https://api.stlouisfed.org/fred/series/observations"
                       f"?series_id={series_id}&api_key={FRED_API_KEY}"
                       f"&file_type=json&sort_order=desc&limit=1")
                import urllib.request
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = __import__("json").loads(resp.read())
                val = float(data["observations"][0]["value"])
                values[prop] = val
            except Exception:
                pass

        if not values:
            return

        set_clause = ", ".join(f"r.{k} = {v}" for k, v in values.items())
        set_clause += f", r.macro_updated = '{datetime.utcnow().date()}'"
        query = f"""
        MATCH (r:Regime)
        SET {set_clause}
        """
        try:
            self.db.execute(query)
        except Exception as e:
            logger.error(f"Regime macro set failed: {e}")

    # ── Earnings transcription ────────────────────────────────────────────────
    async def _process_earnings_queue(self) -> tuple[int, int]:
        """
        Poll a Redis queue for audio URLs submitted by the user/frontend.
        Transcribe via Speechmatics, extract entities via Featherless,
        add EarningsEvent + NewsEntity nodes to the graph.
        """
        import redis.asyncio as aioredis
        r = aioredis.from_url(
            f"redis://{os.getenv('REDIS_HOST', 'redis')}:"
            f"{os.getenv('REDIS_PORT', 6379)}"
        )
        nodes = edges = 0
        while True:
            item = await r.lpop("graphalpha:earnings_queue")
            if not item:
                break
            try:
                payload = __import__("json").loads(item)
                transcript = await self._transcribe(payload["audio_url"])
                entities   = await self._extract_entities(transcript, payload.get("ticker", ""))
                n, e = self._add_to_graph(entities, payload.get("ticker", ""), transcript)
                nodes += n
                edges += e
            except Exception as ex:
                logger.error(f"Earnings item failed: {ex}")
        await r.aclose()
        return nodes, edges

    async def _transcribe(self, audio_url: str) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Submit job
            r = await client.post(
                "https://asr.api.speechmatics.com/v2/jobs/",
                headers={"Authorization": f"Bearer {SPEECHMATICS_KEY}"},
                json={
                    "config": {
                        "type": "transcription",
                        "transcription_config": {"language": "en"},
                    },
                    "data_url": audio_url,
                },
            )
            job_id = r.json()["id"]

            # Poll until done (max 10 min)
            import asyncio
            for _ in range(60):
                await asyncio.sleep(10)
                status_r = await client.get(
                    f"https://asr.api.speechmatics.com/v2/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {SPEECHMATICS_KEY}"},
                )
                if status_r.json()["job"]["status"] == "done":
                    break

            transcript_r = await client.get(
                f"https://asr.api.speechmatics.com/v2/jobs/{job_id}/transcript",
                headers={"Authorization": f"Bearer {SPEECHMATICS_KEY}"},
                params={"format": "txt"},
            )
            return transcript_r.text

    async def _extract_entities(self, transcript: str, ticker: str) -> list[dict]:
        if not FEATHERLESS_KEY:
            return []
        prompt = (
            f"Extract financial entities from this earnings call transcript for {ticker}. "
            "Return a JSON array of objects with keys: entity_type (Risk|Strategy|Metric|"
            "MacroFactor), name, sentiment (-1 to 1), excerpt. Transcript:\n\n"
            + transcript[:3000]
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{FEATHERLESS_URL}/chat/completions",
                json={
                    "model":       FEATHERLESS_MODEL,
                    "messages":    [{"role": "user", "content": prompt}],
                    "max_tokens":  512,
                    "temperature": 0.1,
                },
                headers={"Authorization": f"Bearer {FEATHERLESS_KEY}"},
            )
        raw = r.json()["choices"][0]["message"]["content"]
        try:
            import re, json
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            return json.loads(match.group()) if match else []
        except Exception:
            return []

    def _add_to_graph(self, entities: list[dict], ticker: str,
                      transcript: str) -> tuple[int, int]:
        nodes = edges = 0
        event_id = f"EarningsEvent_{ticker}_{datetime.utcnow().date()}"
        try:
            self.db.execute(f"""
            MERGE (e:EarningsEvent {{id: '{event_id}'}})
            SET e.ticker = '{ticker}',
                e.date   = '{datetime.utcnow().date()}',
                e.transcript_excerpt = {repr(transcript[:500])}
            """)
            nodes += 1
        except Exception:
            pass

        for ent in entities:
            name = ent.get("name", "").replace("'", "\\'")
            etype = ent.get("entity_type", "NewsEntity")
            sentiment = ent.get("sentiment", 0)
            try:
                self.db.execute(f"""
                MERGE (n:NewsEntity {{name: '{name}', type: '{etype}'}})
                SET n.last_sentiment = {sentiment},
                    n.updated = '{datetime.utcnow().date()}'
                WITH n
                MATCH (e:EarningsEvent {{id: '{event_id}'}})
                MERGE (e)-[:MENTIONS]->(n)
                """)
                nodes += 1
                edges += 1
            except Exception:
                pass

        return nodes, edges
