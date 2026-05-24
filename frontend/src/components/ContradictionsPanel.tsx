import { useState } from "react";
import { agentApi, Contradiction } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { AlertTriangle, Shield, EyeOff, Eye } from "lucide-react";
import clsx from "clsx";

export default function ContradictionsPanel() {
  const { data, loading, refresh } = usePolling<Contradiction[]>(agentApi.contradictions, 60_000);
  const [pending, setPending] = useState<string>("");

  if (loading) return <Skeleton />;

  const active     = (data ?? []).filter(c => !c.suppressed);
  const suppressed = (data ?? []).filter(c => c.suppressed);

  const toggle = async (c: Contradiction) => {
    const key = `${c.strategy_a}|${c.strategy_b}`;
    setPending(key);
    try {
      if (c.suppressed) {
        await agentApi.unsuppressContradiction(c.strategy_a, c.strategy_b);
      } else {
        await agentApi.suppressContradiction(c.strategy_a, c.strategy_b);
      }
      refresh?.();
    } finally {
      setPending("");
    }
  };

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4">
      <div className="flex items-center gap-2 mb-3">
        {active.length > 0
          ? <AlertTriangle size={14} className="text-yellow-400" />
          : <Shield size={14} className="text-emerald-400" />}
        <span className="text-sm font-semibold text-slate-200">Contradictions</span>
        <span className={clsx(
          "ml-auto text-xs font-mono px-2 py-0.5 rounded-full",
          active.length > 0 ? "bg-yellow-900 text-yellow-300" : "bg-emerald-900 text-emerald-300"
        )}>
          {active.length} active
        </span>
        {suppressed.length > 0 && (
          <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">
            {suppressed.length} suppressed
          </span>
        )}
      </div>

      {(data ?? []).length === 0 ? (
        <p className="text-xs text-slate-500">
          No contradicting active strategies. KG contradiction-blocking is clear.
        </p>
      ) : (
        <div className="space-y-2">
          {(data ?? []).map((c, i) => {
            const key = `${c.strategy_a}|${c.strategy_b}`;
            const isLoading = pending === key;
            return (
              <div
                key={i}
                className={clsx(
                  "rounded-lg border p-2.5 text-xs font-mono transition-opacity",
                  c.suppressed
                    ? "bg-slate-800/40 border-slate-700 opacity-60"
                    : "bg-yellow-950/40 border-yellow-800/50"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={clsx("font-bold", c.suppressed ? "text-slate-400" : "text-yellow-300")}>
                        {c.strategy_a}
                      </span>
                      <span className="text-slate-500">↔</span>
                      <span className={clsx("font-bold", c.suppressed ? "text-slate-400" : "text-yellow-300")}>
                        {c.strategy_b}
                      </span>
                    </div>
                    <div className="mt-1 text-slate-400">
                      via <span className="text-indigo-300">{c.via_concept_a}</span>
                      {" "}↔{" "}
                      <span className="text-indigo-300">{c.via_concept_b}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => toggle(c)}
                    disabled={isLoading}
                    title={c.suppressed ? "Re-activate blocking" : "Suppress contradiction"}
                    className={clsx(
                      "shrink-0 flex items-center gap-1 px-2 py-1 rounded text-[10px] border transition-colors",
                      c.suppressed
                        ? "bg-emerald-900/50 border-emerald-700 text-emerald-300 hover:bg-emerald-800"
                        : "bg-slate-800 border-slate-600 text-slate-400 hover:bg-yellow-900/30 hover:text-yellow-300",
                      isLoading && "opacity-50 cursor-not-allowed"
                    )}
                  >
                    {c.suppressed ? <Eye size={10} /> : <EyeOff size={10} />}
                    {c.suppressed ? "Restore" : "Suppress"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <p className="mt-3 text-[10px] text-slate-600">
        Suppressing a contradiction allows both strategies to fire concurrently. Use with caution.
      </p>
    </div>
  );
}

function Skeleton() {
  return <div className="rounded-xl border border-slate-700 bg-slate-800 h-24 animate-pulse" />;
}
