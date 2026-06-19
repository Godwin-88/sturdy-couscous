import asyncio
import json
import uuid
from datetime import datetime
from common.redis_publisher import publish_signal

async def main():
    signal = {
        "schema_version": 1,
        "cycle_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "regime": "Trending",
        "strategy": "MomentumOverlay",
        "ticker": "BTC-USD",
        "venue": "kraken",
        "venue_symbol": "BTCUSD",
        "asset_class": "crypto",
        "direction": "buy",
        "score": 0.8,
        "quant_score": 0.7,
        "sentiment_score": 0.9,
        "news_overlay": 0.1,
        "macro_overlay": 0.0,
        "kg_formula_contribution": 0.0,
        "graph_path": ["Concept A", "Concept B"],
        "contradiction_blocked": False
    }
    print(f"Publishing signal for {signal['ticker']}...")
    success = await publish_signal(signal)
    if success:
        print("Signal published successfully!")
    else:
        print("Failed to publish signal.")

if __name__ == "__main__":
    asyncio.run(main())
