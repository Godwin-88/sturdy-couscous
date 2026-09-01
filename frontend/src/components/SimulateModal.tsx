import { useState } from "react";
import { X, Play, AlertCircle } from "lucide-react";
import { researchApi } from "@/lib/api";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose: () => void;
}

const SCENARIOS = [
  { id: "add_edge", label: "Add Edge" },
  { id: "remove_edge", label: "Remove Edge" },
  { id: "change_weight", label: "Change Weight" },
];

export default function SimulateModal({ open, onClose }: Props) {
  const [scenario, setScenario] = useState("add_edge");
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [relType, setRelType] = useState("TRANSMITS_TO");
  const [weight, setWeight] = useState("0.5");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  if (!open) return null;

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const params: Record<string, unknown> = { source, target, rel_type: relType, weight: parseFloat(weight) };
      const res = await researchApi.graphSimulate(scenario as "add_edge" | "remove_edge" | "change_weight", params);
      setResult(res as unknown as Record<string, unknown>);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
          <h2 className="text-sm font-semibold text-slate-200">⚡ Graph Simulation</h2>
          <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300 rounded"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-4">
          {/* Scenario selector */}
          <div className="space-y-1.5">
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">Scenario</label>
            <div className="flex gap-1.5">
              {SCENARIOS.map(s => (
                <button key={s.id} onClick={() => setScenario(s.id)}
                  className={clsx("px-2.5 py-1 rounded text-xs font-mono",
                    scenario === s.id ? "bg-amber-600 text-white" : "bg-slate-800 text-slate-400 hover:text-slate-200"
                  )}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Source / Target */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[10px] text-slate-500 uppercase">Source Node</label>
              <input value={source} onChange={e => setSource(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-amber-500"
                placeholder="e.g. Momentum" />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-slate-500 uppercase">Target Node</label>
              <input value={target} onChange={e => setTarget(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-amber-500"
                placeholder="e.g. TrendFollow" />
            </div>
          </div>

          {/* Relationship type */}
          <div className="space-y-1">
            <label className="text-[10px] text-slate-500 uppercase">Relationship Type</label>
            <input value={relType} onChange={e => setRelType(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-amber-500" />
          </div>

          {/* Weight (for change_weight) */}
          {scenario === "change_weight" && (
            <div className="space-y-1">
              <label className="text-[10px] text-slate-500 uppercase">New Weight</label>
              <input type="number" step="0.1" min="0" max="1" value={weight} onChange={e => setWeight(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-amber-500" />
            </div>
          )}

          {/* Error */}
          {error && <div className="flex items-center gap-1.5 text-xs text-red-400"><AlertCircle size={12} />{error}</div>}

          {/* Results */}
          {result && (
            <div className="bg-slate-800 rounded-lg p-3 space-y-2 text-xs font-mono">
              <div className="text-slate-400 text-[10px] uppercase tracking-wider">Results</div>
              <div className="flex justify-between"><span className="text-slate-500">Affected strategies:</span><span className="text-slate-200">{(result.affected_strategies as string[] || []).length}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">New activations:</span><span className="text-slate-200">{String(result.predicted_new_activations ?? "?")}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Contradiction risk:</span><span className="text-amber-400">{(result.contradiction_risk as Record<string, unknown> || {}).severity as string ?? "?"}</span></div>
              {(result.predicted_signal_changes as Array<Record<string, unknown>> || []).length > 0 && (
                <div className="pt-2 border-t border-slate-700">
                  <div className="text-slate-400 text-[10px] mb-1">Signal changes:</div>
                  {(result.predicted_signal_changes as Array<Record<string, unknown>>).slice(0, 5).map((ch, i) => (
                    <div key={i} className="flex justify-between text-[10px]">
                      <span className="text-slate-400">{ch.strategy as string}</span>
                      <span className="text-emerald-400">{ch.change_pct as string}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Run button */}
          <button onClick={handleRun} disabled={loading || !source || !target}
            className="flex items-center gap-2 px-4 py-2 rounded text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white disabled:opacity-50">
            <Play size={14} />{loading ? "Simulating..." : "Run Simulation"}
          </button>
        </div>
      </div>
    </div>
  );
}