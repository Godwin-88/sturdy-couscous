from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class BacktestConfig:
    # Data / universe
    kg_signal_tickers: tuple[str, ...] = (
        "SPY",
        "QQQ",
        "XLF",
        "XLE",
        "GLD",
    )

    # Cadence
    rebal_freq: int = 5
    train_window: int = 252
    wf_train_days: int = 252
    wf_test_days: int = 63

    # Fusion
    quant_weight: float = 0.70
    sentiment_weight: float = 0.30
    score_clip: float = 1.0
    trade_threshold: float = float(os.getenv("BT_TRADE_THRESHOLD", "0.15"))

    # Fees / slippage (env-overridable)
    crypto_fee_pct: float = float(os.getenv("BACKTEST_CRYPTO_FEE_PCT", "0.0026"))
    crypto_slip_pct: float = float(os.getenv("BACKTEST_CRYPTO_SLIP_PCT", "0.0010"))
    equity_fee_pct: float = float(os.getenv("BACKTEST_EQUITY_FEE_PCT", "0.0010"))
    equity_slip_pct: float = float(os.getenv("BACKTEST_EQUITY_SLIP_PCT", "0.0005"))

    # Price data
    interval: Literal["1d", "1h"] = "1d"

    # Schema
    schema_version: int = 1
    max_schema_version: int = 1

    # KG
    graph_db_host: str = os.getenv("NEO4J_HOST", os.getenv("MEMGRAPH_HOST", "localhost"))
    graph_db_port: int = int(os.getenv("NEO4J_PORT", os.getenv("MEMGRAPH_PORT", "7687")))
    graph_db_user: str = os.getenv("NEO4J_USER", "neo4j")
    graph_db_password: str = os.getenv("NEO4J_PASSWORD", "")

    # KB formula cost model note (backtest-only approximation)
    ibkr_fill_mode: str = "backtest_simulated"


cfg = BacktestConfig()
