import { useState } from "react";
import { X, Save, AlertCircle, CheckCircle2 } from "lucide-react";
import { researchApi } from "@/lib/api";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const OPERATIONS = [
  { id: "create_node", label: "Create Node" },
  { id: "create_edge", label: "Create Edge" },
  { id: "delete_node", label: "Delete Node" },
  { id: "delete_edge", label: "Delete Edge" },
  { id: "update_property", label: "Update Property" },
];

export default function KGEditModal({ open, onClose, onSuccess }: Props) {
  const [operation, setOperation] = useState("create_node");
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [relType, setRelType] = useState("DERIVED_FROM");
  const [properties, setProperties] = useState("{}");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      let props: Record<string, unknown> = {};
      try { props = JSON.parse(properties); } catch { throw new Error("Invalid JSON in properties field"); }
      const res = await researchApi.graphEdit(operation, source || undefined, target || undefined, relType, props);
      setResult(`Operation succeeded. Affected strategies: ${(res.affected_strategies ?? []).join(", ") || "none"}`);
      onSuccess();
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
          <h2 className="text-sm font-semibold text-slate-200">✏️ Edit Knowledge Graph</h2>
          <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300 rounded"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-4">
          {/* Operation selector */}
          <div className="space-y-1.5">
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">Operation</label>
            <div className="flex flex-wrap gap-1.5">
              {OPERATIONS.map(op => (
                <button key={op.id} onClick={() => setOperation(op.id)}
                  className={clsx("px-2.5 py-1 rounded text-xs font-mono transition-colors",
                    operation === op.id ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-400 hover:text-slate-200"
                  )}>
                  {op.label}
                </button>
              ))}
            </div>
          </div>

          {/* Source / Target */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[10px] text-slate-500 uppercase">Source Name</label>
              <input value={source} onChange={e => setSource(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-indigo-500"
                placeholder="e.g. MomentumStrategy" />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-slate-500 uppercase">Target Name</label>
              <input value={target} onChange={e => setTarget(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-indigo-500"
                placeholder="e.g. TrendFollowing" />
            </div>
          </div>

          {/* Relationship type */}
          <div className="space-y-1">
            <label className="text-[10px] text-slate-500 uppercase">Relationship Type</label>
            <input value={relType} onChange={e => setRelType(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-indigo-500"
              placeholder="DERIVED_FROM / ACTIVATED_BY / CONTRADICTED_BY" />
          </div>

          {/* Properties JSON */}
          <div className="space-y-1">
            <label className="text-[10px] text-slate-500 uppercase">Properties (JSON)</label>
            <textarea value={properties} onChange={e => setProperties(e.target.value)} rows={3}
              className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-indigo-500 resize-none"
              placeholder='{"name": "MyNode", "description": "..."}' />
          </div>

          {/* Error / Result */}
          {error && <div className="flex items-center gap-1.5 text-xs text-red-400"><AlertCircle size={12} />{error}</div>}
          {result && <div className="flex items-center gap-1.5 text-xs text-emerald-400"><CheckCircle2 size={12} />{result}</div>}

          {/* Submit */}
          <button onClick={handleSubmit} disabled={loading}
            className="flex items-center gap-2 px-4 py-2 rounded text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50">
            <Save size={14} />{loading ? "Saving..." : "Apply Edit"}
          </button>
        </div>
      </div>
    </div>
  );
}