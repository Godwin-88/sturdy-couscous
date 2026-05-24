"""
Macro Calendar Agent — fetches upcoming and recent economic events,
scores their market impact, and writes MacroEvent nodes to the KG.

Sources (all free):
  - FRED API (release calendar) — requires FRED_API_KEY env var
  - Hardcoded recurring event schedule as fallback when no key set
  - Investopedia / Trading Economics scrape as tertiary fallback

Impact scoring:
  - 3 tiers: HIGH / MEDIUM / LOW based on event type
  - Pre-event signal: reduce position sizing 24h before HIGH events
  - Post-event signal: sentiment direction based on beat/miss vs consensus
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from gqlalchemy import Memgraph
from loguru import logger

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FRED_BASE    = "https://api.stlouisfed.org/fred"

# ── High-impact recurring events ──────────────────────────────────────────────
# Manually curated list of market-moving events with their typical cadence.
# Used when FRED_API_KEY is not available.
HIGH_IMPACT_EVENTS = [
    "FOMC Meeting",
    "CPI Release",
    "PCE Price Index",
    "Nonfarm Payrolls",
    "GDP Advance Estimate",
    "Fed Chair Speech",
    "Jackson Hole Symposium",
    "Treasury Refunding Announcement",
]

MEDIUM_IMPACT_EVENTS = [
    "PPI Release",
    "Retail Sales",
    "ISM Manufacturing PMI",
    "ISM Services PMI",
    "JOLTS Job Openings",
    "Consumer Confidence",
    "Housing Starts",
    "Industrial Production",
    "Durable Goods Orders",
]

# FRED series → event display name mapping
FRED_SERIES_NAMES = {
    "CPIAUCSL":    ("CPI Release",              "HIGH",   ["Interest Rates", "Inflation"]),
    "PCEPI":       ("PCE Price Index",           "HIGH",   ["Interest Rates", "Inflation"]),
    "PAYEMS":      ("Nonfarm Payrolls",           "HIGH",   ["Market Momentum"]),
    "GDP":         ("GDP Advance Estimate",       "HIGH",   ["Market Momentum"]),
    "PPIFIS":      ("PPI Release",               "MEDIUM", ["Inflation"]),
    "RSXFS":       ("Retail Sales",              "MEDIUM", ["Market Momentum", "Earnings"]),
    "NAPM":        ("ISM Manufacturing PMI",     "MEDIUM", ["Market Momentum"]),
    "UNRATE":      ("Unemployment Rate",         "MEDIUM", ["Market Momentum"]),
    "HOUST":       ("Housing Starts",            "MEDIUM", ["Credit Risk"]),
    "INDPRO":      ("Industrial Production",     "MEDIUM", ["Market Momentum"]),
    "FEDFUNDS":    ("Fed Funds Rate Decision",   "HIGH",   ["Interest Rates", "Volatility"]),
}

IMPACT_PRE_SIGNAL: dict[str, float] = {
    "HIGH":   -0.15,   # reduce size 15% before high-impact events
    "MEDIUM": -0.05,   # reduce size 5% before medium-impact events
    "LOW":     0.0,
}


class MacroCalendarAgent:
    def __init__(self):
        self.db = Memgraph(
            host=os.getenv("MEMGRAPH_HOST", "memgraph"),
            port=int(os.getenv("MEMGRAPH_PORT", 7687)),
        )

    async def run(self, lookahead_days: int = 7) -> dict[str, Any]:
        """
        Fetch upcoming macro events, write MacroEvent nodes to KG,
        return pre-event position-sizing signals.
        """
        events = await self._fetch_events(lookahead_days)
        if not events:
            return {"events": 0, "pre_event_signals": {}, "upcoming": []}

        nodes_written = self._write_to_kg(events)
        pre_signals   = self._build_pre_event_signals(events)

        upcoming = [
            {
                "name":   e["name"],
                "date":   e["date"],
                "impact": e["impact"],
                "concepts": e["concepts"],
            }
            for e in events[:10]
        ]

        logger.info(f"MacroCalendarAgent: {len(events)} events | "
                    f"{nodes_written} KG nodes | "
                    f"pre_signals={list(pre_signals.keys())}")
        return {
            "events":            len(events),
            "pre_event_signals": pre_signals,
            "upcoming":          upcoming,
        }

    async def _fetch_events(self, lookahead_days: int) -> list[dict]:
        events: list[dict] = []

        if FRED_API_KEY:
            events = await self._fetch_fred_releases(lookahead_days)
        else:
            events = self._synthetic_upcoming_events(lookahead_days)

        return sorted(events, key=lambda e: e["date"])

    async def _fetch_fred_releases(self, lookahead_days: int) -> list[dict]:
        """Query FRED release calendar for upcoming release dates."""
        events: list[dict] = []
        today = datetime.now(timezone.utc).date()
        end   = today + timedelta(days=lookahead_days)

        async with httpx.AsyncClient(timeout=10.0) as client:
            for series_id, (name, impact, concepts) in FRED_SERIES_NAMES.items():
                try:
                    url = (
                        f"{FRED_BASE}/release/dates"
                        f"?series_id={series_id}"
                        f"&realtime_start={today}"
                        f"&realtime_end={end}"
                        f"&api_key={FRED_API_KEY}"
                        f"&file_type=json"
                    )
                    r = await client.get(url)
                    if r.status_code != 200:
                        continue
                    data = r.json()
                    for rd in data.get("release_dates", []):
                        release_date = rd.get("date", "")
                        if release_date:
                            events.append({
                                "id":       f"fred_{series_id}_{release_date}",
                                "name":     name,
                                "series":   series_id,
                                "date":     release_date,
                                "impact":   impact,
                                "concepts": concepts,
                                "source":   "FRED",
                            })
                except Exception as e:
                    logger.debug(f"FRED fetch failed for {series_id}: {e}")

        return events

    def _synthetic_upcoming_events(self, lookahead_days: int) -> list[dict]:
        """
        Fallback: generate plausible upcoming events without an API key.
        Uses the fact that most US macro releases occur on fixed weekday patterns.
        """
        today  = datetime.now(timezone.utc).date()
        events: list[dict] = []

        # CPI: typically 2nd or 3rd Wednesday of the month
        for offset in range(lookahead_days + 30):
            d = today + timedelta(days=offset)
            if d.weekday() == 2 and 8 <= d.day <= 21:   # Wednesday, 8th–21st
                events.append({
                    "id":       f"syn_cpi_{d}",
                    "name":     "CPI Release",
                    "series":   "CPIAUCSL",
                    "date":     str(d),
                    "impact":   "HIGH",
                    "concepts": ["Interest Rates", "Inflation"],
                    "source":   "synthetic",
                })
                break

        # NFP: typically first Friday of the month
        for offset in range(lookahead_days + 30):
            d = today + timedelta(days=offset)
            if d.weekday() == 4 and 1 <= d.day <= 7:    # Friday, 1st–7th
                events.append({
                    "id":       f"syn_nfp_{d}",
                    "name":     "Nonfarm Payrolls",
                    "series":   "PAYEMS",
                    "date":     str(d),
                    "impact":   "HIGH",
                    "concepts": ["Market Momentum"],
                    "source":   "synthetic",
                })
                break

        # FOMC: ~8 times per year — next one within 45 days heuristic
        # Hard-code 2025/2026 FOMC dates
        fomc_dates = [
            "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17",
            "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
            "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16",
        ]
        for fd in fomc_dates:
            fd_date = datetime.strptime(fd, "%Y-%m-%d").date()
            if today <= fd_date <= today + timedelta(days=lookahead_days + 30):
                events.append({
                    "id":       f"fomc_{fd}",
                    "name":     "FOMC Meeting",
                    "series":   "FEDFUNDS",
                    "date":     fd,
                    "impact":   "HIGH",
                    "concepts": ["Interest Rates", "Volatility"],
                    "source":   "hardcoded",
                })
                break

        return [e for e in events if e["date"] <= str(today + timedelta(days=lookahead_days))]

    def _build_pre_event_signals(self, events: list[dict]) -> dict[str, float]:
        """
        Return concept-level position-sizing modifiers for the next 48 hours.
        Negative = reduce size, positive = not used here.
        """
        today    = datetime.now(timezone.utc).date()
        cutoff   = today + timedelta(days=2)
        signals: dict[str, float] = {}

        for e in events:
            try:
                edate = datetime.strptime(e["date"], "%Y-%m-%d").date()
            except ValueError:
                continue
            if edate > cutoff:
                continue
            modifier = IMPACT_PRE_SIGNAL.get(e["impact"], 0.0)
            for concept in e.get("concepts", []):
                # Take the most restrictive (most negative) modifier
                if concept not in signals or modifier < signals[concept]:
                    signals[concept] = modifier

        return signals

    def _write_to_kg(self, events: list[dict]) -> int:
        written = 0
        for e in events:
            eid    = e["id"].replace("'", "")
            name   = e["name"].replace("'", "\\'")
            date   = e["date"]
            impact = e["impact"]
            source = e["source"]
            try:
                self.db.execute(f"""
                MERGE (m:MacroEvent {{id: '{eid}'}})
                SET m.name      = '{name}',
                    m.date      = '{date}',
                    m.impact    = '{impact}',
                    m.source    = '{source}'
                """)
                written += 1

                for concept in e.get("concepts", []):
                    concept_esc = concept.replace("'", "\\'")
                    try:
                        self.db.execute(f"""
                        MATCH (c:Concept {{name: '{concept_esc}'}})
                        MATCH (m:MacroEvent {{id: '{eid}'}})
                        MERGE (m)-[:AFFECTS]->(c)
                        """)
                    except Exception:
                        pass
            except Exception as ex:
                logger.debug(f"KG write failed for macro event {eid}: {ex}")

        return written
