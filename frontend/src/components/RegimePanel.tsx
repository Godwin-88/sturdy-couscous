import { Activity, TrendingUp, CheckCircle, XCircle } from "lucide-react";
import { agentApi, AgentStatus, EligibleStrategy } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { REGIME_META, relTime, fmtPct } from "@/lib/utils";
import clsx from "clsx";

export default function RegimePanel() {
  const { data, error, loading } = usePolling<AgentStatus>(agentApi.status, 15_000);
  const { data: eligible } = usePolling<EligibleStrategy[]>(
    () => agentApi.eligibleStrategies(data?.regime ?? ""),
    30_000,
    [data?.regime]
  );

  if (loading) return <Skeleton />;
  if (error || !data) return <ErrorCard msg={error ?? "No data"} />;

  const meta = REGIME_META[data.regime] ?? {
    color: "text-slate-300", bg: "bg-slate-800 border-slate-600", desc: "Unknown",
  };

  const confWidth = `${Math.round(data.regime_confidence * 100)}%`;

  const activeSet   = new Set(data.active_strategies);
  const eligActive  = (eligible ?? []).filter(s => activeSet.has(s.name));
  const eligInactive = (eligible ?? []).filter(s => !activeSet.has(s.name));

  return (
    <div className={clsx("rounded-xl border p-4 space-y-3", meta.bg)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={14} className={meta.color} />
          <span className="text-xs text-slate-400 uppercase tracking-widest">Market Regime</span>
        </div>
        <span className="text-xs text-slate-500 font-mono">{relTime(data.last_cycle_at)}</span>
      </div>

      {/* Regime name */}
      <div>
        <div className={clsx("text-2xl font-bold font-mono", meta.color)}>{data.regime}</div>
        <div className="text-xs text-slate-400 mt-0.5">{meta.desc}</div>
      </div>

      {/* Confidence bar */}
      <div>
        <div className="flex justify-between text-xs text-slate-400 mb-1">
          <span>Confidence</span>
          <span>{fmtPct(data.regime_confidence)}</span>
        </div>
        <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
          <div
            className={clsx("h-full rounded-full transition-all duration-500",
              data.regime_confidence > 0.75 ? "bg-emerald-500" :
              data.regime_confidence > 0.55 ? "bg-yellow-500" : "bg-red-500")}
            style={{ width: confWidth }}
          />
        </div>
      </div>

      {/* Halt banner */}
      {data.halted && (
        <div className="rounded bg-red-900 border border-red-500 px-3 py-2 text-xs text-red-200 font-bold animate-pulse">
          AGENT HALTED — drawdown circuit breaker triggered
        </div>
      )}

      {/* Eligible strategies split */}
      {(eligible && eligible.length > 0) ? (
        <div className="space-y-2 pt-1 border-t border-slate-700">
          <div className="flex items-center gap-1">
            <TrendingUp size={12} className="text-slate-400" />
            <span className="text-xs text-slate-400 uppercase tracking-wider">Eligible Strategies</span>
            <span className="ml-auto text-[10px] font-mono text-slate-500">
              {eligActive.length}/{eligible.length} active
            </span>
          </div>
          <div className="grid grid-cols-2 gap-1">
            <div>
              <div className="text-[10px] text-emerald-500 font-mono mb-1 uppercase">Active</div>
              {eligActive.length === 0
                ? <div className="text-[10px] text-slate-600">none</div>
                : eligActive.map(s => (
                    <div key={s.name} className="flex items-center gap-1 py-0.5">
                      <CheckCircle size={9} className="text-emerald-400 shrink-0" />
                      <span className="text-[10px] font-mono text-emerald-300 truncate" title={s.description}>{s.name}</span>
                    </div>
                  ))
              }
            </div>
            <div>
              <div className="text-[10px] text-slate-500 font-mono mb-1 uppercase">Eligible / Inactive</div>
              {eligInactive.length === 0
                ? <div className="text-[10px] text-slate-600">none</div>
                : eligInactive.map(s => (
                    <div key={s.name} className="flex items-center gap-1 py-0.5">
                      <XCircle size={9} className="text-slate-600 shrink-0" />
                      <span className="text-[10px] font-mono text-slate-500 truncate" title={s.description}>{s.name}</span>
                    </div>
                  ))
              }
            </div>
          </div>
        </div>
      ) : (
        <div className="pt-1 border-t border-slate-700">
          <div className="flex items-center gap-1 mb-1.5">
            <TrendingUp size={12} className="text-slate-400" />
            <span className="text-xs text-slate-400 uppercase tracking-wider">Active Strategies</span>
          </div>
          {data.active_strategies.length === 0
            ? <span className="text-xs text-slate-500">None activated for this regime</span>
            : data.active_strategies.map(s => (
                <div key={s} className="text-xs font-mono text-indigo-300 py-0.5">{s}</div>
              ))
          }
        </div>
      )}

      {/* Cycle stats */}
      <div className="grid grid-cols-3 gap-2 pt-1 border-t border-slate-700">
        <Stat label="Signals" value={String(data.signals_generated)} />
        <Stat label="Approved" value={String(data.orders_approved)} />
        <Stat label="Cycle" value={`${data.cycle_duration_s.toFixed(1)}s`} />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-center">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-sm font-mono text-slate-200">{value}</div>
    </div>
  );
}

function Skeleton() {
  return <div className="rounded-xl border border-slate-700 bg-slate-800 p-4 h-48 animate-pulse" />;
}

function ErrorCard({ msg }: { msg: string }) {
  return (
    <div className="rounded-xl border border-red-800 bg-red-950 p-4 text-xs text-red-300 font-mono">
      Agent unreachable: {msg}
    </div>
  );
}
