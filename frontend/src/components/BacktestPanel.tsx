import { useState, useEffect, useRef } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";
import { agentApi, BacktestResult } from "@/lib/api";
import { fmtPct, fmtN } from "@/lib/utils";
import { Play, BarChart2 } from "lucide-react";
import clsx from "clsx";

type Comparison = { grounded: BacktestResult | null; ungrounded: BacktestResult | null };

export default function BacktestPanel() {
  const [startDate, setStartDate] = useState("2021-01-01");
  const [endDate,   setEndDate]   = useState("2023-12-31");
  const [capital,   setCapital]   = useState("10000");
  const [running,   setRunning]   = useState(false);
  const [status,    setStatus]    = useState("idle");
  const [results,   setResults]   = useState<Comparison>({ grounded: null, ungrounded: null });
  const [mode,      setMode]      = useState<"grounded" | "ungrounded" | "both">("both");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  useEffect(() => stop, []);

  const pollStatus = async () => {
    const { status: s, result } = await agentApi.backtestStatus();
    setStatus(s);
    if (s === "done" && result) {
      setResults(prev => result.use_graph
        ? { ...prev, grounded:   result }
        : { ...prev, ungrounded: result }
      );
      setRunning(false);
      stop();
    } else if (s.startsWith("error")) {
      setRunning(false);
      stop();
    }
  };

  const runOne = async (useGraph: boolean) => {
    await agentApi.runBacktest({
      start_date: startDate,
      end_date: endDate,
      initial_capital: Number(capital),
      use_graph: useGraph,
    });
    pollRef.current = setInterval(pollStatus, 3000);
  };

  const handleRun = async () => {
    setRunning(true);
    setStatus("starting...");
    if (mode === "both") {
      await runOne(true);
      // second run after first completes via poll
    } else {
      await runOne(mode === "grounded");
    }
  };

  const metrics: { label: string; key: keyof BacktestResult; fmt: (v: number) => string; good: "high" | "low" }[] = [
    { label: "Total Return",  key: "total_return",  fmt: fmtPct,          good: "high" },
    { label: "Sharpe Ratio",  key: "sharpe_ratio",  fmt: v => fmtN(v, 2), good: "high" },
    { label: "Calmar Ratio",  key: "calmar_ratio",  fmt: v => fmtN(v, 2), good: "high" },
    { label: "Max Drawdown",  key: "max_drawdown",  fmt: fmtPct,          good: "low"  },
    { label: "Ann. Vol",      key: "ann_volatility", fmt: fmtPct,          good: "low"  },
    { label: "Final NAV",     key: "final_nav",     fmt: v => `$${v.toFixed(0)}`, good: "high" },
  ];

  const barData = metrics.map(m => ({
    name:      m.label,
    grounded:   results.grounded  ? Number(results.grounded[m.key])  : null,
    ungrounded: results.ungrounded ? Number(results.ungrounded[m.key]) : null,
  }));

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <BarChart2 size={16} className="text-indigo-400" />
        <h2 className="text-sm font-semibold text-slate-200">Walk-Forward Backtest</h2>
        <span className="text-xs text-slate-500 ml-auto font-mono">
          {running ? <span className="text-indigo-400 animate-pulse">{status}</span> : status}
        </span>
      </div>

      {/* Controls */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <LabeledInput label="Start" type="date" value={startDate} onChange={setStartDate} />
        <LabeledInput label="End"   type="date" value={endDate}   onChange={setEndDate}   />
        <LabeledInput label="Capital ($)" type="number" value={capital} onChange={setCapital} />
        <div>
          <div className="text-[10px] text-slate-400 mb-1 uppercase tracking-wider">Mode</div>
          <select
            value={mode}
            onChange={e => setMode(e.target.value as typeof mode)}
            className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5"
          >
            <option value="both">Both (ablation)</option>
            <option value="grounded">KG-Grounded only</option>
            <option value="ungrounded">Ungrounded only</option>
          </select>
        </div>
      </div>

      <button
        onClick={handleRun}
        disabled={running}
        className={clsx(
          "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
          running
            ? "bg-slate-700 text-slate-500 cursor-not-allowed"
            : "bg-indigo-600 hover:bg-indigo-500 text-white"
        )}
      >
        <Play size={14} className={running ? "animate-pulse" : ""} />
        {running ? "Running..." : "Run Backtest"}
      </button>

      {/* Results comparison table */}
      {(results.grounded || results.ungrounded) && (
        <>
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-left py-2">Metric</th>
                <th className="text-right py-2 text-indigo-400">KG-Grounded</th>
                <th className="text-right py-2 text-slate-400">Ungrounded</th>
                <th className="text-right py-2 text-slate-500">Delta</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map(m => {
                const g = results.grounded  ? Number(results.grounded[m.key])  : null;
                const u = results.ungrounded ? Number(results.ungrounded[m.key]) : null;
                const delta = g !== null && u !== null ? g - u : null;
                const positive = delta !== null
                  ? (m.good === "high" ? delta >= 0 : delta <= 0)
                  : null;
                return (
                  <tr key={m.key} className="border-t border-slate-800">
                    <td className="py-1.5 text-slate-400">{m.label}</td>
                    <td className="py-1.5 text-right text-indigo-300">
                      {g !== null ? m.fmt(g) : "—"}
                    </td>
                    <td className="py-1.5 text-right text-slate-400">
                      {u !== null ? m.fmt(u) : "—"}
                    </td>
                    <td className={clsx("py-1.5 text-right font-bold",
                      positive === null ? "text-slate-600" :
                      positive ? "text-emerald-400" : "text-red-400")}>
                      {delta !== null
                        ? `${delta >= 0 ? "+" : ""}${m.fmt(delta)}`
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* JK significance */}
          {results.grounded?.jk_p_value != null && (
            <div className={clsx(
              "rounded border px-3 py-2 text-xs font-mono",
              results.grounded.jk_significant
                ? "bg-emerald-950 border-emerald-700 text-emerald-300"
                : "bg-slate-800 border-slate-600 text-slate-400"
            )}>
              <span className="font-bold">Jobson-Korkie test: </span>
              {results.grounded.jk_significant
                ? `Statistically significant outperformance (p = ${results.grounded.jk_p_value.toFixed(4)})`
                : `Not statistically significant (p = ${results.grounded.jk_p_value.toFixed(4)})`
              }
            </div>
          )}

          {/* Bar chart */}
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={[
                { name: "Sharpe",   g: results.grounded?.sharpe_ratio,  u: results.ungrounded?.sharpe_ratio  },
                { name: "Calmar",   g: results.grounded?.calmar_ratio,  u: results.ungrounded?.calmar_ratio  },
                { name: "Return %", g: results.grounded ? results.grounded.total_return  * 100 : null,
                                    u: results.ungrounded ? results.ungrounded.total_return * 100 : null },
                { name: "MaxDD %",  g: results.grounded ? results.grounded.max_drawdown  * 100 : null,
                                    u: results.ungrounded ? results.ungrounded.max_drawdown * 100 : null },
              ]} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#64748b" }} />
                <YAxis tick={{ fontSize: 10, fill: "#64748b" }} />
                <Tooltip
                  contentStyle={{ background: "#1e293b", border: "1px solid #334155" }}
                  labelStyle={{ color: "#94a3b8", fontSize: 11 }}
                />
                <ReferenceLine y={0} stroke="#475569" />
                <Bar dataKey="g" name="KG-Grounded"  fill="#6366f1" />
                <Bar dataKey="u" name="Ungrounded"   fill="#475569" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}

function LabeledInput({
  label, type, value, onChange,
}: { label: string; type: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <div className="text-[10px] text-slate-400 mb-1 uppercase tracking-wider">{label}</div>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5"
      />
    </div>
  );
}
