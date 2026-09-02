import { useState, useRef, useEffect } from "react";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import clsx from "clsx";
import {
  Activity, GitBranch, BarChart2, Table2, Radio, ShieldAlert, Brain,
  FlaskConical, LayoutDashboard, Terminal, Download, Search,
  Lightbulb, Zap, Shield, Edit3, ChevronDown, ChevronUp, Bot,
} from "lucide-react";
import Sigma from "sigma";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";

import RegimePanel         from "@/components/RegimePanel";
import PnLDashboard        from "@/components/PnLDashboard";
import AgentLog            from "@/components/AgentLog";
import GraphCanvas         from "@/components/GraphCanvas";
import SignalsTable        from "@/components/SignalsTable";
import BacktestWorkspace   from "@/components/BacktestWorkspace";
import ContradictionsPanel from "@/components/ContradictionsPanel";
import RiskWorkspace       from "@/components/RiskWorkspace";
import IntelligencePanel   from "@/components/IntelligencePanel";
  import AlpacaPanel        from "@/components/AlpacaPanel";
import OptionsPanel       from "@/components/OptionsPanel";
import OptionPnlPanel     from "@/components/OptionPnlPanel";
import AnalyticsPanel     from "@/components/AnalyticsPanel";
import ContextMenu, { type ContextMenuSeries } from "@/components/ContextMenu";
import HypothesisBoard     from "@/components/HypothesisBoard";
import CypherConsole       from "@/components/CypherConsole";
import KGEditModal         from "@/components/KGEditModal";
import ContradictionManager from "@/components/ContradictionManager";
import SimulateModal       from "@/components/SimulateModal";
import SignalLineageModal  from "@/components/SignalLineageModal";
import RecommendationsPanel from "@/components/RecommendationsPanel";
import ScreenChat from "@/components/ScreenChat";
import AgentCoPilot from "@/components/AgentCoPilot";
import { agentApi, researchApi, hypothesisApi } from "@/lib/api";
import { registerWebMCPTools, unregisterWebMCPTools, WEBMCP_TOOL_COUNT } from "@/webmcp/tools";
import { LABEL_COLOR } from "@/lib/utils";

type Tab = "dashboard" | "graph" | "signals" | "backtest" | "risk" | "intelligence" | "options";

const OP_TABS: { id: Tab; label: string; icon: React.ReactNode; stage: string }[] = [
  { id: "backtest",    label: "Backtest",      icon: <BarChart2       size={14} />, stage: "TESTING" },
  { id: "signals",     label: "Signals",       icon: <Table2          size={14} />, stage: "DEPLOYED" },
  { id: "options",     label: "Options",       icon: <Activity        size={14} />, stage: "DEPLOYED" },
  { id: "risk",        label: "Risk",          icon: <ShieldAlert     size={14} />, stage: "DEPLOYED" },
  { id: "dashboard",   label: "Dashboard",     icon: <LayoutDashboard size={14} />, stage: "MONITORING" },
  { id: "intelligence",label: "Intelligence",  icon: <Brain           size={14} />, stage: "MONITORING" },
  { id: "graph",       label: "KG Explorer",   icon: <GitBranch       size={14} />, stage: "MONITORING" },
];

const ANALYSIS_ITEMS: { id: string; label: string; icon: React.ReactNode; path: string }[] = [
  { id: "analytics",  label: "Analytics",  icon: <FlaskConical size={14} />, path: "/analytics" },
  { id: "hypothesis", label: "Hypotheses", icon: <Brain        size={14} />, path: "/hypothesis" },
];

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [opTab, setOpTab] = useState<Tab>("dashboard");
  const appRef = useRef<HTMLDivElement>(null);
  const [copilotOpen, setCopilotOpen] = useState(false);

  const isAnalyticsRoute  = location.pathname.startsWith("/analytics");
  const isHypothesisRoute = location.pathname.startsWith("/hypothesis");
  const isAnalysisRoute   = isAnalyticsRoute || isHypothesisRoute;

  // Derive the current "screen" id for the Financial Engineer chat context.
  const currentScreen = isAnalyticsRoute
    ? "analytics"
    : isHypothesisRoute
      ? "hypothesis"
      : opTab;

  const handleCreateHypothesis = (series: ContextMenuSeries) => {
    navigate(`/hypothesis/new?series=${encodeURIComponent(series.id)}&ticker=${encodeURIComponent(series.ticker)}`);
  };

  const handlePinToHypothesis = (series: ContextMenuSeries) => {
    const hypId = prompt("Enter hypothesis ID to pin this evidence to:");
    if (!hypId) return;
    hypothesisApi.attachEvidence(hypId, {
      evidence_type: "chart",
      tier: "diagnostic",
      series_id: series.id,
      label: `Pinned: ${series.name}`,
      data: { series },
    }).then(() => alert("Evidence pinned!")).catch(() => alert("Failed to pin evidence"));
  };

  const handleOpNav = (tab: string) => {
    setOpTab(tab as Tab);
    navigate("/");
  };

  // WebMCP tool registration — once on mount, unregister on unmount.
  useEffect(() => {
    registerWebMCPTools();
    return () => unregisterWebMCPTools();
  }, []);

  return (
    <div ref={appRef} className="flex h-screen bg-slate-950 overflow-hidden">
      <ContextMenu
        containerRef={appRef}
        onCreateHypothesis={handleCreateHypothesis}
        onPinToHypothesis={handlePinToHypothesis}
        onAnalyze={(series) => {
          navigate(`/analytics?series=${encodeURIComponent(series.id)}&start=${series.startDate || ""}&end=${series.endDate || ""}`);
        }}
      />

      <aside className="w-52 shrink-0 flex flex-col bg-slate-900 border-r border-slate-800 h-full">
        <div className="flex items-center gap-2 px-4 py-4 border-b border-slate-800">
          <div className="w-7 h-7 rounded bg-indigo-600 flex items-center justify-center">
            <Radio size={14} className="text-white" />
          </div>
          <span className="text-sm font-bold text-slate-100 font-mono tracking-tight">
            Graph<span className="text-indigo-400">Alpha</span>
          </span>
        </div>

        {/* Grouped by lifecycle stage */}
        {(["TESTING", "DEPLOYED", "MONITORING"] as const).map(stage => {
          const opItems = OP_TABS.filter(t => t.stage === stage);
          const analysisItems = stage === "TESTING" ? ANALYSIS_ITEMS : [];
          const allItems = [...opItems, ...analysisItems];
          if (allItems.length === 0) return null;
          return (
            <div key={stage} className="px-3 pt-3 pb-1">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5 px-2">
                {stage}
              </div>
              <nav className="space-y-0.5">
                {allItems.map(item => {
                  const isTabNav = "id" in item && OP_TABS.some(t => t.id === item.id);
                  if (isTabNav) {
                    const t = item as typeof OP_TABS[0];
                    const isActive = !isAnalysisRoute && opTab === t.id;
                    return (
                      <button key={t.id} onClick={() => handleOpNav(t.id)}
                        className={clsx("flex items-center gap-2.5 w-full px-3 py-2 text-xs font-mono rounded-lg transition-colors text-left",
                          isActive
                            ? "bg-indigo-600/20 text-indigo-400 border border-indigo-500/30"
                            : "text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-transparent"
                        )}>
                        {t.icon}{t.label}
                      </button>
                    );
                  } else {
                    const a = item as typeof ANALYSIS_ITEMS[0];
                    const isActive = (a.id === "analytics" && isAnalyticsRoute) || (a.id === "hypothesis" && isHypothesisRoute);
                    return (
                      <button key={a.id} onClick={() => navigate(a.path)}
                        className={clsx("flex items-center gap-2.5 w-full px-3 py-2 text-xs font-mono rounded-lg transition-colors text-left",
                          isActive
                            ? "bg-indigo-600/20 text-indigo-400 border border-indigo-500/30"
                            : "text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-transparent"
                        )}>
                        {a.icon}{a.label}
                      </button>
                    );
                  }
                })}
              </nav>
            </div>
          );
        })}

        <div className="mt-auto px-4 py-3 border-t border-slate-800 space-y-2">
          <button
            onClick={() => setCopilotOpen(true)}
            className="flex items-center gap-2 w-full px-3 py-2 text-xs font-mono rounded-lg border border-emerald-600/40 bg-emerald-950/30 text-emerald-300 hover:bg-emerald-900/40"
          >
            <Bot size={13} /> Agent CoPilot
            <span className="ml-auto text-[10px] text-emerald-400/70">{WEBMCP_TOOL_COUNT} tools</span>
          </button>
          <div className="flex items-center gap-1.5 text-xs font-mono text-slate-500">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />paper mode
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/analytics" element={<AnalyticsRoute />} />
          <Route path="/hypothesis" element={<HypothesisRoute />} />
          <Route path="/hypothesis/new" element={<NewHypothesisRoute />} />
          <Route path="/signals" element={<OperationsShell opTab="signals" onNavigate={handleOpNav} />} />
          <Route path="/" element={<OperationsShell opTab={opTab} onNavigate={handleOpNav} />} />
        </Routes>
      </main>

      {/* Global Financial Engineer chat — screen-aware, right slide-over */}
      <ScreenChat screen={currentScreen} />
      {/* Agent CoPilot — WebMCP event echo + two-phase order approval */}
      <AgentCoPilot open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}

function OperationsShell({ opTab, onNavigate }: { opTab: string; onNavigate?: (tab: string) => void }) {
  return (
    <>
      {opTab === "dashboard" && <DashboardTab onNavigate={onNavigate} />}
      {opTab === "graph"     && <GraphTab />}
      {opTab === "signals"   && <SignalsTab />}
      {opTab === "options"   && <OptionsTab />}
      {opTab === "risk"      && <RiskWorkspaceTab />}
      {opTab === "backtest"  && <BacktestWorkspaceTab />}
      {opTab === "intelligence" && <IntelligenceTab />}
    </>
  );
}

function AnalyticsRoute() {
  return (
    <div className="h-full overflow-y-auto p-3">
      <AnalyticsPanel />
    </div>
  );
}

function HypothesisRoute() {
  return (
    <div className="h-full overflow-y-auto p-3">
      <HypothesisBoard />
    </div>
  );
}

function NewHypothesisRoute() {
  return (
    <div className="h-full overflow-y-auto p-3">
      <HypothesisBoard initialMode="create" />
    </div>
  );
}

function DashboardTab({ onNavigate }: { onNavigate?: (tab: string) => void }) {
  return (
    <div className="h-full grid grid-cols-[340px_1fr] gap-3 p-3 overflow-hidden">
      <div className="flex flex-col gap-3 overflow-y-auto min-h-0">
        <RegimePanel />
        <ContradictionsPanel />
        <div className="flex-1 min-h-[240px]"><AgentLog /></div>
      </div>
      <div className="flex flex-col gap-3 overflow-y-auto min-h-0">
        <div className="shrink-0"><AlpacaPanel onNavigate={onNavigate} /></div>
        <div className="shrink-0"><OptionPnlPanel /></div>
        <div className="shrink-0"><PnLDashboard /></div>
        <div className="flex-1 min-h-[200px]"><DashboardGraph /></div>
      </div>
    </div>
  );
}

function DashboardGraph() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef     = useRef<Sigma | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    Promise.all([agentApi.graphNodes("Strategy", 80), agentApi.graphEdges(200)])
      .then(([nodes, edges]) => {
        const g = new Graph({ multi: false, type: "directed" });
        nodes.forEach(n => {
          if (!g.hasNode(String(n.id))) {
            g.addNode(String(n.id), {
              label: String(n.properties.name ?? n.id), size: 10,
              color: LABEL_COLOR[n.labels[0]] ?? "#94a3b8",
              x: Math.random() * 10, y: Math.random() * 10,
            });
          }
        });
        edges.forEach(e => {
          const s = String(e.source), t = String(e.target);
          if (g.hasNode(s) && g.hasNode(t) && !g.hasEdge(s, t)) {
            g.addEdge(s, t, { size: 1, color: "#334155", type: "arrow" });
          }
        });
        if (g.order > 0) forceAtlas2.assign(g, { iterations: 100, settings: forceAtlas2.inferSettings(g) });
        if (sigmaRef.current) sigmaRef.current.kill();
        sigmaRef.current = new Sigma(g, containerRef.current!, {
          renderEdgeLabels: false, defaultNodeColor: "#94a3b8",
          labelColor: { color: "#cbd5e1" }, labelSize: 11,
        });
      }).catch(() => null);
    return () => { sigmaRef.current?.kill(); };
  }, []);

  return (
    <div className="h-full rounded-xl border border-slate-700 overflow-hidden bg-slate-950 relative"
         data-series-id="strategy-graph" data-series-name="Strategy Graph" data-series-source="neo4j">
      <div className="absolute top-2 left-3 text-[10px] font-mono text-slate-500 z-10">Strategy Graph</div>
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  KG Explorer Tab — with embedded Cypher Console + 5 interactive modals
// ═══════════════════════════════════════════════════════════════════════════════
function GraphTab() {
  const [summary, setSummary] = useState<{ total_nodes: number; total_edges: number; by_label: Record<string, number>; formula_coverage_pct: number; orphaned_nodes: number; strategies_without_concepts: number } | null>(null);
  const [gaps, setGaps] = useState<{ orphaned_nodes: { labels: string[]; name: string; cnt: number }[]; uncovered_strategies: { name: string; asset_class: string }[]; sparse_regimes: { regime: string; strategy_count: number }[] } | null>(null);
  const [importance, setImportance] = useState<{ name: string; centrality: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [graphKey, setGraphKey] = useState(0);

  // Modal/panel state
  const [showConsole, setShowConsole] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [contraOpen, setContraOpen] = useState(false);
  const [simOpen, setSimOpen] = useState(false);
  const [lineageOpen, setLineageOpen] = useState(false);
  const [recsOpen, setRecsOpen] = useState(false);

  useEffect(() => {
    Promise.all([
      researchApi.graphSummary(),
      researchApi.graphGaps(),
      researchApi.graphImportance("degree", 10),
    ]).then(([s, g, i]) => {
      setSummary(s as typeof summary);
      setGaps(g as typeof gaps);
      setImportance(i);
    }).catch(() => null).finally(() => setLoading(false));
  }, []);

  const refreshGraph = () => setGraphKey(k => k + 1);

  const actions = [
    { icon: <Terminal size={14} />, label: "Query",    onClick: () => setShowConsole(!showConsole), active: showConsole, color: "text-emerald-400" },
    { icon: <Edit3 size={14} />,    label: "Edit",     onClick: () => setEditOpen(true),             active: false,        color: "text-blue-400" },
    { icon: <Zap size={14} />,      label: "Simulate", onClick: () => setSimOpen(true),              active: false,        color: "text-amber-400" },
    { icon: <Search size={14} />,   label: "Lineage",  onClick: () => setLineageOpen(true),          active: false,        color: "text-purple-400" },
    { icon: <Shield size={14} />,   label: "Conflicts",onClick: () => setContraOpen(true),           active: false,        color: "text-red-400" },
    { icon: <Lightbulb size={14} />,label: "Fix KG",   onClick: () => setRecsOpen(true),             active: false,        color: "text-yellow-400" },
  ];

  return (
    <>
      <div className="h-full flex flex-col">
        <div className="flex-1 flex gap-3 p-3 min-h-0">
          {/* Left sidebar — KG Summary + action buttons */}
          <div className="w-72 shrink-0 flex flex-col gap-3 overflow-y-auto">
            {/* KG Summary */}
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-3 space-y-2">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">KG Summary</div>
              {loading ? (
                <div className="text-xs text-slate-500 animate-pulse">Loading...</div>
              ) : summary ? (
                <div className="grid grid-cols-2 gap-2">
                  <StatBox label="Nodes" value={String(summary.total_nodes)} />
                  <StatBox label="Edges" value={String(summary.total_edges)} />
                  <StatBox label="Coverage" value={`${(summary.formula_coverage_pct * 100).toFixed(0)}%`} />
                  <StatBox label="Orphans" value={String(summary.orphaned_nodes)} color="text-amber-400" />
                </div>
              ) : null}
              {summary && Object.keys(summary.by_label).length > 0 && (
                <div className="space-y-1 pt-1 border-t border-slate-700">
                  {Object.entries(summary.by_label).sort((a, b) => b[1] - a[1]).map(([label, count]) => (
                    <div key={label} className="flex justify-between text-xs font-mono">
                      <span className="text-slate-400">{label}</span>
                      <span className="text-slate-200">{count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-3 space-y-2">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Actions</div>
              <div className="grid grid-cols-2 gap-1.5">
                {actions.map(a => (
                  <button key={a.label} onClick={a.onClick}
                    className={clsx(
                      "flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-mono transition-colors border",
                      a.active
                        ? "bg-emerald-600/20 border-emerald-500/30 text-emerald-400"
                        : "bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-700"
                    )}>
                    {a.icon}
                    {a.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Gaps */}
            {gaps && (gaps.uncovered_strategies.length > 0 || gaps.sparse_regimes.length > 0) && (
              <div className="rounded-xl border border-amber-800/50 bg-amber-950/20 p-3 space-y-2">
                <div className="text-[10px] text-amber-400 uppercase tracking-wider font-semibold">⚠ Gaps</div>
                {gaps.uncovered_strategies.length > 0 && <div className="text-xs text-amber-300">{gaps.uncovered_strategies.length} strategies without concepts</div>}
                {gaps.sparse_regimes.length > 0 && <div className="text-xs text-amber-300">{gaps.sparse_regimes.length} regimes with {'<'}2 strategies</div>}
              </div>
            )}

            {/* Top concepts */}
            {importance.length > 0 && (
              <div className="rounded-xl border border-slate-700 bg-slate-900 p-3 space-y-2">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Top Concepts</div>
                {importance.slice(0, 8).map((c, i) => (
                  <div key={c.name} className="flex items-center gap-2 text-xs font-mono">
                    <span className="text-slate-600 w-4">{i + 1}.</span>
                    <span className="text-slate-300 flex-1 truncate">{c.name}</span>
                    <span className="text-indigo-400">{c.centrality}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Graph Canvas */}
          <div className="flex-1 min-h-0" key={graphKey} data-series-id="kg-explorer" data-series-name="KG Explorer" data-series-source="neo4j">
            <GraphCanvas />
          </div>
        </div>

        {/* Cypher Console — collapsible bottom drawer */}
        {showConsole && (
          <div className="h-1/2 border-t border-slate-700 shrink-0 flex flex-col bg-slate-900">
            <button onClick={() => setShowConsole(false)}
              className="flex items-center gap-1 px-3 py-1 text-[10px] text-slate-500 hover:text-slate-300 bg-slate-800 border-b border-slate-700">
              <ChevronDown size={12} /> Close Console
            </button>
            <div className="flex-1 min-h-0 overflow-hidden">
              <CypherConsole />
            </div>
          </div>
        )}
        {!showConsole && (
          <button onClick={() => setShowConsole(true)}
            className="flex items-center justify-center gap-1 py-1 text-[10px] text-slate-500 hover:text-slate-300 bg-slate-900 border-t border-slate-800">
            <ChevronUp size={12} /> Open Cypher Console
          </button>
        )}
      </div>

      {/* Modals */}
      <KGEditModal open={editOpen} onClose={() => setEditOpen(false)} onSuccess={refreshGraph} />
      <ContradictionManager open={contraOpen} onClose={() => setContraOpen(false)} />
      <SimulateModal open={simOpen} onClose={() => setSimOpen(false)} />
      <SignalLineageModal open={lineageOpen} onClose={() => setLineageOpen(false)} />
      <RecommendationsPanel open={recsOpen} onClose={() => setRecsOpen(false)} />
    </>
  );
}

function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-slate-800 rounded-lg p-2 text-center border border-slate-700">
      <div className="text-[10px] text-slate-500 uppercase">{label}</div>
      <div className={`text-sm font-bold font-mono ${color ?? "text-slate-100"}`}>{value}</div>
    </div>
  );
}

function SignalsTab() {
  return <div className="h-full p-3" data-series-id="signals-tab" data-series-name="Signals" data-series-source="postgres"><SignalsTable /></div>;
}

function OptionsTab() {
  return <OptionsPanel />;
}

function RiskWorkspaceTab() {
  return (
    <div className="h-full overflow-hidden">
      <RiskWorkspace />
    </div>
  );
}

function BacktestWorkspaceTab() {
  return <div className="h-full overflow-hidden"><BacktestWorkspace /></div>;
}

function IntelligenceTab() {
  return <div className="h-full overflow-y-auto"><IntelligencePanel /></div>;
}