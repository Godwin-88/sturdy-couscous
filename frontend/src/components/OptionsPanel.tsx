import { useMemo, useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Activity, ArrowRightLeft, Loader2, CheckCircle2, XCircle, Brain, RefreshCw, Shield, Clock, AlertTriangle, Zap, ChevronRight, Filter, LineChart } from "lucide-react";
import { optionsApi, OptionContractRow, OptionSuggestion, OptionLeg, AlpacaAsset, HedgeState } from "@/lib/api";
import Greeks3DVisualization from "@/components/Greeks3DVisualization";
import OptionDiagrams from "@/components/OptionDiagrams";
import { fmt$, fmtN } from "@/lib/utils";
import { getScreenContext, setScreenContext, type ScreenContextData } from "@/lib/screenContext";
import clsx from "clsx";

const MOODS = ["call", "put"] as const;

// Regime catalogue — kept in sync with agent/regime_agent.py:194-237.
// "auto" (empty string) = use whatever RegimeAgent currently reports.
const REGIME_CHOICES: { value: string; label: string }[] = [
  { value: "",              label: "Auto (current)" },
  { value: "Trending",      label: "Trending" },
  { value: "MeanReverting", label: "Mean Reverting" },
  { value: "LowVolatility", label: "Low Volatility" },
  { value: "HighVolatility",label: "High Volatility" },
  { value: "Recovery",      label: "Recovery" },
  { value: "Crisis",        label: "Crisis" },
  { value: "SystemicStress",label: "Systemic Stress" },
];

type WireLeg = {
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  position_intent: "buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close";
};

/**
 * Collapse legs that share the same symbol+side+intent into a single
 * OptionLegRequest with summed qty. Required for ratio structures (butterfly,
 * strip, strap) where the agent emits the same option twice with qty=1 to
 * represent a 2x ratio — Alpaca's MLEG validator rejects duplicate symbols,
 * so the wire format must have one entry per symbol with ratio_qty=2.
 */
function consolidateLegs(legs: WireLeg[]): WireLeg[] {
  const byKey = new Map<string, WireLeg>();
  for (const l of legs) {
    const k = `${l.symbol}|${l.side}|${l.position_intent}`;
    const prev = byKey.get(k);
    if (prev) prev.qty += l.qty;
    else byKey.set(k, { ...l });
  }
  return Array.from(byKey.values());
}

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

export default function OptionsPanel({ onNavigate }: { onNavigate?: (tab: string) => void }) {
  const navigate = useNavigate();
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
  const [allStrategies, setAllStrategies] = useState<{ name: string; method: string | null; regimes: string[] }[]>([]);
  const [sugMeta, setSugMeta] = useState<{ regime: string; regime_confidence: number; spot_estimate: number | null; dte: number; active_strategies: string[]; lens: string; max_loss_cap_pct: number; nav: number; alt_expirations: string[]; alt_count: number; primary_count: number } | null>(null);
  const [loadingSug, setLoadingSug] = useState(false);
  const [sugErr, setSugErr] = useState<string | null>(null);
  const [rejected, setRejected] = useState<{ strategy: string; max_loss_pct_nav: number; reason: string }[]>([]);

  const [lens, setLens] = useState<"average" | "defensive">("defensive");
  const [regimeOverride, setRegimeOverride] = useState<string>("");
  const [strategyFilter, setStrategyFilter] = useState<string>("");

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
        regime: regimeOverride || sugMeta?.regime || undefined,
        strategy_filter: strategyFilter || undefined,
      },
    });
  }, [underlying, expiration, mood, selected, lens, sugMeta, rows.length, regimeOverride, strategyFilter]);

  // Auto-poll suggestions when a row is selected
  useEffect(() => {
    if (!selected) return;
    const interval = setInterval(() => {
      loadSuggestions();
    }, 15_000);
    return () => clearInterval(interval);
  }, [selected, underlying, expiration, mood, lens, regimeOverride, strategyFilter]);

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

  // Chain-aware deep links — the menu into Analytics (default = underlying
  // series, with the chain context passed via URL) and Risk (chain context is
  // already published to screenContext by the effect above).
  function goToAnalyze() {
    if (!underlying) return;
    const params = new URLSearchParams({ series: `px:${underlying}:Close` });
    params.set("underlying", underlying);
    if (expiration) params.set("expiration", expiration);
    params.set("contract_type", mood);
    if (atmApprox?.strike_price != null) params.set("strike", String(atmApprox.strike_price));
    navigate(`/analytics?${params.toString()}`);
  }

  function goToRisk() {
    onNavigate?.("risk");
  }

  async function loadSuggestions() {
    setLoadingSug(true);
    setSugErr(null);
    try {
      const res = await optionsApi.suggestions(underlying, {
        expiration: expiration || undefined,
        contract_type: mood,
        lens,
        regime: regimeOverride || undefined,
        strategy: strategyFilter || undefined,
      });
      setSuggestions(res.suggestions ?? []);
      setAllStrategies(res.all_strategies ?? []);
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
        alt_expirations: (res as { alt_expirations?: string[] }).alt_expirations ?? [],
        alt_count: (res as { alt_count?: number }).alt_count ?? 0,
        primary_count: (res as { primary_count?: number }).primary_count ?? res.suggestions?.length ?? 0,
      });
      // If the active strategy filter no longer matches any returned card,
      // clear it so the user isn't staring at an empty filtered list.
      const names = new Set((res.suggestions ?? []).map(s => s.strategy));
      setStrategyFilter(prev => (prev && !names.has(prev) ? "" : prev));
    } catch (e) {
      setSugErr(String(e));
      setSuggestions([]);
    } finally {
      setLoadingSug(false);
    }
  }

  function toggleLens() {
    setLens(prev => (prev === "defensive" ? "average" : "defensive"));
    setTimeout(loadSuggestions, 0);
  }

  function changeRegime(next: string) {
    setRegimeOverride(next);
    setStrategyFilter(""); // strategy mix changes with regime — clear stale filter
    setTimeout(loadSuggestions, 0);
  }

  function changeStrategyFilter(next: string) {
    // Server-side force-select: toggling picks a specific strategy from the
    // full KG library and re-scores it against the current chain (accurate
    // metrics computed even when the strategy isn't regime-active).
    setStrategyFilter(prev => {
      const nv = prev === next ? "" : next;
      setTimeout(loadSuggestions, 0);
      return nv;
    });
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

  // Regime pick deep-link: consume a pending orderDraft. Event-driven so it works even when Options was already mounted (no mount race), and deferred so the chain reload triggered by setMood/setExpiration settles first (its setSelected(null) won't clobber the prefill).
  const draftConsumed = useRef(false);
  const consumeDraft = useCallback((draft: OptionSuggestion, und?: string) => {
    if (draftConsumed.current || !draft?.legs?.length) return;
    draftConsumed.current = true;
    const u = und || draft.legs[0].symbol.replace(/[^A-Z]+$/, "");
    setUnderlying(u);
    const exp = expiryFromSymbol(draft.legs[0].symbol) || "";
    if (exp) setExpiration(exp);
    if (draft.legs[0].contract_type) setMood(draft.legs[0].contract_type as "call" | "put");
    // Let the chain-load effect run first, then open the modal prefilled
    window.setTimeout(() => openSuggestionInTicket(draft), 80);
    setScreenContext("options", { screen: "options" });
  }, []);
  useEffect(() => {
    const onCtx = (ev: Event) => {
      const detail = (ev as CustomEvent).detail as { screen?: string; data?: Partial<ScreenContextData> } | undefined;
      if (!detail || detail.screen !== "options") return;
      const draft = detail.data?.extra?.orderDraft as OptionSuggestion | undefined;
      if (draft?.legs?.length) consumeDraft(draft, detail.data?.underlying);
    };
    window.addEventListener("ga-screen-context", onCtx);
    // Also check on mount (first-mount path)
    const ctx = getScreenContext("options");
    const initial = ctx?.extra?.orderDraft as OptionSuggestion | undefined;
    if (initial?.legs?.length) consumeDraft(initial, ctx?.underlying);
    return () => window.removeEventListener("ga-screen-context", onCtx);
  }, [consumeDraft]);

  function openTradeModal(row: OptionContractRow) {
    setSelected(row);
    setPlaced(null);
    setPlaceErr(null);
    setModalOpen(true);
  }

  async function submitOrder() {
    if (!selected) return;
    if (orderClass === "vertical" && spreadLegs.length < 2) {
      setPlaceErr("Vertical spread needs at least 2 legs — switch to SIMPLE or pick a multi-leg suggestion.");
      return;
    }
    setPlacing(true); setPlaced(null); setPlaceErr(null);
    try {
      // Consolidate legs by symbol with summed qty. The agent sometimes builds
      // butterfly/strip/strap structures where the same symbol appears with a
      // ratio (e.g. sell 2x K2). Alpaca's MLEG validator rejects duplicate
      // symbols, so we collapse to one OptionLegRequest per symbol with the
      // combined ratio_qty.
      const wireLegs = orderClass === "vertical"
        ? consolidateLegs(spreadLegs.map(l => ({
            symbol: l.symbol,
            side: (l.side.startsWith("buy") ? "buy" : "sell") as "buy" | "sell",
            qty: Math.max(1, Number(l.contracts ?? 1) || 1),
            position_intent: l.side as "buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close",
          })))
        : undefined;

      const res = await optionsApi.place({
        contract_symbol: selected.symbol,
        qty,
        side,
        position_intent: intent,
        order_type: orderType,
        limit_price: orderType === "limit" && limitPrice ? Number(limitPrice) : null,
        label: "ui-manual",
        order_class: orderClass,
        legs: wireLegs,
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
          <div className="ml-auto flex items-center gap-1.5">
            <button onClick={goToAnalyze} disabled={!rows.length} title="Deep-link this chain into Analytics (default = underlying series)"
              className="flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-semibold font-mono bg-indigo-600/30 border border-indigo-500/40 text-indigo-300 hover:bg-indigo-600/50 disabled:opacity-40 disabled:cursor-not-allowed">
              <LineChart size={11} /> Analyze
            </button>
            <button onClick={goToRisk} title="Open Risk — chain context carries over"
              className="flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-semibold font-mono bg-rose-600/20 border border-rose-500/30 text-rose-300 hover:bg-rose-600/40">
              <Shield size={11} /> Risk
            </button>
          </div>
          <span className="flex items-center gap-1.5 text-[10px] font-mono text-emerald-400">
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
                regime <b className={clsx(regimeOverride ? "text-amber-300" : "text-slate-200")}>
                  {regimeOverride || sugMeta.regime}
                </b> ({sugMeta.regime_confidence.toFixed(2)}) · {sugMeta.dte} DTE · spot {sugMeta.spot_estimate != null ? fmt$(sugMeta.spot_estimate) : "-"} · {sugMeta.lens} lens
                {sugMeta.alt_count > 0 && (
                  <span className="ml-1 text-violet-300" title={`Also evaluating KG strategies against: ${sugMeta.alt_expirations.join(", ")}`}>
                    · +{sugMeta.alt_count} alt-expiry play{sugMeta.alt_count === 1 ? "" : "s"}
                  </span>
                )}
              </span>
            )}
            {/* Regime override — re-scores the strategy library via the KG ACTIVATED_BY edges. */}
            <label className="flex items-center gap-1 text-[10px] font-mono text-slate-400" title="Override the current regime to re-score this chain under a different market state.">
              <Filter size={10} className="text-slate-500" />
              <span className="uppercase text-slate-500">Regime:</span>
              <select
                value={regimeOverride}
                onChange={e => changeRegime(e.target.value)}
                disabled={!selected || loadingSug}
                className={clsx(
                  "rounded border px-1.5 py-0.5 text-[10px] font-mono outline-none",
                  regimeOverride
                    ? "bg-amber-950/40 border-amber-500/50 text-amber-200 hover:border-amber-400"
                    : "bg-slate-950 border-slate-700 text-slate-300 hover:border-slate-500",
                  "disabled:opacity-50"
                )}
              >
                {REGIME_CHOICES.map(r => (
                  <option key={r.value || "auto"} value={r.value}>{r.label}</option>
                ))}
              </select>
            </label>
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
                {/* Strategy picker — select ANY strategy from the full KG
                    library (not just regime-active ones). Choosing one
                    re-scores it against the current chain server-side, so the
                    metrics shown are computed from live option quotes. */}
                {(() => {
                  const library = allStrategies.length > 0 ? allStrategies : [];
                  if (library.length === 0 && suggestions.length === 0) return null;
                  const sorted = [...library].sort((a, b) => a.name.localeCompare(b.name));
                  const active = strategyFilter;
                  return (
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="text-[10px] text-slate-500 uppercase">Strategy:</span>
                      <select
                        value={active}
                        onChange={e => changeStrategyFilter(e.target.value)}
                        className="rounded border px-1.5 py-0.5 text-[10px] font-mono bg-slate-950 border-slate-700 text-slate-200 hover:border-slate-500 outline-none max-w-[220px]"
                        title="Select any KG strategy — metrics are re-computed live from the current option chain (regime-independent)."
                      >
                        <option value="">All strategies (regime-active)</option>
                        {sorted.map(s => (
                          <option key={s.name} value={s.name}>
                            {s.name}{s.regimes?.length ? `  [${s.regimes.join(", ")}]` : ""}
                          </option>
                        ))}
                      </select>
                      {active && (
                        <button
                          onClick={() => changeStrategyFilter("")}
                          className="text-[10px] font-mono px-1.5 py-0.5 rounded border bg-slate-800 border-slate-600 text-slate-300 hover:bg-slate-700"
                        >
                          ✕ clear
                        </button>
                      )}
                    </div>
                  );
                })()}
                {(strategyFilter
                  ? suggestions.filter(s => s.strategy === strategyFilter)
                  : suggestions
                ).map((s) => (
                  <StrategyCard
                    key={`${s.strategy}-${(s as OptionSuggestion & { expiration?: string }).expiration ?? ""}-${(s as OptionSuggestion & { contract_type?: string }).contract_type ?? ""}-${s.rank ?? 0}`}
                    s={s}
                    sugMeta={sugMeta}
                    onOpenTicket={() => openSuggestionInTicket(s)}
                  />
                ))}
                {strategyFilter && suggestions.filter(s => s.strategy === strategyFilter).length === 0 && (
                  <div className="text-[10px] font-mono text-slate-500">No computable card for {strategyFilter} on this chain right now (chain may not support its strikes/DTE) — try another strategy or expiry.</div>
                )}
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
          setSpreadLegs={setSpreadLegs}
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
  orderClass, setOrderClass, spreadLegs, setSpreadLegs,
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
  setSpreadLegs: (legs: OptionLeg[]) => void;
  placing: boolean;
  placed: { order_id: string; status: string; contract: string; fill: number | null; mode: string } | null;
  placeErr: string | null;
  matching: OptionSuggestion | null;
  onClose: () => void;
  onSubmit: () => void;
}) {
  const mid = ((selected.bid ?? 0) + (selected.ask ?? 0)) / 2;
  const isSpread = orderClass === "vertical" && spreadLegs.length > 1;

  // Live re-compute from the (editable) leg set — premium/net debit/credit,
  // max profit, max loss, based on each leg's mid quote × multiplier × qty.
  const legMetrics = (() => {
    const legs = isSpread ? spreadLegs : [];
    if (legs.length === 0) {
      // single leg
      const notional = (mid || 0) * (selected.multiplier ?? 100) * qty;
      return {
        premium: mid || 0,
        net: side === "buy" ? -notional : notional,
        max_profit: side === "buy" ? null : notional,
        max_loss: side === "buy" ? notional : null,
      };
    }
    let net = 0;
    for (const l of legs) {
      const legMid = l.mid ?? 0;
      const legNotional = legMid * (selected.multiplier ?? 100) * Math.max(1, Number(l.contracts ?? 1) || 1);
      net += l.side.startsWith("buy") ? -legNotional : legNotional;
    }
    // Max loss/profit approximation for a defined-risk vertical:
    // net > 0 = credit (maxP = net, maxL = width - net); net < 0 = debit.
    let max_profit: number | null = null;
    let max_loss: number | null = null;
    if (net >= 0) {
      max_profit = net;
    } else {
      max_loss = -net;
    }
    return { premium: null, net, max_profit, max_loss };
  })();

  function setLegQty(i: number, n: number) {
    const next = spreadLegs.map((l, idx) => (idx === i ? { ...l, contracts: Math.max(1, n || 1) } : l));
    setSpreadLegs(next);
  }
  function setLegSide(i: number, s: string) {
    const next = spreadLegs.map((l, idx) => (idx === i ? { ...l, side: s as OptionLeg["side"] } : l));
    setSpreadLegs(next);
  }
  function removeLeg(i: number) {
    setSpreadLegs(spreadLegs.filter((_, idx) => idx !== i));
  }
  function addLeg() {
    // Add a leg derived from the last one but with the opposite side, so the
    // user can build a genuine pair (e.g. BTO + STO) and edit it further.
    const last = spreadLegs[spreadLegs.length - 1];
    const base = last ?? {
      symbol: selected.symbol,
      strike: selected.strike_price,
      contract_type: selected.contract_type,
      mid,
      delta: selected.greeks?.delta,
    };
    const inverse = (base.side ?? "buy_to_open").startsWith("buy") ? "sell_to_open" : "buy_to_open";
    setSpreadLegs([...spreadLegs, {
      symbol: base.symbol,
      strike: base.strike,
      contract_type: base.contract_type,
      side: inverse as OptionLeg["side"],
      contracts: 1,
      mid: base.mid ?? mid,
      delta: base.delta,
    }]);
  }
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

          {/* Spread legs (when vertical) — editable: side/contracts per leg,
              add/remove legs, and metrics re-compute live from leg mids. */}
          {isSpread && (
            <div className="rounded border border-violet-800/40 bg-violet-950/10 px-3 py-2 space-y-1.5">
              <div className="flex items-center gap-2">
                <div className="text-[10px] text-violet-300 uppercase tracking-widest font-mono">Spread legs</div>
                <button onClick={addLeg}
                  className="ml-auto text-[10px] font-mono px-1.5 py-0.5 rounded border border-violet-500/40 bg-violet-950/40 text-violet-300 hover:bg-violet-900/50">
                  + leg
                </button>
              </div>
              {spreadLegs.map((l, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px] font-mono text-slate-300">
                  <select value={l.side}
                    onChange={e => setLegSide(i, e.target.value)}
                    className="bg-slate-950 border border-violet-700/60 rounded px-1 py-0.5 text-[10px] font-mono text-slate-200">
                    <option value="buy_to_open">BTO</option>
                    <option value="sell_to_open">STO</option>
                    <option value="buy_to_close">BTC</option>
                    <option value="sell_to_close">STC</option>
                  </select>
                  <span className="truncate flex-1 text-slate-400" title={l.symbol}>{l.symbol}</span>
                  <span>K {fmtN(l.strike)}</span>
                  <span className="text-slate-500">mid {l.mid != null ? fmt$(l.mid) : "-"}</span>
                  <input type="number" min={1} value={l.contracts ?? 1}
                    onChange={e => setLegQty(i, Number(e.target.value))}
                    className="w-14 bg-slate-950 border border-violet-700/60 rounded px-1 py-0.5 text-[10px] font-mono text-slate-200" />
                  <button onClick={() => removeLeg(i)} disabled={spreadLegs.length <= 1}
                    className="text-slate-500 hover:text-red-400 disabled:opacity-30 ml-0.5">
                    <XCircle size={11} />
                  </button>
                </div>
              ))}
              {/* Live recomputed metrics from the editable legs */}
              <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono pt-1.5 border-t border-violet-900/40">
                <div className="text-slate-300">
                  {legMetrics.net >= 0 ? "Net CREDIT" : "Net DEBIT"}{" "}
                  <b className={legMetrics.net >= 0 ? "text-emerald-400" : "text-amber-400"}>{fmt$(Math.abs(legMetrics.net))}</b>
                </div>
                <div className="text-slate-300">
                  maxP <b className="text-emerald-400">{legMetrics.max_profit != null ? fmt$(legMetrics.max_profit) : "-"}</b>
                </div>
                <div className="text-slate-300">
                  maxL <b className="text-red-400">{legMetrics.max_loss != null ? fmt$(legMetrics.max_loss) : "-"}</b>
                </div>
                <div className="text-slate-300">
                  RR <b className="text-slate-100">
                    {legMetrics.max_profit != null && legMetrics.max_loss != null && legMetrics.max_loss > 0
                      ? `${(legMetrics.max_profit / legMetrics.max_loss).toFixed(2)}`
                      : "-"}
                  </b>
                </div>
              </div>
              {matching && (
                <div className="text-[10px] text-slate-500 font-mono pt-1 border-t border-violet-900/40">
                  {matching.strategy} (agent) · maxP {fmt$(matching.max_profit_low)} · maxL {fmt$(matching.max_loss)} — edits re-compute above
                </div>
              )}
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
        {(s as OptionSuggestion & { chain_label?: string }).chain_label && (
          <span
            className={clsx(
              "text-[10px] font-mono px-1.5 py-0.5 rounded",
              (s as OptionSuggestion & { chain_source?: string }).chain_source === "primary"
                ? "bg-slate-800 text-slate-400 border border-slate-700"
                : (s as OptionSuggestion & { chain_source?: string }).chain_source === "alt_type"
                ? "bg-amber-950/40 text-amber-300 border border-amber-800/60"
                : "bg-violet-950/40 text-violet-300 border border-violet-800/60"
            )}
            title={
              (s as OptionSuggestion & { chain_source?: string }).chain_source === "primary"
                ? "Built from the chain you selected"
                : (s as OptionSuggestion & { chain_source?: string }).chain_source === "alt_type"
                ? "Built from the opposite contract type on the same expiry"
                : "Built from a nearby expiry — comparable play"
            }
          >
            {(s as OptionSuggestion & { chain_label?: string }).chain_label}
            {(s as OptionSuggestion & { chain_source?: string }).chain_source !== "primary" && (
              <span className="ml-1 opacity-70">alt</span>
            )}
          </span>
        )}
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
