import { agentApi, Contradiction } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { AlertTriangle, Shield } from "lucide-react";

export default function ContradictionsPanel() {
  const { data, loading } = usePolling<Contradiction[]>(agentApi.contradictions, 60_000);

  if (loading) return <Skeleton />;

  const count = data?.length ?? 0;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4">
      <div className="flex items-center gap-2 mb-3">
        {count > 0
          ? <AlertTriangle size={14} className="text-yellow-400" />
          : <Shield size={14} className="text-emerald-400" />}
        <span className="text-sm font-semibold text-slate-200">CONTRADICTED_BY Edges</span>
        <span className={`ml-auto text-xs font-mono px-2 py-0.5 rounded-full
          ${count > 0 ? "bg-yellow-900 text-yellow-300" : "bg-emerald-900 text-emerald-300"}`}>
          {count} active
        </span>
      </div>

      {count === 0 ? (
        <p className="text-xs text-slate-500">
          No contradicting active strategies. KG contradiction-blocking is clear.
        </p>
      ) : (
        <div className="space-y-2">
          {(data ?? []).map((c, i) => (
            <div key={i} className="rounded-lg bg-yellow-950/40 border border-yellow-800/50 p-2.5 text-xs font-mono">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-yellow-300 font-bold">{c.strategy_a}</span>
                <span className="text-slate-500">↔</span>
                <span className="text-yellow-300 font-bold">{c.strategy_b}</span>
              </div>
              <div className="mt-1 text-slate-400">
                via <span className="text-indigo-300">{c.via_concept_a}</span>
                {" "}↔{" "}
                <span className="text-indigo-300">{c.via_concept_b}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="mt-3 text-[10px] text-slate-600">
        Strategies blocked by CONTRADICTED_BY edges generate no orders that cycle.
      </p>
    </div>
  );
}

function Skeleton() {
  return <div className="rounded-xl border border-slate-700 bg-slate-800 h-24 animate-pulse" />;
}
