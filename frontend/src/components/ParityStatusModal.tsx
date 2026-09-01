import { useState, useEffect } from "react";
import { X, AlertCircle, Loader2, CheckCircle2, XCircle, GitCompare } from "lucide-react";
import { researchApi, ParityStatus } from "@/lib/api";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ParityStatusModal({ open, onClose }: Props) {
  const [data, setData] = useState<ParityStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    researchApi.parityStatus()
      .then(setData)
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 shrink-0">
          <h2 className="text-sm font-semibold text-slate-200">🔄 C++ / Python Parity</h2>
          <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300 rounded"><X size={16} /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {loading && <div className="flex items-center justify-center gap-2 text-xs text-slate-500 py-8"><Loader2 size={14} className="animate-spin" /> Loading...</div>}
          {error && <div className="flex items-center gap-1.5 text-xs text-red-400"><AlertCircle size={12} />{error}</div>}

          {!loading && data && (
            <div className="space-y-4">
              {/* Status badge */}
              <div className={clsx("flex items-center gap-2 p-3 rounded-lg border text-xs font-mono",
                data.status === "healthy"
                  ? "bg-emerald-950/30 border-emerald-800 text-emerald-400"
                  : "bg-amber-950/30 border-amber-800 text-amber-400"
              )}>
                {data.status === "healthy" ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                Status: {data.status.toUpperCase()}
              </div>

              {/* Summary cards */}
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-slate-800 rounded-lg p-2.5 border border-slate-700">
                  <div className="text-[10px] text-slate-500 uppercase">Total Cycles</div>
                  <div className="text-lg font-bold font-mono text-slate-100">{data.total_cycles}</div>
                </div>
                <div className="bg-slate-800 rounded-lg p-2.5 border border-slate-700">
                  <div className="text-[10px] text-slate-500 uppercase">Discrepancies</div>
                  <div className={clsx("text-lg font-bold font-mono",
                    data.discrepancies === 0 ? "text-emerald-400" : "text-red-400"
                  )}>{data.discrepancies}</div>
                </div>
                <div className="bg-slate-800 rounded-lg p-2.5 border border-slate-700">
                  <div className="text-[10px] text-slate-500 uppercase">C++ Version</div>
                  <div className="text-sm font-bold font-mono text-slate-200">{data.cpp_version}</div>
                </div>
                <div className="bg-slate-800 rounded-lg p-2.5 border border-slate-700">
                  <div className="text-[10px] text-slate-500 uppercase">Python Version</div>
                  <div className="text-sm font-bold font-mono text-slate-200">{data.python_version}</div>
                </div>
              </div>

              {/* Tolerance */}
              <div className="bg-slate-800 rounded p-2 border border-slate-700 text-xs font-mono">
                <span className="text-slate-500">Tolerance: </span>
                <span className="text-slate-200">{data.tolerance}</span>
              </div>

              {/* Latest discrepancies */}
              {data.latest_discrepancies && data.latest_discrepancies.length > 0 && (
                <div>
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Latest Discrepancies</div>
                  <div className="space-y-1">
                    {data.latest_discrepancies.slice(0, 5).map((d: unknown, i: number) => (
                      <div key={i} className="bg-red-950/20 border border-red-800/50 rounded p-2 text-[10px] font-mono text-red-300">
                        {JSON.stringify(d).slice(0, 200)}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {!loading && !data && !error && (
            <div className="text-xs text-slate-500 text-center py-8">No parity data available.</div>
          )}
        </div>
      </div>
    </div>
  );
}