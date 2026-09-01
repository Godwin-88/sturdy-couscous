"""
News Agent — fetches financial news, scores sentiment, maps entities to the KG.

Sources (all free, no API key required by default):
  - Yahoo Finance RSS per ticker
  - Reuters RSS (markets)
  - FRED release calendar

Entity matching: news mentions are linked to existing Concept/Ticker nodes
so the KG captures sentiment context for downstream signal fusion.
"""

import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
import numpy as np
from common.graph import get_db
from loguru import logger

LLM_URL = os.getenv("GROQ_BASE_URL", os.getenv("FEATHERLESS_BASE_URL", "https://api.groq.com/openai/v1"))
LLM_KEY = os.getenv("GROQ_API_KEY", os.getenv("FEATHERLESS_API_KEY", ""))
LLM_MODEL = os.getenv("GROQ_MODEL", os.getenv("FEATHERLESS_MODEL", "llama-3.3-70b-versatile"))

# ── RSS feed registry ─────────────────────────────────────────────────────────
RSS_FEEDS = {
    "yahoo_markets":  "https://finance.yahoo.com/news/rssindex",
    "reuters_biz":    "https://feeds.reuters.com/reuters/businessNews",
    "reuters_mkts":   "https://feeds.reuters.com/reuters/financialsNews",
    "seeking_alpha":  "https://seekingalpha.com/market_currents.xml",
    "ft_markets":     "https://www.ft.com/markets?format=rss",
    "wsj_markets":    "https://feeds.content.dowjones.io/public/rss/mktw_topstories",
}

# Per-ticker Yahoo Finance RSS
TICKER_FEEDS = {
    "SPY":  "https://finance.yahoo.com/rss/headline?s=SPY",
    "QQQ":  "https://finance.yahoo.com/rss/headline?s=QQQ",
    "BTC":  "https://finance.yahoo.com/rss/headline?s=BTC-USD",
    "ETH":  "https://finance.yahoo.com/rss/headline?s=ETH-USD",
    "XLF":  "https://finance.yahoo.com/rss/headline?s=XLF",
    "GLD":  "https://finance.yahoo.com/rss/headline?s=GLD",
}

# Financial lexicon for fast VADER-style scoring (no model download needed)
BULL_WORDS = {
    "surge", "rally", "soar", "gain", "rise", "beat", "exceed", "strong",
    "bullish", "upgrade", "buy", "outperform", "record", "growth", "positive",
    "recovery", "boom", "robust", "accelerate", "upside", "breakout",
}
BEAR_WORDS = {
    "crash", "plunge", "fall", "drop", "miss", "weak", "bearish", "downgrade",
    "sell", "underperform", "recession", "decline", "loss", "risk", "concern",
    "fear", "volatile", "crisis", "inflation", "hawkish", "tighten", "default",
}

# Macro concept keywords → KG Concept node names
MACRO_KEYWORDS: dict[str, list[str]] = {
    "Interest Rates":          ["rate", "fed", "fomc", "yield", "treasury", "monetary"],
    "Inflation":               ["inflation", "cpi", "ppi", "price", "consumer price"],
    "Volatility":              ["vix", "volatility", "vol", "fear"],
    "Credit Risk":             ["credit", "spread", "default", "bond", "debt"],
    "Market Momentum":         ["momentum", "trend", "breakout", "moving average"],
    "Earnings":                ["earnings", "eps", "revenue", "guidance", "profit"],
    "Geopolitical Risk":       ["war", "sanction", "geopolit", "conflict", "trade war"],
    "Liquidity":               ["liquidity", "repo", "funding", "balance sheet"],
}


def _lexicon_score(text: str) -> float:
    """Fast lexicon-based sentiment: range [-1, 1]."""
    words  = re.findall(r"\b\w+\b", text.lower())
    bull   = sum(1 for w in words if w in BULL_WORDS)
    bear   = sum(1 for w in words if w in BEAR_WORDS)
    total  = bull + bear
    if total == 0:
        return 0.0
    return round((bull - bear) / total, 3)


def _match_concepts(text: str) -> list[str]:
    """Return KG concept names whose keywords appear in the text."""
    tl = text.lower()
    return [concept for concept, kws in MACRO_KEYWORDS.items()
            if any(kw in tl for kw in kws)]


def _article_id(url: str, title: str) -> str:
    return hashlib.md5(f"{url}{title}".encode()).hexdigest()[:16]


class NewsAgent:
    def __init__(self):
        self.db = get_db()

    async def run(self, max_articles: int = 40) -> dict[str, Any]:
        """
        Fetch headlines, score sentiment, write NewsEvent nodes to KG,
        return aggregated sentiment signals per ticker and concept.
        """
        articles = await self._fetch_all(max_articles)
        if not articles:
            return {"ticker_sentiment": {}, "concept_sentiment": {}, "articles": 0}

        # Optional: enrich with LLM for top 5 articles
        if LLM_KEY and articles:
            top = sorted(articles, key=lambda a: abs(a["score"]), reverse=True)[:5]
            for art in top:
                art["llm_score"] = await self._llm_score(art["title"] + " " + art.get("summary", ""))

        # Persist to KG
        nodes_written = self._write_to_kg(articles)

        # Aggregate by ticker and concept
        ticker_sentiment: dict[str, list[float]] = {}
        concept_sentiment: dict[str, list[float]] = {}

        for art in articles:
            eff_score = art.get("llm_score", art["score"])
            for tk in art.get("tickers", []):
                ticker_sentiment.setdefault(tk, []).append(eff_score)
            for concept in art.get("concepts", []):
                concept_sentiment.setdefault(concept, []).append(eff_score)

        agg_ticker  = {k: round(float(np.mean(v)), 3) for k, v in ticker_sentiment.items()}
        agg_concept = {k: round(float(np.mean(v)), 3) for k, v in concept_sentiment.items()}

        logger.info(f"NewsAgent: {len(articles)} articles | "
                    f"tickers={list(agg_ticker.keys())} | "
                    f"{nodes_written} KG nodes written")

        return {
            "ticker_sentiment":  agg_ticker,
            "concept_sentiment": agg_concept,
            "articles":          len(articles),
            "top_headlines":     [a["title"] for a in articles[:5]],
        }

    # ── Feed fetching ─────────────────────────────────────────────────────────

    async def _fetch_all(self, max_articles: int) -> list[dict]:
        articles: list[dict] = []
        feeds = {**RSS_FEEDS, **{f"ticker_{tk}": url for tk, url in TICKER_FEEDS.items()}}

        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            for feed_name, url in feeds.items():
                try:
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    parsed = feedparser.parse(resp.text)
                    ticker_hint = feed_name.replace("ticker_", "") if "ticker_" in feed_name else None

                    for entry in parsed.entries[:8]:
                        title   = getattr(entry, "title", "")
                        summary = getattr(entry, "summary", "")
                        link    = getattr(entry, "link", "")
                        pub     = getattr(entry, "published", datetime.utcnow().isoformat())
                        text    = f"{title} {summary}"

                        art = {
                            "id":       _article_id(link, title),
                            "title":    title,
                            "summary":  summary[:400],
                            "url":      link,
                            "source":   feed_name,
                            "pub_date": str(pub)[:10],
                            "score":    _lexicon_score(text),
                            "tickers":  ([ticker_hint] if ticker_hint else []) + self._extract_tickers(text),
                            "concepts": _match_concepts(text),
                        }
                        articles.append(art)

                except Exception as e:
                    logger.debug(f"Feed {feed_name} failed: {e}")

        # Deduplicate by id, keep most recent
        seen: set[str] = set()
        unique = []
        for a in articles:
            if a["id"] not in seen:
                seen.add(a["id"])
                unique.append(a)

        return unique[:max_articles]

    def _extract_tickers(self, text: str) -> list[str]:
        known = list(TICKER_FEEDS.keys()) + ["AAPL", "MSFT", "AMZN", "NVDA", "META",
                                              "TSLA", "JPM", "GS", "GLD", "TLT"]
        found = []
        for tk in known:
            pattern = rf"\b{re.escape(tk)}\b"
            if re.search(pattern, text, re.IGNORECASE):
                found.append(tk)
        return list(set(found))

    # ── LLM enrichment ────────────────────────────────────────────────────────

    async def _llm_score(self, text: str) -> float:
        prompt = (
            "You are a financial analyst. Score the sentiment of this headline "
            "from -1.0 (very bearish) to +1.0 (very bullish) for equities. "
            "Reply with a single float only.\n\n" + text[:600]
        )
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.post(
                    f"{LLM_URL}/chat/completions",
                    json={"model": LLM_MODEL,
                          "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": 8, "temperature": 0.0},
                    headers={"Authorization": f"Bearer {LLM_KEY}"},
                )
                return float(np.clip(float(r.json()["choices"][0]["message"]["content"].strip()), -1, 1))
        except Exception:
            return 0.0

    # ── KG persistence ────────────────────────────────────────────────────────

    def _write_to_kg(self, articles: list[dict]) -> int:
        written = 0
        for art in articles:
            art_id  = art["id"]
            title   = art["title"].replace("'", "\\'")[:200]
            score   = art.get("llm_score", art["score"])
            pub     = art["pub_date"]
            try:
                # Create/update NewsEvent node
                self.db.execute(f"""
                MERGE (n:NewsEvent {{id: '{art_id}'}})
                SET n.title     = '{title}',
                    n.sentiment = {score},
                    n.source    = '{art["source"]}',
                    n.pub_date  = '{pub}',
                    n.fetched_at = '{datetime.utcnow().date()}'
                """)
                written += 1

                # Link to Ticker nodes
                for tk in art.get("tickers", []):
                    try:
                        self.db.execute(f"""
                        MATCH (t:Ticker {{symbol: '{tk}'}})
                        MATCH (n:NewsEvent {{id: '{art_id}'}})
                        MERGE (n)-[:SENTIMENT_ON {{score: {score}}}]->(t)
                        """)
                    except Exception:
                        pass

                # Link to matching Concept nodes
                for concept in art.get("concepts", []):
                    concept_esc = concept.replace("'", "\\'")
                    try:
                        self.db.execute(f"""
                        MATCH (c:Concept {{name: '{concept_esc}'}})
                        MATCH (n:NewsEvent {{id: '{art_id}'}})
                        MERGE (n)-[:RELATED_TO {{score: {score}}}]->(c)
                        """)
                    except Exception:
                        pass

            except Exception as e:
                logger.debug(f"KG write failed for article {art_id}: {e}")

        return written
