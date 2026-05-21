import { useState } from "react";
import { agentApi, Signal } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmt$, relTime } from "@/lib/utils";
import { RefreshCw } from "lucide-react";
import clsx from "clsx";

export default function SignalsTable() {
  const [limit, setLimit] = useState(50);
  const { data, loading, refresh } = usePolling<Signal[]>(
    () => agentApi.signals(limit), 20_000, [limit]
  );

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
                <td colSpan={8} className="text-center py-8 text-slate-500">
                  No orders yet — agent is generating signals
                </td>
              </tr>
            )}
            {(data ?? []).map(s => (
              <tr key={s.order_id} className="border-t border-slate-800 hover:bg-slate-800/60">
                <td className="py-1.5 px-3 text-slate-500">{relTime(s.created_at)}</td>
                <td className="py-1.5 px-3 text-slate-300 max-w-[140px] truncate"
                    title={s.strategy}>{s.strategy}</td>
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
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
