import { useState } from "react";
import { agentApi, Signal, SignalLineage } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmt$, relTime } from "@/lib/utils";
import { RefreshCw, ChevronDown, ChevronRight, BookOpen } from "lucide-react";
import clsx from "clsx";

export default function SignalsTable() {
  const [limit, setLimit] = useState(50);
  const { data, loading, refresh } = usePolling<Signal[]>(
    () => agentApi.signals(limit), 20_000, [limit]
  );
  const [expanded, setExpanded] = useState<string | null>(null);
  const [lineage, setLineage]   = useState<Record<string, SignalLineage>>({});
  const [lineageLoading, setLineageLoading] = useState<string | null>(null);

  const toggleLineage = async (strategy: string) => {
    if (expanded === strategy) { setExpanded(null); return; }
    setExpanded(strategy);
    if (!lineage[strategy]) {
      setLineageLoading(strategy);
      try {
        const result = await agentApi.signalLineage(strategy);
        setLineage(prev => ({ ...prev, [strategy]: result }));
      } finally {
        setLineageLoading(null);
      }
    }
  };

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-700 shrink-0">
        <span className="text-sm font-semibold text-slate-200">Order History</span>
        <div className="flex items-center gap-2">
          <select
            value={limit}
            onChange={e => setLimit(Number(e.target.value))}
            className="bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-1.5 py-0.5"
          >
            {[25, 50, 100, 200].map(n => (
              <option key={n} value={n}>{n} rows</option>
            ))}
          </select>
          <button
            onClick={refresh}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-700"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto min-h-0">
        <table className="w-full text-xs font-mono">
          <thead className="sticky top-0 bg-slate-800 z-10">
            <tr className="text-slate-400">
              <th className="py-2 px-2 w-6" />
              {["Time","Strategy","Ticker","Side","Qty","Fill $","Score","Mode"].map(h => (
                <th key={h} className={clsx(
                  "py-2 px-3 font-medium text-[10px] uppercase tracking-wider",
                  ["Qty","Fill $","Score"].includes(h) ? "text-right" : "text-left"
                )}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(!data || data.length === 0) && (
              <tr>
                <td colSpan={9} className="text-center py-8 text-slate-500">
                  No orders yet — agent is generating signals
                </td>
              </tr>
            )}
            {(data ?? []).map(s => {
              const isExpanded = expanded === s.strategy;
              const lg = lineage[s.strategy];
              const isLoadingLg = lineageLoading === s.strategy;
              return [
                <tr key={s.order_id} className="border-t border-slate-800 hover:bg-slate-800/60">
                  <td className="py-1.5 px-2">
                    <button
                      onClick={() => toggleLineage(s.strategy)}
                      className="p-0.5 rounded text-slate-500 hover:text-indigo-400"
                      title="View KG lineage"
                    >
                      {isExpanded
                        ? <ChevronDown size={11} />
                        : <ChevronRight size={11} />}
                    </button>
                  </td>
                  <td className="py-1.5 px-3 text-slate-500">{relTime(s.created_at)}</td>
                  <td className="py-1.5 px-3 text-slate-300 max-w-[140px] truncate" title={s.strategy}>
                    {s.strategy}
                  </td>
                  <td className="py-1.5 px-3 text-slate-100 font-bold">{s.ticker}</td>
                  <td className={clsx("py-1.5 px-3 font-bold",
                    s.direction === "buy" ? "text-emerald-400" : "text-red-400")}>
                    {s.direction.toUpperCase()}
                  </td>
                  <td className="py-1.5 px-3 text-right text-slate-300">{s.quantity.toFixed(4)}</td>
                  <td className="py-1.5 px-3 text-right text-slate-300">
                    {s.fill_price ? fmt$(s.fill_price) : "—"}
                  </td>
                  <td className={clsx("py-1.5 px-3 text-right font-bold",
                    (s.signal_score ?? 0) > 0 ? "text-emerald-400" : "text-red-400")}>
                    {(s.signal_score ?? 0) >= 0 ? "+" : ""}{(s.signal_score ?? 0).toFixed(3)}
                  </td>
                  <td className="py-1.5 px-3">
                    <span className={clsx("px-1.5 py-0.5 rounded text-[10px]",
                      s.mode === "live"
                        ? "bg-red-900 text-red-300 border border-red-700"
                        : "bg-slate-700 text-slate-400")}>
                      {s.mode}
                    </span>
                  </td>
                </tr>,
                isExpanded && (
                  <tr key={`${s.order_id}-lineage`} className="bg-slate-950/80">
                    <td colSpan={9} className="px-6 py-3">
                      {isLoadingLg ? (
                        <div className="text-xs text-slate-500 animate-pulse">Loading KG lineage...</div>
                      ) : lg ? (
                        <LineageDrawer lineage={lg} />
                      ) : (
                        <div className="text-xs text-slate-500">No lineage data found</div>
                      )}
                    </td>
                  </tr>
                ),
              ];
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LineageDrawer({ lineage }: { lineage: SignalLineage }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <BookOpen size={12} className="text-indigo-400" />
        <span className="text-xs font-semibold text-indigo-300">{lineage.strategy}</span>
        {lineage.strategy_desc && (
          <span className="text-xs text-slate-500">— {lineage.strategy_desc}</span>
        )}
        <div className="flex gap-1 ml-auto">
          {lineage.regimes.map(r => (
            <span key={r} className="text-[10px] px-1.5 py-0.5 rounded bg-purple-900/60 text-purple-300 border border-purple-700 font-mono">
              {r}
            </span>
          ))}
        </div>
      </div>

      {/* Concepts */}
      {lineage.concepts.length > 0 && (
        <div>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">
            Derived Concepts ({lineage.concepts.length})
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            {lineage.concepts.map((c, i) => (
              <div key={i} className="bg-slate-800 rounded p-2 border border-slate-700">
                <div className="flex items-center justify-between gap-1 mb-0.5">
                  <span className="text-[11px] font-semibold text-slate-200">{c.name}</span>
                  <span className={clsx(
                    "text-[9px] px-1 py-0.5 rounded font-mono",
                    c.difficulty === "hard" ? "bg-red-900/50 text-red-300" :
                    c.difficulty === "medium" ? "bg-yellow-900/50 text-yellow-300" :
                    "bg-slate-700 text-slate-400"
                  )}>{c.difficulty}</span>
                </div>
                {c.definition && (
                  <div className="text-[10px] text-slate-500 line-clamp-2">{c.definition}</div>
                )}
                <div className="text-[9px] text-indigo-500 mt-0.5">{c.category}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Formulas */}
      {lineage.formulas.length > 0 && (
        <div>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">
            Formulas ({lineage.formulas.length})
          </div>
          <div className="space-y-1">
            {lineage.formulas.map((f, i) => (
              <div key={i} className="flex items-start gap-2 bg-slate-800/60 rounded px-2 py-1.5 border border-slate-700/50">
                <span className="text-[10px] text-slate-400 font-semibold shrink-0">{f.name}</span>
                <code className="text-[10px] text-emerald-300 font-mono break-all">{f.expression}</code>
                {f.output && (
                  <span className="text-[9px] text-slate-500 shrink-0 ml-auto">→ {f.output}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
