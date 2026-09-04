import { useState, useMemo, useEffect } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  AreaChart, Area,
} from "recharts";
import { agentApi, researchApi, optionsApi, RiskMetrics, AgentPerformance, ParityStatus, HedgeState } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { getScreenContext } from "@/lib/screenContext";
import { ShieldAlert, TrendingDown, Percent, Activity, GitCompare, FlaskConical, RefreshCw, Zap, Scale, Bot, Wallet, AlertTriangle, Shield, Clock, Link2, ArrowLeft, HelpCircle } from "lucide-react";
import { fmt$, fmtPct } from "@/lib/utils";
import clsx from "clsx";
import BrokerTable from "@/components/BrokerTable";
import StressTestModal from "@/components/StressTestModal";
import RebalancePanel from "@/components/RebalancePanel";
import AgentPerformanceModal from "@/components/AgentPerformanceModal";
import ParityStatusModal from "@/components/ParityStatusModal";
import Greeks3DVisualization from "@/components/Greeks3DVisualization";

type SubTab = "overview" | "options" | "stress" | "rebalance" | "agents" | "parity";

// Options risk view. When a chain context is shared by the Options panel
// (screenContext "options"), the hedge state is fetched for that exact
// underlying from the broker; without context it falls back to a well-formed
// illustrative mock so the tab stays usable standalone.
function useOptionsRiskData(chainUnderlying?: string) {
  const [hedgeState, setHedgeState] = useState<HedgeState | null>(null);
  const [loadingHedge, setLoadingHedge] = useState(false);

  const buildMock = (): HedgeState => {
    const sym = chainUnderlying || "SPY";
    return {
      underlying: sym,
      regime: "RiskOn",
      confidence: 0.78,
      greeks: { delta: 12.4, gamma: 3.2, theta: -45.8, vega: 28.5 },
      positions: [
        { symbol: `${sym}260918C00850000`, cls: "option", qty: 5, delta: 0.65, gamma: 0.02, theta: -0.15, vega: 0.12, iv: 0.18 },
        { symbol: `${sym}260918P00750000`, cls: "option", qty: -3, delta: -0.35, gamma: 0.015, theta: -0.12, vega: 0.09, iv: 0.22 },
      ],
      spot: 85.00,
      hedge_shares: 0,
      band_shares: 15,
      needs_rebalance: false,
      reason: "delta within band (illustrative — no chain context)",
      proposal: null,
      tail_sleeve: { recommended: false, reason: "regime stable", budget_usd: 0, suggest: "", note: "" },
    };
  };

  const loadHedge = async () => {
    setLoadingHedge(true);
    try {
      if (chainUnderlying) {
        const res = await optionsApi.hedge.state(chainUnderlying);
        if (res.hedge_state) {
          setHedgeState(res.hedge_state);
          return;
        }
      }
      setHedgeState(buildMock());
    } catch {
      setHedgeState(buildMock());
    } finally {
      setLoadingHedge(false);
    }
  };

  return { hedgeState, loadingHedge, loadHedge };
}

export default function RiskWorkspace({ onNavigate }: { onNavigate?: (tab: string) => void }) {
  const { data, loading } = usePolling<RiskMetrics>(agentApi.risk, 15_000);
  // Chain context shared by the Options panel — deep-link arrives with the
  // underlying/expiry of the chain the user was just looking at.
  const chainCtx = useMemo(() => getScreenContext("options"), []);
  const [subTab, setSubTab] = useState<SubTab>(chainCtx?.underlying ? "options" : "overview");
  const { hedgeState, loadingHedge, loadHedge } = useOptionsRiskData(chainCtx?.underlying);

  // Auto-open the Options sub-tab when a chain context is present.
  useEffect(() => {
    if (chainCtx?.underlying) setSubTab("options");
  }, [chainCtx?.underlying]);

  // Modal state
  const [stressOpen, setStressOpen] = useState(false);
  const [rebalanceOpen, setRebalanceOpen] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [parityOpen, setParityOpen] = useState(false);

  // Load hedge data when options tab is selected
  useMemo(() => {
    if (subTab === "options" && !hedgeState && !loadingHedge) {
      loadHedge();
    }
  }, [subTab]);

  if (loading || !data) return <Skeleton />;

  const ddPct = data.drawdown_current / (data.drawdown_limit || 1);
  const ddColor = ddPct > 0.8 ? "#ef4444" : ddPct > 0.5 ? "#f59e0b" : "#10b981";
  const kellyCapped = Math.min(data.kelly_fraction ?? 0, 1);

  const subTabs: { id: SubTab; label: string; icon: React.ReactNode }[] = [
    { id: "overview",  label: "Overview",  icon: <Activity size={12} /> },
    { id: "options",   label: "Options",   icon: <Zap size={12} /> },
    { id: "stress",    label: "Stress",    icon: <FlaskConical size={12} /> },
    { id: "rebalance", label: "Rebalance", icon: <Scale size={12} /> },
    { id: "agents",    label: "Agents",    icon: <Bot size={12} /> },
    { id: "parity",    label: "Parity",    icon: <GitCompare size={12} /> },
  ];

  const goBack = () => {
    if (onNavigate) { onNavigate("dashboard"); return; }
    window.location.hash = "#/dashboard";
  };

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
          <div className="ml-auto flex items-center gap-1">
            {chainCtx?.underlying && (
              <span className="flex items-center gap-1 text-[10px] font-mono text-violet-300 bg-violet-950/40 border border-violet-500/30 rounded px-2 py-1">
                <Link2 size={10} /> chain: {chainCtx.underlying}
                {chainCtx.expiration ? ` · ${chainCtx.expiration}` : ""}
                {chainCtx.contract_type ? ` · ${chainCtx.contract_type}` : ""}
              </span>
            )}
            <button onClick={goBack}
              title="Back to where you came from (e.g. Dashboard)"
              className="flex items-center gap-1 px-2 py-1.5 rounded text-[10px] font-mono bg-slate-800 border border-slate-600 text-slate-300 hover:bg-slate-700">
              <ArrowLeft size={11} /> Back
            </button>
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

              {/* Full broker book — every Alpaca position (options + crypto + equity) */}
              <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
                <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
                  <Wallet size={14} className="text-indigo-400" />
                  <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">
                    Broker Book <span className="text-slate-500">({data.n_positions} positions)</span>
                  </span>
                  <span className="ml-auto flex items-center gap-1 text-[10px] text-slate-500 font-mono">
                    <HelpCircle size={11} /> hover a column for meaning · click Analyze per position
                  </span>
                </div>
                <BrokerTable onNavigate={onNavigate} maxHeight="max-h-[360px]" />
              </div>
            </div>
          )}

          {subTab === "options" && (
            <OptionsRiskSection
              hedgeState={hedgeState}
              loading={loadingHedge}
              onLoadHedge={loadHedge}
              nav={data.nav}
            >
              <div className="w-full">
                <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
                  <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
                    <Wallet size={14} className="text-indigo-400" />
                    <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">
                      Broker Book <span className="text-slate-500">(all Alpaca positions)</span>
                    </span>
                    <span className="ml-auto flex items-center gap-1 text-[10px] text-slate-500 font-mono">
                      <HelpCircle size={11} /> hover a column for meaning
                    </span>
                  </div>
                  <BrokerTable onNavigate={onNavigate} maxHeight="max-h-[340px]" />
                </div>
              </div>
            </OptionsRiskSection>
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

function OptionsRiskSection({
  hedgeState, loading, onLoadHedge, nav, children,
}: {
  hedgeState: HedgeState | null;
  loading: boolean;
  onLoadHedge: () => void;
  nav: number;
  children?: React.ReactNode;
}) {
  const premiumBudget = 0.15;
  const premiumUsed = hedgeState ? Math.abs(hedgeState.greeks.theta) * 30 : 0;
  const premiumPct = nav > 0 ? (premiumUsed / nav) * 100 : 0;
  const budgetPct = (premiumUsed / (premiumBudget * nav)) * 100;

  const var95 = hedgeState ? Math.abs(hedgeState.greeks.delta * hedgeState.spot! * 0.02) : 0;
  const var99 = var95 * 1.4;

  const nakedCalls = hedgeState?.positions.filter(p => p.delta > 0.5 && p.qty > 0) ?? [];
  const illiquidRejects = hedgeState?.positions.filter(p => (p.iv ?? 0) > 0.5) ?? [];

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left column: gauges + greeks */}
        <div className="space-y-4">
          {/* Premium Budget Gauge */}
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Wallet size={14} className="text-amber-400" />
              <span className="text-sm font-semibold text-slate-200">Premium Budget</span>
              <span className="ml-auto text-[10px] font-mono text-slate-400">monthly allocation</span>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Used vs Budget</span>
                <span className={clsx("font-mono font-bold", budgetPct > 90 ? "text-red-400" : budgetPct > 70 ? "text-amber-400" : "text-emerald-400")}>
                  {premiumPct.toFixed(2)}% / {(premiumBudget * 100).toFixed(0)}%
                </span>
              </div>
              <div className="h-3 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className={clsx("h-full rounded-full transition-all duration-500",
                    budgetPct > 90 ? "bg-red-500" : budgetPct > 70 ? "bg-amber-500" : "bg-emerald-500"
                  )}
                  style={{ width: `${Math.min(budgetPct, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-[10px] font-mono text-slate-500">
                <span>Used: {fmt$(premiumUsed)}</span>
                <span>Budget: {fmt$(premiumBudget * nav)}</span>
              </div>
            </div>
          </div>

          {/* Delta-Gamma VaR */}
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} className="text-red-400" />
              <span className="text-sm font-semibold text-slate-200">Delta-Gamma VaR</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-slate-800/60 rounded-lg p-3">
                <div className="text-[10px] text-slate-500 uppercase">95% VaR (1d)</div>
                <div className="text-base font-mono font-bold text-amber-400">{fmt$(var95)}</div>
              </div>
              <div className="bg-slate-800/60 rounded-lg p-3">
                <div className="text-[10px] text-slate-500 uppercase">99% VaR (1d)</div>
                <div className="text-base font-mono font-bold text-red-400">{fmt$(var99)}</div>
              </div>
            </div>
            {hedgeState && (
              <div className="text-[10px] font-mono text-slate-500">
                δ={hedgeState.greeks.delta.toFixed(1)} × spot={fmt$(hedgeState.spot ?? 0)} × 2σ shock
              </div>
            )}
          </div>

          {/* Naked Calls / Illiquid Rejects */}
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Shield size={14} className="text-orange-400" />
              <span className="text-sm font-semibold text-slate-200">Risk Gates</span>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">Naked Call Exposures</span>
                <span className={clsx("text-xs font-mono font-bold", nakedCalls.length > 0 ? "text-red-400" : "text-emerald-400")}>
                  {nakedCalls.length > 0 ? `${nakedCalls.length} ACTIVE` : "CLEAR"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">Illiquid Contract Rejects</span>
                <span className={clsx("text-xs font-mono font-bold", illiquidRejects.length > 0 ? "text-amber-400" : "text-emerald-400")}>
                  {illiquidRejects.length > 0 ? `${illiquidRejects.length} FLAGGED` : "CLEAR"}
                </span>
              </div>
            </div>
            {nakedCalls.length > 0 && (
              <div className="space-y-1">
                {nakedCalls.map(p => (
                  <div key={p.symbol} className="flex items-center gap-2 text-[10px] font-mono bg-red-950/20 border border-red-900/40 rounded px-2 py-1">
                    <AlertTriangle size={10} className="text-red-400" />
                    <span className="text-red-300">{p.symbol}</span>
                    <span className="text-slate-500">qty {p.qty}</span>
                    <span className="text-red-400 ml-auto">δ {p.delta.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right column: 3D Greeks + positions */}
        <div className="space-y-4">
          {hedgeState ? (
            <Greeks3DVisualization greeks={hedgeState.greeks} title="Options Greeks 3D" />
          ) : (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-6 flex flex-col items-center justify-center gap-3">
              <Activity size={24} className="text-slate-600" />
              <span className="text-xs text-slate-500 text-center">Load hedge state to view 3D Greeks exposure</span>
              <button onClick={onLoadHedge} disabled={loading}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono bg-indigo-600/30 border border-indigo-500/40 text-indigo-300 hover:bg-indigo-600/50 disabled:opacity-50">
                {loading ? "Loading..." : "Load Hedge State"}
              </button>
            </div>
          )}

          {/* Options Positions Exposure */}
          {hedgeState && hedgeState.positions.length > 0 && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Clock size={14} className="text-cyan-400" />
                <span className="text-sm font-semibold text-slate-200">Options Positions</span>
              </div>
              <div className="space-y-2">
                {hedgeState.positions.map(p => (
                  <div key={p.symbol} className="bg-slate-800/60 rounded-lg p-2.5 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-200 font-mono">{p.symbol}</span>
                      <span className={clsx("text-[10px] font-mono font-bold px-1.5 py-0.5 rounded",
                        p.qty > 0 ? "bg-emerald-900/50 text-emerald-300" : "bg-red-900/50 text-red-300")}>
                        {p.qty > 0 ? "LONG" : "SHORT"} {Math.abs(p.qty)}
                      </span>
                    </div>
                    <div className="grid grid-cols-4 gap-1 text-[10px] font-mono">
                      <div>
                        <span className="text-slate-500">Δ</span>{" "}
                        <span className={p.delta >= 0 ? "text-emerald-400" : "text-red-400"}>{p.delta.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">Γ</span>{" "}
                        <span className="text-indigo-400">{p.gamma.toFixed(3)}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">Θ</span>{" "}
                        <span className="text-amber-400">{p.theta.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">V</span>{" "}
                        <span className="text-pink-400">{p.vega.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Full broker book (children) */}
        <div className="w-full pt-2">
          {children}
        </div>
      </div>
    </div>
  );
}