"""
Schema Registry & shared constants for GraphAlpha.
Single source of truth for regime names, schema version, and channel names.
"""

SCHEMA_VERSION = 1

# Graph-valid canonical regime names (must match master.cypher :Regime nodes)
REGIME_NAMES = [
    "Trending",
    "MeanReverting",
    "HighVolatility",
    "LowVolatility",
    "Crisis",
    "SystemicStress",
    "Recovery",
    "Neutral",
]

# Redis channel names (versioned to match Signal.schema_version)
SIGNALS_CHANNEL = "graphalpha:signals:v1"
EVENTS_CHANNEL = "graphalpha:events"
HEARTBEAT_KEY = "graphalpha:heartbeat"


def is_valid_regime(name: str) -> bool:
    return name in REGIME_NAMES


def validate_regime(name: str) -> str:
    if not is_valid_regime(name):
        raise ValueError(f"Invalid regime '{name}'. Allowed: {REGIME_NAMES}")
    return name
