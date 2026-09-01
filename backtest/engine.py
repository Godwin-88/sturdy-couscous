"""
Walk-Forward Backtest Engine — GraphAlpha
Full quant-grade output: trade log, drawdown series, per-strategy breakdown,
benchmark comparison, walk-forward windows, progress streaming via Redis.
"""
import argparse, json, os, sys, time
from datetime import datetime
import numpy as np
import pandas as pd
import redis
import yfinance as yf
from arch import arch_model
from common.graph import get_db
from loguru import logger

_start_time = time.time()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
from metrics import summary

TICKERS       = os.getenv("BT_TICKERS", "SPY,QQQ,XLF,XLE,GLD").split(",")
REBAL_FREQ    = 5
TRAIN_WINDOW  = 252
FEE_PCT       = 0.0010
SLIP_PCT      = 0.0005
WF_TRAIN_DAYS = 252
WF_TEST_DAYS  = 63
BT_TRADE_THRESHOLD = float(os.getenv("BT_TRADE_THRESHOLD", "0.05"))
BENCHMARK = "SPY"
RF_RATE = 0.05

STRATEGY_TICKER_MAP = {
    "GARCHVolatility":      "SPY",
    "MomentumOverlay":      "QQQ",
    "ValueMeanReversion":   "XLF",
    "TrendFollowing":       "XLE",
    "VolatilityArbitrage":  "SPY",
    "CrisisAlpha":          "GLD",
    "BayesianMacroRisk":    "SPY",
    "DYNOTEARSContagion":   "XLF",
    "ClimatePhysicalRisk":  "XLE",
}

def _redis():
    try:
        return redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True, socket_connect_timeout=2,
        )
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        return None

def _is_cancelled(r):
    if not r: return False
    return r.get("graphalpha:backtest_cancel") == "1"

def _progress(r, pct, msg, window=None):
    if r:
        elapsed = time.time() - _start_time
        eta_s = (elapsed / max(pct, 1)) * (100 - pct) if pct > 0 else 0
        payload = {
            "pct": pct,
            "msg": msg,
            "eta": f"{int(eta_s // 60)}m {int(eta_s % 60)}s" if eta_s > 0 else "calculating...",
            "window": window
        }
        r.set("graphalpha:backtest_progress", json.dumps(payload))
        logger.info(f"[{pct:3d}%] {msg}")

def load_prices(start, end):
    """Load price data with comprehensive error handling"""
    extended = str(pd.Timestamp(start) - pd.DateOffset(years=1))[:10]
    logger.info(f"Loading prices for {TICKERS} from {extended} to {end}")
    
    try:
        # Separate crypto and equity tickers
        equity_tickers = [t for t in TICKERS if not (t.upper().endswith("-USD") or t.upper() in {"BTC-USD", "ETH-USD"})]
        crypto_tickers = [t for t in TICKERS if t.upper().endswith("-USD") or t.upper() in {"BTC-USD", "ETH-USD"}]
        
        # Fetch equity data
        raw = pd.DataFrame()
        if equity_tickers:
            tickers_to_fetch = equity_tickers + [BENCHMARK, "^VIX"]
            tickers_to_fetch = list(set(tickers_to_fetch))  # Remove duplicates
            logger.info(f"Fetching equity tickers: {tickers_to_fetch}")
            raw = yf.download(tickers_to_fetch, start=extended, end=end,
                            auto_adjust=True, progress=False)
            
            if raw.empty:
                logger.error("yfinance returned empty DataFrame for equity tickers")
                raise ValueError("No equity data available")
            
            if isinstance(raw.columns, pd.MultiIndex):
                raw = raw["Close"]
        
        # Fetch crypto data separately
        if crypto_tickers:
            logger.info(f"Fetching crypto tickers: {crypto_tickers}")
            for ct in crypto_tickers:
                try:
                    symbol = ct.upper().replace("-", "").replace("USD", "")
                    if symbol == "BTC":
                        symbol = "XBT"
                    pair = f"{symbol}USD" if symbol != "XBT" else "XBTUSD"
                    url = f"https://api.exchange.coinbase.com/products/{pair}/candles?granularity=86400"
                    
                    import urllib.request
                    with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as resp:
                        data = json.loads(resp.read().decode())
                    
                    if data:
                        ts = pd.to_datetime([r[0] for r in data], unit='s', utc=True)
                        cl = [r[4] for r in data]
                        crypto_series = pd.Series(cl, index=ts).astype(float)
                        raw[ct] = crypto_series
                        logger.info(f"Loaded {len(crypto_series)} crypto candles for {ct}")
                except Exception as e:
                    logger.warning(f"Coinbase fetch failed for {ct}: {e}; using synthetic data")
                    rng = pd.date_range(start=extended, end=end, freq="B", tz="UTC")
                    base = 20000 + np.cumsum(np.random.RandomState(42).normal(0, 100, len(rng)))
                    raw[ct] = pd.Series(base, index=rng).astype(float)
        
        # Validate we have data
        if raw.empty:
            raise ValueError("No price data available from any source")
        
        # Forward fill and drop rows where ALL tickers are NaN
        raw = raw.ffill().dropna(how="all")
        
        # Log data quality
        logger.info(f"Loaded {len(raw)} rows of price data")
        logger.info(f"Columns: {list(raw.columns)}")
        logger.info(f"Date range: {raw.index[0]} to {raw.index[-1]}")
        
        # Check for missing tickers
        missing = [t for t in TICKERS if t not in raw.columns]
        if missing:
            logger.warning(f"Missing data for tickers: {missing}")
        
        return raw
        
    except Exception as e:
        logger.error(f"Failed to load prices: {e}")
        raise

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
        db = get_db()
        rows = list(db.execute_and_fetch(
            f"MATCH (r:Regime {{name:'{regime}'}}) <-[:ACTIVATED_BY]-(s:Strategy) "
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
        except Exception as e:
            logger.debug(f"GARCH fit failed: {e}")
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
    total_fees = 0.0
    total_slippage = 0.0
    
    logger.info(f"Running period: {start_idx} to {end_idx}, capital={capital}, steps={total_steps}")
    
    for step, i in enumerate(range(start_idx, end_idx, rebal_freq)):
        # Check for cancellation
        if _is_cancelled(r):
            logger.warning("Backtest cancelled by user")
            sys.exit(0)
        
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
        
        # Add generic momentum for tickers without strategy signals
        for tk in TICKERS:
            if tk in ticker_sigs:
                continue
            if tk in prices.columns:
                hist = prices.iloc[max(0, i - 63):i]
                s = hist[tk] if tk in hist.columns else None
                if s is not None and len(s) > 21:
                    price_series = s.dropna()
                    if len(price_series) > 1:
                        score = float(np.clip((price_series.iloc[-1] - price_series.iloc[-21]) / (price_series.iloc[-21] + 1e-10) * 2, -1, 1))
                        ticker_sigs[tk] = [("GenericMomentum", score)]
        
        target_w: dict = {}
        for tk, sigs in ticker_sigs.items():
            avg = sum(s for _, s in sigs) / len(sigs)
            if avg > BT_TRADE_THRESHOLD:  target_w[tk] = min(0.30, avg * 0.30)
            elif avg < -BT_TRADE_THRESHOLD: target_w[tk] = 0.0
        
        # Execute trades
        for tk in TICKERS:
            price = float(today_p.get(tk, 0))
            if price <= 0: continue
            
            tgt   = nav * target_w.get(tk, 0.0)
            cur   = holdings[tk] * price
            delta = tgt - cur
            
            if abs(delta) < max(10.0, nav * 0.002): continue
            
            fill    = price * (1 + slip_pct * np.sign(delta))
            slip_cost = abs(fill - price) * abs(delta / fill)
            qty_d   = delta / fill
            fee     = abs(qty_d) * fill * fee_pct
            
            total_fees += fee
            total_slippage += slip_cost
            
            direction = "buy" if delta > 0 else "sell"
            holdings[tk] += qty_d
            cash -= qty_d * fill + fee
            
            strat_name = ticker_sigs.get(tk, [("unknown", 0)])[0][0]
            
            if direction == "buy" and tk not in open_pos:
                open_pos[tk] = {
                    "entry_date": str(today.date()),
                    "entry_price": round(fill, 4),
                    "qty": round(holdings[tk], 6),
                    "strategy": strat_name,
                    "slip_cost": slip_cost
                }
            elif direction == "sell" and tk in open_pos:
                ent = open_pos.pop(tk)
                pnl = round((fill - ent["entry_price"]) * abs(qty_d) - fee, 4)
                trade_slip = ent.get("slip_cost", 0) + slip_cost
                hd = (today - pd.Timestamp(ent["entry_date"])).days
                
                trade_log.append({
                    "ticker": tk,
                    "strategy": ent["strategy"],
                    "direction": direction,
                    "entry_date": ent["entry_date"],
                    "exit_date": str(today.date()),
                    "entry_price": ent["entry_price"],
                    "exit_price": round(fill, 4),
                    "qty": round(abs(qty_d), 6),
                    "pnl": pnl,
                    "fee": round(fee, 4),
                    "slippage": round(trade_slip, 4),
                    "hold_days": hd,
                    "regime": regime,
                    "asset_class": "crypto" if tk.upper().endswith("-USD") else "equity"
                })
                
                strat_pnl[ent["strategy"]] = strat_pnl.get(ent["strategy"], 0.0) + pnl
                strat_n[ent["strategy"]] = strat_n.get(ent["strategy"], 0) + 1
                if pnl > 0:
                    strat_wins[ent["strategy"]] = strat_wins.get(ent["strategy"], 0) + 1
        
        if step % 10 == 0:
            pct = prog_offset + int(step / total_steps * prog_range)
            _progress(r, pct, f"{label}Simulating {today.date()} | NAV ${nav:,.0f} | {regime}")
    
    # Calculate metrics
    nav_arr = np.array(nav_series)
    cum     = nav_arr / (nav_arr[0] + 1e-10)
    peak    = np.maximum.accumulate(cum)
    dd_ser  = ((cum - peak) / (peak + 1e-10) * 100).tolist()
    
    # Benchmark returns
    bm_raw = prices[BENCHMARK].iloc[start_idx:end_idx].ffill().values if BENCHMARK in prices.columns else None
    bm_rets = np.diff(bm_raw) / (bm_raw[:-1] + 1e-10) if bm_raw is not None and len(bm_raw) > 1 else np.array([])
    
    returns = np.diff(nav_arr) / (nav_arr[:-1] + 1e-10)
    ml = min(len(returns), len(bm_rets))
    
    logger.info(f"Period complete: {len(returns)} returns, {len(trade_log)} trades")
    
    stats = summary(returns[:ml], bm_rets[:ml], rf=RF_RATE)
    
    # Benchmark NAV
    spy_raw = None
    if "SPY" in prices.columns:
        spy_raw = prices["SPY"].iloc[start_idx:end_idx].ffill().values
    elif BENCHMARK in prices.columns:
        spy_raw = prices[BENCHMARK].iloc[start_idx:end_idx].ffill().values
    
    spy_nav = (spy_raw / (spy_raw[0] + 1e-10) * capital).tolist() if spy_raw is not None else []
    
    # Strategy breakdown
    sb = []
    for strat in sorted(strat_pnl):
        n = strat_n.get(strat, 0)
        w = strat_wins.get(strat, 0)
        sb.append({
            "strategy": strat,
            "total_pnl": round(strat_pnl[strat], 2),
            "n_trades": n,
            "win_rate": round(w/n, 3) if n else 0.0,
            "avg_pnl": round(strat_pnl[strat]/n, 2) if n else 0.0
        })
    
    from collections import Counter
    rd = {k: round(v/len(regime_log), 3) for k, v in Counter(regime_log).items()} if regime_log else {}
    
    gross_p = sum(t["pnl"] for t in trade_log if t["pnl"] > 0)
    gross_l = abs(sum(t["pnl"] for t in trade_log if t["pnl"] < 0))
    
    return {
        **stats,
        "final_nav": round(float(nav_arr[-1]), 2),
        "use_graph": use_graph,
        "start": date_series[0] if date_series else "",
        "end": date_series[-1] if date_series else "",
        "equity_curve": [{"date": d, "nav": n} for d, n in zip(date_series, nav_series)],
        "benchmark_curve": [{"date": d, "nav": round(float(n), 2)} for d, n in zip(date_series[:len(spy_nav)], spy_nav)],
        "drawdown_series": [{"date": d, "dd": round(dd, 2)} for d, dd in zip(date_series, dd_ser)],
        "trade_log": trade_log,
        "strategy_breakdown": sb,
        "regime_distribution": rd,
        "walk_forward_windows": [],
        "n_trades": len(trade_log),
        "win_rate": round(sum(1 for t in trade_log if t["pnl"] > 0)/len(trade_log), 3) if trade_log else 0.0,
        "avg_hold_days": round(sum(t["hold_days"] for t in trade_log)/len(trade_log), 1) if trade_log else 0.0,
        "profit_factor": round(gross_p/gross_l, 3) if gross_l > 0 else 0.0,
        "total_fees": round(total_fees, 2),
        "total_slippage": round(total_slippage, 2),
    }

def walk_forward_backtest(prices, start, end, capital, use_graph,
                         rebal_freq, fee_pct, slip_pct, r=None):
    all_dates = prices.index
    start_idx = all_dates.searchsorted(pd.Timestamp(start))
    end_idx   = min(all_dates.searchsorted(pd.Timestamp(end)) + 1, len(all_dates))
    
    windows, i, wid = [], start_idx, 0
    while i + WF_TRAIN_DAYS + WF_TEST_DAYS <= end_idx:
        te = min(i + WF_TRAIN_DAYS + WF_TEST_DAYS, end_idx)
        windows.append({
            "id": wid,
            "train_start": str(all_dates[i].date()),
            "train_end":   str(all_dates[i + WF_TRAIN_DAYS - 1].date()),
            "test_start":  str(all_dates[i + WF_TRAIN_DAYS].date()),
            "test_end":    str(all_dates[te - 1].date()),
            "test_s_idx":  i + WF_TRAIN_DAYS,
            "test_e_idx": te
        })
        i += WF_TEST_DAYS
        wid += 1
    
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
        
        wf_rows.append({
            **{k: win[k] for k in ["id","train_start","train_end","test_start","test_end"]},
            "sharpe_ratio": period["sharpe_ratio"],
            "total_return": period["total_return"],
            "max_drawdown": period["max_drawdown"],
            "n_trades": period["n_trades"],
            "final_nav": period["final_nav"]
        })
    
    nav_vals = [p["nav"] for p in agg_nav]
    bm_vals  = [p["nav"] for p in agg_bm]
    rets  = np.diff(nav_vals) / (np.array(nav_vals[:-1]) + 1e-10)
    brets = np.diff(bm_vals) / (np.array(bm_vals[:-1]) + 1e-10)
    ml    = min(len(rets), len(brets))
    
    stats = summary(rets[:ml], brets[:ml], rf=RF_RATE)
    
    sb_agg = []
    for strat in sorted(agg_sp):
        n = agg_sn.get(strat, 0)
        w = agg_sw.get(strat, 0)
        sb_agg.append({
            "strategy": strat,
            "total_pnl": round(agg_sp[strat], 2),
            "n_trades": n,
            "win_rate": round(w/n, 3) if n else 0.0,
            "avg_pnl": round(agg_sp[strat]/n, 2) if n else 0.0
        })
    
    gp = sum(t["pnl"] for t in agg_trades if t["pnl"] > 0)
    gl = abs(sum(t["pnl"] for t in agg_trades if t["pnl"] < 0))
    
    _progress(r, 98, f"{len(agg_trades)} trades | final NAV ${running_cap:,.0f}")
    
    # Regime performance attribution
    regime_stats = {}
    for t in agg_trades:
        rg = t.get("regime", "Unknown")
        if rg not in regime_stats:
            regime_stats[rg] = {"pnl": 0.0, "n": 0, "wins": 0}
        regime_stats[rg]["pnl"] += t["pnl"]
        regime_stats[rg]["n"] += 1
        if t["pnl"] > 0: regime_stats[rg]["wins"] += 1
    
    regime_performance = []
    for rg, st in regime_stats.items():
        regime_performance.append({
            "regime": rg,
            "return_pct": round(st["pnl"], 2),
            "sharpe": 0.0,
            "trades": st["n"],
            "win_rate": round(st["wins"] / st["n"], 3) if st["n"] > 0 else 0.0
        })
    
    return {
        **stats,
        "final_nav": round(running_cap, 2),
        "use_graph": use_graph,
        "start": agg_nav[0]["date"] if agg_nav else start,
        "end": agg_nav[-1]["date"] if agg_nav else end,
        "equity_curve": agg_nav,
        "benchmark_curve": agg_bm,
        "drawdown_series": agg_dd,
        "trade_log": agg_trades,
        "strategy_breakdown": sb_agg,
        "walk_forward_windows": wf_rows,
        "regime_distribution": {},
        "n_trades": len(agg_trades),
        "win_rate": round(sum(1 for t in agg_trades if t["pnl"] > 0)/len(agg_trades), 3) if agg_trades else 0.0,
        "avg_hold_days": round(sum(t["hold_days"] for t in agg_trades)/len(agg_trades), 1) if agg_trades else 0.0,
        "profit_factor": round(gp/gl, 3) if gl > 0 else 0.0,
        "regime_performance": regime_performance,
        "total_fees": round(sum(t.get("fee", 0) for t in agg_trades), 2),
        "total_slippage": round(sum(t.get("slippage", 0) for t in agg_trades), 2),
    }

def generate_suggestions(result, regime, r):
    candidates = [s for s in result.get("strategy_breakdown", [])
                  if s["total_pnl"] > 0 and s["win_rate"] > 0.5 and s["n_trades"] >= 3]
    candidates.sort(key=lambda x: x["total_pnl"], reverse=True)
    
    suggestions = []
    for c in candidates[:5]:
        strat = c["strategy"]
        tk = STRATEGY_TICKER_MAP.get(strat, "SPY")
        suggestions.append({
            "id": f"{strat}_{tk}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "strategy": strat,
            "ticker": tk,
            "direction": "buy",
            "regime": regime,
            "rationale": f"{strat}: {c['n_trades']} trades, {c['win_rate']*100:.0f}% win rate, ${c['total_pnl']:,.2f} P&L",
            "backtest_pnl": c["total_pnl"],
            "backtest_trades": c["n_trades"],
            "win_rate": c["win_rate"],
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        })
    
    if r and suggestions:
        r.set("graphalpha:trade_suggestions", json.dumps(suggestions))
    
    return suggestions

def main():
    global REBAL_FREQ, TRAIN_WINDOW, FEE_PCT, SLIP_PCT, TICKERS, BT_TRADE_THRESHOLD, BENCHMARK, RF_RATE
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",        default="2021-01-01")
    parser.add_argument("--end",          default="2023-12-31")
    parser.add_argument("--capital",      type=float, default=10000.0)
    parser.add_argument("--rebal-freq",   type=int,   default=REBAL_FREQ)
    parser.add_argument("--train-window", type=int,   default=TRAIN_WINDOW)
    parser.add_argument("--fee-pct",      type=float, default=FEE_PCT)
    parser.add_argument("--slip-pct",     type=float, default=SLIP_PCT)
    parser.add_argument("--tickers",      default=",".join(TICKERS))
    parser.add_argument("--trade-threshold", type=float, default=BT_TRADE_THRESHOLD)
    parser.add_argument("--use-graph",    dest="use_graph", action="store_true")
    parser.add_argument("--no-graph",     dest="use_graph", action="store_false")
    parser.add_argument("--benchmark",    default="SPY")
    parser.add_argument("--rf-rate",      type=float, default=0.05)
    parser.set_defaults(use_graph=True)
    
    args = parser.parse_args()
    
    REBAL_FREQ = args.rebal_freq
    TRAIN_WINDOW = args.train_window
    FEE_PCT = args.fee_pct
    SLIP_PCT = args.slip_pct
    TICKERS = [t.strip() for t in args.tickers.split(",") if t.strip()]
    BT_TRADE_THRESHOLD = args.trade_threshold
    BENCHMARK = args.benchmark
    RF_RATE = args.rf_rate
    
    logger.info(f"Starting backtest: {args.start} to {args.end}")
    logger.info(f"Tickers: {TICKERS}")
    logger.info(f"Benchmark: {BENCHMARK}, RF Rate: {RF_RATE}")
    
    r = _redis()
    if r:
        r.set("graphalpha:backtest_cancel", "0")  # Clear cancel flag
        r.set("graphalpha:backtest_progress", json.dumps({"pct": 0, "msg": "Loading prices…"}))
    
    _progress(r, 1, f"Loading prices {args.start} → {args.end}")
    
    try:
        prices = load_prices(args.start, args.end)
        
        if prices.empty:
            raise ValueError("No price data loaded")
        
        result = walk_forward_backtest(prices, args.start, args.end, args.capital,
                                      args.use_graph, REBAL_FREQ, FEE_PCT, SLIP_PCT, r)
        
        end_idx = prices.index.searchsorted(pd.Timestamp(args.end))
        regime = classify_regime(prices, min(end_idx, len(prices) - 1))
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
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        if r:
            r.set("graphalpha:backtest_status", f"error:{str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()