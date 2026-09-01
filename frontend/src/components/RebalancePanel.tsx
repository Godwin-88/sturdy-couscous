import { useState, useEffect } from "react";
import { X, RefreshCw, AlertCircle, ArrowUpCircle, ArrowDownCircle } from "lucide-react";
import { researchApi, PortfolioRebalance } from "@/lib/api";
import { fmt$, fmtPct } from "@/lib/utils";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function RebalancePanel({ open, onClose }: Props) {
  const [data, setData] = useState<PortfolioRebalance | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRebalance = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await researchApi.portfolioRebalance();
      setData(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) fetchRebalance();
  }, [open]);

  if (!open) return null;

  const allTickers = data ? Object.keys({ ...data.current, ...data.optimal }) : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 shrink-0">
          <h2 className="text-sm font-semibold text-slate-200">⚖️ Portfolio Rebalance</h2>
          <div className="flex items-center gap-2">
            <button onClick={fetchRebalance} className="p-1 text-slate-500 hover:text-slate-300 rounded"><RefreshCw size={14} /></button>
            <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300 rounded"><X size={16} /></button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {loading && <div className="text-xs text-slate-500 animate-pulse text-center py-8">Loading rebalance data...</div>}
          {error && <div className="flex items-center gap-1.5 text-xs text-red-400 mb-3"><AlertCircle size={12} />{error}</div>}

          {!loading && data && (
            <div className="space-y-4">
              {/* Weights comparison table */}
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="text-slate-400 border-b border-slate-700">
                      <th className="text-left py-2 px-2 text-[10px] uppercase">Ticker</th>
                      <th className="text-right py-2 px-2 text-[10px] uppercase">Current</th>
                      <th className="text-right py-2 px-2 text-[10px] uppercase">Optimal</th>
                      <th className="text-right py-2 px-2 text-[10px] uppercase">Δ</th>
                      <th className="text-right py-2 px-2 text-[10px] uppercase">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allTickers.map(ticker => {
                      const cur = data.current[ticker] ?? 0;
                      const opt = data.optimal[ticker] ?? 0;
                      const diff = opt - cur;
                      return (
                        <tr key={ticker} className="border-b border-slate-800 hover:bg-slate-800/40">
                          <td className="py-2 px-2 text-slate-200 font-bold">{ticker}</td>
                          <td className="py-2 px-2 text-right text-slate-400">{fmtPct(cur)}</td>
                          <td className="py-2 px-2 text-right text-slate-200">{fmtPct(opt)}</td>
                          <td className={clsx("py-2 px-2 text-right font-bold",
                            diff > 0.01 ? "text-emerald-400" : diff < -0.01 ? "text-red-400" : "text-slate-500"
                          )}>
                            {diff > 0 ? "+" : ""}{fmtPct(diff)}
                          </td>
                          <td className="py-2 px-2 text-right">
                            {diff > 0.02 ? (
                              <span className="flex items-center justify-end gap-1 text-emerald-400 text-[10px]">
                                <ArrowUpCircle size={10} /> Buy
                              </span>
                            ) : diff < -0.02 ? (
                              <span className="flex items-center justify-end gap-1 text-red-400 text-[10px]">
                                <ArrowDownCircle size={10} /> Sell
                              </span>
                            ) : (
                              <span className="text-slate-600 text-[10px]">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Suggested trades */}
              {data.trades_suggested.length > 0 && (
                <div>
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Suggested Trades</div>
                  <div className="space-y-1.5">
                    {data.trades_suggested.map((t, i) => (
                      <div key={i} className="flex items-center justify-between bg-slate-800 rounded p-2 border border-slate-700 text-xs font-mono">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-200">{t.ticker}</span>
                          <span className={clsx("px-1.5 py-0.5 rounded text-[10px]",
                            t.action === "buy" ? "bg-emerald-900/50 text-emerald-300" : "bg-red-900/50 text-red-300"
                          )}>
                            {t.action.toUpperCase()}
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-slate-400">Target: {fmtPct(t.target_weight)}</span>
                          <span className="text-slate-200">{fmt$(t.notional_usd)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {!loading && !data && !error && (
            <div className="text-xs text-slate-500 text-center py-8">No rebalance data available.</div>
          )}
        </div>
      </div>
    </div>
  );
}