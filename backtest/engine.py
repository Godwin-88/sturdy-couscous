"""
Walk-Forward Backtest Engine — GraphAlpha
Full quant-grade output: trade log, drawdown series, per-strategy breakdown,
benchmark comparison, walk-forward windows, progress streaming via Redis.
"""
import argparse, json, os, sys
from datetime import datetime

import numpy as np
import pandas as pd
import redis
import yfinance as yf
from arch import arch_model
from gqlalchemy import Memgraph
from loguru import logger

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
from metrics import summary

TICKERS       = ["SPY", "QQQ", "XLF", "XLE"]
REBAL_FREQ    = 5
TRAIN_WINDOW  = 252
FEE_PCT       = 0.0010
SLIP_PCT      = 0.0005
WF_TRAIN_DAYS = 252
WF_TEST_DAYS  = 63

STRATEGY_TICKER_MAP = {
    "GARCHVolatility":     "SPY",
    "MomentumOverlay":     "QQQ",
    "ValueMeanReversion":  "XLF",
    "TrendFollowing":      "SPY",
    "VolatilityArbitrage": "XLE",
    "CrisisAlpha":         "SPY",
}


def _redis():
    try:
        return redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True, socket_connect_timeout=2,
        )
    except Exception:
        return None


def _progress(r, pct, msg):
    if r:
        r.set("graphalpha:backtest_progress", json.dumps({"pct": pct, "msg": msg}))
    logger.info(f"[{pct:3d}%] {msg}")


def load_prices(start, end):
    extended = str(pd.Timestamp(start) - pd.DateOffset(years=1))[:10]
    raw = yf.download(TICKERS + ["^VIX"], start=extended, end=end,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw["Close"]
    return raw.ffill().dropna(how="all")


def classify_regime(prices, idx):
    w   = prices.iloc[max(0, idx - 252):idx]
    spy = w.get("SPY", pd.Series(dtype=float))
    vix = w.get("^VIX", pd.Series(dtype=float))
    if spy.empty or len(spy) < 22:
        return "LowVolatility"
    vix_now = float(vix.iloc[-1]) if not vix.empty else 20.0
    ret_21  = spy.pct_change(21).iloc[-1]
    vol_21  = spy.pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)
    ma_200  = spy.rolling(200).mean().iloc[-1] if len(spy) >= 200 else spy.mean()
    if vix_now > 35:           return "SystemicStress"
    if vix_now > 25 and ret_21 < -0.05: return "Crisis"
    if vol_21 > 0.25:          return "HighVolatility"
    if spy.iloc[-1] < ma_200 * 0.95: return "Crisis"
    if ret_21 > 0.03 and vix_now < 18: return "Trending"
    return "LowVolatility"


_kg_cache: dict = {}

def get_active_strategies(regime, use_graph):
    if not use_graph:
        return ["MomentumOverlay"]
    if regime in _kg_cache:
        return _kg_cache[regime]
    try:
        db = Memgraph(host=os.getenv("MEMGRAPH_HOST", "localhost"),
                      port=int(os.getenv("MEMGRAPH_PORT", 7687)))
        rows = list(db.execute_and_fetch(
            f"MATCH (r:Regime {{name:'{regime}'}})<-[:ACTIVATED_BY]-(s:Strategy) "
            f"WHERE s.status='active' RETURN s.name AS name"))
        result = [r["name"] for r in rows] or ["MomentumOverlay"]
    except Exception as e:
        logger.warning(f"KG query failed ({regime}): {e}")
        result = ["MomentumOverlay"]
    _kg_cache[regime] = result
    return result


def compute_signal(strategy, prices, idx):
    hist   = prices.iloc[max(0, idx - TRAIN_WINDOW):idx]
    ticker = STRATEGY_TICKER_MAP.get(strategy, "SPY")
    if ticker not in hist.columns:
        ticker = "SPY"
    s = hist[ticker]
    if len(s) < 22:
        return ticker, 0.0
    if "GARCH" in strategy or "Vol" in strategy:
        try:
            rets = np.log(s + 1e-10).diff().dropna() * 100
            fit  = arch_model(rets, vol="Garch", p=1, q=1).fit(disp="off")
            av   = float(fit.conditional_volatility.iloc[-1]) * np.sqrt(252)
            return ticker, float(np.clip(-((av - 0.15) / 0.30), -1, 1))
        except Exception:
            return ticker, 0.0
    if "Momentum" in strategy or "Trend" in strategy:
        if len(s) < 252: return ticker, 0.0
        score = float(np.clip((s.pct_change(252).iloc[-1] - s.pct_change(21).iloc[-1]) * 5, -1, 1))
        return ticker, score
    if "Value" in strategy or "MeanReversion" in strategy:
        ma50  = s.rolling(50).mean().iloc[-1]
        ma200 = s.rolling(200).mean().iloc[-1] if len(s) >= 200 else ma50
        score = float(np.clip((ma200 - s.iloc[-1]) / (ma200 + 1e-10) * 10, -1, 1))
        return ticker, score
    if "Crisis" in strategy:
        vix = hist.get("^VIX", pd.Series(dtype=float))
        if vix.empty: return ticker, 0.0
        return ticker, float(np.clip((float(vix.iloc[-1]) - 25) / 20, 0, 1))
    return ticker, 0.0


def run_period(prices, start_idx, end_idx, capital, use_graph,
               rebal_freq, fee_pct, slip_pct, r=None,
               prog_offset=0, prog_range=100, label=""):
    cash     = capital
    holdings = {t: 0.0 for t in TICKERS}
    nav_series, date_series, trade_log, regime_log = [], [], [], []
    strat_pnl, strat_n, strat_wins = {}, {}, {}
    open_pos: dict = {}
    total_steps = max((end_idx - start_idx) // rebal_freq, 1)

    for step, i in enumerate(range(start_idx, end_idx, rebal_freq)):
        today   = prices.index[i]
        today_p = prices.iloc[i]
        nav     = cash + sum(holdings[t] * float(today_p.get(t, 0)) for t in TICKERS)
        nav_series.append(round(nav, 2))
        date_series.append(str(today.date()))
        regime     = classify_regime(prices, i)
        strategies = get_active_strategies(regime, use_graph)
        regime_log.append(regime)

        ticker_sigs: dict = {}
        for strat in strategies:
            tk, score = compute_signal(strat, prices, i)
            ticker_sigs.setdefault(tk, []).append((strat, score))

        target_w: dict = {}
        for tk, sigs in ticker_sigs.items():
            avg = sum(s for _, s in sigs) / len(sigs)
            if avg > 0.15:  target_w[tk] = min(0.30, avg * 0.30)
            elif avg < -0.15: target_w[tk] = 0.0

        for tk in TICKERS:
            price = float(today_p.get(tk, 0))
            if price <= 0: continue
            tgt   = nav * target_w.get(tk, 0.0)
            cur   = holdings[tk] * price
            delta = tgt - cur
            if abs(delta) < max(10.0, nav * 0.002): continue
            fill    = price * (1 + slip_pct * np.sign(delta))
            qty_d   = delta / fill
            fee     = abs(qty_d) * fill * fee_pct
            direction = "buy" if delta > 0 else "sell"
            holdings[tk] += qty_d
            cash -= qty_d * fill + fee
            strat_name = ticker_sigs.get(tk, [("unknown", 0)])[0][0]
            if direction == "buy" and tk not in open_pos:
                open_pos[tk] = {"entry_date": str(today.date()), "entry_price": round(fill, 4),
                                "qty": round(holdings[tk], 6), "strategy": strat_name}
            elif direction == "sell" and tk in open_pos:
                ent = open_pos.pop(tk)
                pnl = round((fill - ent["entry_price"]) * abs(qty_d) - fee, 4)
                hd  = (today - pd.Timestamp(ent["entry_date"])).days
                trade_log.append({"ticker": tk, "strategy": ent["strategy"],
                    "direction": direction, "entry_date": ent["entry_date"],
                    "exit_date": str(today.date()), "entry_price": ent["entry_price"],
                    "exit_price": round(fill, 4), "qty": round(abs(qty_d), 6),
                    "pnl": pnl, "fee": round(fee, 4), "hold_days": hd, "regime": regime})
                strat_pnl[ent["strategy"]]  = strat_pnl.get(ent["strategy"], 0.0) + pnl
                strat_n[ent["strategy"]]    = strat_n.get(ent["strategy"], 0) + 1
                if pnl > 0:
                    strat_wins[ent["strategy"]] = strat_wins.get(ent["strategy"], 0) + 1

        if step % 10 == 0:
            pct = prog_offset + int(step / total_steps * prog_range)
            _progress(r, pct, f"{label}Simulating {today.date()} | NAV ${nav:,.0f} | {regime}")

    nav_arr = np.array(nav_series)
    cum     = nav_arr / (nav_arr[0] + 1e-10)
    peak    = np.maximum.accumulate(cum)
    dd_ser  = ((cum - peak) / (peak + 1e-10) * 100).tolist()

    spy_raw  = prices["SPY"].iloc[start_idx:end_idx].ffill().values
    spy_rets = np.diff(spy_raw) / (spy_raw[:-1] + 1e-10)
    returns  = np.diff(nav_arr) / (nav_arr[:-1] + 1e-10)
    ml       = min(len(returns), len(spy_rets))
    stats    = summary(returns[:ml], spy_rets[:ml])
    spy_nav  = (spy_raw / (spy_raw[0] + 1e-10) * capital).tolist()

    sb = []
    for strat in sorted(strat_pnl):
        n = strat_n.get(strat, 0)
        w = strat_wins.get(strat, 0)
        sb.append({"strategy": strat, "total_pnl": round(strat_pnl[strat], 2),
                   "n_trades": n, "win_rate": round(w/n, 3) if n else 0.0,
                   "avg_pnl": round(strat_pnl[strat]/n, 2) if n else 0.0})

    from collections import Counter
    rd = {k: round(v/len(regime_log), 3) for k, v in Counter(regime_log).items()} if regime_log else {}

    gross_p = sum(t["pnl"] for t in trade_log if t["pnl"] > 0)
    gross_l = abs(sum(t["pnl"] for t in trade_log if t["pnl"] < 0))

    return {**stats,
        "final_nav": round(float(nav_arr[-1]), 2), "use_graph": use_graph,
        "start": date_series[0] if date_series else "", "end": date_series[-1] if date_series else "",
        "equity_curve":      [{"date": d, "nav": n} for d, n in zip(date_series, nav_series)],
        "benchmark_curve":   [{"date": d, "nav": round(float(n), 2)} for d, n in zip(date_series[:len(spy_nav)], spy_nav)],
        "drawdown_series":   [{"date": d, "dd": round(dd, 2)} for d, dd in zip(date_series, dd_ser)],
        "trade_log": trade_log, "strategy_breakdown": sb,
        "regime_distribution": rd, "walk_forward_windows": [],
        "n_trades": len(trade_log),
        "win_rate": round(sum(1 for t in trade_log if t["pnl"] > 0)/len(trade_log), 3) if trade_log else 0.0,
        "avg_hold_days": round(sum(t["hold_days"] for t in trade_log)/len(trade_log), 1) if trade_log else 0.0,
        "profit_factor": round(gross_p/gross_l, 3) if gross_l > 0 else 0.0}


def walk_forward_backtest(prices, start, end, capital, use_graph,
                          rebal_freq, fee_pct, slip_pct, r=None):
    all_dates  = prices.index
    start_idx  = all_dates.searchsorted(pd.Timestamp(start))
    end_idx    = min(all_dates.searchsorted(pd.Timestamp(end)) + 1, len(all_dates))

    windows, i, wid = [], start_idx, 0
    while i + WF_TRAIN_DAYS + WF_TEST_DAYS <= end_idx:
        te = min(i + WF_TRAIN_DAYS + WF_TEST_DAYS, end_idx)
        windows.append({"id": wid,
            "train_start": str(all_dates[i].date()),
            "train_end":   str(all_dates[i + WF_TRAIN_DAYS - 1].date()),
            "test_start":  str(all_dates[i + WF_TRAIN_DAYS].date()),
            "test_end":    str(all_dates[te - 1].date()),
            "test_s_idx":  i + WF_TRAIN_DAYS, "test_e_idx": te})
        i += WF_TEST_DAYS; wid += 1

    if not windows:
        _progress(r, 5, "Short range — single period mode")
        res = run_period(prices, start_idx, end_idx, capital, use_graph,
                         rebal_freq, fee_pct, slip_pct, r, 5, 90)
        res["walk_forward_windows"] = []
        _progress(r, 100, "Complete")
        return res

    _progress(r, 2, f"Walk-forward: {len(windows)} windows")
    agg_trades, agg_nav, agg_bm, agg_dd = [], [], [], []
    agg_sp, agg_sn, agg_sw = {}, {}, {}
    wf_rows, running_cap = [], capital

    for wi, win in enumerate(windows):
        p0 = 5 + int(wi / len(windows) * 85)
        p1 = 5 + int((wi + 1) / len(windows) * 85)
        lbl = f"WF {wi+1}/{len(windows)} | "
        period = run_period(prices, win["test_s_idx"], win["test_e_idx"],
                            running_cap, use_graph, rebal_freq, fee_pct, slip_pct,
                            r, p0, p1 - p0, lbl)
        running_cap = period["final_nav"]
        agg_trades += period["trade_log"]
        agg_nav    += period["equity_curve"]
        agg_bm     += period["benchmark_curve"]
        agg_dd     += period["drawdown_series"]
        for sb in period["strategy_breakdown"]:
            agg_sp[sb["strategy"]] = agg_sp.get(sb["strategy"], 0) + sb["total_pnl"]
            agg_sn[sb["strategy"]] = agg_sn.get(sb["strategy"], 0) + sb["n_trades"]
            agg_sw[sb["strategy"]] = agg_sw.get(sb["strategy"], 0) + int(sb["win_rate"] * sb["n_trades"])
        wf_rows.append({**{k: win[k] for k in ["id","train_start","train_end","test_start","test_end"]},
            "sharpe_ratio": period["sharpe_ratio"], "total_return": period["total_return"],
            "max_drawdown": period["max_drawdown"], "n_trades": period["n_trades"],
            "final_nav": period["final_nav"]})

    nav_vals = [p["nav"] for p in agg_nav]
    bm_vals  = [p["nav"] for p in agg_bm]
    rets  = np.diff(nav_vals) / (np.array(nav_vals[:-1]) + 1e-10)
    brets = np.diff(bm_vals)  / (np.array(bm_vals[:-1])  + 1e-10)
    ml    = min(len(rets), len(brets))
    stats = summary(rets[:ml], brets[:ml])

    sb_agg = []
    for strat in sorted(agg_sp):
        n = agg_sn.get(strat, 0); w = agg_sw.get(strat, 0)
        sb_agg.append({"strategy": strat, "total_pnl": round(agg_sp[strat], 2),
            "n_trades": n, "win_rate": round(w/n, 3) if n else 0.0,
            "avg_pnl": round(agg_sp[strat]/n, 2) if n else 0.0})

    gp = sum(t["pnl"] for t in agg_trades if t["pnl"] > 0)
    gl = abs(sum(t["pnl"] for t in agg_trades if t["pnl"] < 0))
    _progress(r, 98, f"{len(agg_trades)} trades | final NAV ${running_cap:,.0f}")

    return {**stats,
        "final_nav": round(running_cap, 2), "use_graph": use_graph,
        "start": agg_nav[0]["date"] if agg_nav else start,
        "end":   agg_nav[-1]["date"] if agg_nav else end,
        "equity_curve": agg_nav, "benchmark_curve": agg_bm,
        "drawdown_series": agg_dd, "trade_log": agg_trades,
        "strategy_breakdown": sb_agg, "walk_forward_windows": wf_rows,
        "regime_distribution": {},
        "n_trades": len(agg_trades),
        "win_rate": round(sum(1 for t in agg_trades if t["pnl"] > 0)/len(agg_trades), 3) if agg_trades else 0.0,
        "avg_hold_days": round(sum(t["hold_days"] for t in agg_trades)/len(agg_trades), 1) if agg_trades else 0.0,
        "profit_factor": round(gp/gl, 3) if gl > 0 else 0.0}


def generate_suggestions(result, regime, r):
    candidates = [s for s in result.get("strategy_breakdown", [])
                  if s["total_pnl"] > 0 and s["win_rate"] > 0.5 and s["n_trades"] >= 3]
    candidates.sort(key=lambda x: x["total_pnl"], reverse=True)
    suggestions = []
    for c in candidates[:5]:
        strat = c["strategy"]; tk = STRATEGY_TICKER_MAP.get(strat, "SPY")
        suggestions.append({"id": f"{strat}_{tk}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "strategy": strat, "ticker": tk, "direction": "buy", "regime": regime,
            "rationale": f"{strat}: {c['n_trades']} trades, {c['win_rate']*100:.0f}% win rate, ${c['total_pnl']:,.2f} P&L",
            "backtest_pnl": c["total_pnl"], "backtest_trades": c["n_trades"],
            "win_rate": c["win_rate"], "status": "pending",
            "created_at": datetime.utcnow().isoformat()})
    if r and suggestions:
        r.set("graphalpha:trade_suggestions", json.dumps(suggestions))
    return suggestions


def main():
    global REBAL_FREQ, TRAIN_WINDOW, FEE_PCT, SLIP_PCT
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",        default="2021-01-01")
    parser.add_argument("--end",          default="2023-12-31")
    parser.add_argument("--capital",      type=float, default=10000.0)
    parser.add_argument("--rebal-freq",   type=int,   default=REBAL_FREQ)
    parser.add_argument("--train-window", type=int,   default=TRAIN_WINDOW)
    parser.add_argument("--fee-pct",      type=float, default=FEE_PCT)
    parser.add_argument("--slip-pct",     type=float, default=SLIP_PCT)
    parser.add_argument("--use-graph",    dest="use_graph", action="store_true")
    parser.add_argument("--no-graph",     dest="use_graph", action="store_false")
    parser.set_defaults(use_graph=True)
    args = parser.parse_args()
    REBAL_FREQ = args.rebal_freq; TRAIN_WINDOW = args.train_window
    FEE_PCT = args.fee_pct;       SLIP_PCT = args.slip_pct

    r = _redis()
    if r: r.set("graphalpha:backtest_progress", json.dumps({"pct": 0, "msg": "Loading prices…"}))
    _progress(r, 1, f"Loading prices {args.start} → {args.end}")
    prices = load_prices(args.start, args.end)
    result = walk_forward_backtest(prices, args.start, args.end, args.capital,
                                   args.use_graph, REBAL_FREQ, FEE_PCT, SLIP_PCT, r)
    end_idx = prices.index.searchsorted(pd.Timestamp(args.end))
    regime  = classify_regime(prices, min(end_idx, len(prices) - 1))
    result["suggestions"] = generate_suggestions(result, regime, r)
    _progress(r, 100, "Done")
    def _clean(v):
        if isinstance(v, float) and (v != v or v == float("inf") or v == float("-inf")):
            return None
        if isinstance(v, dict):
            return {kk: _clean(vv) for kk, vv in v.items()}
        if isinstance(v, list):
            return [_clean(i) for i in v]
        return v
    print(json.dumps(_clean(result), default=str))

if __name__ == "__main__":
    main()
