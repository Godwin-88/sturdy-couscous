import { useState } from "react";
import clsx from "clsx";
import { Activity, GitBranch, BarChart2, Table2, Radio, ShieldAlert, Brain } from "lucide-react";

import RegimePanel         from "@/components/RegimePanel";
import PnLDashboard        from "@/components/PnLDashboard";
import AgentLog            from "@/components/AgentLog";
import GraphCanvas         from "@/components/GraphCanvas";
import SignalsTable        from "@/components/SignalsTable";
import BacktestPanel       from "@/components/BacktestPanel";
import ContradictionsPanel from "@/components/ContradictionsPanel";
import RiskPanel           from "@/components/RiskPanel";
import IntelligencePanel   from "@/components/IntelligencePanel";

type Tab = "dashboard" | "graph" | "signals" | "backtest" | "risk" | "intelligence";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "dashboard", label: "Dashboard",  icon: <Activity    size={14} /> },
  { id: "graph",     label: "KG Explorer",icon: <GitBranch   size={14} /> },
  { id: "signals",   label: "Signals",    icon: <Table2      size={14} /> },
  { id: "risk",      label: "Risk",       icon: <ShieldAlert size={14} /> },
  { id: "backtest",      label: "Backtest",     icon: <BarChart2   size={14} /> },
  { id: "intelligence",  label: "Intelligence", icon: <Brain       size={14} /> },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("dashboard");

  return (
    <div className="flex flex-col h-screen bg-slate-950 overflow-hidden">
      {/* ── Top nav ─────────────────────────────────────────────────────────── */}
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

        {/* Tabs */}
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={clsx(
              "flex items-center gap-1.5 px-4 py-3 text-xs font-mono font-medium",
              "border-b-2 transition-colors -mb-px",
              tab === t.id
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            )}
          >
            {t.icon}{t.label}
          </button>
        ))}

        {/* Right: live indicator */}
        <div className="ml-auto flex items-center gap-1.5 text-xs font-mono text-slate-500">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          paper mode
        </div>
      </header>

      {/* ── Tab content ──────────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-hidden">
        {tab === "dashboard" && <DashboardTab />}
        {tab === "graph"     && <GraphTab />}
        {tab === "signals"   && <SignalsTab />}
        {tab === "risk"         && <RiskTab />}
        {tab === "backtest"     && <BacktestTab />}
        {tab === "intelligence" && <IntelligenceTab />}
      </main>
    </div>
  );
}

// ── Dashboard ──────────────────────────────────────────────────────────────────
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

// Lightweight graph shown on dashboard (Strategies only)
import { useEffect, useRef } from "react";
import Sigma from "sigma";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { agentApi } from "@/lib/api";
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
    <div className="h-full rounded-xl border border-slate-700 overflow-hidden bg-slate-950 relative">
      <div className="absolute top-2 left-3 text-[10px] font-mono text-slate-500 z-10">
        Strategy Graph
      </div>
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
}

// ── Full Graph tab ─────────────────────────────────────────────────────────────
function GraphTab() {
  return (
    <div className="h-full p-3">
      <GraphCanvas />
    </div>
  );
}

// ── Signals tab ────────────────────────────────────────────────────────────────
function SignalsTab() {
  return (
    <div className="h-full p-3">
      <SignalsTable />
    </div>
  );
}

// ── Risk tab ───────────────────────────────────────────────────────────────────
function RiskTab() {
  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="max-w-2xl mx-auto">
        <RiskPanel />
      </div>
    </div>
  );
}

// ── Backtest tab ───────────────────────────────────────────────────────────────
function BacktestTab() {
  return (
    <div className="h-full overflow-y-auto p-3">
      <BacktestPanel />
    </div>
  );
}

// ── Intelligence tab ──────────────────────────────────────────────────────────
function IntelligenceTab() {
  return (
    <div className="h-full overflow-y-auto">
      <IntelligencePanel />
    </div>
  );
}
