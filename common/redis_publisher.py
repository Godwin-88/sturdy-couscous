import asyncio
import json
import os
from typing import Any, Optional

import redis.asyncio as aioredis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
SIGNALS_CHANNEL = os.getenv("REDIS_SIGNALS_CHANNEL", "graphalpha:signals:v1")
HEARTBEAT_KEY = "graphalpha:heartbeat"


def _url() -> str:
    return f"redis://{REDIS_HOST}:{REDIS_PORT}"


async def publish_signal(signal: dict[str, Any]) -> bool:
    """
    Publish a single Schema v1 signal to the versioned Redis channel.
    Returns True on success, False on failure (non-fatal).
    """
    try:
        r = aioredis.from_url(_url(), socket_connect_timeout=2)
        await r.publish(SIGNALS_CHANNEL, json.dumps(signal, ensure_ascii=False, default=str))
        await r.aclose()
        return True
    except Exception:
        return False


async def publish_heartbeat(cycle_id: Optional[str], status: str) -> None:
    """
    Update heartbeat so operators can distinguish 'no signals this cycle'
    from 'agent-worker is down'.
    """
    try:
        r = aioredis.from_url(_url(), socket_connect_timeout=2)
        await r.set(
            HEARTBEAT_KEY,
            json.dumps({"cycle_id": cycle_id, "status": status}),
            ex=30,
        )
        await r.aclose()
    except Exception:
        pass


async def publish_signal_batch(signals: list[dict[str, Any]]) -> int:
    """
    Publish a batch of signals. Returns count of successful publishes.
    Failed publishes are logged but do not raise.
    """
    count = 0
    for sig in signals:
        if await publish_signal(sig):
            count += 1
    return count
