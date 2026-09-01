import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { agentApi, researchApi, RiskMetrics, AgentPerformance, ParityStatus } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { ShieldAlert, TrendingDown, Percent, Activity, GitCompare, FlaskConical, RefreshCw, Zap, Scale, Bot } from "lucide-react";
import { fmt$, fmtPct } from "@/lib/utils";
import clsx from "clsx";
import StressTestModal from "@/components/StressTestModal";
import RebalancePanel from "@/components/RebalancePanel";
import AgentPerformanceModal from "@/components/AgentPerformanceModal";
import ParityStatusModal from "@/components/ParityStatusModal";

type SubTab = "overview" | "stress" | "rebalance" | "agents" | "parity";

export default function RiskWorkspace() {
  const { data, loading } = usePolling<RiskMetrics>(agentApi.risk, 15_000);
  const [subTab, setSubTab] = useState<SubTab>("overview");

  // Modal state
  const [stressOpen, setStressOpen] = useState(false);
  const [rebalanceOpen, setRebalanceOpen] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [parityOpen, setParityOpen] = useState(false);

  if (loading || !data) return <Skeleton />;

  const ddPct = data.drawdown_current / (data.drawdown_limit || 1);
  const ddColor = ddPct > 0.8 ? "#ef4444" : ddPct > 0.5 ? "#f59e0b" : "#10b981";
  const kellyCapped = Math.min(data.kelly_fraction ?? 0, 1);

  const subTabs: { id: SubTab; label: string; icon: React.ReactNode }[] = [
    { id: "overview",  label: "Overview",  icon: <Activity size={12} /> },
    { id: "stress",    label: "Stress",    icon: <FlaskConical size={12} /> },
    { id: "rebalance", label: "Rebalance", icon: <Scale size={12} /> },
    { id: "agents",    label: "Agents",    icon: <Bot size={12} /> },
    { id: "parity",    label: "Parity",    icon: <GitCompare size={12} /> },
  ];

  const actions = [
    { icon: <FlaskConical size={14} />, label: "Stress Test", onClick: () => setStressOpen(true), color: "text-amber-400" },
    { icon: <Scale size={14} />,        label: "Rebalance",   onClick: () => setRebalanceOpen(true), color: "text-blue-400" },
    { icon: <Bot size={14} />,          label: "Agents",      onClick: () => setAgentOpen(true), color: "text-purple-400" },
    { icon: <GitCompare size={14} />,   label: "Parity",      onClick: () => setParityOpen(true), color: "text-emerald-400" },
  ];

  return (
    <>
      <div className="h-full flex flex-col">
        {/* Sub-tab navigation */}
        <div className="flex items-center gap-1 px-3 pt-2 pb-0 shrink-0">
          <div className="flex gap-0.5 bg-slate-800 rounded-lg p-0.5">
            {subTabs.map(t => (
              <button key={t.id} onClick={() => setSubTab(t.id)}
                className={clsx("flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-semibold font-mono rounded-md transition-colors",
                  subTab === t.id ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
                )}>
                {t.icon}{t.label}
              </button>
            ))}
          </div>
          <div className="ml-auto flex gap-1">
            {actions.map(a => (
              <button key={a.label} onClick={a.onClick}
                className="flex items-center gap-1 px-2 py-1.5 rounded text-[10px] font-mono bg-slate-800 border border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-700">
                {a.icon}{a.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {subTab === "overview" && (
            <div className="max-w-3xl mx-auto space-y-4">
              {/* Header */}
              <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
                <div className="flex items-center gap-2">
                  <ShieldAlert size={14} className="text-indigo-400" />
                  <span className="text-sm font-semibold text-slate-200">Risk Dashboard</span>
                  {data.halted && (
                    <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-red-900 text-red-300 font-mono font-bold animate-pulse">HALTED</span>
                  )}
                </div>

                {/* Exposure row */}
                <div className="grid grid-cols-2 gap-3">
                  <MetricBox label="Gross Exposure" value={fmt$(data.gross_exposure)} sub={fmtPct(data.gross_pct_nav) + " of NAV"} warn={data.gross_pct_nav > 1.5} />
                  <MetricBox label="Net Exposure" value={fmt$(data.net_exposure)} sub={fmtPct(data.net_pct_nav) + " of NAV"} neutral />
                </div>

                {/* Drawdown gauge */}
                <div>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-slate-400 flex items-center gap-1"><TrendingDown size={11} /> Drawdown</span>
                    <span className="font-mono" style={{ color: ddColor }}>{fmtPct(data.drawdown_current)} / {fmtPct(data.drawdown_limit)} limit</span>
                  </div>
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(ddPct * 100, 100)}%`, background: ddColor }} />
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5 text-right font-mono">{fmtPct(data.drawdown_remaining)} remaining</div>
                </div>

                {/* Kelly fraction */}
                {data.kelly_fraction !== null && (
                  <div>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-slate-400 flex items-center gap-1"><Percent size={11} /> Kelly Fraction (7d)</span>
                      <span className="font-mono text-purple-300">{fmtPct(data.kelly_fraction)}</span>
                    </div>
                    <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div className="h-full rounded-full bg-purple-500 transition-all duration-500" style={{ width: `${Math.min(kellyCapped * 100, 100)}%` }} />
                    </div>
                  </div>
                )}

                {/* Concentration bar chart */}
                {data.concentration.length > 0 && (
                  <div>
                    <div className="text-xs text-slate-400 mb-2">Position Concentration (% NAV)</div>
                    <ResponsiveContainer width="100%" height={Math.max(60, data.concentration.length * 28)}>
                      <BarChart layout="vertical" data={data.concentration} margin={{ top: 0, right: 40, bottom: 0, left: 60 }}>
                        <XAxis type="number" tick={{ fontSize: 9, fill: "#64748b" }} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
                        <YAxis type="category" dataKey="ticker" tick={{ fontSize: 10, fill: "#cbd5e1" }} width={55} />
                        <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                          formatter={(v: number, _: string, entry: { payload?: { direction?: string; pnl?: number } }) => [
                            `${fmtPct(v)} · P&L: ${fmt$(entry.payload?.pnl ?? 0)}`,
                            entry.payload?.direction === "buy" ? "LONG" : "SHORT",
                          ]} />
                        <Bar dataKey="pct_nav" radius={[0, 3, 3, 0]}>
                          {data.concentration.map((entry, i) => (
                            <Cell key={i} fill={entry.direction === "buy" ? "#6366f1" : "#f43f5e"} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3 pt-1 border-t border-slate-700">
                  <MetricBox label="Positions" value={String(data.n_positions)} />
                  <MetricBox label="NAV" value={fmt$(data.nav)} />
                </div>
              </div>
            </div>
          )}

          {subTab === "stress" && (
            <div className="max-w-lg mx-auto">
              <div className="rounded-xl border border-slate-700 bg-slate-900 p-4">
                <div className="flex items-center gap-2 mb-4">
                  <FlaskConical size={14} className="text-amber-400" />
                  <span className="text-sm font-semibold text-slate-200">Stress Test</span>
                </div>
                <p className="text-xs text-slate-500 mb-4">Run what-if scenarios to test portfolio resilience. Click the "Stress Test" button in the top-right to open the scenario builder.</p>
                <button onClick={() => setStressOpen(true)}
                  className="flex items-center gap-2 px-4 py-2 rounded text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white">
                  <FlaskConical size={14} /> Open Stress Test
                </button>
              </div>
            </div>
          )}

          {subTab === "rebalance" && (
            <div className="max-w-lg mx-auto">
              <div className="rounded-xl border border-slate-700 bg-slate-900 p-4">
                <div className="flex items-center gap-2 mb-4">
                  <Scale size={14} className="text-blue-400" />
                  <span className="text-sm font-semibold text-slate-200">Portfolio Rebalance</span>
                </div>
                <p className="text-xs text-slate-500 mb-4">View current vs KG-optimal portfolio weights and suggested trades.</p>
                <button onClick={() => setRebalanceOpen(true)}
                  className="flex items-center gap-2 px-4 py-2 rounded text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white">
                  <Scale size={14} /> Open Rebalance
                </button>
              </div>
            </div>
          )}

          {subTab === "agents" && (
            <div className="max-w-lg mx-auto">
              <div className="rounded-xl border border-slate-700 bg-slate-900 p-4">
                <div className="flex items-center gap-2 mb-4">
                  <Bot size={14} className="text-purple-400" />
                  <span className="text-sm font-semibold text-slate-200">Agent Performance</span>
                </div>
                <p className="text-xs text-slate-500 mb-4">View per-agent cycle statistics, success rates, and performance breakdown.</p>
                <button onClick={() => setAgentOpen(true)}
                  className="flex items-center gap-2 px-4 py-2 rounded text-xs font-semibold bg-purple-600 hover:bg-purple-500 text-white">
                  <Bot size={14} /> Open Agent Performance
                </button>
              </div>
            </div>
          )}

          {subTab === "parity" && (
            <div className="max-w-lg mx-auto">
              <div className="rounded-xl border border-slate-700 bg-slate-900 p-4">
                <div className="flex items-center gap-2 mb-4">
                  <GitCompare size={14} className="text-emerald-400" />
                  <span className="text-sm font-semibold text-slate-200">C++ / Python Parity</span>
                </div>
                <p className="text-xs text-slate-500 mb-4">Monitor C++ vs Python engine parity status, discrepancy count, and version info.</p>
                <button onClick={() => setParityOpen(true)}
                  className="flex items-center gap-2 px-4 py-2 rounded text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white">
                  <GitCompare size={14} /> Open Parity Dashboard
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      <StressTestModal open={stressOpen} onClose={() => setStressOpen(false)} />
      <RebalancePanel open={rebalanceOpen} onClose={() => setRebalanceOpen(false)} />
      <AgentPerformanceModal open={agentOpen} onClose={() => setAgentOpen(false)} />
      <ParityStatusModal open={parityOpen} onClose={() => setParityOpen(false)} />
    </>
  );
}

function MetricBox({ label, value, sub, warn, neutral }: { label: string; value: string; sub?: string; warn?: boolean; neutral?: boolean }) {
  return (
    <div className="bg-slate-800/60 rounded-lg p-2.5">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={clsx("text-base font-mono font-bold mt-0.5", warn ? "text-red-400" : neutral ? "text-slate-200" : "text-slate-100")}>{value}</div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}

function Skeleton() {
  return <div className="rounded-xl border border-slate-700 bg-slate-800 h-48 animate-pulse" />;
}