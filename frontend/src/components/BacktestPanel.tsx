import { useState, useEffect, useRef } from "react";
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell, Legend,
} from "recharts";
import {
  agentApi, BacktestResult, TradeSuggestion,
  TradeLogEntry, StrategyBreakdown, WalkForwardWindow,
} from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmtPct, fmtN, fmt$, relTime } from "@/lib/utils";
import {
  Play, BarChart2, CheckCircle, XCircle, ChevronDown,
  ChevronRight, TrendingUp, TrendingDown, AlertTriangle, BookOpen,
} from "lucide-react";
import clsx from "clsx";

type RunMode = "grounded" | "ungrounded" | "both";
type ResultTab = "summary" | "equity" | "drawdown" | "trades" | "strategies" | "wf" | "suggestions";

const RESULT_TABS: { id: ResultTab; label: string }[] = [
  { id: "summary",     label: "Summary"     },
  { id: "equity",      label: "Equity Curve"},
  { id: "drawdown",    label: "Drawdown"    },
  { id: "trades",      label: "Trade Log"   },
  { id: "strategies",  label: "Strategies"  },
  { id: "wf",          label: "Walk-Fwd"    },
  { id: "suggestions", label: "Suggestions" },
];

export default function BacktestPanel() {
  const [startDate,  setStartDate]  = useState("2021-01-01");
  const [endDate,    setEndDate]    = useState("2023-12-31");
  const [capital,    setCapital]    = useState("10000");
  const [mode,       setMode]       = useState<RunMode>("both");
  const [rebalFreq,  setRebalFreq]  = useState("5");
  const [feePct,     setFeePct]     = useState("0.001");
  const [slipPct,    setSlipPct]    = useState("0.0005");
  const [running,    setRunning]    = useState(false);
  const [progress,   setProgress]   = useState<{ pct: number; msg: string } | null>(null);
  const [grounded,   setGrounded]   = useState<BacktestResult | null>(null);
  const [ungrounded, setUngrounded] = useState<BacktestResult | null>(null);
  const [resultTab,  setResultTab]  = useState<ResultTab>("summary");
  const [showParams, setShowParams] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { data: suggestions, refresh: refreshSuggestions } =
    usePolling(agentApi.backtestSuggestions, 15_000);

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };
  useEffect(() => stopPoll, []);

  const pollStatus = async () => {
    const res = await agentApi.backtestStatus();
    if (res.progress) setProgress(res.progress);
    if (res.grounded)   setGrounded(res.grounded);
    if (res.ungrounded) setUngrounded(res.ungrounded);
    if (res.status === "done" || res.status.startsWith("error")) {
      setRunning(false);
      stopPoll();
      refreshSuggestions?.();
    }
  };

  const handleRun = async () => {
    setRunning(true);
    setProgress({ pct: 0, msg: "Starting…" });
    setGrounded(null);
    setUngrounded(null);
    await agentApi.runBacktest({
      start_date: startDate, end_date: endDate,
      initial_capital: Number(capital),
      use_graph: mode !== "ungrounded",
      run_both:  mode === "both",
      rebal_freq: Number(rebalFreq),
      fee_pct:   Number(feePct),
      slip_pct:  Number(slipPct),
    });
    pollRef.current = setInterval(pollStatus, 2000);
  };

  const hasResults = grounded || ungrounded;
  const primary = grounded ?? ungrounded;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <BarChart2 size={16} className="text-indigo-400" />
        <h2 className="text-sm font-semibold text-slate-200">Walk-Forward Backtest</h2>
        <button
          onClick={() => setShowParams(v => !v)}
          className="ml-2 text-[10px] text-slate-500 hover:text-slate-300 font-mono"
        >
          {showParams ? "▲ hide params" : "▼ params"}
        </button>
        {running && progress && (
          <div className="ml-auto flex items-center gap-2">
            <div className="w-32 h-1.5 bg-slate-700 rounded-full overflow-hidden">
              <div className="h-full bg-indigo-500 transition-all duration-500 rounded-full"
                   style={{ width: `${progress.pct}%` }} />
            </div>
            <span className="text-xs font-mono text-indigo-400 animate-pulse">
              {progress.pct}% — {progress.msg.slice(0, 40)}
            </span>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <LabeledInput label="Start"        type="date"   value={startDate}  onChange={setStartDate} />
        <LabeledInput label="End"          type="date"   value={endDate}    onChange={setEndDate} />
        <LabeledInput label="Capital ($)"  type="number" value={capital}    onChange={setCapital} />
        <div>
          <div className="text-[10px] text-slate-400 mb-1 uppercase tracking-wider">Mode</div>
          <select value={mode} onChange={e => setMode(e.target.value as RunMode)}
            className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
            <option value="both">Both (KG vs baseline)</option>
            <option value="grounded">KG-Grounded only</option>
            <option value="ungrounded">Baseline only</option>
          </select>
        </div>
      </div>

      {showParams && (
        <div className="grid grid-cols-3 gap-2 p-3 bg-slate-800/50 rounded-lg border border-slate-700">
          <LabeledInput label="Rebal Freq (days)" type="number" value={rebalFreq} onChange={setRebalFreq} />
          <LabeledInput label="Fee % (e.g. 0.001)" type="number" value={feePct}   onChange={setFeePct} />
          <LabeledInput label="Slip % (e.g. 0.0005)" type="number" value={slipPct} onChange={setSlipPct} />
        </div>
      )}

      <button onClick={handleRun} disabled={running}
        className={clsx("flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
          running ? "bg-slate-700 text-slate-500 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-500 text-white")}>
        <Play size={14} className={running ? "animate-pulse" : ""} />
        {running ? "Running…" : "Run Backtest"}
      </button>

      {/* Result tabs */}
      {hasResults && (
        <>
          <div className="flex gap-0 border-b border-slate-700 overflow-x-auto">
            {RESULT_TABS.map(t => {
              const badge = t.id === "suggestions"
                ? (suggestions ?? []).filter(s => s.status === "pending").length
                : t.id === "trades" ? (primary?.n_trades ?? 0)
                : 0;
              return (
                <button key={t.id} onClick={() => setResultTab(t.id)}
                  className={clsx("px-3 py-2 text-xs font-mono whitespace-nowrap transition-colors border-b-2 -mb-px",
                    resultTab === t.id
                      ? "border-indigo-500 text-indigo-400"
                      : "border-transparent text-slate-400 hover:text-slate-200")}>
                  {t.label}
                  {badge > 0 && (
                    <span className="ml-1 px-1.5 py-0.5 rounded-full bg-indigo-900 text-indigo-300 text-[9px]">
                      {badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <div className="min-h-[300px]">
            {resultTab === "summary"     && <SummaryTab     g={grounded} u={ungrounded} />}
            {resultTab === "equity"      && <EquityTab      g={grounded} u={ungrounded} />}
            {resultTab === "drawdown"    && <DrawdownTab    g={grounded} u={ungrounded} />}
            {resultTab === "trades"      && <TradeLogTab    trades={primary?.trade_log ?? []} />}
            {resultTab === "strategies"  && <StrategyTab    g={grounded} u={ungrounded} />}
            {resultTab === "wf"          && <WalkFwdTab     g={grounded} />}
            {resultTab === "suggestions" && (
              <SuggestionsTab
                suggestions={suggestions ?? []}
                onAction={async (id, action) => {
                  await agentApi.actionSuggestion(id, action);
                  refreshSuggestions?.();
                }}
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Summary tab ────────────────────────────────────────────────────────────────
function SummaryTab({ g, u }: { g: BacktestResult | null; u: BacktestResult | null }) {
  const metrics: { label: string; key: keyof BacktestResult; fmt: (v: number) => string; good: "high" | "low" }[] = [
    { label: "Total Return",   key: "total_return",   fmt: fmtPct,          good: "high" },
    { label: "Sharpe Ratio",   key: "sharpe_ratio",   fmt: v => fmtN(v, 2), good: "high" },
    { label: "Calmar Ratio",   key: "calmar_ratio",   fmt: v => fmtN(v, 2), good: "high" },
    { label: "Max Drawdown",   key: "max_drawdown",   fmt: fmtPct,          good: "low"  },
    { label: "Ann. Vol",       key: "ann_volatility", fmt: fmtPct,          good: "low"  },
    { label: "Final NAV",      key: "final_nav",      fmt: fmt$,            good: "high" },
    { label: "# Trades",       key: "n_trades",       fmt: String,          good: "high" },
    { label: "Win Rate",       key: "win_rate",       fmt: fmtPct,          good: "high" },
    { label: "Profit Factor",  key: "profit_factor",  fmt: v => fmtN(v, 2), good: "high" },
    { label: "Avg Hold Days",  key: "avg_hold_days",  fmt: v => `${v}d`,    good: "high" },
  ];

  return (
    <div className="space-y-4">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="text-slate-400 border-b border-slate-700">
            <th className="text-left py-2">Metric</th>
            <th className="text-right py-2 text-indigo-400">KG-Grounded</th>
            {u && <th className="text-right py-2 text-slate-400">Baseline</th>}
            {u && <th className="text-right py-2 text-slate-500">Δ</th>}
          </tr>
        </thead>
        <tbody>
          {metrics.map(m => {
            const gv = g ? Number(g[m.key]) : null;
            const uv = u ? Number(u[m.key]) : null;
            const delta = gv !== null && uv !== null ? gv - uv : null;
            const pos = delta !== null ? (m.good === "high" ? delta >= 0 : delta <= 0) : null;
            return (
              <tr key={m.key} className="border-t border-slate-800">
                <td className="py-1.5 text-slate-400">{m.label}</td>
                <td className="py-1.5 text-right text-indigo-300">{gv !== null ? m.fmt(gv) : "—"}</td>
                {u && <td className="py-1.5 text-right text-slate-400">{uv !== null ? m.fmt(uv) : "—"}</td>}
                {u && <td className={clsx("py-1.5 text-right font-bold",
                  pos === null ? "text-slate-600" : pos ? "text-emerald-400" : "text-red-400")}>
                  {delta !== null ? `${delta >= 0 ? "+" : ""}${m.fmt(delta)}` : "—"}
                </td>}
              </tr>
            );
          })}
        </tbody>
      </table>

      {g?.jk_p_value != null && (
        <div className={clsx("rounded border px-3 py-2 text-xs font-mono",
          g.jk_significant ? "bg-emerald-950 border-emerald-700 text-emerald-300"
                           : "bg-slate-800 border-slate-600 text-slate-400")}>
          <span className="font-bold">Jobson-Korkie test: </span>
          {g.jk_significant
            ? `Statistically significant outperformance vs benchmark (p = ${g.jk_p_value.toFixed(4)})`
            : `Not statistically significant vs benchmark (p = ${g.jk_p_value.toFixed(4)})`}
        </div>
      )}

      {g?.regime_distribution && Object.keys(g.regime_distribution).length > 0 && (
        <div>
          <div className="text-[10px] text-slate-500 uppercase mb-2">Regime Distribution</div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(g.regime_distribution).map(([regime, pct]) => (
              <span key={regime} className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
                {regime} {fmtPct(pct)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Equity curve tab ──────────────────────────────────────────────────────────
function EquityTab({ g, u }: { g: BacktestResult | null; u: BacktestResult | null }) {
  const data = mergeByDate(
    g?.equity_curve?.map(p => ({ date: p.date, grounded: p.nav })) ?? [],
    u?.equity_curve?.map(p => ({ date: p.date, ungrounded: p.nav })) ?? [],
    g?.benchmark_curve?.map(p => ({ date: p.date, benchmark: p.nav })) ?? [],
  );
  if (!data.length) return <Empty />;
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#64748b" }} tickLine={false} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 9, fill: "#64748b" }} tickLine={false} tickFormatter={v => `$${(v/1000).toFixed(1)}k`} />
        <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                 formatter={(v: number, name: string) => [fmt$(v), name]} />
        <Legend wrapperStyle={{ fontSize: 10, color: "#94a3b8" }} />
        {g && <Line type="monotone" dataKey="grounded"  name="KG-Grounded" stroke="#6366f1" strokeWidth={2} dot={false} connectNulls />}
        {u && <Line type="monotone" dataKey="ungrounded" name="Baseline"   stroke="#475569" strokeWidth={1.5} dot={false} connectNulls strokeDasharray="4 2" />}
        {g?.benchmark_curve && <Line type="monotone" dataKey="benchmark" name="SPY Buy&Hold" stroke="#f59e0b" strokeWidth={1.5} dot={false} connectNulls strokeDasharray="6 3" />}
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Drawdown / underwater tab ─────────────────────────────────────────────────
function DrawdownTab({ g, u }: { g: BacktestResult | null; u: BacktestResult | null }) {
  const data = mergeByDate(
    g?.drawdown_series?.map(p => ({ date: p.date, grounded: p.dd })) ?? [],
    u?.drawdown_series?.map(p => ({ date: p.date, ungrounded: p.dd })) ?? [],
  );
  if (!data.length) return <Empty />;
  return (
    <div className="space-y-1">
      <div className="text-[10px] text-slate-500">Underwater curve (% below high-water mark)</div>
      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#64748b" }} tickLine={false} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 9, fill: "#64748b" }} tickLine={false} tickFormatter={v => `${v.toFixed(0)}%`} />
          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                   formatter={(v: number, name: string) => [`${v.toFixed(2)}%`, name]} />
          <ReferenceLine y={0} stroke="#475569" />
          {g && <Area type="monotone" dataKey="grounded"   name="KG-Grounded" stroke="#6366f1" fill="url(#ddGrad)" strokeWidth={2} dot={false} connectNulls />}
          {u && <Line type="monotone" dataKey="ungrounded" name="Baseline"     stroke="#475569" strokeWidth={1.5} dot={false} connectNulls strokeDasharray="4 2" />}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Trade log tab ─────────────────────────────────────────────────────────────
function TradeLogTab({ trades }: { trades: TradeLogEntry[] }) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<keyof TradeLogEntry>("exit_date");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);

  const filtered = trades
    .filter(t => !filter || t.ticker.includes(filter.toUpperCase()) || t.strategy.includes(filter) || t.regime.includes(filter))
    .sort((a, b) => {
      const av = a[sortKey]; const bv = b[sortKey];
      return sortDir * (av < bv ? -1 : av > bv ? 1 : 0);
    });

  const toggleSort = (key: keyof TradeLogEntry) => {
    if (sortKey === key) setSortDir(d => d === 1 ? -1 : 1);
    else { setSortKey(key); setSortDir(-1); }
  };

  if (!trades.length) return <Empty msg="No closed trades yet" />;

  const totalPnl = trades.reduce((s, t) => s + t.pnl, 0);
  const winners  = trades.filter(t => t.pnl > 0).length;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <input value={filter} onChange={e => setFilter(e.target.value)}
          placeholder="Filter by ticker / strategy / regime…"
          className="flex-1 bg-slate-800 border border-slate-700 text-xs text-slate-300 rounded px-2 py-1.5" />
        <span className="text-xs font-mono text-slate-400">
          {filtered.length}/{trades.length} trades
        </span>
        <span className={clsx("text-xs font-mono font-bold", totalPnl >= 0 ? "text-emerald-400" : "text-red-400")}>
          Net P&L: {totalPnl >= 0 ? "+" : ""}{fmt$(totalPnl)}
        </span>
        <span className="text-xs font-mono text-slate-400">
          WR: {fmtPct(winners / trades.length)}
        </span>
      </div>
      <div className="overflow-auto max-h-64">
        <table className="w-full text-xs font-mono">
          <thead className="sticky top-0 bg-slate-800 z-10">
            <tr className="text-slate-400">
              {(["ticker","strategy","regime","entry_date","exit_date","entry_price","exit_price","qty","pnl","hold_days"] as (keyof TradeLogEntry)[]).map(k => (
                <th key={k} onClick={() => toggleSort(k)}
                  className="py-1.5 px-2 text-left text-[10px] uppercase tracking-wider cursor-pointer hover:text-slate-200">
                  {k.replace(/_/g, " ")}{sortKey === k ? (sortDir === 1 ? " ↑" : " ↓") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((t, i) => (
              <tr key={i} className="border-t border-slate-800 hover:bg-slate-800/50">
                <td className="py-1 px-2 font-bold text-slate-100">{t.ticker}</td>
                <td className="py-1 px-2 text-slate-400 max-w-[100px] truncate" title={t.strategy}>{t.strategy}</td>
                <td className="py-1 px-2 text-slate-500 text-[10px]">{t.regime}</td>
                <td className="py-1 px-2 text-slate-500">{t.entry_date}</td>
                <td className="py-1 px-2 text-slate-500">{t.exit_date}</td>
                <td className="py-1 px-2 text-right text-slate-400">{fmt$(t.entry_price)}</td>
                <td className="py-1 px-2 text-right text-slate-400">{fmt$(t.exit_price)}</td>
                <td className="py-1 px-2 text-right text-slate-300">{t.qty.toFixed(4)}</td>
                <td className={clsx("py-1 px-2 text-right font-bold",
                  t.pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                  {t.pnl >= 0 ? "+" : ""}{fmt$(t.pnl)}
                </td>
                <td className="py-1 px-2 text-right text-slate-400">{t.hold_days}d</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Strategy breakdown tab ────────────────────────────────────────────────────
function StrategyTab({ g, u }: { g: BacktestResult | null; u: BacktestResult | null }) {
  const data = g?.strategy_breakdown ?? u?.strategy_breakdown ?? [];
  if (!data.length) return <Empty />;
  return (
    <div className="space-y-4">
      <ResponsiveContainer width="100%" height={Math.max(100, data.length * 36)}>
        <BarChart layout="vertical" data={data} margin={{ top: 0, right: 60, bottom: 0, left: 120 }}>
          <XAxis type="number" tick={{ fontSize: 9, fill: "#64748b" }} tickFormatter={v => fmt$(v)} />
          <YAxis type="category" dataKey="strategy" tick={{ fontSize: 10, fill: "#cbd5e1" }} width={115} />
          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                   formatter={(v: number, name: string) => [name === "total_pnl" ? fmt$(v) : fmtPct(v), name]} />
          <ReferenceLine x={0} stroke="#475569" />
          <Bar dataKey="total_pnl" name="Total P&L" radius={[0, 3, 3, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.total_pnl >= 0 ? "#6366f1" : "#ef4444"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="text-slate-400 border-b border-slate-700">
            <th className="text-left py-1.5">Strategy</th>
            <th className="text-right py-1.5">P&L</th>
            <th className="text-right py-1.5">Trades</th>
            <th className="text-right py-1.5">Win Rate</th>
            <th className="text-right py-1.5">Avg P&L</th>
          </tr>
        </thead>
        <tbody>
          {data.sort((a, b) => b.total_pnl - a.total_pnl).map((s, i) => (
            <tr key={i} className="border-t border-slate-800">
              <td className="py-1.5 text-slate-300">{s.strategy}</td>
              <td className={clsx("py-1.5 text-right font-bold",
                s.total_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                {s.total_pnl >= 0 ? "+" : ""}{fmt$(s.total_pnl)}
              </td>
              <td className="py-1.5 text-right text-slate-400">{s.n_trades}</td>
              <td className={clsx("py-1.5 text-right", s.win_rate > 0.5 ? "text-emerald-400" : "text-red-400")}>
                {fmtPct(s.win_rate)}
              </td>
              <td className={clsx("py-1.5 text-right",
                s.avg_pnl >= 0 ? "text-slate-300" : "text-red-400")}>
                {fmt$(s.avg_pnl)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Walk-forward windows tab ──────────────────────────────────────────────────
function WalkFwdTab({ g }: { g: BacktestResult | null }) {
  const windows = g?.walk_forward_windows ?? [];
  if (!windows.length) return <Empty msg="Walk-forward windows not available for this date range" />;
  return (
    <div className="space-y-3">
      <div className="text-[10px] text-slate-500">
        Out-of-sample performance per walk-forward window. Each window trains on {252} days, tests on {63} days.
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={windows} margin={{ top: 4, right: 8, bottom: 0, left: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="id" tick={{ fontSize: 9, fill: "#64748b" }} tickFormatter={v => `W${v + 1}`} />
          <YAxis tick={{ fontSize: 9, fill: "#64748b" }} tickFormatter={v => fmtPct(v)} />
          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                   formatter={(v: number, name: string) => [name === "total_return" ? fmtPct(v) : fmtN(v, 2), name]} />
          <ReferenceLine y={0} stroke="#475569" />
          <Bar dataKey="total_return" name="Return" radius={[3, 3, 0, 0]}>
            {windows.map((w, i) => (
              <Cell key={i} fill={w.total_return >= 0 ? "#6366f1" : "#ef4444"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="overflow-auto max-h-48">
        <table className="w-full text-xs font-mono">
          <thead className="sticky top-0 bg-slate-800">
            <tr className="text-slate-400">
              <th className="text-left py-1.5 px-2">Window</th>
              <th className="text-left py-1.5 px-2">Test Period</th>
              <th className="text-right py-1.5 px-2">Return</th>
              <th className="text-right py-1.5 px-2">Sharpe</th>
              <th className="text-right py-1.5 px-2">Max DD</th>
              <th className="text-right py-1.5 px-2">Trades</th>
              <th className="text-right py-1.5 px-2">Final NAV</th>
            </tr>
          </thead>
          <tbody>
            {windows.map(w => (
              <tr key={w.id} className="border-t border-slate-800">
                <td className="py-1 px-2 text-slate-400">W{w.id + 1}</td>
                <td className="py-1 px-2 text-slate-500 text-[10px]">{w.test_start} → {w.test_end}</td>
                <td className={clsx("py-1 px-2 text-right font-bold",
                  w.total_return >= 0 ? "text-emerald-400" : "text-red-400")}>
                  {fmtPct(w.total_return)}
                </td>
                <td className="py-1 px-2 text-right text-slate-300">{fmtN(w.sharpe_ratio, 2)}</td>
                <td className="py-1 px-2 text-right text-red-400">{fmtPct(w.max_drawdown)}</td>
                <td className="py-1 px-2 text-right text-slate-400">{w.n_trades}</td>
                <td className="py-1 px-2 text-right text-slate-300">{fmt$(w.final_nav)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Trade suggestions tab ─────────────────────────────────────────────────────
function SuggestionsTab({
  suggestions,
  onAction,
}: {
  suggestions: TradeSuggestion[];
  onAction: (id: string, action: string) => Promise<void>;
}) {
  const [pending, setPending] = useState<string>("");
  const act = async (id: string, action: string) => {
    setPending(id + action);
    await onAction(id, action);
    setPending("");
  };

  const queue = suggestions.filter(s => s.status === "pending");
  const acted = suggestions.filter(s => s.status !== "pending");

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <BookOpen size={13} className="text-indigo-400" />
        <span className="text-xs text-slate-300 font-semibold">
          KG-Backed Trade Suggestions
        </span>
        <span className="text-[10px] text-slate-500 ml-auto">
          Based on backtest strategy performance in current regime
        </span>
      </div>

      {queue.length === 0 && acted.length === 0 && (
        <div className="text-xs text-slate-500 py-4 text-center">
          No suggestions yet — run a backtest to generate KG-backed trade ideas.
        </div>
      )}

      {queue.map(s => (
        <div key={s.id} className="rounded-lg border border-indigo-800/50 bg-indigo-950/30 p-3 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-indigo-300">{s.ticker}</span>
                <span className={clsx("text-xs font-bold px-1.5 py-0.5 rounded",
                  s.direction === "buy" ? "bg-emerald-900/60 text-emerald-300" : "bg-red-900/60 text-red-300")}>
                  {s.direction.toUpperCase()}
                </span>
                <span className="text-[10px] text-slate-500 font-mono">{s.regime}</span>
              </div>
              <div className="text-xs text-slate-400 mt-0.5">{s.strategy}</div>
            </div>
            <div className="flex gap-2 shrink-0">
              <button
                disabled={!!pending}
                onClick={() => act(s.id, "approve")}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-medium disabled:opacity-50">
                <CheckCircle size={12} /> Approve
              </button>
              <button
                disabled={!!pending}
                onClick={() => act(s.id, "reject")}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs font-medium disabled:opacity-50">
                <XCircle size={12} /> Reject
              </button>
            </div>
          </div>
          <div className="text-[11px] text-slate-400 leading-relaxed">{s.rationale}</div>
          <div className="flex gap-4 text-[10px] font-mono text-slate-500">
            <span>Backtest P&L: <span className="text-emerald-400">{fmt$(s.backtest_pnl)}</span></span>
            <span>Trades: {s.backtest_trades}</span>
            <span>Win Rate: <span className={s.win_rate > 0.5 ? "text-emerald-400" : "text-red-400"}>{fmtPct(s.win_rate)}</span></span>
          </div>
        </div>
      ))}

      {acted.length > 0 && (
        <div className="mt-4 space-y-1">
          <div className="text-[10px] text-slate-600 uppercase tracking-wider mb-2">Actioned</div>
          {acted.map(s => (
            <div key={s.id} className="flex items-center gap-2 px-3 py-1.5 rounded border border-slate-800 bg-slate-800/30 text-xs font-mono">
              {s.status === "approve"
                ? <CheckCircle size={11} className="text-emerald-500" />
                : <XCircle    size={11} className="text-slate-500" />}
              <span className="text-slate-400">{s.ticker}</span>
              <span className="text-slate-500">{s.strategy}</span>
              <span className={clsx("ml-auto text-[10px]",
                s.status === "approve" ? "text-emerald-500" : "text-slate-600")}>
                {s.status.toUpperCase()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function mergeByDate(...arrays: { date: string; [k: string]: unknown }[][]): Record<string, unknown>[] {
  const map = new Map<string, Record<string, unknown>>();
  for (const arr of arrays) {
    for (const row of arr) {
      const existing = map.get(row.date) ?? { date: row.date };
      map.set(row.date, { ...existing, ...row });
    }
  }
  return Array.from(map.values()).sort((a, b) =>
    String(a.date).localeCompare(String(b.date)));
}

function Empty({ msg = "No data available" }: { msg?: string }) {
  return <div className="flex items-center justify-center h-40 text-slate-500 text-sm">{msg}</div>;
}

function LabeledInput({ label, type, value, onChange }:
  { label: string; type: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <div className="text-[10px] text-slate-400 mb-1 uppercase tracking-wider">{label}</div>
      <input type={type} value={value} onChange={e => onChange(e.target.value)}
        className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
    </div>
  );
}
