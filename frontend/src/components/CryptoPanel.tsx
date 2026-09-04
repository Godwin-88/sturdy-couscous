import { useEffect, useMemo, useState, useRef, useCallback } from "react";
import {
  Search, RefreshCw, Loader2, Activity, TrendingUp, TrendingDown,
  Brain, Shield, Clock, Zap, ArrowRight, CheckCircle2, AlertTriangle, LineChart as LineIcon,
} from "lucide-react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { cryptoApi, type CryptoAsset, type CryptoSuggestions, type CryptoCard } from "../lib/api";
import { setScreenContext } from "../lib/screenContext";
import clsx from "clsx";

const QUICK_PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "XRP/USD", "ADA/USD"];
const REGIMES = ["Neutral", "Trending", "MeanReverting", "HighVolatility", "LowVolatility", "Crisis", "Recovery", "SystemicStress"];

export default function CryptoPanel() {
  const [pair, setPair] = useState("BTC/USD");
  const [assets, setAssets] = useState<CryptoAsset[]>([]);
  const [q, setQ] = useState("");
  const [tape, setTape] = useState<{ rows: number; prices: { t: string; close: number; volume?: number }[] }>({ rows: 0, prices: [] });
  const [sug, setSug] = useState<CryptoSuggestions | null>(null);
  const [lens, setLens] = useState<"defensive" | "average">("defensive");
  const [regime, setRegime] = useState<string | "">("");
  const [strategyFilter, setStrategyFilter] = useState<string>("");
  const [nav, setNav] = useState(100000);
  const [loadingTape, setLoadingTape] = useState(false);
  const [loadingSug, setLoadingSug] = useState(false);
  const [tapeErr, setTapeErr] = useState<string | null>(null);
  const [sugErr, setSugErr] = useState<string | null>(null);

  // Order modal state (two-phase HITL)
  const [modalOpen, setModalOpen] = useState(false);
  const [orderSide, setOrderSide] = useState("buy");
  const [orderQty, setOrderQty] = useState("1");
  const [orderType, setOrderType] = useState("market");
  const [limitPrice, setLimitPrice] = useState("");
  const [placedCard, setPlacedCard] = useState<CryptoCard | null>(null);
  // proposal flow
  const [token, setToken] = useState<string | null>(null);
  const [previewInfo, setPreviewInfo] = useState<{ notional: number; fee: number } | null>(null);
  const [execInfo, setExecInfo] = useState<string | null>(null);
  const [execErr, setExecErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pub = useCallback((extra = {}) => {
    setScreenContext("crypto", { screen: "crypto", underlying: pair, regime: regime || undefined, lens, extra: { orderDraft: undefined as any, regime: regime || null, lens, strategy: strategyFilter || null, ...extra } });
  }, [pair, regime, lens, strategyFilter]);
  useMemo(() => pub({}), [pub]);

  const loadTape = useCallback(async (p = pair) => {
    setLoadingTape(true); setTapeErr(null);
    try {
      const t = await cryptoApi.tape(p, 90);
      setTape(t);
    } catch (e: any) { setTapeErr(String(e?.message || e)); setTape({ rows: 0, prices: [] }); }
    setLoadingTape(false);
  }, [pair]);

  const loadSug = useCallback(async (p = pair, l = lens, r = regime, n = nav, st = strategyFilter) => {
    setLoadingSug(true); setSugErr(null);
    try {
      const s = await cryptoApi.suggestions(p, l, n, r || null, st || null);
      setSug(s);
    } catch (e: any) { setSugErr(String(e?.message || e)); setSug(null); }
    setLoadingSug(false);
  }, [pair, lens, regime, nav, strategyFilter]);

  const loadAll = useCallback(async (p = pair) => {
    await Promise.all([loadTape(p), loadSug(p, lens, regime, nav, strategyFilter)]);
    pub({});
  }, [pair, lens, regime, nav, strategyFilter, loadTape, loadSug, pub]);

  // Initial load + whenever pair/filters change
  useEffect(() => { loadAll(pair); }, [pair]);
  useEffect(() => { if (pair) loadSug(pair, lens, regime, nav, strategyFilter); }, [lens, regime, nav, strategyFilter]);

  // Universe search
  const search = useCallback(async (query = q) => {
    try { setAssets((await cryptoApi.searchPairs(query)).slice(0, 40)); } catch { /* noop */ }
  }, [q]);
  useEffect(() => { search(q); }, [q]);
  useEffect(() => { search(""); }, []);

  const pickPair = (p: string) => { setPair(p); setQ(""); setStrategyFilter(""); };

  const openTicket = (card: CryptoCard) => {
    setPlacedCard(card);
    setOrderSide(card.side);
    setOrderType("market");
    setToken(null); setPreviewInfo(null); setExecInfo(null); setExecErr(null);
    setModalOpen(true);
  };

  const doPreview = async () => {
    setBusy(true); setExecErr(null); setExecInfo(null);
    try {
      const p = await cryptoApi.preview({ pair, side: orderSide, qty: Number(orderQty) || 0, order_type: orderType, limit_price: orderType === "limit" ? Number(limitPrice) || null : null });
      setToken(p.proposal_token);
      setPreviewInfo({ notional: p.risk_preview.estimated_notional_usd, fee: p.risk_preview.estimated_fee_usd });
    } catch (e: any) { setExecErr(String(e?.message || e)); }
    setBusy(false);
  };

  const doConfirm = async () => {
    if (!token) return;
    setBusy(true); setExecErr(null); setExecInfo(null);
    try {
      const c = await cryptoApi.confirm({ pair, side: orderSide, qty: Number(orderQty) || 0, order_type: orderType, limit_price: orderType === "limit" ? Number(limitPrice) || null : null, proposal_token: token });
      setExecInfo(`Filled ${c.pair} ${c.side.toUpperCase()} ${c.qty} @ ${c.filled_avg_price ?? "—"} (${c.status}) · order ${c.order_id.slice(0, 8)}`);
      setToken(null); setPreviewInfo(null);
      setTimeout(() => loadAll(), 1500);
    } catch (e: any) { setExecErr(String(e?.message || e)); }
    setBusy(false);
  };

  const chartData = useMemo(() => tape.prices.map((p, i) => ({ i, ...p })), [tape]);
  const atmDelta = sug?.spot ?? (tape.prices.length ? tape.prices[tape.prices.length - 1].close : null);

  return (
    <div className="p-3 space-y-3 text-sm">
      {/* Header: pair search — full Alpaca crypto universe */}
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-3">
        <div className="flex items-center gap-2">
          <Zap size={14} className="text-amber-400" />
          <span className="text-xs font-semibold uppercase tracking-widest text-slate-300">Crypto — Alpaca universe</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <div className="flex flex-1 min-w-[220px] items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1">
            <Search size={13} className="text-slate-500" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search any pair… (SOL, DOGE, XRP…)"
              className="w-full bg-transparent text-xs font-mono text-slate-200 outline-none placeholder:text-slate-500" />
          </div>
          <button onClick={() => setPair(q.toUpperCase().includes("/") ? q.toUpperCase() : `${q.toUpperCase()}/USD`)} disabled={!q}
            className="px-3 py-1 rounded bg-amber-600/30 border border-amber-500/40 text-[11px] font-bold text-amber-200 hover:bg-amber-600/50 disabled:opacity-40">Go</button>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {assets.map((a) => (
            <button key={a.pair} onClick={() => pickPair(a.pair)}
              className={clsx("px-2 py-0.5 rounded border text-[10px] font-mono",
                pair === a.pair ? "bg-amber-600/30 border-amber-500/50 text-amber-200" : "border-slate-700 text-slate-400 hover:bg-slate-800")}>
              {a.pair} {a.name ? `· ${a.name.slice(0, 18)}` : ""}
            </button>
          ))}
          {assets.length === 0 && QUICK_PAIRS.map((p) => (
            <button key={p} onClick={() => pickPair(p)}
              className={clsx("px-2 py-0.5 rounded border text-[10px] font-mono",
                pair === p ? "bg-amber-600/30 border-amber-500/50 text-amber-200" : "border-slate-700 text-slate-400 hover:bg-slate-800")}>
              {p}
            </button>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] font-mono text-slate-400">
          <span className="text-slate-500">lens</span>
          <button onClick={() => setLens(lens === "defensive" ? "average" : "defensive")}
            className={clsx("px-2 py-0.5 rounded border font-bold", lens === "defensive" ? "bg-rose-600/30 border-rose-500/40 text-rose-300" : "bg-amber-600/20 border-amber-500/30 text-amber-300")}>
            {lens === "defensive" ? "Defensive λ3.5" : "Average λ2.25"}
          </button>
          <span className="text-slate-500">regime</span>
          <select value={regime} onChange={(e) => setRegime(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded px-1 py-0.5 text-[10px] font-mono text-slate-300">
            <option value="">auto</option>
            {REGIMES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <span className="text-slate-500">strategy</span>
          <select value={strategyFilter || ""} onChange={(e) => setStrategyFilter(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded px-1 py-0.5 text-[10px] font-mono text-slate-300 max-w-[170px]">
            <option value="">all strategies</option>
            {(sug?.all_strategies ?? []).map((s) => (
              <option key={s.name} value={s.name}>
                {s.name}{s.computable === false ? " ⛔(spot-incompatible)" : ""}
              </option>
            ))}
          </select>
          <span className="text-slate-500">nav</span>
          <input type="number" value={nav} onChange={(e) => setNav(Number(e.target.value) || 0)}
            className="w-24 bg-slate-950 border border-slate-700 rounded px-1 py-0.5 text-[10px] font-mono text-slate-200" />
          <button onClick={() => loadAll()} disabled={loadingTape || loadingSug}
            className="ml-auto flex items-center gap-1 px-2 py-0.5 rounded bg-slate-700/40 border border-slate-600 text-[10px] text-slate-200 hover:bg-slate-700 disabled:opacity-50">
            {loadingTape || loadingSug ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />} Refresh
          </button>
        </div>
      </div>

      {/* Tape — the chain-equivalent */}
      <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
          <LineIcon size={14} className="text-sky-400" />
          <span className="text-xs font-semibold uppercase tracking-widest text-slate-300">{pair} · 90d tape</span>
          {atmDelta != null && (
            <span className="ml-auto text-xs font-mono text-slate-200">
              spot <b className="text-amber-300">${atmDelta.toLocaleString()}</b>
            </span>
          )}
        </div>
        {tapeErr ? <div className="p-3 text-xs text-red-400 font-mono">{tapeErr}</div>
          : tape.rows === 0 ? <div className="p-3 text-xs text-slate-500 font-mono">No tape — pick a pair above.</div>
          : (
            <div className="h-40 px-2 py-1">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid stroke="#1e293b" />
                  <XAxis dataKey="t" hide />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 9, fill: "#64748b" }} width={62} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 11 }} />
                  <Line type="monotone" dataKey="close" stroke="#38bdf8" dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        {sug && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 px-3 pb-2 text-[10px] font-mono text-slate-400">
            <span>12-1 <b className="text-slate-200">{sug.mom_12_1 != null ? (sug.mom_12_1 * 100).toFixed(2) + "%" : "—"}</b></span>
            <span>21-7 <b className="text-slate-200">{sug.mom_21_7 != null ? (sug.mom_21_7 * 100).toFixed(2) + "%" : "—"}</b></span>
            <span>RV21 <b className="text-slate-200">{sug.rv_21 != null ? (sug.rv_21 * 100).toFixed(0) + "%" : "—"}</b></span>
            <span>RV pctile <b className="text-slate-200">{sug.rv_pctile != null ? (sug.rv_pctile * 100).toFixed(0) + "%" : "—"}</b></span>
            <span>regime <b className="text-violet-300">{sug.regime ?? "—"}</b></span>
          </div>
        )}
      </div>

      {/* Agent suggestions — FE/KG-grounded, loss-averse ranked */}
      <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
          <Brain size={14} className="text-violet-400" />
          <span className="text-xs font-semibold uppercase tracking-widest text-slate-300">Agent Suggestions</span>
          <span className="ml-1 text-[10px] font-mono text-slate-500">KG crypto strategies · loss-averse lens</span>
          {sug && sug.regime && <span className="ml-auto text-[10px] font-mono text-violet-300">{sug.regime}</span>}
        </div>
        <div className="p-3 space-y-2">
          {sugErr ? <div className="text-xs font-mono text-red-400 bg-red-950/30 border border-red-800 rounded p-2">{sugErr}</div>
            : loadingSug && !sug ? <div className="flex items-center gap-2 text-xs text-slate-400 font-mono"><Loader2 size={12} className="animate-spin" /> Computing {pair} strategies from tape + KG…</div>
            : !sug || sug.suggestions.length === 0 ? (
              sug?.filter_note ? <div className="text-xs font-mono text-amber-300 bg-amber-950/20 border border-amber-800 rounded p-2">{sug.filter_note}</div>
              : <div className="text-xs text-slate-500 font-mono">No strategies scored for {pair} right now — try another pair, lens, regime or strategy.</div>
            )
            : sug.suggestions.map((s) => (
              <div key={s.strategy} className="rounded-lg border border-slate-700 bg-slate-950/40 p-2 flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold text-slate-100">{s.strategy}</span>
                {s.activated !== false && s.activated !== undefined ? (
                  <span className="text-[9px] font-mono px-1 py-0.5 rounded bg-violet-600/20 text-violet-300 border border-violet-700">regime {s.regime ?? "—"}</span>
                ) : (
                  <span className="text-[9px] font-mono px-1 py-0.5 rounded bg-slate-700/30 text-slate-400 border border-slate-600">not regime-active (forced)</span>
                )}
                <span className={clsx("text-[10px] font-mono px-1.5 py-0.5 rounded", s.side === "buy" ? "bg-emerald-600/20 text-emerald-300 border border-emerald-700" : "bg-red-600/20 text-red-300 border border-red-700")}>{s.side.toUpperCase()}</span>
                <span className="text-[10px] font-mono text-slate-400">qty {s.qty_rec.toFixed(3)}</span>
                <span className="text-[10px] font-mono text-amber-300">score {s.score.toFixed(1)}</span>
                <span className="text-[10px] font-mono text-emerald-300">maxP ${s.max_profit_low.toLocaleString()}</span>
                <span className="text-[10px] font-mono text-red-300">maxL ${s.max_loss.toLocaleString()} ({s.max_loss_pct_nav * 100}% NAV)</span>
                <span className="text-[10px] font-mono text-slate-500">RR {s.risk_reward_pct.toFixed(1)}%</span>
                <button onClick={() => openTicket(s)}
                  className="ml-auto flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-600/30 border border-emerald-500/40 text-[10px] font-bold text-emerald-200 hover:bg-emerald-600/50">
                  Open in ticket <ArrowRight size={10} />
                </button>
              </div>
            ))}
        </div>
      </div>

      {/* Order modal — two-phase HITL */}
      {modalOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60" onClick={() => setModalOpen(false)}>
          <div className="w-[460px] max-w-[92vw] rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2">
              <Shield size={14} className="text-rose-400" />
              <span className="text-sm font-bold text-slate-100">Crypto Order — {pair}</span>
              <button onClick={() => setModalOpen(false)} className="ml-auto text-slate-500 hover:text-slate-300">✕</button>
            </div>
            {placedCard && (
              <div className="rounded-lg border border-slate-700 bg-slate-950/40 p-2 text-[10px] font-mono">
                <div className="text-slate-300 font-semibold">{placedCard.strategy}</div>
                <div className="text-slate-500">maxP ${placedCard.max_profit_low.toLocaleString()} · maxL ${placedCard.max_loss.toLocaleString()} ({placedCard.max_loss_pct_nav * 100}% NAV) · score {placedCard.score.toFixed(1)}</div>
                {placedCard.notes?.map((n, i) => <div key={i} className="text-slate-400">· {n}</div>)}
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              <label className="text-[10px] uppercase tracking-widest text-slate-500">Side
                <select value={orderSide} onChange={(e) => setOrderSide(e.target.value)}
                  className="w-full mt-0.5 bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200">
                  <option value="buy">buy</option><option value="sell">sell</option>
                </select>
              </label>
              <label className="text-[10px] uppercase tracking-widest text-slate-500">Qty ({pair.split("/")[0]})
                <input value={orderQty} onChange={(e) => setOrderQty(e.target.value)}
                  className="w-full mt-0.5 bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200" />
              </label>
              <Select label="Type" value={orderType} onChange={setOrderType} opts={[["market", "market"], ["limit", "limit"]]} />
              {orderType === "limit" && (
                <label className="text-[10px] uppercase tracking-widest text-slate-500">Limit ($)
                  <input value={limitPrice} onChange={(e) => setLimitPrice(e.target.value)} placeholder="limit price"
                    className="w-full mt-0.5 bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200" />
                </label>
              )}
            </div>
            {previewInfo && (
              <div className="rounded-lg border border-amber-700/50 bg-amber-950/10 p-2 text-[10px] font-mono text-amber-200">
                Preview: notional ${previewInfo.notional.toLocaleString()} · fee ${previewInfo.fee.toLocaleString()} · token active (10m) — nothing placed yet.
              </div>
            )}
            {execInfo && <div className="flex items-center gap-1.5 text-[11px] text-emerald-300 font-mono"><CheckCircle2 size={12} /> {execInfo}</div>}
            {execErr && <div className="flex items-center gap-1.5 text-[11px] text-red-300 font-mono"><AlertTriangle size={12} /> {execErr}</div>}
            <div className="flex gap-2 pt-1">
              <button onClick={doPreview} disabled={busy}
                className="flex-1 py-2 rounded bg-slate-700/60 border border-slate-600 text-xs font-bold text-slate-200 hover:bg-slate-700 disabled:opacity-50">
                {busy && !token ? <Loader2 size={12} className="animate-spin inline mr-1" /> : null} 1️⃣ Preview
              </button>
              <button onClick={doConfirm} disabled={!token || busy}
                className="flex-1 py-2 rounded bg-emerald-600/30 border border-emerald-500/40 text-xs font-bold text-emerald-200 hover:bg-emerald-600/50 disabled:opacity-40 disabled:cursor-not-allowed">
                2️⃣ Execute on Alpaca paper
              </button>
            </div>
            <div className="text-[9px] font-mono text-slate-500">Human-in-the-loop: preview issues a one-time token (10-min); execute requires it. Repo/NAV caps enforced server-side.</div>
          </div>
        </div>
      )}
    </div>
  );
}

function Select({ label, value, onChange, opts }: { label: string; value: string; onChange: (v: string) => void; opts: [string, string][] }) {
  return (
    <label className="text-[10px] uppercase tracking-widest text-slate-500">{label}
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full mt-0.5 bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200">
        {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}
