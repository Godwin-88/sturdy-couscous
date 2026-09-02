import { Wallet, TrendingUp, TrendingDown, ShieldCheck } from "lucide-react";
import { optionsApi, OptionPnl } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmt$, fmtN } from "@/lib/utils";
import clsx from "clsx";

/**
 * Options P&L tile — premium income vs hedge cost, mark-to-market, hedge sleeve.
 * Mounted in the Dashboard (MONITORING) so the user always sees the true
 * paper-options economics: income collected, debit paid, MTM, and the delta-hedge
 * sleeve. Polls every 10s.
 */
export default function OptionPnlPanel({ underlying = "SPY" }: { underlying?: string }) {
  const { data, error, loading } = usePolling<{ option_pnl: OptionPnl }>(
    () => optionsApi.pnl(underlying),
    10_000,
  );
  const pnl = data?.option_pnl;

  if (error) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-3">
        <div className="text-xs text-slate-400">Options P&amp;L</div>
        <div className="text-xs text-red-400 bg-red-950/30 border border-red-800 rounded p-2 mt-2">
          {error}
        </div>
      </div>
    );
  }
  if (loading || !pnl) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-3">
        <div className="text-xs text-slate-400">Options P&amp;L</div>
        <div className="text-xs text-slate-500 mt-2">Loading…</div>
      </div>
    );
  }

  const net = pnl.net_option_pnl_usd;
  const incomeColor = pnl.net_premium_usd >= 0 ? "text-emerald-400" : "text-red-400";

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden transition-all duration-200 hover:border-slate-500 hover:shadow-lg hover:shadow-amber-500/10 hover:-translate-y-0.5 cursor-pointer">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700 bg-slate-950">
        <div className="flex items-center gap-2">
          <Wallet size={14} className="text-amber-400" />
          <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Options P&amp;L</span>
        </div>
        <span className="flex items-center gap-1 text-[10px] text-slate-500 font-mono">
          <ShieldCheck size={11} /> {pnl.underlying}
        </span>
      </div>

      <div className="p-3 space-y-3">
        {/* Net income & MTM */}
        <div className="grid grid-cols-2 gap-2">
          <Metric
            label="Net Premium"
            value={`${pnl.net_premium_usd >= 0 ? "+" : ""}${fmt$(pnl.net_premium_usd)}`}
            cls={incomeColor}
          />
          <Metric
            label="Unrealised P&L"
            value={`${pnl.unrealized_pnl_usd >= 0 ? "+" : ""}${fmt$(pnl.unrealized_pnl_usd)}`}
            cls={pnl.unrealized_pnl_usd >= 0 ? "text-emerald-400" : "text-red-400"}
          />
        </div>

        {/* Income vs cost breakdown */}
        <div className="text-[10px] text-slate-500 uppercase tracking-wider">Income vs Hedge Cost</div>
        <div className="space-y-1 text-xs font-mono">
          <Row label="Premium income (sold)" value={fmt$(pnl.premium_income_usd)} />
          <Row label="Premium cost (bought)" value={fmt$(pnl.premium_cost_usd)} />
          <Row label="Hedge sleeve MV" value={fmt$(pnl.hedge_sleeve_mv_usd)} />
          <Row label={`Contracts (${fmtN(pnl.contracts)})`} value={pnl.underlyings.length ? pnl.underlyings.join(", ") : "—"} />
        </div>

        {/* Net option P&L */}
        <div className={clsx(
          "flex items-center justify-between px-3 py-2 rounded-lg border",
          net >= 0 ? "bg-emerald-950/40 border-emerald-800" : "bg-red-950/40 border-red-800",
        )}>
          <span className="text-xs text-slate-300 font-semibold">Net Options P&amp;L</span>
          <span className={clsx("text-sm font-bold font-mono", net >= 0 ? "text-emerald-400" : "text-red-400")}>
            {net >= 0 ? "+" : ""}{fmt$(net)}
            {net >= 0 ? <TrendingUp size={12} className="inline ml-1" /> : <TrendingDown size={12} className="inline ml-1" />}
          </span>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div className="bg-slate-800 rounded-lg p-2 border border-slate-700 text-center">
      <div className="text-[10px] text-slate-500 uppercase">{label}</div>
      <div className={clsx("text-sm font-bold font-mono", cls ?? "text-slate-100")}>{value}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-200">{value}</span>
    </div>
  );
}