import { useState } from "react";
import { X, Search, AlertCircle, GitBranch } from "lucide-react";
import { agentApi, SignalLineage } from "@/lib/api";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose: () => void;
}

const STRATEGIES = [
  "MomentumStrategy", "MeanReversionStrategy", "TrendFollowingStrategy",
  "BreakoutStrategy", "PairsTradingStrategy", "VolatilityStrategy",
  "CarryTradeStrategy", "SentimentStrategy", "MacroStrategy",
  "RiskParityStrategy", "FactorStrategy", "ArbitrageStrategy",
];

export default function SignalLineageModal({ open, onClose }: Props) {
  const [strategy, setStrategy] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lineage, setLineage] = useState<SignalLineage | null>(null);

  if (!open) return null;

  const handleSearch = async () => {
    if (!strategy.trim()) return;
    setLoading(true);
    setError(null);
    setLineage(null);
    try {
      const res = await agentApi.signalLineage(strategy.trim());
      setLineage(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 shrink-0">
          <h2 className="text-sm font-semibold text-slate-200">🔗 Signal Lineage</h2>
          <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300 rounded"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-4">
          {/* Strategy selector */}
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <input
                value={strategy}
                onChange={e => setStrategy(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSearch()}
                list="strategy-list"
                className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-indigo-500"
                placeholder="Type or select a strategy..."
              />
              <datalist id="strategy-list">
                {STRATEGIES.map(s => <option key={s} value={s} />)}
              </datalist>
            </div>
            <button onClick={handleSearch} disabled={loading || !strategy.trim()}
              className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50">
              <Search size={12} />{loading ? "..." : "Search"}
            </button>
          </div>

          {/* Error */}
          {error && <div className="flex items-center gap-1.5 text-xs text-red-400"><AlertCircle size={12} />{error}</div>}

          {/* Lineage results */}
          {lineage && (
            <div className="space-y-4 overflow-y-auto max-h-[50vh]">
              {/* Strategy info */}
              <div className="bg-slate-800 rounded-lg p-3">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider">Strategy</div>
                <div className="text-sm font-bold text-slate-100 mt-1">{lineage.strategy}</div>
                {lineage.strategy_desc && <div className="text-xs text-slate-400 mt-0.5">{lineage.strategy_desc}</div>}
              </div>

              {/* Regimes */}
              {lineage.regimes && lineage.regimes.length > 0 && (
                <div className="bg-slate-800 rounded-lg p-3">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Regimes</div>
                  <div className="flex flex-wrap gap-1.5">
                    {lineage.regimes.map(r => (
                      <span key={r} className="px-2 py-0.5 rounded text-[10px] font-mono bg-blue-950 text-blue-300 border border-blue-800">{r}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Concepts */}
              {lineage.concepts && lineage.concepts.length > 0 && (
                <div className="bg-slate-800 rounded-lg p-3">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Concepts</div>
                  <div className="space-y-2">
                    {lineage.concepts.map((c, i) => (
                      <div key={i} className="border border-slate-700 rounded p-2">
                        <div className="text-xs font-semibold text-indigo-300">{c.name}</div>
                        {c.definition && <div className="text-[10px] text-slate-400 mt-0.5">{c.definition}</div>}
                        <div className="flex gap-2 mt-1 text-[10px] text-slate-500">
                          {c.category && <span>Category: {c.category}</span>}
                          {c.difficulty && <span>Difficulty: {c.difficulty}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Formulas */}
              {lineage.formulas && lineage.formulas.length > 0 && (
                <div className="bg-slate-800 rounded-lg p-3">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Formulas</div>
                  <div className="space-y-2">
                    {lineage.formulas.map((f, i) => (
                      <div key={i} className="border border-slate-700 rounded p-2">
                        <div className="text-xs font-semibold text-emerald-300">{f.name || f.id}</div>
                        <div className="text-[10px] font-mono text-amber-300 mt-0.5 bg-slate-900 rounded px-1.5 py-0.5">{f.expression}</div>
                        {f.output && <div className="text-[10px] text-slate-400 mt-0.5">Output: {f.output}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Categories */}
              {lineage.categories && lineage.categories.length > 0 && (
                <div className="bg-slate-800 rounded-lg p-3">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Categories</div>
                  <div className="flex flex-wrap gap-1.5">
                    {lineage.categories.map(c => (
                      <span key={c} className="px-2 py-0.5 rounded text-[10px] font-mono bg-purple-950 text-purple-300 border border-purple-800">{c}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}