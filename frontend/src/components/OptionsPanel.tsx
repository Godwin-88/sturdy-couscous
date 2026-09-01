import { useMemo, useState } from "react";
import { Search, Activity, ArrowRightLeft, Loader2, CheckCircle2, XCircle, Brain, RefreshCw, Shield } from "lucide-react";
import { optionsApi, OptionContractRow, OptionSuggestion, OptionLeg, AlpacaAsset, HedgeState } from "@/lib/api";
import { fmt$, fmtN } from "@/lib/utils";
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
    setSide(leg.side.startsWith("buy") ? "buy" : "sell");
    setIntent(leg.side);
    setSelected(legToRow(leg, expiration, underlying));
    setPlaced(null);
    setPlaceErr(null);
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
            <div className="max-h-[46vh] overflow-y-auto border border-slate-700 rounded">
              <table className="w-full text-xs font-mono">
                <thead className="sticky top-0 bg-slate-950">
                  <tr className="text-slate-500 border-b border-slate-700">
                    <th className="text-left py-1.5 px-2">Strike</th>
                    <th className="text-right px-2">Bid</th>
                    <th className="text-right px-2">Ask</th>
                    <th className="text-right px-2">Mid</th>
                    <th className="text-right px-2">Spread%</th>
                    <th className="text-right px-2">IV</th>
                    <th className="text-right px-2">Delta</th>
                    <th className="text-right px-2">Theta</th>
                    <th className="text-right px-2">OI</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => {
                    const mid = ((r.bid ?? 0) + (r.ask ?? 0)) / 2;
                    const isAtm = atmApprox?.symbol === r.symbol;
                    return (
                      <tr key={r.symbol}
                        onClick={() => { setSelected(r); loadSuggestions(); }}
                        className={clsx("border-b border-slate-800 cursor-pointer hover:bg-slate-800/60",
                          selected?.symbol === r.symbol ? "bg-indigo-600/10 ring-1 ring-inset ring-indigo-500/40" : "",
                          isAtm && selected?.symbol !== r.symbol ? "bg-slate-800/30" : "")}>
                        <td className="py-1.5 px-2 text-slate-200 font-bold">{fmtN(r.strike_price)}</td>
                        <td className="py-1 text-right text-emerald-400">{r.bid != null ? fmt$(r.bid) : "-"}</td>
                        <td className="py-1 text-right text-red-400">{r.ask != null ? fmt$(r.ask) : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{mid ? fmt$(mid) : "-"}</td>
                        <td className="py-1 text-right text-slate-400">{r.spread_pct != null ? `${(r.spread_pct * 100).toFixed(1)}%` : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{r.implied_volatility != null ? `${(r.implied_volatility * 100).toFixed(0)}%` : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{r.greeks?.delta != null ? r.greeks.delta.toFixed(2) : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{r.greeks?.theta != null ? fmt$(r.greeks.theta) : "-"}</td>
                        <td className="py-1 text-right text-slate-400">{r.open_interest != null ? fmtN(r.open_interest) : "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Agent Suggestions — KG-grounded, computed from selected chain metrics */}
      <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
          <Brain size={14} className="text-violet-400" />
          <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Agent Suggestions</span>
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
                <div key={s.strategy} className={clsx("rounded-lg border p-2.5 space-y-1.5",
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

                  {s.hedge?.hedge_req && (
                    <div className="text-[10px] font-mono text-rose-300/90 bg-rose-950/20 border border-rose-900/50 rounded px-2 py-1">
                      ⛨ {s.hedge.hedge_reason} — see Dynamic Hedge panel below
                    </div>
                  )}

                  <div className="flex flex-wrap items-center gap-2">
                    <button onClick={() => openLegInTicket(s.legs[0])}
                      className="px-2 py-1 rounded bg-emerald-600/30 border border-emerald-500/40 text-[10px] font-bold text-emerald-300 hover:bg-emerald-600/50">
                      Open in ticket →
                    </button>
                    <span className="text-[10px] font-mono text-slate-600 truncate max-w-full">KG → {s.graph_path.join(" → ")}</span>
                  </div>
                </div>
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

      {/* Dynamic Delta Hedge — Taleb posture, dry-run by default */}
      <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
          <Shield size={14} className="text-rose-400" />
          <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Dynamic Delta Hedge</span>
          <span className="text-[10px] font-mono text-slate-500">dry-run first · human confirms execution</span>
          <button onClick={loadHedge} disabled={loadingHedge}
            className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded bg-rose-600/20 border border-rose-500/30 text-[10px] text-rose-300 hover:bg-rose-600/40 disabled:opacity-50">
            {loadingHedge ? <Loader2 size={10} className="animate-spin" /> : <Activity size={10} />} State
          </button>
        </div>
        <div className="p-3 space-y-2">
          {hedgeMsg && <div className="text-[10px] font-mono text-slate-300 bg-slate-950 border border-slate-700 rounded p-2">{hedgeMsg}</div>}
          {!hedgeState ? (
            <div className="text-xs text-slate-500 font-mono">
              {loadingHedge ? "Reading portfolio greeks from Alpaca…" : "Open a position (or place an option order) then load hedge state — the agent aggregates delta/gamma/theta/vega and tells you what to hedge."}
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] font-mono text-slate-300">
                <span>δ <b className={hedgeState.greeks.delta >= 0 ? "text-emerald-300" : "text-rose-300"}>{hedgeState.greeks.delta.toFixed(1)}</b></span>
                <span>γ <b className="text-slate-300">{hedgeState.greeks.gamma.toFixed(2)}</b></span>
                <span>θ <b className="text-amber-300">{fmt$(hedgeState.greeks.theta)}</b></span>
                <span>V <b className="text-slate-300">{hedgeState.greeks.vega.toFixed(1)}</b></span>
                <span>spot {hedgeState.spot != null ? fmt$(hedgeState.spot) : "-"}</span>
                <span>hedge ≤ {hedgeState.band_shares.toFixed(0)} shares band</span>
                <span>regime <b className="text-indigo-300">{hedgeState.regime}</b></span>
              </div>
              {hedgeState.needs_rebalance && hedgeState.proposal ? (
                <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono">
                  <span className="text-rose-300">⛨ {hedgeState.proposal.side.toUpperCase()} {hedgeState.proposal.qty} {hedgeState.proposal.symbol}</span>
                  <button onClick={() => runHedge(false)}
                    className="px-2 py-1 rounded bg-slate-700/50 border border-slate-600 text-[10px] font-bold text-slate-200 hover:bg-slate-700 disabled:opacity-50">
                    Dry-run hedge
                  </button>
                  <button onClick={() => { if (window.confirm(`Place ${hedgeState.proposal!.side.toUpperCase()} ${hedgeState.proposal!.qty} ${underlying} on Alpaca PAPER? (human-in-the-loop)`)) runHedge(true); }}
                    className="px-2 py-1 rounded bg-rose-600/30 border border-rose-500/40 text-[10px] font-bold text-rose-200 hover:bg-rose-600/50 disabled:opacity-50">
                    Execute on paper
                  </button>
                </div>
              ) : (
                <div className="text-[11px] font-mono text-emerald-400/90">✓ delta within band — no rebalance required</div>
              )}
              {hedgeState.tail_sleeve.recommended ? (
                <div className="text-[10px] font-mono text-amber-300/90 bg-amber-950/20 border border-amber-800/50 rounded px-2 py-1">
                  🛡 Tail sleeve: {hedgeState.tail_sleeve.suggest}
                  <div className="text-slate-500">{hedgeState.tail_sleeve.note}</div>
                </div>
              ) : (
                <div className="text-[10px] font-mono text-slate-600">tail sleeve: {hedgeState.tail_sleeve.reason}</div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Order ticket */}
      <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
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

              <button onClick={submitOrder} disabled={placing}
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
    </div>
  );
}
