import { useState, useEffect } from "react";
import { X, Lightbulb, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { researchApi, GraphRecommendation } from "@/lib/api";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose: () => void;
}

const PRIORITY_COLORS: Record<string, string> = {
  high:   "text-red-400 border-red-800 bg-red-950/20",
  medium: "text-amber-400 border-amber-800 bg-amber-950/20",
  low:    "text-slate-400 border-slate-700 bg-slate-800/50",
};

const TYPE_ICONS: Record<string, string> = {
  add_edge:            "➕",
  resolve_contradiction: "⚖️",
  connect_orphan:      "🔗",
};

export default function RecommendationsPanel({ open, onClose }: Props) {
  const [recommendations, setRecommendations] = useState<GraphRecommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<Set<number>>(new Set());

  const fetchRecommendations = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await researchApi.graphRecommendations();
      setRecommendations(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) fetchRecommendations();
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 shrink-0">
          <h2 className="text-sm font-semibold text-slate-200">💡 KG Auto-Fix Recommendations</h2>
          <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300 rounded"><X size={16} /></button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading && (
            <div className="flex items-center justify-center gap-2 text-xs text-slate-500 py-8">
              <Loader2 size={14} className="animate-spin" /> Loading recommendations...
            </div>
          )}
          {error && <div className="flex items-center gap-1.5 text-xs text-red-400 mb-3"><AlertCircle size={12} />{error}</div>}
          {!loading && recommendations.length === 0 && (
            <div className="text-xs text-slate-500 text-center py-8">No recommendations at this time. Your KG looks healthy!</div>
          )}
          {!loading && recommendations.length > 0 && (
            <div className="space-y-2">
              {recommendations.map((rec, i) => (
                <div key={i} className={clsx(
                  "flex items-start gap-3 p-3 rounded-lg border text-xs font-mono",
                  applied.has(i) ? "opacity-50" : "",
                  PRIORITY_COLORS[rec.priority] ?? PRIORITY_COLORS.low
                )}>
                  <span className="text-base shrink-0 mt-0.5">{TYPE_ICONS[rec.type] ?? "💡"}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={clsx(
                        "text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded",
                        rec.priority === "high" ? "bg-red-800/50 text-red-300" :
                        rec.priority === "medium" ? "bg-amber-800/50 text-amber-300" :
                        "bg-slate-700 text-slate-400"
                      )}>
                        {rec.priority}
                      </span>
                      <span className="text-slate-400 text-[10px]">{rec.type.replace(/_/g, " ")}</span>
                    </div>
                    <div className="text-slate-200 mt-1">{rec.reason}</div>
                    <div className="text-slate-500 mt-0.5 text-[10px]">{rec.suggestion}</div>
                  </div>
                  {!applied.has(i) && (
                    <button
                      onClick={() => setApplied(prev => new Set(prev).add(i))}
                      className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-semibold bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30 shrink-0"
                    >
                      <CheckCircle2 size={10} /> Dismiss
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}