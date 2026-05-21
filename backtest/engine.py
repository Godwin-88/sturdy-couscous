"""
Walk-Forward Backtest Engine
Simulates the GraphAlpha agent loop over historical data.
Supports KG-grounded vs ungrounded (ablation) modes.

Usage:
  python engine.py --start 2021-01-01 --end 2023-12-31 --capital 10000 --use-graph
  python engine.py --start 2021-01-01 --end 2023-12-31 --capital 10000 --no-graph
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
from arch import arch_model
from gqlalchemy import Memgraph
from loguru import logger

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..","agent"))
from metrics import summary

TICKERS        = ["SPY", "QQQ", "XLF", "XLE"]
REBAL_FREQ     = 5       # days between rebalance
TRAIN_WINDOW   = 252     # days of history for model training
FEE_PCT        = 0.0026  # Kraken taker
SLIP_PCT       = 0.0005


def load_prices(start: str, end: str) -> pd.DataFrame:
    # Extra history for warm-up
    extended_start = str(pd.Timestamp(start) - pd.DateOffset(years=1))[:10]
    raw = yf.download(TICKERS + ["^VIX"], start=extended_start,
                      end=end, auto_adjust=True, progress=False)
    return raw["Close"].dropna()


def classify_regime(prices: pd.DataFrame, idx: int) -> str:
    window = prices.iloc[max(0, idx-252):idx]
    spy  = window["SPY"]
    vix  = window["^VIX"]
    if vix.empty or spy.empty:
        return "LowVolatility"
    vix_now = vix.iloc[-1]
    ret_21   = spy.pct_change(21).iloc[-1]
    vol_21   = spy.pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)
    ma_200   = spy.rolling(200).mean().iloc[-1]
    if vix_now > 35:
        return "SystemicStress"
    if vix_now > 25 and ret_21 < -0.05:
        return "CrisisRegime"
    if vol_21 > 0.25:
        return "HighVolatility"
    if spy.iloc[-1] < ma_200 * 0.95:
        return "BearMarket"
    if ret_21 > 0.03 and vix_now < 18:
        return "BullMarket"
    return "LowVolatility"


def get_active_strategies(regime: str, use_graph: bool) -> list[str]:
    if not use_graph:
        return ["MomentumOverlay"]  # ungrounded baseline: always use momentum
    try:
        db = Memgraph(
            host=os.getenv("MEMGRAPH_HOST", "memgraph"),
            port=int(os.getenv("MEMGRAPH_PORT", 7687)),
        )
        query = f"""
        MATCH (r:Regime {{name: '{regime}'}})<-[:ACTIVATED_BY]-(s:Strategy)
        WHERE s.status = 'active'
        RETURN s.name AS name
        """
        return [r["name"] for r in db.execute_and_fetch(query)]
    except Exception as e:
        logger.warning(f"Graph query failed, falling back to momentum: {e}")
        return ["MomentumOverlay"]


def compute_signal(strategy: str, prices: pd.DataFrame,
                   idx: int, use_graph: bool) -> float:
    hist = prices.iloc[max(0, idx-TRAIN_WINDOW):idx]
    if "GARCH" in strategy or "Vol" in strategy:
        try:
            rets = np.log(hist["SPY"]).diff().dropna() * 100
            fit  = arch_model(rets, vol="Garch", p=1, q=1).fit(disp="off")
            ann_vol = fit.conditional_volatility.iloc[-1] * np.sqrt(252)
            return -min(1.0, (ann_vol - 0.15) / 0.30)
        except Exception:
            return 0.0
    # Default momentum
    spy = hist["SPY"]
    if len(spy) < 252:
        return 0.0
    mom = spy.pct_change(252).iloc[-1] - spy.pct_change(21).iloc[-1]
    return float(np.clip(mom * 5, -1, 1))


def backtest(start: str, end: str, capital: float, use_graph: bool) -> dict:
    prices = load_prices(start, end)
    start_idx = prices.index.searchsorted(pd.Timestamp(start))
    end_idx   = prices.index.searchsorted(pd.Timestamp(end))

    cash     = capital
    holdings = {t: 0.0 for t in TICKERS}
    nav_series = []
    dates      = []

    for i in range(start_idx, end_idx, REBAL_FREQ):
        today   = prices.index[i]
        today_p = prices.iloc[i]

        # Mark-to-market
        nav = cash + sum(holdings[t] * today_p.get(t, 0) for t in TICKERS)
        nav_series.append(nav)
        dates.append(today)

        regime     = classify_regime(prices, i)
        strategies = get_active_strategies(regime, use_graph)

        # Aggregate signals
        scores: dict[str, float] = {}
        for s in strategies:
            sig = compute_signal(s, prices, i, use_graph)
            ticker = "SPY"   # simplified: map strategy → ticker
            scores[ticker] = scores.get(ticker, 0.0) + sig / len(strategies)

        # Rebalance
        target_weights = {}
        for ticker, score in scores.items():
            if score > 0.2:
                target_weights[ticker] = min(0.25, score * 0.25)
            elif score < -0.2:
                target_weights[ticker] = 0.0

        for ticker in TICKERS:
            target_weight = target_weights.get(ticker, 0.0)
            target_notional = nav * target_weight
            current_notional = holdings[ticker] * today_p.get(ticker, 0)
            delta = target_notional - current_notional
            price = today_p.get(ticker, 0)
            if price > 0 and abs(delta) > 10:
                fill = price * (1 + SLIP_PCT * np.sign(delta))
                qty_delta = delta / fill
                cost = abs(qty_delta) * fill * FEE_PCT
                holdings[ticker] += qty_delta
                cash -= (qty_delta * fill + cost)

    nav_arr = np.array(nav_series)
    returns = np.diff(nav_arr) / nav_arr[:-1]

    # Buy-and-hold SPY benchmark
    spy_prices = prices["SPY"].iloc[start_idx:end_idx:REBAL_FREQ].values
    spy_rets   = np.diff(spy_prices) / spy_prices[:-1]

    min_len = min(len(returns), len(spy_rets))
    metrics = summary(returns[:min_len], spy_rets[:min_len])
    metrics["final_nav"]    = round(float(nav_arr[-1]), 2)
    metrics["use_graph"]    = use_graph
    metrics["start"]        = start
    metrics["end"]          = end
    metrics["regime_sample"] = classify_regime(prices, end_idx - 1)

    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",   default="2021-01-01")
    parser.add_argument("--end",     default="2023-12-31")
    parser.add_argument("--capital", type=float, default=10000.0)
    parser.add_argument("--use-graph",  dest="use_graph", action="store_true")
    parser.add_argument("--no-graph",   dest="use_graph", action="store_false")
    parser.set_defaults(use_graph=True)
    args = parser.parse_args()

    logger.info(f"Running backtest: {args.start} → {args.end} | "
                f"graph={'yes' if args.use_graph else 'no'}")
    result = backtest(args.start, args.end, args.capital, args.use_graph)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
