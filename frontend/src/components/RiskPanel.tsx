import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { agentApi, RiskMetrics } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { ShieldAlert, TrendingDown, Percent } from "lucide-react";
import { fmt$, fmtPct } from "@/lib/utils";
import clsx from "clsx";

export default function RiskPanel() {
  const { data, loading } = usePolling<RiskMetrics>(agentApi.risk, 15_000);

  if (loading || !data) return <Skeleton />;

  const ddPct      = data.drawdown_current / (data.drawdown_limit || 1);
  const ddColor    = ddPct > 0.8 ? "#ef4444" : ddPct > 0.5 ? "#f59e0b" : "#10b981";
  const kellyCapped = Math.min(data.kelly_fraction ?? 0, 1);

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <ShieldAlert size={14} className="text-indigo-400" />
        <span className="text-sm font-semibold text-slate-200">Risk Dashboard</span>
        {data.halted && (
          <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-red-900 text-red-300 font-mono font-bold animate-pulse">
            HALTED
          </span>
        )}
      </div>

      {/* Exposure row */}
      <div className="grid grid-cols-2 gap-3">
        <MetricBox
          label="Gross Exposure"
          value={fmt$(data.gross_exposure)}
          sub={fmtPct(data.gross_pct_nav) + " of NAV"}
          warn={data.gross_pct_nav > 1.5}
        />
        <MetricBox
          label="Net Exposure"
          value={fmt$(data.net_exposure)}
          sub={fmtPct(data.net_pct_nav) + " of NAV"}
          neutral
        />
      </div>

      {/* Drawdown gauge */}
      <div>
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-slate-400 flex items-center gap-1">
            <TrendingDown size={11} /> Drawdown
          </span>
          <span className="font-mono" style={{ color: ddColor }}>
            {fmtPct(data.drawdown_current)} / {fmtPct(data.drawdown_limit)} limit
          </span>
        </div>
        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${Math.min(ddPct * 100, 100)}%`, background: ddColor }}
          />
        </div>
        <div className="text-[10px] text-slate-500 mt-0.5 text-right font-mono">
          {fmtPct(data.drawdown_remaining)} remaining
        </div>
      </div>

      {/* Kelly fraction */}
      {data.kelly_fraction !== null && (
        <div>
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-slate-400 flex items-center gap-1">
              <Percent size={11} /> Kelly Fraction (7d)
            </span>
            <span className="font-mono text-purple-300">{fmtPct(data.kelly_fraction)}</span>
          </div>
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-purple-500 transition-all duration-500"
              style={{ width: `${Math.min(kellyCapped * 100, 100)}%` }}
            />
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            Optimal position size based on recent win rate
          </div>
        </div>
      )}

      {/* Concentration bar chart */}
      {data.concentration.length > 0 && (
        <div>
          <div className="text-xs text-slate-400 mb-2">Position Concentration (% NAV)</div>
          <ResponsiveContainer width="100%" height={Math.max(60, data.concentration.length * 28)}>
            <BarChart
              layout="vertical"
              data={data.concentration}
              margin={{ top: 0, right: 40, bottom: 0, left: 60 }}
            >
              <XAxis type="number" tick={{ fontSize: 9, fill: "#64748b" }}
                     tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
              <YAxis type="category" dataKey="ticker" tick={{ fontSize: 10, fill: "#cbd5e1" }} width={55} />
              <Tooltip
                contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                formatter={(v: number, _: string, entry: { payload?: { direction?: string; pnl?: number } }) => [
                  `${fmtPct(v)} · P&L: ${fmt$(entry.payload?.pnl ?? 0)}`,
                  entry.payload?.direction === "buy" ? "LONG" : "SHORT",
                ]}
              />
              <Bar dataKey="pct_nav" radius={[0, 3, 3, 0]}>
                {data.concentration.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={entry.direction === "buy" ? "#6366f1" : "#f43f5e"}
                  />
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
  );
}

function MetricBox({
  label, value, sub, warn, neutral,
}: {
  label: string; value: string; sub?: string; warn?: boolean; neutral?: boolean;
}) {
  return (
    <div className="bg-slate-800/60 rounded-lg p-2.5">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={clsx(
        "text-base font-mono font-bold mt-0.5",
        warn ? "text-red-400" : neutral ? "text-slate-200" : "text-slate-100"
      )}>
        {value}
      </div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}

function Skeleton() {
  return <div className="rounded-xl border border-slate-700 bg-slate-800 h-48 animate-pulse" />;
}
