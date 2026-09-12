/**
 * CreditWorkspace.tsx
 * ───────────────────
 * Credit (P10 / BUIDL-CTC) inside GraphAlpha — a cohesive 2-tab console:
 *
 *   Fund      → FundConsole: attested-NAV → CC3 executor → credit decision →
 *               APPROVE → EXECUTE (the human-in-the-loop critical path)
 *   Evidence  → Attestcoin / NAVAnchor proof trail (verify + history)
 *
 * The financial-engineer chat lives in the GLOBAL ScreenChat slide-over
 * (screen="credit"), so this workspace carries no chat UI. Old demo-toy tabs
 * (Risk Graph / Quant / Portfolio / Governance / Chat) and the standalone
 * credit.css chrome are removed for uniformity with GraphAlpha's design system.
 */
import { useState } from "react";
import type { ReactNode } from "react";
import clsx from "clsx";
import { Landmark, ShieldCheck } from "lucide-react";
import FundConsole from "./FundConsole";
import EvidenceTab from "./EvidenceTab";

type TabId = "fund" | "evidence";

const TABS: { id: TabId; label: string; icon: ReactNode }[] = [
  { id: "fund", label: "Fund", icon: <Landmark size={13} /> },
  { id: "evidence", label: "Evidence", icon: <ShieldCheck size={13} /> },
];

export default function CreditWorkspace() {
  const [tab, setTab] = useState<TabId>("fund");

  return (
    <div className="h-full flex flex-col">
      {/* Tab bar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-800">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            aria-selected={tab === t.id}
            className={clsx(
              "inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded transition-colors",
              tab === t.id
                ? "bg-brand-500/15 text-brand-200 border border-brand-500/30"
                : "text-gray-400 border border-transparent hover:text-white"
            )}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
        <span className="ml-auto text-[10px] text-gray-600 font-mono">
          credit · attested-nav financing · human-gated execution
        </span>
      </div>

      {/* Tab body */}
      <div className="flex-1 overflow-y-auto">
        {tab === "fund" && <FundConsole />}
        {tab === "evidence" && <EvidenceTab borrowerId="fund_graphalpha" />}
      </div>
    </div>
  );
}