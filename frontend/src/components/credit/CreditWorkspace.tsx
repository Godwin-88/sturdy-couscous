/**
 * CreditWorkspace.tsx
 * ───────────────────
 * CreditGraph (P10) as a menu item inside GraphAlpha.
 *
 * A faithful port of the /attest frontend App.tsx shell — header with live
 * API/Neo4j/Redis status, 7-tab sidebar (Credit Dashboard, Risk Graph,
 * Quantitative Risk, Evidence, Chat, Portfolio, Governance) — wrapped in a
 * `.credit-workspace` scope so its styles (credit.css) cannot collide with
 * GraphAlpha's design system. Read-only surfaces; execution stays behind the
 * human-approved decision flow of /api/v1/risk/*.
 */

import { useEffect, useState } from "react";
import { api } from "../../lib/creditApi";
import type { DbStatus, HealthResponse } from "../../types/credit";
import CreditDashboard from "./CreditDashboard";
import RiskGraph from "./RiskGraph";
import QuantTab from "./StressTab";
import ChatTab from "./ChatTab";
import EvidenceTab from "./EvidenceTab";
import PortfolioTab from "./PortfolioTab";
import GovernanceTab from "./GovernanceTab";
import { ToastContainer } from "./Toast";
import "./credit.css";

type TabId = "dashboard" | "graph" | "quant" | "evidence" | "chat" | "portfolio" | "governance";

const TABS: { id: TabId; label: string }[] = [
  { id: "dashboard", label: "Credit Dashboard" },
  { id: "graph", label: "Risk Graph" },
  { id: "quant", label: "Quantitative Risk" },
  { id: "evidence", label: "Evidence" },
  { id: "chat", label: "Chat" },
  { id: "portfolio", label: "Portfolio" },
  { id: "governance", label: "Governance" },
];

export default function CreditWorkspace() {
  const [tab, setTab] = useState<TabId>("dashboard");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [db, setDb] = useState<DbStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const [h, d] = await Promise.all([api.health(), api.db()]);
        setHealth(h);
        setDb(d);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
      }
    };
    load();
  }, []);

  return (
    <div className="credit-workspace">
      <ToastContainer />
      <header className="app-header">
        <div>
          <h1>CreditGraph</h1>
          <p className="tagline">
            Verifiable cross-chain credit intelligence &amp; risk decisioning
          </p>
        </div>
        <div className="status-grid">
          <span className="status-item">
            <span className="dot" data-ok={health?.status === "ok"} /> API
          </span>
          <span className="status-item">
            <span className="dot" data-ok={db?.neo4j === "ok"} /> Neo4j
          </span>
          <span className="status-item">
            <span className="dot" data-ok={db?.redis === "ok"} /> Redis
          </span>
        </div>
      </header>

      {error && <p className="error">Backend unreachable: {error}</p>}

      <button
        className="mobile-menu-btn"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        aria-label={sidebarOpen ? "Close menu" : "Open menu"}
        aria-expanded={sidebarOpen}
      >
        {sidebarOpen ? "✕" : "☰"}
      </button>

      {sidebarOpen && (
        <div
          className="sidebar-overlay open"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <div className="layout">
        <nav
          className={`sidebar ${sidebarOpen ? "open" : ""}`}
          role="tablist"
          aria-label="CreditGraph navigation"
        >
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              aria-controls={`credit-panel-${t.id}`}
              className={`sidebar-tab ${tab === t.id ? "active" : ""}`}
              onClick={() => {
                setTab(t.id);
                setSidebarOpen(false);
              }}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <main
          className="tab-body"
          role="tabpanel"
          id={`credit-panel-${tab}`}
          aria-labelledby={`credit-tab-${tab}`}
        >
          {tab === "dashboard" && <CreditDashboard />}
          {tab === "graph" && <RiskGraph />}
          {tab === "quant" && <QuantTab />}
          {tab === "evidence" && <EvidenceTab />}
          {tab === "chat" && <ChatTab />}
          {tab === "portfolio" && <PortfolioTab />}
          {tab === "governance" && <GovernanceTab />}
        </main>
      </div>

      <footer>
        <p>CreditGraph × GraphAlpha • Deterministic risk core + GraphRAG + Attestcoin evidence + Creditcoin execution</p>
      </footer>
    </div>
  );
}