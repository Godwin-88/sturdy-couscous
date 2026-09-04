"""
GraphAlpha FastAPI Gateway
WebSocket endpoint broadcasts live agent events from Redis pub/sub.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from prometheus_client import make_asgi_app

from routes.agent     import router as agent_router
from routes.signals   import router as signals_router
from routes.positions import router as positions_router
from routes.graph     import router as graph_router
from routes.backtest  import router as backtest_router
from routes.market        import router as market_router
from routes.intelligence  import router as intelligence_router
from routes.research      import router as research_router
from routes.analytics     import router as analytics_router
from routes.alpaca        import router as alpaca_router
from routes.options       import router as options_router
from routes.chat          import router as chat_router
from routes.crypto         import router as crypto_router
from routes.settings       import router as settings_router

load_dotenv()

REDIS_URL = (
    f"redis://{os.getenv('REDIS_HOST', 'redis')}:"
    f"{os.getenv('REDIS_PORT', 6379)}"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("GraphAlpha API starting")
    yield
    logger.info("GraphAlpha API shutting down")


app = FastAPI(
    title="GraphAlpha",
    description="Knowledge Graph-Grounded Autonomous Trading Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics sub-app
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

app.include_router(agent_router)
app.include_router(signals_router)
app.include_router(positions_router)
app.include_router(graph_router)
app.include_router(backtest_router)
app.include_router(market_router)
app.include_router(intelligence_router)
app.include_router(research_router)
app.include_router(analytics_router)
app.include_router(alpaca_router)
app.include_router(options_router)
app.include_router(chat_router)
app.include_router(crypto_router)
app.include_router(settings_router)


# ── Global exception handler: ensures CORS headers on all error responses ─────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {exc}"},
    )


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# ── WebSocket: live agent event stream ────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, message: str):
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()


@app.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    await manager.connect(ws)
    r = aioredis.from_url(REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.subscribe("graphalpha:events")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await manager.broadcast(message["data"])
    except WebSocketDisconnect:
        manager.disconnect(ws)
    finally:
        await pubsub.unsubscribe("graphalpha:events")
        await r.aclose()


@app.websocket("/ws/signals")
async def websocket_signals(ws: WebSocket):
    """Pushes latest signals every 5 seconds."""
    await manager.connect(ws)
    r = aioredis.from_url(REDIS_URL)
    try:
        while True:
            raw = await r.get("graphalpha:latest_signals")
            if raw:
                await ws.send_text(raw)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    finally:
        await r.aclose()
