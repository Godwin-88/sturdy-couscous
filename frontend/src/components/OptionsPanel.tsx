import { useMemo, useState, useEffect, useCallback } from "react";
import { Search, Activity, ArrowRightLeft, Loader2, CheckCircle2, XCircle, Brain, RefreshCw, Shield, Clock, AlertTriangle, Zap, ChevronRight } from "lucide-react";
import { optionsApi, OptionContractRow, OptionSuggestion, OptionLeg, AlpacaAsset, HedgeState } from "@/lib/api";
import Greeks3DVisualization from "@/components/Greeks3DVisualization";
import OptionDiagrams from "@/components/OptionDiagrams";
import { fmt$, fmtN } from "@/lib/utils";
import { setScreenContext } from "@/lib/screenContext";
import clsx from "clsx";

const MOODS = ["call", "put"] as const;

function expiryFromSymbol(sym: string): string {
  // SPY250904C00770000 -> 2025-09-04
  const m = sym.match(/^[A-Z]{1,5}(\d{6})[CP]\d{8}$/);
  if (!m) return "";
  const yymmdd = m[1];
  return `20${yymmdd.slice(0, 2)}-${yymmdd.slice(2, 4)}-${yymmdd.slice(4, 6)}`;
}

function legToRow(leg: OptionLeg, fallbackExp: string, fallbackUnderlying: string): OptionContractRow {
  const exp = expiryFromSymbol(leg.symbol) || fallbackExp;
  return {
    symbol: leg.symbol,
    underlying_symbol: fallbackUnderlying,
    root_symbol: fallbackUnderlying,
    expiration_date: exp,
    contract_type: leg.contract_type,
    strike_price: leg.strike,
    multiplier: 100,
    style: "american",
    tradable: true,
    bid: leg.bid ?? null,
    ask: leg.ask ?? null,
    last: null,
    volume: null,
    open_interest: leg.open_interest ?? null,
    implied_volatility: leg.implied_volatility ?? null,
    greeks: { delta: leg.delta ?? null, gamma: null, theta: null, vega: null, rho: null },
    spread_pct: leg.spread_pct ?? null,
  };
}

export default function OptionsPanel() {
  const [query, setQuery] = useState("");
  const [assets, setAssets] = useState<AlpacaAsset[]>([]);
  const [searching, setSearching] = useState(false);
  const [underlying, setUnderlying] = useState<string>("SPY");

  const [expiration, setExpiration] = useState<string>("");
  const [expirations, setExpirations] = useState<string[]>([]);
  const [mood, setMood] = useState<"call" | "put">("call");

  const [rows, setRows] = useState<OptionContractRow[]>([]);
  const [loadingChain, setLoadingChain] = useState(false);
  const [chainErr, setChainErr] = useState<string | null>(null);

  const [selected, setSelected] = useState<OptionContractRow | null>(null);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [intent, setIntent] = useState<"buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close">("buy_to_open");
  const [qty, setQty] = useState(1);
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState<string>("");
  const [placing, setPlacing] = useState(false);
  const [placed, setPlaced] = useState<{ order_id: string; status: string; contract: string; fill: number | null; mode: string } | null>(null);
  const [placeErr, setPlaceErr] = useState<string | null>(null);

  const [suggestions, setSuggestions] = useState<OptionSuggestion[]>([]);
  const [sugMeta, setSugMeta] = useState<{ regime: string; regime_confidence: number; spot_estimate: number | null; dte: number; active_strategies: string[]; lens: string; max_loss_cap_pct: number; nav: number } | null>(null);
  const [loadingSug, setLoadingSug] = useState(false);
  const [sugErr, setSugErr] = useState<string | null>(null);
  const [rejected, setRejected] = useState<{ strategy: string; max_loss_pct_nav: number; reason: string }[]>([]);

  const [lens, setLens] = useState<"average" | "defensive">("defensive");

  const [hedgeState, setHedgeState] = useState<HedgeState | null>(null);
  const [loadingHedge, setLoadingHedge] = useState(false);
  const [hedgeMsg, setHedgeMsg] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [orderClass, setOrderClass] = useState<"simple" | "vertical">("simple");
  const [spreadLegs, setSpreadLegs] = useState<OptionLeg[]>([]);

  // Publish live page-session context so the Financial Engineer chat anchors
  // on the same underlying/strike the user is actually viewing (e.g. MCHP).
  useEffect(() => {
    setScreenContext("options", {
      screen: "options",
      underlying,
      expiration: expiration || undefined,
      contract_type: mood,
      contract_symbol: selected?.symbol ?? undefined,
      strike: selected?.strike_price ?? undefined,
      lens,
      extra: {
        spot_estimate: sugMeta?.spot_estimate ?? undefined,
        dte: sugMeta?.dte ?? undefined,
        chain_size: rows.length,
      },
    });
  }, [underlying, expiration, mood, selected, lens, sugMeta, rows.length]);

  // Auto-poll suggestions when a row is selected
  useEffect(() => {
    if (!selected) return;
    const interval = setInterval(() => {
      loadSuggestions();
    }, 15_000);
    return () => clearInterval(interval);
  }, [selected, underlying, expiration, mood, lens]);

  async function searchUnderlyings() {
    setSearching(true);
    setChainErr(null);
    try {
      const res = await optionsApi.underlyings(query.trim());
      setAssets(res.assets ?? []);
    } catch (e) { setChainErr(String(e)); }
    finally { setSearching(false); }
  }

  async function pickUnderlying(sym: string) {
    setUnderlying(sym);
    setQuery("");
    setAssets([]);
    setExpiration("");
    setRows([]);
    setSelected(null);
    try {
      const ex = await optionsApi.expirations(sym);
      setExpirations(ex.expirations ?? []);
      if ((ex.expirations ?? []).length) {
        const first = ex.expirations[0];
        setExpiration(first);
        await loadChain(sym, first, "call");
      }
    } catch (e) { setChainErr(String(e)); }
  }

  async function loadChain(sym: string, exp: string, type: "call" | "put") {
    setLoadingChain(true);
    setChainErr(null);
    setSelected(null);
    try {
      const res = await optionsApi.chain(sym, { expiration: exp, contract_type: type });
      setRows(res.rows ?? []);
    } catch (e) { setChainErr(String(e)); setRows([]); }
    finally { setLoadingChain(false); }
  }

  function onExpirationChange(exp: string) {
    setExpiration(exp);
    loadChain(underlying, exp, mood);
  }

  function onMoodChange(m: "call" | "put") {
    setMood(m);
    loadChain(underlying, expiration || "", m);
  }

  const atmApprox = useMemo(() => {
    if (!rows.length) return null;
    const mid = (r: OptionContractRow) => ((r.bid ?? 0) + (r.ask ?? 0)) / 2;
    let best = rows[0];
    for (const r of rows) if (mid(r) > mid(best)) best = r;
    return best;
  }, [rows]);

  async function loadSuggestions() {
    setLoadingSug(true);
    setSugErr(null);
    try {
      const res = await optionsApi.suggestions(underlying, { expiration: expiration || undefined, contract_type: mood, lens });
      setSuggestions(res.suggestions ?? []);
      setRejected((res.rejected ?? []).map(r => ({ strategy: r.strategy, max_loss_pct_nav: r.max_loss_pct_nav, reason: r.reason })));
      setSugMeta({
        regime: res.regime,
        regime_confidence: res.regime_confidence,
        spot_estimate: res.spot_estimate,
        dte: res.dte,
        active_strategies: res.active_strategies ?? [],
        lens: res.lens,
        max_loss_cap_pct: res.max_loss_cap_pct,
        nav: res.nav,
      });
    } catch (e) {
      setSugErr(String(e));
      setSuggestions([]);
    } finally {
      setLoadingSug(false);
    }
  }

  function toggleLens() {
    setLens(prev => (prev === "defensive" ? "average" : "defensive"));
    // re-compute w/ the new lens; the backend caches per (chain,lens) for 60s
    setTimeout(loadSuggestions, 0);
  }

  async function loadHedge() {
    setLoadingHedge(true);
    setHedgeMsg(null);
    try {
      const res = await optionsApi.hedge.state(underlying);
      setHedgeState(res.hedge_state ?? null);
    } catch (e) {
      setHedgeState(null);
      setHedgeMsg(String(e));
    } finally {
      setLoadingHedge(false);
    }
  }

  async function runHedge(confirm: boolean) {
    setLoadingHedge(true);
    setHedgeMsg(null);
    try {
      const res = await optionsApi.hedge.rebalance(underlying, confirm);
      setHedgeState(res.hedge_state ?? null);
      setHedgeMsg(confirm
        ? `${res.status.toUpperCase()} − order ${res.order ? String(res.order.order_id) : "n/a"} (${res.order ? String(res.order.side) : ""} ${String(res.order ? res.order.qty : 0)} ${underlying})`
        : `${res.status.toUpperCase()} ${res.message ?? ""}`);
    } catch (e) {
      setHedgeMsg(String(e));
    } finally {
      setLoadingHedge(false);
    }
  }

  function openLegInTicket(leg: OptionLeg) {
    setOrderClass("simple");
    setSpreadLegs([]);
    setSide(leg.side.startsWith("buy") ? "buy" : "sell");
    setIntent(leg.side);
    setSelected(legToRow(leg, expiration, underlying));
    setPlaced(null);
    setPlaceErr(null);
    setModalOpen(true);
  }

  function openSuggestionInTicket(s: OptionSuggestion) {
    const legs = s.legs ?? [];
    if (legs.length > 1) {
      // Multi-leg spread — prefill the full vertical order
      setSpreadLegs(legs);
      setOrderClass("vertical");
      const first = legs[0];
      setSide(first.side.startsWith("buy") ? "buy" : "sell");
      setIntent(first.side);
      setSelected(legToRow(first, expiration, underlying));
    } else {
      openLegInTicket(legs[0] ?? s.legs[0]);
      return;
    }
    setPlaced(null);
    setPlaceErr(null);
    setModalOpen(true);
  }

  function openTradeModal(row: OptionContractRow) {
    setSelected(row);
    setPlaced(null);
    setPlaceErr(null);
    setModalOpen(true);
  }

  async function submitOrder() {
    if (!selected) return;
    setPlacing(true); setPlaced(null); setPlaceErr(null);
    try {
      const res = await optionsApi.place({
        contract_symbol: selected.symbol,
        qty,
        side,
        position_intent: intent,
        order_type: orderType,
        limit_price: orderType === "limit" && limitPrice ? Number(limitPrice) : null,
        label: "ui-manual",
        order_class: orderClass,
        legs: orderClass === "vertical"
          ? spreadLegs.map(l => ({
              symbol: l.symbol,
              side: l.side.startsWith("buy") ? "buy" : "sell",
              qty: 1, // ratio_qty per leg; top-level qty = number of spreads
              position_intent: l.side,
            }))
          : undefined,
      });
      setPlaced({
        order_id: res.order_id,
        status: res.status,
        contract: res.contract_symbol,
        fill: res.filled_avg_price,
        mode: res.mode,
      });
    } catch (e) { setPlaceErr(String(e)); }
    finally { setPlacing(false); }
  }
  return (
    <div className="h-full overflow-y-auto p-3 space-y-3">
      <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
          <Activity size={14} className="text-indigo-400" />
          <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Options - Alpaca Paper</span>
          <span className="ml-auto flex items-center gap-1.5 text-[10px] font-mono text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />LIVE CHAINS
          </span>
        </div>

        {/* Underlying discovery */}
        <div className="p-3 space-y-2">
          <div className="flex gap-2">
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") searchUnderlyings(); }}
              placeholder="Search any underlying (SPY, QQQ, AAPL, TSLA, XLF...)"
              className="flex-1 bg-slate-950 border border-slate-700 rounded px-3 py-1.5 text-xs font-mono text-slate-200 placeholder:text-slate-600 outline-none focus:border-indigo-500"
            />
            <button onClick={searchUnderlyings} disabled={searching}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-indigo-600/30 border border-indigo-500/40 text-xs text-indigo-300 hover:bg-indigo-600/50 disabled:opacity-50">
              {searching ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />} Search
            </button>
          </div>

          {assets.length > 0 && (
            <div className="max-h-44 overflow-y-auto border border-slate-700 rounded bg-slate-950 divide-y divide-slate-800">
              {assets.map(a => (
                <button key={a.symbol} onClick={() => pickUnderlying(a.symbol)}
                  className="w-full flex items-center justify-between gap-2 px-3 py-1.5 text-left hover:bg-slate-800">
                  <span className="font-mono text-xs text-slate-200">{a.symbol}</span>
                  <span className="text-[10px] text-slate-500 truncate max-w-[60%]">{a.name}</span>
                  <span className={clsx("text-[10px] font-mono", a.tradable ? "text-emerald-400" : "text-slate-600")}>
                    {a.tradable ? "TRADABLE" : "N/A"}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* Selection: underlying + expiry + call/put */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500 font-mono">Underlying:</span>
            {["SPY", "QQQ", "AAPL", "TSLA"].map(s => (
              <button key={s} onClick={() => pickUnderlying(s)}
                className={clsx("px-2.5 py-1 rounded text-xs font-mono", underlying === s ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-300")}>
                {s}
              </button>
            ))}
            {!["SPY", "QQQ", "AAPL", "TSLA"].includes(underlying) && (
              <span className="px-2.5 py-1 rounded text-xs font-mono bg-indigo-600 text-white">{underlying}</span>
            )}

            <select value={expiration} onChange={e => onExpirationChange(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-200">
              {!expirations.length && <option value="">expirations...</option>}
              {expirations.map(e => <option key={e} value={e}>{e}</option>)}
            </select>

            <div className="flex rounded overflow-hidden border border-slate-700">
              {MOODS.map(m => (
                <button key={m} onClick={() => onMoodChange(m)}
                  className={clsx("px-3 py-1 text-xs font-mono uppercase",
                    mood === m ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-400")}>
                  {m}
                </button>
                             ))}
            </div>
          </div>
        </div>
        {/* Chain table */}
        <div className="px-3 pb-3">
          {loadingChain ? (
            <div className="flex items-center gap-2 text-xs text-slate-500 py-6 justify-center">
              <Loader2 size={14} className="animate-spin" /> Loading chain...
            </div>
          ) : chainErr ? (
            <div className="text-xs text-red-400 bg-red-950/30 border border-red-800 rounded p-2">{chainErr}</div>
          ) : rows.length === 0 ? (
            <div className="text-xs text-slate-500 py-4 text-center font-mono">No contracts for this selection</div>
          ) : (
            <div className="max-h-[46vh] overflow-auto overscroll-x-contain border border-slate-700 rounded">
              <table className="w-full min-w-[1180px] text-xs font-mono">
                <thead className="sticky top-0 bg-slate-950 z-10">
                  <tr className="text-slate-500 border-b border-slate-700">
                    <th className="text-left py-1.5 px-2">Strike</th>
                    <th className="text-right px-2">Contract</th>
                    <th className="text-right px-2">Last</th>
                    <th className="text-right px-2">Volume</th>
                    <th className="text-right px-2">Open Int</th>
                    <th className="text-right px-2">Bid</th>
                    <th className="text-right px-2">Ask</th>
                    <th className="text-right px-2">Mid</th>
                    <th className="text-right px-2">Spread%</th>
                    <th className="text-right px-2">IV</th>
                    <th className="text-right px-2">Delta</th>
                    <th className="text-right px-2">Gamma</th>
                    <th className="text-right px-2">Theta</th>
                    <th className="text-right px-2">Vega</th>
                    <th className="text-right px-2 w-20">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => {
                    const mid = ((r.bid ?? 0) + (r.ask ?? 0)) / 2;
                    const isAtm = atmApprox?.symbol === r.symbol;
                    return (
                      <tr key={r.symbol}
                        onClick={() => { setSelected(r); loadSuggestions(); }}
                        className={clsx("border-b border-slate-800 cursor-pointer hover:bg-slate-800/60 group",
                          selected?.symbol === r.symbol ? "bg-indigo-600/10 ring-1 ring-inset ring-indigo-500/40" : "",
                          isAtm && selected?.symbol !== r.symbol ? "bg-slate-800/30" : "")}>
                        <td className="py-1.5 px-2 text-slate-200 font-bold sticky left-0 bg-slate-950 group-hover:bg-slate-800 z-[5]">{fmtN(r.strike_price)}</td>
                        <td className="py-1 px-2 text-right text-slate-400 whitespace-nowrap">{r.symbol}</td>
                        <td className="py-1 text-right text-slate-300">{r.last != null ? fmt$(r.last) : "-"}</td>
                        <td className="py-1 text-right text-slate-400">{r.volume != null ? fmtN(r.volume) : "-"}</td>
                        <td className="py-1 text-right text-slate-400">{r.open_interest != null ? fmtN(r.open_interest) : "-"}</td>
                        <td className="py-1 text-right text-emerald-400">{r.bid != null ? fmt$(r.bid) : "-"}</td>
                        <td className="py-1 text-right text-red-400">{r.ask != null ? fmt$(r.ask) : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{mid ? fmt$(mid) : "-"}</td>
                        <td className="py-1 text-right text-slate-400">{r.spread_pct != null ? `${(r.spread_pct * 100).toFixed(1)}%` : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{r.implied_volatility != null ? `${(r.implied_volatility * 100).toFixed(0)}%` : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{r.greeks?.delta != null ? r.greeks.delta.toFixed(3) : "-"}</td>
                        <td className="py-1 text-right text-slate-400">{r.greeks?.gamma != null ? r.greeks.gamma.toFixed(4) : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{r.greeks?.theta != null ? fmt$(r.greeks.theta) : "-"}</td>
                        <td className="py-1 text-right text-slate-400">{r.greeks?.vega != null ? r.greeks.vega.toFixed(2) : "-"}</td>
                        <td className="py-1 px-2 text-right">
                          <button
                            onClick={(e) => { e.stopPropagation(); openTradeModal(r); }}
                            className="px-2 py-0.5 rounded bg-emerald-600/30 border border-emerald-500/40 text-[10px] font-bold text-emerald-300 hover:bg-emerald-600/50 transition-colors whitespace-nowrap">
                            Trade
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Dynamic Delta Hedge — Taleb posture */}
      <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
          <Shield size={14} className="text-rose-400" />
          <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Dynamic Delta Hedge</span>
          <button onClick={loadHedge} disabled={loadingHedge}
            className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-700/40 border border-slate-600 text-[10px] text-slate-300 hover:bg-slate-700 disabled:opacity-50">
            {loadingHedge ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />} Refresh
          </button>
        </div>
        <div className="p-3 space-y-2 text-xs font-mono">
          {hedgeMsg && <div className="text-[10px] text-slate-400">{hedgeMsg}</div>}
          {!hedgeState ? (
            <div className="text-slate-500">Load hedge state to see portfolio Δ/Γ/Θ/V and the recommended underlying hedge.</div>
          ) : (
            <>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-slate-300">
                <span>Δ <b className="text-slate-100">{hedgeState.greeks.delta.toFixed(2)}</b></span>
                <span>Γ <b className="text-slate-100">{hedgeState.greeks.gamma.toFixed(4)}</b></span>
                <span>Θ <b className="text-slate-100">{fmt$(hedgeState.greeks.theta)}</b></span>
                <span>V <b className="text-slate-100">{hedgeState.greeks.vega.toFixed(2)}</b></span>
                <span>spot <b className="text-slate-100">{hedgeState.spot != null ? fmt$(hedgeState.spot) : "-"}</b></span>
                <span>regime <b className="text-slate-100">{hedgeState.regime}</b></span>
                <span>band <b className="text-slate-100">{hedgeState.band_shares}</b></span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-slate-400">hedge {hedgeState.hedge_shares >= 0 ? "BUY" : "SELL"} <b className="text-slate-100">{Math.abs(hedgeState.hedge_shares).toFixed(0)}</b> {underlying}</span>
                {hedgeState.needs_rebalance && <span className="text-amber-400">needs rebalance</span>}
                {hedgeState.tail_sleeve?.recommended && <span className="text-rose-400">tail sleeve recommended</span>}
                <button onClick={() => runHedge(false)}
                  className="px-2.5 py-1 rounded bg-slate-700/40 border border-slate-600 text-[10px] text-slate-200 hover:bg-slate-700">
                  Dry-run hedge
                </button>
                <button onClick={() => runHedge(true)}
                  className="px-2.5 py-1 rounded bg-rose-600/30 border border-rose-500/40 text-[10px] text-rose-300 hover:bg-rose-600/50">
                  Execute on paper
                </button>
              </div>

              {/* 3D Greeks exposure */}
              <Greeks3DVisualization greeks={hedgeState.greeks} title="Portfolio Greeks 3D" size={170} />
            </>
          )}
        </div>
      </div>

      {/* Option diagrams — payoff + 3D surfaces */}
      <OptionDiagrams
        selected={selected}
        side={side}
        qty={qty}
        spot={sugMeta?.spot_estimate ?? null}
        dte={sugMeta?.dte ?? 0}
        rows={rows}
        mood={mood}
      />

      {/* Side-by-side: Agent Suggestions + Order Ticket */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-3">
        {/* Agent Suggestions — KG-grounded, computed from selected chain metrics */}
        <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
            <Brain size={14} className="text-violet-400" />
            <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Agent Suggestions</span>
            {selected && (
              <span className="flex items-center gap-1 text-[10px] font-mono text-amber-400">
                <Clock size={10} /> auto-poll 15s
              </span>
            )}
            {sugMeta && (
              <span className="ml-2 text-[10px] font-mono text-slate-400">
                regime {sugMeta.regime} ({sugMeta.regime_confidence.toFixed(2)}) · {sugMeta.dte} DTE · spot {sugMeta.spot_estimate != null ? fmt$(sugMeta.spot_estimate) : "-"} · {sugMeta.lens} lens
              </span>
            )}
            <button onClick={toggleLens} title="Loss-aversion lens (defensive = max-loss cap 5% NAV, lambda 3.5; average = cap 10%, lambda 2.25)"
              className={clsx("flex items-center gap-1.5 px-2.5 py-1 rounded border text-[10px] font-bold",
                lens === "defensive" ? "bg-rose-600/30 border-rose-500/40 text-rose-300 hover:bg-rose-600/50"
                                      : "bg-amber-600/20 border-amber-500/30 text-amber-300 hover:bg-amber-600/40")}>
              <Shield size={10} /> {lens === "defensive" ? "Defensive (λ3.5)" : "Average (λ2.25)"}
            </button>
            <button onClick={loadSuggestions} disabled={loadingSug}
              className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded bg-violet-600/30 border border-violet-500/40 text-[10px] text-violet-300 hover:bg-violet-600/50 disabled:opacity-50">
              {loadingSug ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />} Refresh
            </button>
          </div>
          <div className="p-3 space-y-2">
            {!selected ? (
              <div className="text-xs text-slate-500 font-mono">Select a contract row above and the agents will score the full strategy library for this chain, grounded in the knowledge graph + current regime.</div>
            ) : sugErr ? (
              <div className="text-xs font-mono text-red-400 bg-red-950/30 border border-red-800 rounded p-2">{sugErr}</div>
            ) : loadingSug && suggestions.length === 0 ? (
              <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                <Loader2 size={12} className="animate-spin" /> Computing {underlying} {mood} strategies from chain greeks + KG regime…
              </div>
            ) : suggestions.length === 0 ? (
              <div className="text-xs text-slate-500 font-mono">No strategies scored for this chain right now — try a different expiry or call/put.</div>
            ) : (
              <div className="space-y-2">
                {sugMeta && sugMeta.active_strategies.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    <span className="text-[10px] text-slate-500 uppercase">KG active:</span>
                    {sugMeta.active_strategies.map(s => (
                      <span key={s} className="text-[10px] font-mono text-violet-300 bg-violet-950/40 border border-violet-800 rounded px-1.5 py-0.5">{s}</span>
                    ))}
                  </div>
                )}
                {sugMeta && (sugMeta.max_loss_cap_pct > 0) && (
                  <div className="text-[10px] font-mono text-slate-500">
                    loss-aversion gates: max loss ≤ {sugMeta.max_loss_cap_pct.toFixed(0)}% of NAV ({sugMeta.nav ? fmt$(sugMeta.nav) : "-"}) — anything bigger is rejected
                  </div>
                )}
                {suggestions.map((s) => (
                  <StrategyCard key={s.strategy} s={s} sugMeta={sugMeta} onOpenTicket={() => openSuggestionInTicket(s)} />
                ))}
                {rejected.length > 0 && (
                  <div className="rounded border border-amber-900/60 bg-amber-950/10 p-2">
                    <div className="text-[10px] font-mono text-amber-300 uppercase tracking-widest mb-1">
                      Blocked by loss-aversion gates ({rejected.length})
                    </div>
                    {rejected.map((r, i) => (
                      <div key={i} className="text-[10px] font-mono text-amber-400/90">
                        ⛔ {r.strategy} — {r.reason}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Order ticket — sticky sidebar */}
        <div className="lg:sticky lg:top-3 self-start">
          <OrderTicket
            selected={selected}
            side={side}
            setSide={setSide}
            intent={intent}
            setIntent={setIntent}
            qty={qty}
            setQty={setQty}
            orderType={orderType}
            setOrderType={setOrderType}
            limitPrice={limitPrice}
            setLimitPrice={setLimitPrice}
            placing={placing}
            placed={placed}
            placeErr={placeErr}
            onSubmit={submitOrder}
          />
        </div>
      </div>

      {/* Order Confirmation Modal — completes the paper-trading user story */}
      {modalOpen && selected && (
        <OrderModal
          selected={selected}
          underlying={underlying}
          side={side}
          setSide={setSide}
          intent={intent}
          setIntent={setIntent}
          qty={qty}
          setQty={setQty}
          orderType={orderType}
          setOrderType={setOrderType}
          limitPrice={limitPrice}
          setLimitPrice={setLimitPrice}
          orderClass={orderClass}
          setOrderClass={setOrderClass}
          spreadLegs={spreadLegs}
          placing={placing}
          placed={placed}
          placeErr={placeErr}
          matching={suggestions.find(s => s.legs.some(l => l.symbol === selected.symbol)) ?? null}
          onClose={() => setModalOpen(false)}
          onSubmit={submitOrder}
        />
      )}
    </div>
  );
}

function OrderModal({
  selected, underlying, side, setSide, intent, setIntent, qty, setQty,
  orderType, setOrderType, limitPrice, setLimitPrice,
  orderClass, setOrderClass, spreadLegs,
  placing, placed, placeErr,
  matching, onClose, onSubmit,
}: {
  selected: OptionContractRow;
  underlying: string;
  side: "buy" | "sell";
  setSide: (s: "buy" | "sell") => void;
  intent: "buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close";
  setIntent: (i: "buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close") => void;
  qty: number;
  setQty: (q: number) => void;
  orderType: "market" | "limit";
  setOrderType: (t: "market" | "limit") => void;
  limitPrice: string;
  setLimitPrice: (p: string) => void;
  orderClass: "simple" | "vertical";
  setOrderClass: (c: "simple" | "vertical") => void;
  spreadLegs: OptionLeg[];
  placing: boolean;
  placed: { order_id: string; status: string; contract: string; fill: number | null; mode: string } | null;
  placeErr: string | null;
  matching: OptionSuggestion | null;
  onClose: () => void;
  onSubmit: () => void;
}) {
  const mid = ((selected.bid ?? 0) + (selected.ask ?? 0)) / 2;
  const isSpread = orderClass === "vertical" && spreadLegs.length > 1;
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-slate-600 bg-slate-900 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-700 bg-slate-950">
          <ArrowRightLeft size={15} className="text-emerald-400" />
          <span className="text-sm font-semibold text-slate-100">Confirm Option Trade</span>
          <button onClick={onClose} className="ml-auto p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200">
            <XCircle size={16} />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {/* Order class: simple vs vertical (multi-leg) */}
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => setOrderClass("simple")}
              className={clsx("px-2 py-1.5 rounded border text-[11px] font-bold font-mono",
                orderClass === "simple" ? "bg-indigo-600/30 border-indigo-500/50 text-indigo-200" : "bg-slate-950 border-slate-700 text-slate-400 hover:bg-slate-800")}>
              SIMPLE (1 leg)
            </button>
            <button onClick={() => setOrderClass("vertical")}
              className={clsx("px-2 py-1.5 rounded border text-[11px] font-bold font-mono",
                orderClass === "vertical" ? "bg-violet-600/30 border-violet-500/50 text-violet-200" : "bg-slate-950 border-slate-700 text-slate-400 hover:bg-slate-800")}>
              VERTICAL (spread)
            </button>
          </div>

          {/* Contract summary */}
          <div className="text-xs font-mono text-slate-200 bg-slate-950 border border-slate-700 rounded px-3 py-2">
            <div className="text-slate-100 font-bold">{selected.symbol}</div>
            <div className="text-slate-500">
              {selected.contract_type.toUpperCase()} x{selected.multiplier} · {selected.expiration_date} · Strike {fmtN(selected.strike_price)} · {underlying}
            </div>
          </div>

          {/* Spread legs (when vertical) */}
          {isSpread && (
            <div className="rounded border border-violet-800/40 bg-violet-950/10 px-3 py-2 space-y-1">
              <div className="text-[10px] text-violet-300 uppercase tracking-widest font-mono">Spread legs</div>
              {spreadLegs.map((l, i) => (
                <div key={i} className="flex items-center justify-between text-[11px] font-mono text-slate-300">
                  <span className={clsx(l.side.startsWith("buy") ? "text-emerald-400" : "text-red-400")}>
                    {l.side.toUpperCase().replace(/_/g, " ")}
                  </span>
                  <span>{l.symbol}</span>
                  <span>K {fmtN(l.strike)}</span>
                  <span>mid {l.mid != null ? fmt$(l.mid) : "-"}</span>
                </div>
              ))}
              <div className="text-[10px] text-slate-500 font-mono pt-1 border-t border-violet-900/40">
                {matching ? `${matching.strategy} · maxP ${fmt$(matching.max_profit_low)} · maxL ${fmt$(matching.max_loss)}` : "Manual vertical"}
              </div>
            </div>
          )}

          {/* Live risk summary */}
          <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
            <div className="rounded bg-slate-950 border border-slate-700 px-2 py-1.5 text-slate-300">
              Mid <b className="text-slate-100">{mid ? fmt$(mid) : "-"}</b>
            </div>
            <div className="rounded bg-slate-950 border border-slate-700 px-2 py-1.5 text-slate-300">
              Spread% <b className={clsx((selected.spread_pct ?? 0) > 0.05 ? "text-red-400" : "text-slate-100")}>{selected.spread_pct != null ? `${(selected.spread_pct * 100).toFixed(1)}%` : "-"}</b>
            </div>
            <div className="rounded bg-slate-950 border border-slate-700 px-2 py-1.5 text-slate-300">
              Δ <b className="text-slate-100">{selected.greeks?.delta != null ? selected.greeks.delta.toFixed(3) : "-"}</b> · Γ <b className="text-slate-100">{selected.greeks?.gamma != null ? selected.greeks.gamma.toFixed(4) : "-"}</b>
            </div>
            <div className="rounded bg-slate-950 border border-slate-700 px-2 py-1.5 text-slate-300">
              IV <b className="text-slate-100">{selected.implied_volatility != null ? `${(selected.implied_volatility * 100).toFixed(0)}%` : "-"}</b> · OI <b className="text-slate-100">{selected.open_interest != null ? fmtN(selected.open_interest) : "-"}</b>
            </div>
          </div>

          {/* Matching suggestion risk (if any) */}
          {matching && (
            <div className="rounded border border-violet-800/50 bg-violet-950/10 px-3 py-2 text-[11px] font-mono text-slate-300 space-y-0.5">
              <div className="text-violet-300 uppercase tracking-widest text-[10px]">Strategy: {matching.strategy}</div>
              <div>maxP <b className="text-emerald-400">{fmt$(matching.max_profit_low)}</b> · maxL <b className="text-red-400">{fmt$(matching.max_loss)}</b> · RR <b className="text-slate-100">{matching.risk_reward_pct != null ? matching.risk_reward_pct.toFixed(2) : "-"}</b></div>
              <div>premium <b className="text-slate-100">{fmt$(matching.est_premium)}</b> · budget <b className="text-slate-100">{matching.budget_pct.toFixed(1)}%</b>{matching.liquidity_ok ? <span className="text-emerald-400"> · liq ✓</span> : <span className="text-amber-400"> · liq low</span>}</div>
            </div>
          )}

          {/* Order controls */}
          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">Side</span>
              <select value={side} onChange={e => setSide(e.target.value as "buy" | "sell")}
                className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200">
                <option value="buy">BUY</option>
                <option value="sell">SELL</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">Intent</span>
              <select value={intent} onChange={e => setIntent(e.target.value as typeof intent)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200">
                <option value="buy_to_open">BUY TO OPEN</option>
                <option value="sell_to_open">SELL TO OPEN</option>
                <option value="buy_to_close">BUY TO CLOSE</option>
                <option value="sell_to_close">SELL TO CLOSE</option>
              </select>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">Contracts</span>
              <input type="number" min={1} value={qty} onChange={e => setQty(Math.max(1, Number(e.target.value) || 1))}
                className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200" />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">Type</span>
              <select value={orderType} onChange={e => setOrderType(e.target.value as "market" | "limit")}
                className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200">
                <option value="market">MARKET</option>
                <option value="limit">LIMIT</option>
              </select>
            </label>
          </div>

          {orderType === "limit" && (
            <label className="space-y-1 block">
              <span className="text-[10px] text-slate-500 uppercase">Limit Price (per contract)</span>
              <input value={limitPrice} onChange={e => setLimitPrice(e.target.value)}
                placeholder={mid.toFixed(2)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200 placeholder:text-slate-600" />
            </label>
          )}

          {/* Status banner */}
          {placed && (
            <div className="flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/30 border border-emerald-800 rounded p-2">
              <CheckCircle2 size={12} />
              {placed.contract} {placed.status.toUpperCase()} {placed.fill != null ? fmt$(placed.fill) : ""} {placed.mode.toUpperCase()} id {placed.order_id}
            </div>
          )}
          {placeErr && (
            <div className="flex items-center gap-1.5 text-xs font-mono text-red-400 bg-red-950/30 border border-red-800 rounded p-2">
              <XCircle size={12} /> {placeErr}
            </div>
          )}

          <div className="flex gap-2">
            <button onClick={onClose} disabled={placing}
              className="flex-1 px-3 py-2 rounded bg-slate-800 border border-slate-600 text-xs font-bold text-slate-300 hover:bg-slate-700 disabled:opacity-50">
              Cancel
            </button>
            <button onClick={onSubmit} disabled={placing}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded bg-emerald-600/30 border border-emerald-500/40 text-xs font-bold text-emerald-300 hover:bg-emerald-600/50 disabled:opacity-50">
              {placing ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />} Execute on Alpaca Paper
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function StrategyCard({ s, sugMeta, onOpenTicket }: { s: OptionSuggestion; sugMeta: { max_loss_cap_pct: number; nav: number } | null; onOpenTicket: () => void }) {
  const riskNotes: string[] = [];
  if (s.max_loss_pct_nav != null && sugMeta && s.max_loss_pct_nav > sugMeta.max_loss_cap_pct) {
    riskNotes.push(`exceeds ${(sugMeta.max_loss_cap_pct)}% NAV cap`);
  }
  if (!s.liquidity_ok) riskNotes.push("low liquidity");
  if (s.hedge?.hedge_req) riskNotes.push("hedge required");

  return (
    <div className={clsx("rounded-lg border p-2.5 space-y-1.5 transition-all duration-200 hover:shadow-md hover:shadow-violet-500/10",
      s.rank === 1 ? "border-emerald-500/50 bg-emerald-950/10"
           : s.rank === 2 ? "border-slate-500/40 bg-slate-950"
           : "border-slate-700 bg-slate-950")}>
      <div className="flex flex-wrap items-center gap-2">
        {s.rank != null && s.rank <= 3 && (
          <span className={clsx("text-[10px] font-mono font-bold px-1.5 py-0.5 rounded",
            s.rank === 1 ? "bg-emerald-500/30 text-emerald-300" : "bg-slate-700 text-slate-300")}>
            #{s.rank}
          </span>
        )}
        <span className="text-xs font-bold text-slate-100">{s.strategy}</span>
        <span className="text-[10px] font-mono text-slate-500 uppercase">{s.signal_method}</span>
        {s.hedge?.hedge_req && (
          <span className="text-[10px] font-mono text-rose-300 bg-rose-950/40 border border-rose-800 rounded px-1.5 py-0.5" title={s.hedge.hedge_reason}>
            ⛨ hedge
          </span>
        )}
        <span className={clsx("ml-auto text-[10px] font-mono px-1.5 py-0.5 rounded",
          s.regime === "Crisis" || s.regime === "SystemicStress" ? "bg-red-950/60 text-red-300" : "bg-indigo-950/60 text-indigo-300")}>
          {s.regime} · w{s.regime_weight.toFixed(2)}
        </span>
        <span className="text-[10px] font-mono text-emerald-400">score {s.score.toFixed(2)}</span>
        {s.loss_aversion_score != null && (
          <span className={clsx("text-[10px] font-mono font-bold",
            s.loss_aversion_score >= s.score ? "text-emerald-300" : "text-rose-300")}>
            LA {s.loss_aversion_score.toFixed(2)}
          </span>
        )}
        <span className="text-[10px] font-mono text-slate-500">{Math.round(s.confidence * 100)}% conf</span>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] font-mono text-slate-300">
        <span>prem {fmt$(s.est_premium)}</span>
        <span className="text-emerald-400">maxP {fmt$(s.max_profit_low)}</span>
        <span className="text-red-400">maxL {fmt$(s.max_loss)}</span>
        {s.max_loss_pct_nav != null && (
          <span className={clsx("font-bold", s.max_loss_pct_nav > (sugMeta?.max_loss_cap_pct ?? 5) ? "text-rose-400" : "text-slate-400")}>
            {s.max_loss_pct_nav.toFixed(1)}% NAV
          </span>
        )}
        {s.risk_reward_pct != null && <span>RR {s.risk_reward_pct.toFixed(2)}</span>}
        {s.legs[0]?.delta != null && <span>Δ {s.legs[0].delta.toFixed(2)}</span>}
        <span>budget {s.budget_pct.toFixed(1)}%</span>
        {s.liquidity_ok ? <span className="text-emerald-400">liq ✓</span> : <span className="text-amber-400">liq low</span>}
      </div>

      <div className="text-[11px] text-slate-400 space-y-0.5">
        {s.legs.map((l) => (
          <div key={l.symbol} className="flex flex-wrap items-center gap-1.5 font-mono">
            <span className="text-violet-400">{l.side.replace(/_/g, " ").toUpperCase()}</span>
            <span>{l.symbol}</span>
            <span className="text-slate-600">strike {fmtN(l.strike)} {l.contract_type.toUpperCase()} x{l.contracts} @ {fmt$(l.mid)}</span>
          </div>
        ))}
      </div>

      {s.notes.length > 0 && <div className="text-[10px] text-slate-500">{s.notes.join(" · ")}</div>}

      {riskNotes.length > 0 && (
        <div className="flex items-center gap-1 text-[10px] font-mono text-amber-400 bg-amber-950/20 border border-amber-800/40 rounded px-2 py-1">
          <AlertTriangle size={10} /> {riskNotes.join(" · ")}
        </div>
      )}

      {s.hedge?.hedge_req && (
        <div className="text-[10px] font-mono text-rose-300/90 bg-rose-950/20 border border-rose-900/50 rounded px-2 py-1">
          ⛨ {s.hedge.hedge_reason} — see Dynamic Hedge panel below
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button onClick={onOpenTicket}
          className="flex items-center gap-1 px-2 py-1 rounded bg-emerald-600/30 border border-emerald-500/40 text-[10px] font-bold text-emerald-300 hover:bg-emerald-600/50 transition-colors">
          <ChevronRight size={10} /> Open in ticket
        </button>
        <span className="text-[10px] font-mono text-slate-600 truncate max-w-full">KG → {s.graph_path.join(" → ")}</span>
      </div>
    </div>
  );
}

function OrderTicket({
  selected, side, setSide, intent, setIntent, qty, setQty, orderType, setOrderType, limitPrice, setLimitPrice, placing, placed, placeErr, onSubmit,
}: {
  selected: OptionContractRow | null;
  side: "buy" | "sell";
  setSide: (s: "buy" | "sell") => void;
  intent: "buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close";
  setIntent: (i: "buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close") => void;
  qty: number;
  setQty: (q: number) => void;
  orderType: "market" | "limit";
  setOrderType: (t: "market" | "limit") => void;
  limitPrice: string;
  setLimitPrice: (p: string) => void;
  placing: boolean;
  placed: { order_id: string; status: string; contract: string; fill: number | null; mode: string } | null;
  placeErr: string | null;
  onSubmit: () => void;
}) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden transition-all duration-200 hover:border-slate-500 hover:shadow-lg hover:shadow-emerald-500/10">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
        <ArrowRightLeft size={14} className="text-emerald-400" />
        <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Order Ticket</span>
      </div>
      <div className="p-3 space-y-3">
        {!selected ? (
          <div className="text-xs text-slate-500 font-mono">Select a contract row above to trade it.</div>
        ) : (
          <>
            <div className="text-xs font-mono text-slate-200 bg-slate-950 border border-slate-700 rounded px-2 py-2">
              {selected.symbol}
              <span className="ml-2 text-slate-500">
                {selected.contract_type.toUpperCase()} x{selected.multiplier} {selected.expiration_date} Strike {fmtN(selected.strike_price)}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <label className="space-y-1">
                <span className="text-[10px] text-slate-500 uppercase">Side</span>
                <select value={side} onChange={e => setSide(e.target.value as "buy" | "sell")}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200">
                  <option value="buy">BUY</option>
                  <option value="sell">SELL</option>
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-[10px] text-slate-500 uppercase">Intent</span>
                <select value={intent} onChange={e => setIntent(e.target.value as typeof intent)}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200">
                  <option value="buy_to_open">BUY TO OPEN</option>
                  <option value="sell_to_open">SELL TO OPEN</option>
                  <option value="buy_to_close">BUY TO CLOSE</option>
                  <option value="sell_to_close">SELL TO CLOSE</option>
                </select>
              </label>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <label className="space-y-1">
                <span className="text-[10px] text-slate-500 uppercase">Contracts</span>
                <input type="number" min={1} value={qty} onChange={e => setQty(Math.max(1, Number(e.target.value) || 1))}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200" />
              </label>
              <label className="space-y-1">
                <span className="text-[10px] text-slate-500 uppercase">Type</span>
                <select value={orderType} onChange={e => setOrderType(e.target.value as "market" | "limit")}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200">
                  <option value="market">MARKET</option>
                  <option value="limit">LIMIT</option>
                </select>
              </label>
            </div>

            {orderType === "limit" && (
              <label className="space-y-1 block">
                <span className="text-[10px] text-slate-500 uppercase">Limit Price (per contract)</span>
                <input value={limitPrice} onChange={e => setLimitPrice(e.target.value)}
                  placeholder={(((selected.bid ?? 0) + (selected.ask ?? 0)) / 2).toFixed(2)}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200 placeholder:text-slate-600" />
              </label>
            )}

            <button onClick={onSubmit} disabled={placing}
              className="w-full flex items-center justify-center gap-2 py-2 rounded bg-emerald-600/30 border border-emerald-500/40 text-xs font-bold text-emerald-300 hover:bg-emerald-600/50 disabled:opacity-50">
              {placing ? <Loader2 size={12} className="animate-spin" /> : "Place Option Order"}
            </button>

            {placed && (
              <div className="flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/30 border border-emerald-800 rounded p-2">
                <CheckCircle2 size={12} />
                {placed.contract} {placed.status.toUpperCase()} {placed.fill != null ? fmt$(placed.fill) : ""} {placed.mode.toUpperCase()} id {placed.order_id}
              </div>
            )}
            {placeErr && (
              <div className="flex items-center gap-1.5 text-xs font-mono text-red-400 bg-red-950/30 border border-red-800 rounded p-2">
                <XCircle size={12} /> {placeErr}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
