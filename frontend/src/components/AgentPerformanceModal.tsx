import { useState, useEffect } from "react";
import { X, AlertCircle, Loader2, Bot, Activity, CheckCircle2, XCircle } from "lucide-react";
import { researchApi, AgentPerformance } from "@/lib/api";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function AgentPerformanceModal({ open, onClose }: Props) {
  const [data, setData] = useState<AgentPerformance | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    researchApi.agentPerformance(30)
      .then(setData)
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 shrink-0">
          <h2 className="text-sm font-semibold text-slate-200">🤖 Agent Performance</h2>
          <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300 rounded"><X size={16} /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {loading && <div className="flex items-center justify-center gap-2 text-xs text-slate-500 py-8"><Loader2 size={14} className="animate-spin" /> Loading...</div>}
          {error && <div className="flex items-center gap-1.5 text-xs text-red-400"><AlertCircle size={12} />{error}</div>}

          {!loading && data && data.summary && (
            <div className="space-y-4">
              {/* Summary cards */}
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-slate-800 rounded-lg p-2.5 border border-slate-700">
                  <div className="text-[10px] text-slate-500 uppercase">Total Cycles</div>
                  <div className="text-lg font-bold font-mono text-slate-100">{data.summary.total_cycles ?? "—"}</div>
                </div>
                <div className="bg-slate-800 rounded-lg p-2.5 border border-slate-700">
                  <div className="text-[10px] text-slate-500 uppercase">Avg Duration</div>
                  <div className="text-lg font-bold font-mono text-slate-100">{data.summary.avg_duration_s != null ? data.summary.avg_duration_s.toFixed(1) + "s" : "—"}</div>
                </div>
                <div className="bg-slate-800 rounded-lg p-2.5 border border-slate-700">
                  <div className="text-[10px] text-slate-500 uppercase">Avg Confidence</div>
                  <div className="text-lg font-bold font-mono text-indigo-400">{data.summary.avg_regime_confidence != null ? (data.summary.avg_regime_confidence * 100).toFixed(0) + "%" : "—"}</div>
                </div>
                <div className="bg-slate-800 rounded-lg p-2.5 border border-slate-700">
                  <div className="text-[10px] text-slate-500 uppercase">Cycles w/ Signals</div>
                  <div className="text-lg font-bold font-mono text-emerald-400">{data.summary.cycles_with_signals ?? "—"}</div>
                </div>
              </div>

              {/* Agent breakdown */}
              {data.agent_breakdown.length > 0 && (
                <div>
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Agent Breakdown</div>
                  <div className="space-y-1.5">
                    {data.agent_breakdown.map((a, i) => {
                      const successRate = a.appearances > 0 ? (a.successes / a.appearances * 100).toFixed(0) : "0";
                      return (
                        <div key={i} className="flex items-center justify-between bg-slate-800 rounded p-2 border border-slate-700 text-xs font-mono">
                          <div className="flex items-center gap-2">
                            <Bot size={12} className="text-slate-400" />
                            <span className="text-slate-200">{a.agent_name}</span>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="text-slate-500 text-[10px]">{a.appearances} runs</span>
                            <span className={clsx("text-[10px] px-1.5 py-0.5 rounded",
                              parseInt(successRate) >= 80 ? "bg-emerald-900/50 text-emerald-300" :
                              parseInt(successRate) >= 50 ? "bg-amber-900/50 text-amber-300" :
                              "bg-red-900/50 text-red-300"
                            )}>
                              {successRate}% success
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {!loading && !data && !error && (
            <div className="text-xs text-slate-500 text-center py-8">No agent performance data available.</div>
          )}
        </div>
      </div>
    </div>
  );
}