import { useState, useEffect } from "react";
import { X, ShieldAlert, ShieldCheck, RotateCcw, AlertCircle } from "lucide-react";
import { agentApi, Contradiction } from "@/lib/api";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ContradictionManager({ open, onClose }: Props) {
  const [contradictions, setContradictions] = useState<(Contradiction & { loading?: boolean })[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchContradictions = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await agentApi.contradictions();
      setContradictions(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) fetchContradictions();
  }, [open]);

  const toggleSuppress = async (c: Contradiction & { loading?: boolean }) => {
    c.loading = true;
    setContradictions([...contradictions]);
    try {
      if (c.suppressed) {
        await agentApi.unsuppressContradiction(c.strategy_a, c.strategy_b);
      } else {
        await agentApi.suppressContradiction(c.strategy_a, c.strategy_b);
      }
      await fetchContradictions();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      c.loading = false;
      setContradictions([...contradictions]);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 shrink-0">
          <h2 className="text-sm font-semibold text-slate-200">⚠️ Contradiction Manager</h2>
          <div className="flex items-center gap-2">
            <button onClick={fetchContradictions} className="p-1 text-slate-500 hover:text-slate-300 rounded" title="Refresh">
              <RotateCcw size={14} />
            </button>
            <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300 rounded"><X size={16} /></button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading && <div className="text-xs text-slate-500 animate-pulse text-center py-8">Loading contradictions...</div>}
          {error && <div className="flex items-center gap-1.5 text-xs text-red-400 mb-3"><AlertCircle size={12} />{error}</div>}
          {!loading && contradictions.length === 0 && (
            <div className="text-xs text-slate-500 text-center py-8">No active contradictions found.</div>
          )}
          {!loading && contradictions.length > 0 && (
            <div className="space-y-2">
              {contradictions.map((c, i) => (
                <div key={i} className={clsx(
                  "flex items-center justify-between p-3 rounded-lg border text-xs font-mono",
                  c.suppressed
                    ? "bg-slate-800/50 border-slate-700 text-slate-500"
                    : "bg-amber-950/20 border-amber-800/50 text-amber-300"
                )}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{c.strategy_a}</span>
                      <span className="text-slate-600">↔</span>
                      <span className="font-semibold">{c.strategy_b}</span>
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      via {c.via_concept_a} ↔ {c.via_concept_b}
                    </div>
                  </div>
                  <button
                    onClick={() => toggleSuppress(c)}
                    disabled={c.loading}
                    className={clsx(
                      "flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-semibold transition-colors shrink-0 ml-3",
                      c.suppressed
                        ? "bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30"
                        : "bg-slate-700 text-slate-300 hover:bg-slate-600"
                    )}
                  >
                    {c.loading ? "..." : c.suppressed ? <ShieldCheck size={12} /> : <ShieldAlert size={12} />}
                    {c.suppressed ? "Unsuppress" : "Suppress"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}