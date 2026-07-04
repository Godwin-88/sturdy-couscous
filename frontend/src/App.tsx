import { useState, useRef } from "react";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import clsx from "clsx";
import {
  Activity, GitBranch, BarChart2, Table2, Radio, ShieldAlert, Brain,
  FlaskConical, LayoutDashboard,
} from "lucide-react";

import RegimePanel         from "@/components/RegimePanel";
import PnLDashboard        from "@/components/PnLDashboard";
import AgentLog            from "@/components/AgentLog";
import GraphCanvas         from "@/components/GraphCanvas";
import SignalsTable        from "@/components/SignalsTable";
import BacktestPanel       from "@/components/BacktestPanel";
import ContradictionsPanel from "@/components/ContradictionsPanel";
import RiskPanel           from "@/components/RiskPanel";
import IntelligencePanel   from "@/components/IntelligencePanel";
import AnalyticsPanel      from "@/components/AnalyticsPanel";
import ContextMenu, { type ContextMenuSeries } from "@/components/ContextMenu";
import HypothesisBoard     from "@/components/HypothesisBoard";
import { hypothesisApi }   from "@/lib/api";

type Tab = "dashboard" | "graph" | "signals" | "backtest" | "risk" | "intelligence";

const OP_TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "dashboard",   label: "Dashboard",     icon: <LayoutDashboard size={14} /> },
  { id: "graph",       label: "KG Explorer",   icon: <GitBranch       size={14} /> },
  { id: "signals",     label: "Signals",       icon: <Table2          size={14} /> },
  { id: "risk",        label: "Risk",          icon: <ShieldAlert     size={14} /> },
  { id: "backtest",    label: "Backtest",      icon: <BarChart2       size={14} /> },
  { id: "intelligence",label: "Intelligence",  icon: <Brain           size={14} /> },
];

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [opTab, setOpTab] = useState<Tab>("dashboard");
  const appRef = useRef<HTMLDivElement>(null);

  const isAnalyticsRoute = location.pathname.startsWith("/analytics");
  const isHypothesisRoute = location.pathname.startsWith("/hypothesis");

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

  return (
    <div ref={appRef} className="flex flex-col h-screen bg-slate-950 overflow-hidden">
      {/* ── Context menu (global, attached to app container) ─────────────── */}
      <ContextMenu
        containerRef={appRef}
        onCreateHypothesis={handleCreateHypothesis}
        onPinToHypothesis={handlePinToHypothesis}
        onAnalyze={(series) => {
          navigate(`/analytics?series=${encodeURIComponent(series.id)}&start=${series.startDate || ""}&end=${series.endDate || ""}`);
        }}
      />

      {/* ── Top nav ─────────────────────────────────────────────────────── */}
      <header className="flex items-center gap-0 border-b border-slate-800 bg-slate-900 shrink-0 px-4">
        {/* Brand */}
        <div className="flex items-center gap-2 pr-6 py-3 border-r border-slate-800 mr-2">
          <div className="w-6 h-6 rounded bg-indigo-600 flex items-center justify-center">
            <Radio size={12} className="text-white" />
          </div>
          <span className="text-sm font-bold text-slate-100 font-mono tracking-tight">
            Graph<span className="text-indigo-400">Alpha</span>
          </span>
        </div>

        {/* Operations tabs */}
        {!isAnalyticsRoute && !isHypothesisRoute && OP_TABS.map(t => (
          <button
            key={t.id}
            onClick={() => { setOpTab(t.id); navigate("/"); }}
            className={clsx(
              "flex items-center gap-1.5 px-4 py-3 text-xs font-mono font-medium",
              "border-b-2 transition-colors -mb-px",
              opTab === t.id && !isAnalyticsRoute && !isHypothesisRoute
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            )}
          >
            {t.icon}{t.label}
          </button>
        ))}

        {/* Analytics Workspace nav (separate section) */}
        <div className="flex items-center ml-2 pl-3 border-l border-slate-700 gap-1">
          <button
            onClick={() => navigate("/analytics")}
            className={clsx(
              "flex items-center gap-1.5 px-3 py-2 text-xs font-mono font-medium rounded-lg",
              "transition-colors",
              isAnalyticsRoute
                ? "bg-indigo-600/20 text-indigo-400 border border-indigo-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            )}
          >
            <FlaskConical size={13} />
            Analytics
          </button>

          <button
            onClick={() => navigate("/hypothesis")}
            className={clsx(
              "flex items-center gap-1.5 px-3 py-2 text-xs font-mono font-medium rounded-lg",
              "transition-colors",
              isHypothesisRoute
                ? "bg-purple-600/20 text-purple-400 border border-purple-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            )}
          >
            <Brain size={13} />
            Hypotheses
          </button>
        </div>

        {/* Right: live indicator */}
        <div className="ml-auto flex items-center gap-1.5 text-xs font-mono text-slate-500">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          paper mode
        </div>
      </header>

      {/* ── Route content ────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/analytics" element={<AnalyticsRoute />} />
          <Route path="/hypothesis" element={<HypothesisRoute />} />
          <Route path="/hypothesis/new" element={<NewHypothesisRoute />} />
          <Route path="/" element={<OperationsShell opTab={opTab} />} />
        </Routes>
      </main>
    </div>
  );
}

// ── Operations Shell (existing dashboard layout) ────────────────────────────
function OperationsShell({ opTab }: { opTab: string }) {
  return (
    <>
      {opTab === "dashboard" && <DashboardTab />}
      {opTab === "graph"     && <GraphTab />}
      {opTab === "signals"   && <SignalsTab />}
      {opTab === "risk"      && <RiskTab />}
      {opTab === "backtest"  && <BacktestTab />}
      {opTab === "intelligence" && <IntelligenceTab />}
    </>
  );
}

// ── Analytics Workspace Route ──────────────────────────────────────────────
function AnalyticsRoute() {
  return (
    <div className="h-full overflow-y-auto p-3">
      <AnalyticsPanel />
    </div>
  );
}

// ── Hypothesis Board Route ────────────────────────────────────────────────
function HypothesisRoute() {
  return (
    <div className="h-full overflow-y-auto p-3">
      <HypothesisBoard />
    </div>
  );
}

// ── New Hypothesis Route ──────────────────────────────────────────────────
function NewHypothesisRoute() {
  return (
    <div className="h-full overflow-y-auto p-3">
      <HypothesisBoard initialMode="create" />
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────
function DashboardTab() {
  return (
    <div className="h-full grid grid-cols-[340px_1fr] gap-3 p-3 overflow-hidden">
      {/* Left column */}
      <div className="flex flex-col gap-3 overflow-y-auto min-h-0">
        <RegimePanel />
        <ContradictionsPanel />
        <div className="flex-1 min-h-[240px]">
          <AgentLog />
        </div>
      </div>

      {/* Right column */}
      <div className="flex flex-col gap-3 overflow-hidden min-h-0">
        <PnLDashboard />
        <div className="flex-1 min-h-0">
          <DashboardGraph />
        </div>
      </div>
    </div>
  );
}

// ── Lightweight graph on dashboard ────────────────────────────────────────
import { useEffect } from "react";
import Sigma from "sigma";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { agentApi, researchApi } from "@/lib/api";
import { LABEL_COLOR } from "@/lib/utils";

function DashboardGraph() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef     = useRef<Sigma | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    Promise.all([
      agentApi.graphNodes("Strategy", 80),
      agentApi.graphEdges(200),
    ]).then(([nodes, edges]) => {
      const g = new Graph({ multi: false, type: "directed" });
      nodes.forEach(n => {
        if (!g.hasNode(String(n.id))) {
          g.addNode(String(n.id), {
            label: String(n.properties.name ?? n.id),
            size:  10,
            color: LABEL_COLOR[n.labels[0]] ?? "#94a3b8",
            x: Math.random() * 10,
            y: Math.random() * 10,
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

      if (sigmaRef.current) { sigmaRef.current.kill(); }
      sigmaRef.current = new Sigma(g, containerRef.current!, {
        renderEdgeLabels: false,
        defaultNodeColor: "#94a3b8",
        labelColor:       { color: "#cbd5e1" },
        labelSize:        11,
      });
    }).catch(() => null);

    return () => { sigmaRef.current?.kill(); };
  }, []);

  return (
    <div className="h-full rounded-xl border border-slate-700 overflow-hidden bg-slate-950 relative"
         data-series-id="strategy-graph" data-series-name="Strategy Graph" data-series-source="neo4j">
      <div className="absolute top-2 left-3 text-[10px] font-mono text-slate-500 z-10">
        Strategy Graph
      </div>
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
}

// ── Full Graph tab ────────────────────────────────────────────────────────
function GraphTab() {
  const [summary, setSummary] = useState<{ total_nodes: number; total_edges: number; by_label: Record<string, number>; formula_coverage_pct: number; orphaned_nodes: number; strategies_without_concepts: number } | null>(null);
  const [gaps, setGaps] = useState<{ orphaned_nodes: { labels: string[]; name: string; cnt: number }[]; uncovered_strategies: { name: string; asset_class: string }[]; sparse_regimes: { regime: string; strategy_count: number }[] } | null>(null);
  const [importance, setImportance] = useState<{ name: string; centrality: number }[]>([]);
  const [loading, setLoading] = useState(true);

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

  return (
    <div className="h-full flex gap-3 p-3">
      <div className="w-72 shrink-0 flex flex-col gap-3 overflow-y-auto">
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

        {gaps && (gaps.uncovered_strategies.length > 0 || gaps.sparse_regimes.length > 0) && (
          <div className="rounded-xl border border-amber-800/50 bg-amber-950/20 p-3 space-y-2">
            <div className="text-[10px] text-amber-400 uppercase tracking-wider font-semibold">⚠ Gaps</div>
            {gaps.uncovered_strategies.length > 0 && (
              <div className="text-xs text-amber-300">
                {gaps.uncovered_strategies.length} strategies without concepts
              </div>
            )}
              {gaps.sparse_regimes.length > 0 && (
              <div className="text-xs text-amber-300">
                {gaps.sparse_regimes.length} regimes with {'<'}2 strategies
              </div>
            )}
          </div>
        )}

        {importance.length > 0 && (
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-3 space-y-2">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Top Concepts (degree)</div>
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

      <div className="flex-1 min-h-0" data-series-id="kg-explorer" data-series-name="KG Explorer" data-series-source="neo4j">
        <GraphCanvas />
      </div>
    </div>
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

// ── Signals tab ───────────────────────────────────────────────────────────
function SignalsTab() {
  return (
    <div className="h-full p-3" data-series-id="signals-tab" data-series-name="Signals" data-series-source="postgres">
      <SignalsTable />
    </div>
  );
}

// ── Risk tab ──────────────────────────────────────────────────────────────
function RiskTab() {
  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="max-w-2xl mx-auto">
        <RiskPanel />
      </div>
    </div>
  );
}

// ── Backtest tab ──────────────────────────────────────────────────────────
function BacktestTab() {
  return (
    <div className="h-full overflow-y-auto p-3">
      <BacktestPanel />
    </div>
  );
}

// ── Intelligence tab ─────────────────────────────────────────────────────
function IntelligenceTab() {
  return (
    <div className="h-full overflow-y-auto">
      <IntelligencePanel />
    </div>
  );
}