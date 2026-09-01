import { useState, useEffect } from "react";
import { X, BarChart3, History, GitBranch, AlertCircle, BarChart, Brain, FileSearch } from "lucide-react";
import { researchApi, SignalAttribution, OrderLifecycle, SignalLineage } from "@/lib/api";
import { fmt$, relTime } from "@/lib/utils";
import clsx from "clsx";

interface Props {
  orderId: string;
  strategy: string;
  ticker: string;
  direction: string;
  onClose: () => void;
  onAnalyze: () => void;
  onHypothesis: () => void;
}

type Tab = "attribution" | "lifecycle" | "kg";

export default function OrderDetailDrawer({ orderId, strategy, ticker, direction, onClose, onAnalyze, onHypothesis }: Props) {
  const [tab, setTab] = useState<Tab>("attribution");
  const [attribution, setAttribution] = useState<SignalAttribution | null>(null);
  const [lifecycle, setLifecycle] = useState<OrderLifecycle | null>(null);
  const [lineage, setLineage] = useState<SignalLineage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      researchApi.signalAttribution(orderId).catch(() => null),
      researchApi.orderLifecycle(orderId).catch(() => null),
    ]).then(([a, l]) => {
      setAttribution(a);
      setLifecycle(l);
      // Try to get lineage from the API
      if (a?.strategy || strategy) {
        import("@/lib/api").then(({ agentApi }) =>
          agentApi.signalLineage(strategy).then(setLineage).catch(() => null)
        );
      }
    }).catch(e => setError(e instanceof Error ? e.message : String(e)))
    .finally(() => setLoading(false));
  }, [orderId, strategy]);

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "attribution", label: "Attribution", icon: <BarChart3 size={12} /> },
    { id: "lifecycle",   label: "Lifecycle",   icon: <History size={12} /> },
    { id: "kg",          label: "KG Path",     icon: <GitBranch size={12} /> },
  ];

  return (
    <div className="border-t border-slate-700 bg-slate-900/95">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-800 border-b border-slate-700">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-slate-200 font-mono">
            {orderId.slice(0, 12)}...
          </span>
          <span className={clsx("text-xs font-bold font-mono",
            direction === "buy" ? "text-emerald-400" : "text-red-400")}>
            {direction.toUpperCase()} {ticker}
          </span>
          <span className="text-xs text-slate-500 font-mono">{strategy}</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onAnalyze}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-semibold bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30 border border-indigo-500/30">
            <BarChart size={10} /> Analyze
          </button>
          <button onClick={onHypothesis}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-semibold bg-purple-600/20 text-purple-400 hover:bg-purple-600/30 border border-purple-500/30">
            <Brain size={10} /> Hypothesis
          </button>
          <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300 rounded">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-0 px-4 pt-2 bg-slate-900 border-b border-slate-700">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={clsx(
              "flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-semibold font-mono border-b-2 transition-colors",
              tab === t.id
                ? "text-indigo-400 border-indigo-400"
                : "text-slate-500 border-transparent hover:text-slate-300"
            )}>
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-4 max-h-[350px] overflow-y-auto">
        {loading && <div className="text-xs text-slate-500 animate-pulse text-center py-6">Loading details...</div>}
        {error && <div className="flex items-center gap-1.5 text-xs text-red-400"><AlertCircle size={12} />{error}</div>}

        {!loading && !error && tab === "attribution" && attribution && (
          <div className="space-y-3">
            {/* Score breakdown */}
            <div className="grid grid-cols-3 gap-2">
              <ScoreCard label="Signal Score" value={attribution.signal_score?.toFixed(3) ?? "—"} dir={direction}
                sub={attribution.quant_score !== undefined ? `Quant: ${attribution.quant_score?.toFixed(3)}` : undefined} />
              <ScoreCard label="Sentiment" value={attribution.sentiment_score?.toFixed(3) ?? "—"} dir={direction}
                sub={attribution.news_overlay !== undefined ? `News: ${attribution.news_overlay?.toFixed(3)}` : undefined} />
              <ScoreCard label="Macro" value={attribution.macro_overlay?.toFixed(3) ?? "—"} dir={direction} />
            </div>

            {/* KG contribution & contradiction */}
            <div className="flex items-center gap-3 text-xs font-mono">
              {attribution.kg_formula_contribution !== undefined && (
                <div className="bg-slate-800 rounded px-2 py-1 border border-slate-700">
                  <span className="text-slate-500">KG Formula: </span>
                  <span className={attribution.kg_formula_contribution > 0 ? "text-emerald-400" : "text-red-400"}>
                    {attribution.kg_formula_contribution > 0 ? "+" : ""}{attribution.kg_formula_contribution.toFixed(3)}
                  </span>
                </div>
              )}
              {attribution.contradiction_blocked !== undefined && (
                <div className={clsx("rounded px-2 py-1 border text-[10px]",
                  attribution.contradiction_blocked
                    ? "bg-red-950/30 border-red-800 text-red-400"
                    : "bg-emerald-950/30 border-emerald-800 text-emerald-400"
                )}>
                  {attribution.contradiction_blocked ? "⛔ Blocked by contradiction" : "✅ No contradiction"}
                </div>
              )}
            </div>

            {/* Kelly & VaR */}
            <div className="flex items-center gap-3 text-xs font-mono">
              {attribution.kelly_fraction !== undefined && (
                <div className="bg-slate-800 rounded px-2 py-1 border border-slate-700">
                  <span className="text-slate-500">Kelly: </span>
                  <span className="text-slate-200">{attribution.kelly_fraction.toFixed(3)}</span>
                </div>
              )}
              {attribution.var_contribution !== undefined && (
                <div className="bg-slate-800 rounded px-2 py-1 border border-slate-700">
                  <span className="text-slate-500">VaR: </span>
                  <span className="text-slate-200">{attribution.var_contribution.toFixed(3)}</span>
                </div>
              )}
              {attribution.slippage_bps !== undefined && (
                <div className="bg-slate-800 rounded px-2 py-1 border border-slate-700">
                  <span className="text-slate-500">Slippage: </span>
                  <span className={attribution.slippage_bps > 0 ? "text-red-400" : "text-emerald-400"}>
                    {attribution.slippage_bps.toFixed(1)} bps
                  </span>
                </div>
              )}
            </div>

            {/* KG graph path */}
            {attribution.kg_graph_path && attribution.kg_graph_path.length > 0 && (
              <div className="bg-slate-800 rounded p-2 border border-slate-700">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">KG Graph Path</div>
                <div className="flex flex-wrap gap-1 text-[10px] font-mono">
                  {attribution.kg_graph_path.map((node, i) => (
                    <span key={i} className="flex items-center gap-0.5">
                      <span className="text-slate-400">{node}</span>
                      {i < attribution.kg_graph_path!.length - 1 && <span className="text-slate-600">→</span>}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {!loading && !error && tab === "attribution" && !attribution && (
          <div className="text-xs text-slate-500 text-center py-6">No attribution data available for this signal.</div>
        )}

        {!loading && !error && tab === "lifecycle" && lifecycle && (
          <div className="space-y-3">
            {/* Timeline stages */}
            <div className="flex items-center gap-2 text-xs font-mono">
              <Stage status="done" label="Signal" />
              <Stage status={lifecycle.rejection_reason ? "rejected" : "done"} label="Approved" />
              <Stage status={lifecycle.fill_price ? "done" : "pending"} label="Submitted" />
              <Stage status={lifecycle.fill_price ? "done" : "pending"} label="Filled" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <DetailField label="Fill Price" value={lifecycle.fill_price ? fmt$(lifecycle.fill_price) : "—"} />
              <DetailField label="Quantity" value={String(lifecycle.quantity)} />
              <DetailField label="Fee (USD)" value={lifecycle.fee_usd ? fmt$(lifecycle.fee_usd) : "—"} />
              <DetailField label="Mode" value={lifecycle.mode} />
              <DetailField label="Signal Score" value={lifecycle.signal_score?.toFixed(3) ?? "—"} />
              <DetailField label="Kelly Fraction" value={lifecycle.kelly_fraction?.toFixed(3) ?? "—"} />
              <DetailField label="VaR Contribution" value={lifecycle.var_contribution?.toFixed(3) ?? "—"} />
              <DetailField label="Created" value={relTime(lifecycle.created_at)} />
            </div>

            {lifecycle.rejection_reason && (
              <div className="bg-red-950/30 border border-red-800 rounded p-2 text-xs text-red-400 font-mono">
                Rejected: {lifecycle.rejection_reason}
              </div>
            )}

            {lifecycle.contradiction_blocked && (
              <div className="bg-amber-950/30 border border-amber-800 rounded p-2 text-xs text-amber-400 font-mono">
                ⛔ Blocked by contradiction — signal was suppressed by contradiction detection
              </div>
            )}
          </div>
        )}

        {!loading && !error && tab === "lifecycle" && !lifecycle && (
          <div className="text-xs text-slate-500 text-center py-6">No lifecycle data available.</div>
        )}

        {!loading && !error && tab === "kg" && (
          <div className="space-y-3">
            {lineage ? (
              <>
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-semibold text-indigo-300">{lineage.strategy}</span>
                  {lineage.strategy_desc && <span className="text-slate-500">— {lineage.strategy_desc}</span>}
                </div>

                {lineage.regimes.length > 0 && (
                  <div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Regimes</div>
                    <div className="flex flex-wrap gap-1">
                      {lineage.regimes.map(r => (
                        <span key={r} className="text-[10px] px-1.5 py-0.5 rounded bg-purple-900/60 text-purple-300 border border-purple-700 font-mono">{r}</span>
                      ))}
                    </div>
                  </div>
                )}

                {lineage.concepts.length > 0 && (
                  <div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Concepts ({lineage.concepts.length})</div>
                    <div className="grid grid-cols-2 gap-1.5">
                      {lineage.concepts.map((c, i) => (
                        <div key={i} className="bg-slate-800 rounded p-2 border border-slate-700">
                          <div className="text-[11px] font-semibold text-slate-200">{c.name}</div>
                          {c.definition && <div className="text-[10px] text-slate-500">{c.definition}</div>}
                          <div className="flex gap-1 mt-0.5 text-[9px]">
                            <span className="text-indigo-500">{c.category}</span>
                            <span className={clsx("px-1 rounded",
                              c.difficulty === "hard" ? "bg-red-900/50 text-red-300" :
                              c.difficulty === "medium" ? "bg-yellow-900/50 text-yellow-300" :
                              "bg-slate-700 text-slate-400"
                            )}>{c.difficulty}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {lineage.formulas.length > 0 && (
                  <div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Formulas ({lineage.formulas.length})</div>
                    {lineage.formulas.map((f, i) => (
                      <div key={i} className="bg-slate-800 rounded p-2 border border-slate-700 mb-1">
                        <div className="text-xs font-semibold text-emerald-300">{f.name}</div>
                        <code className="text-[10px] text-amber-300 font-mono">{f.expression}</code>
                        {f.output && <div className="text-[10px] text-slate-500">→ {f.output}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="text-xs text-slate-500 text-center py-6">No KG lineage data available for {strategy}.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ScoreCard({ label, value, dir, sub }: { label: string; value: string; dir: string; sub?: string }) {
  const numVal = parseFloat(value);
  const isPositive = !isNaN(numVal) && numVal >= 0;
  return (
    <div className={clsx("bg-slate-800 rounded-lg p-2.5 border",
      isPositive ? "border-emerald-800/30" : "border-red-800/30"
    )}>
      <div className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={clsx("text-sm font-bold font-mono mt-0.5",
        isPositive ? "text-emerald-400" : "text-red-400"
      )}>
        {isPositive ? "+" : ""}{value}
      </div>
      {sub && <div className="text-[10px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function Stage({ status, label }: { status: "done" | "pending" | "rejected"; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={clsx("w-2 h-2 rounded-full",
        status === "done" ? "bg-emerald-400" :
        status === "rejected" ? "bg-red-400" :
        "bg-slate-600"
      )} />
      <span className={clsx("text-[10px]",
        status === "done" ? "text-slate-300" :
        status === "rejected" ? "text-red-400" :
        "text-slate-600"
      )}>{label}</span>
    </div>
  );
}

function DetailField({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-800/60 rounded p-2 border border-slate-700/50">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className="text-xs font-mono text-slate-200 mt-0.5">{value}</div>
    </div>
  );
}