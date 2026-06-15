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
        "TLT",
        "GLD",
        "BTC-USD",
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
    trade_threshold: float = 0.15

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
    memgraph_host: str = os.getenv("MEMGRAPH_HOST", "localhost")
    memgraph_port: int = int(os.getenv("MEMGRAPH_PORT", "7687"))

    # KB formula cost model note (backtest-only approximation)
    ibkr_fill_mode: str = "backtest_simulated"
