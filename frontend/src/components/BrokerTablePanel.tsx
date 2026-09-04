import { Wallet, HelpCircle, ShieldAlert, ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import BrokerTable from "@/components/BrokerTable";

/** Dashboard broker card: header + shared table, with links to Risk and Analytics. */
export default function BrokerTablePanel({ onNavigate }: { onNavigate?: (tab: string) => void } = {}) {
  const navigate = useNavigate();

  const goRisk = () => {
    if (onNavigate) { onNavigate("risk"); return; }
    window.location.hash = "#/risk";
  };

  const goAnalyzePortfolio = () => {
    navigate("/analytics");
  };

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
        <Wallet size={14} className="text-indigo-400" />
        <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Broker Positions</span>
        <span className="ml-auto flex items-center gap-1 text-[10px] text-slate-500 font-mono">
          <HelpCircle size={11} /> hover a column for meaning
        </span>
        <button onClick={goAnalyzePortfolio}
          title="Open the Analytics workspace with your portfolio as the analysis input"
          className="flex items-center gap-1 px-2 py-1 rounded bg-indigo-600/30 border border-indigo-500/40 text-[10px] font-bold text-indigo-300 hover:bg-indigo-600/50">
          Analyze Portfolio
        </button>
        <button onClick={goRisk}
          title="Open the Risk workspace (exposure, VaR, concentration, option book) for this broker account"
          className="flex items-center gap-1 px-2 py-1 rounded bg-rose-600/30 border border-rose-500/40 text-[10px] font-bold text-rose-300 hover:bg-rose-600/50">
          <ShieldAlert size={10} /> Risk <ArrowRight size={10} />
        </button>
      </div>
      <BrokerTable onNavigate={onNavigate} maxHeight="max-h-[320px]" />
    </div>
  );
}
