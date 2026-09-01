import { useState } from "react";
import { X, Play, AlertCircle, TrendingDown, ShieldAlert } from "lucide-react";
import { researchApi, StressTestResult } from "@/lib/api";
import { fmtPct } from "@/lib/utils";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface ShockRow {
  ticker: string;
  shock_pct: number;
}

export default function StressTestModal({ open, onClose }: Props) {
  const [shocks, setShocks] = useState<ShockRow[]>([
    { ticker: "SPY", shock_pct: -0.20 },
    { ticker: "VIX", shock_pct: 0.50 },
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<StressTestResult | null>(null);

  if (!open) return null;

  const updateShock = (i: number, field: keyof ShockRow, value: string) => {
    const updated = [...shocks];
    if (field === "ticker") updated[i].ticker = value.toUpperCase();
    if (field === "shock_pct") updated[i].shock_pct = parseFloat(value) || 0;
    setShocks(updated);
  };

  const addRow = () => setShocks([...shocks, { ticker: "", shock_pct: 0 }]);
  const removeRow = (i: number) => setShocks(shocks.filter((_, idx) => idx !== i));

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await researchApi.stressTest(shocks);
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
          <h2 className="text-sm font-semibold text-slate-200">🧪 Stress Test</h2>
          <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300 rounded"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-4">
          {/* Shock rows */}
          <div className="space-y-2">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider">Scenario Shocks</div>
            {shocks.map((s, i) => (
              <div key={i} className="flex items-center gap-2">
                <input value={s.ticker} onChange={e => updateShock(i, "ticker", e.target.value)}
                  className="w-24 bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-amber-500"
                  placeholder="TICKER" />
                <input type="number" step="0.01" value={s.shock_pct} onChange={e => updateShock(i, "shock_pct", e.target.value)}
                  className="w-24 bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-amber-500" />
                <span className="text-[10px] text-slate-500 w-8">{s.shock_pct >= 0 ? "+" : ""}{(s.shock_pct * 100).toFixed(0)}%</span>
                <button onClick={() => removeRow(i)} className="p-1 text-slate-500 hover:text-red-400 rounded">✕</button>
              </div>
            ))}
            <button onClick={addRow} className="text-[10px] text-indigo-400 hover:text-indigo-300 font-mono">+ Add shock</button>
          </div>

          {error && <div className="flex items-center gap-1.5 text-xs text-red-400"><AlertCircle size={12} />{error}</div>}

          {/* Results */}
          {result && (
            <div className="bg-slate-800 rounded-lg p-3 space-y-2 text-xs font-mono border border-slate-700">
              <div className="text-[10px] text-slate-400 uppercase tracking-wider">Results</div>
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-slate-900 rounded p-2">
                  <div className="text-[10px] text-slate-500">NAV Impact</div>
                  <div className={clsx("text-sm font-bold", result.nav_impact_pct < 0 ? "text-red-400" : "text-emerald-400")}>
                    {fmtPct(result.nav_impact_pct)}
                  </div>
                </div>
                <div className="bg-slate-900 rounded p-2">
                  <div className="text-[10px] text-slate-500">Drawdown Impact</div>
                  <div className="text-sm font-bold text-amber-400">{fmtPct(result.drawdown_impact_pct)}</div>
                </div>
              </div>
              {result.positions_breaching_cap.length > 0 && (
                <div className="bg-red-950/30 border border-red-800 rounded p-2">
                  <div className="text-[10px] text-red-400 uppercase tracking-wider">⚠ Breaching Cap</div>
                  <div className="text-xs text-red-300">{result.positions_breaching_cap.join(", ")}</div>
                </div>
              )}
              {result.halt_triggered && (
                <div className="flex items-center gap-1.5 text-xs text-red-400 bg-red-950/30 border border-red-800 rounded p-2">
                  <ShieldAlert size={12} /> HALT TRIGGERED — drawdown limit exceeded
                </div>
              )}
            </div>
          )}

          <button onClick={handleRun} disabled={loading || shocks.length === 0}
            className="flex items-center gap-2 px-4 py-2 rounded text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white disabled:opacity-50">
            <Play size={14} />{loading ? "Running..." : "Run Stress Test"}
          </button>
        </div>
      </div>
    </div>
  );
}