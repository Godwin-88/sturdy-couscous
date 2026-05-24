"""
Intelligence endpoints — news sentiment and macro calendar data
cached by the agent loop into Redis.
"""

import json
import os
from fastapi import APIRouter
import redis

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


@router.get("/news")
def get_news():
    """Latest news sentiment snapshot written by NewsAgent."""
    r   = _redis()
    raw = r.get("graphalpha:news_latest")
    if not raw:
        return {
            "ticker_sentiment":  {},
            "concept_sentiment": {},
            "articles":          0,
            "top_headlines":     [],
        }
    return json.loads(raw)


@router.get("/macro")
def get_macro():
    """Upcoming macro events and pre-event signals written by MacroCalendarAgent."""
    r   = _redis()
    raw = r.get("graphalpha:macro_calendar")
    if not raw:
        return {"events": 0, "pre_event_signals": {}, "upcoming": []}
    return json.loads(raw)
