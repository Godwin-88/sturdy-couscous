import { useState, useEffect, useCallback } from "react";
import { Activity, TrendingUp, CheckCircle, XCircle, Lightbulb, ChevronDown, ChevronRight, Filter, Zap, RefreshCw, ExternalLink, Search, Loader2 } from "lucide-react";
import { agentApi, optionsApi, AgentStatus, RegimeBenchResult, OptionSuggestion, AlpacaAsset } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { REGIME_META, fmtPct } from "@/lib/utils";
import { setScreenContext } from "@/lib/screenContext";
import clsx from "clsx";

// Catalogue mirrors agent/regime_agent.py:194-237. "auto" = use live regime.
const REGIME_CHOICES: { value: string; label: string }[] = [
  { value: "",              label: "Auto (current)" },
  { value: "Trending",      label: "Trending" },
  { value: "MeanReverting", label: "Mean Reverting" },
  { value: "LowVolatility", label: "Low Volatility" },
  { value: "HighVolatility",label: "High Volatility" },
  { value: "Recovery",      label: "Recovery" },
  { value: "Crisis",        label: "Crisis" },
  { value: "SystemicStress",label: "Systemic Stress" },
];

const LENS_CHOICES: { value: "average" | "defensive"; label: string }[] = [
  { value: "defensive", label: "Defensive (λ=3.5, cap 5%)" },
  { value: "average",   label: "Average (λ=2.25, cap 10%)" },
];

export default function RegimePanel({ onNavigate }: { onNavigate?: (tab: string) => void } = {}) {
  // Live agent regime
  const { data, error, loading } = usePolling<AgentStatus>(agentApi.status, 15_000);

  // User's regime override (UI-only, persisted server-side in Redis)
  const [override, setOverride] = useState<string>("");
  const [lens, setLens] = useState<"average" | "defensive">("defensive");
  const [strategy, setStrategy] = useState<string>("");

  // Underlying selector — defaults to SPY; user can typeahead to any Alpaca asset
  const [underlying, setUnderlying] = useState<string>("SPY");
  const [undQuery, setUndQuery] = useState<string>("");
  const [undAssets, setUndAssets] = useState<AlpacaAsset[]>([]);
  const [undSearching, setUndSearching] = useState(false);
  const [undOpen, setUndOpen] = useState(false);

  const [showAdv, setShowAdv] = useState(false);

  // Fetch current override on mount
  useEffect(() => {
    agentApi.regimeOverrideGet()
      .then(r => setOverride(r.override || ""))
      .catch(() => null);
  }, []);

  // Typeahead: search Alpaca assets when the user types
  useEffect(() => {
    const q = undQuery.trim();
    if (!q || q.length < 1) { setUndAssets([]); return; }
    let alive = true;
    setUndSearching(true);
    const t = setTimeout(() => {
      optionsApi.underlyings(q)
        .then(r => { if (alive) setUndAssets(r.assets ?? []); })
        .catch(() => { if (alive) setUndAssets([]); })
        .finally(() => { if (alive) setUndSearching(false); });
    }, 250); // debounce
    return () => { alive = false; clearTimeout(t); };
  }, [undQuery]);

  // Regime-benchmark payload. Re-polls when override/lens/strategy/underlying change.
  const benchKey = [override, lens, strategy, underlying].join("|");
  const { data: bench, error: benchErr, loading: benchLoading, refresh: refreshBench } = usePolling<RegimeBenchResult>(
    () => agentApi.regimeBench({ regime: override, lens, strategy: strategy, underlying }),
    20_000,
    [benchKey]
  );

  // Persist screen context so the FE chat anchors on the same regime/strategy
  useEffect(() => {
    setScreenContext("dashboard", {
      screen: "dashboard",
      underlying,
      extra: {
        regime: override || bench?.regime || data?.regime,
        regime_confidence: bench?.confidence ?? data?.regime_confidence ?? 0,
        strategy_filter: strategy || undefined,
        is_override: bench?.is_override,
        live_regime: bench?.live_regime,
        eligible_count: bench?.eligible_count,
        top_strategy: bench?.top_suggestion?.strategy,
      },
    });
  }, [override, bench, data?.regime, data?.regime_confidence, strategy, underlying]);

  const pickUnderlying = useCallback((sym: string) => {
    const s = sym.toUpperCase().trim();
    if (!s) return;
    setUnderlying(s);
    setUndQuery("");
    setUndAssets([]);
    setUndOpen(false);
    setStrategy(""); // eligible strategies differ across underlyings
  }, []);

  const onRegimeChange = useCallback(async (next: string) => {
    setOverride(next);
    setStrategy(""); // clear stale strategy filter — different regime → different eligible set
    try {
      await agentApi.regimeOverrideSet(next);
    } catch (e) {
      // non-fatal: card still reflects the chosen override locally
      console.warn("regime override persist failed:", e);
    }
  }, []);

  if (loading) return <Skeleton />;
  if (error || !data) return <ErrorCard msg={error ?? "No data"} />;

  const liveRegime = data.regime;
  const liveConfidence = data.regime_confidence;
  const effectiveRegime = bench?.regime || liveRegime || "Neutral";
  const effectiveConfidence = bench?.confidence ?? liveConfidence;
  const meta = REGIME_META[effectiveRegime] ?? {
    color: "text-slate-300", bg: "bg-slate-800 border-slate-600", desc: "Unknown",
  };

  const confWidth = `${Math.round(effectiveConfidence * 100)}%`;
  const liveActiveSet = new Set(data.active_strategies);
  const eligible = bench?.eligible ?? [];
  const activeInEligible = eligible.filter(s => liveActiveSet.has(s.name));

  return (
    <div className={clsx("rounded-xl border p-4 space-y-3", meta.bg)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={14} className={meta.color} />
          <span className="text-xs text-slate-400 uppercase tracking-widest">Market Regime</span>
          {bench?.is_override && (
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-900 border border-amber-600 text-amber-200">
              OVERRIDE
            </span>
          )}
        </div>
        <button
          onClick={() => refreshBench()}
          className="text-slate-500 hover:text-slate-200 transition"
          title="Refresh regime benchmark"
        >
          <RefreshCw size={11} className={benchLoading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Regime selector — drives everything below */}
      <div>
        <div className="flex items-center gap-2">
          <select
            value={override}
            onChange={e => onRegimeChange(e.target.value)}
            className={clsx(
              "flex-1 bg-slate-900 border rounded px-2 py-1 text-sm font-mono focus:outline-none",
              bench?.is_override
                ? "border-amber-600 text-amber-200"
                : "border-slate-600 text-slate-200"
            )}
            data-testid="regime-selector"
          >
            {REGIME_CHOICES.map(r => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>
        <div className="flex items-baseline gap-2 mt-1">
          <span className={clsx("text-xl font-bold font-mono", meta.color)}>
            {effectiveRegime}
          </span>
          <span className="text-[10px] text-slate-500 font-mono">
            {bench?.is_override && bench?.live_regime
              ? `live: ${bench.live_regime} @ ${Math.round((bench.live_confidence || 0) * 100)}%`
              : `live @ ${Math.round(liveConfidence * 100)}%`}
          </span>
        </div>
        <div className="text-[10px] text-slate-500 mt-0.5">{meta.desc}</div>
      </div>

      {/* Confidence bar (live or override=1.0) */}
      <div>
        <div className="flex justify-between text-[10px] text-slate-400 mb-1">
          <span>Effective confidence</span>
          <span>{fmtPct(effectiveConfidence)}</span>
        </div>
        <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
          <div
            className={clsx("h-full rounded-full transition-all duration-500",
              effectiveConfidence > 0.75 ? "bg-emerald-500" :
              effectiveConfidence > 0.55 ? "bg-yellow-500" : "bg-red-500")}
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

      {/* SPY-benchmark spot (always live, not regime-dependent) */}
      {bench?.spot && bench.spot.spot != null && (
        <div className="grid grid-cols-3 gap-2 pt-1 border-t border-slate-700">
          <SpotStat label="SPY spot"   value={bench.spot.spot.toFixed(2)} />
          <SpotStat label="1d Δ"       value={`${bench.spot.d1_pct! >= 0 ? "+" : ""}${bench.spot.d1_pct!.toFixed(2)}%`}
                    color={bench.spot.d1_pct! >= 0 ? "text-emerald-400" : "text-red-400"} />
          <SpotStat label="5d Δ"       value={`${bench.spot.d5_pct! >= 0 ? "+" : ""}${bench.spot.d5_pct!.toFixed(2)}%`}
                    color={bench.spot.d5_pct! >= 0 ? "text-emerald-400" : "text-red-400"} />
        </div>
      )}

      {/* Eligible strategies — clickable chips that filter the top suggestion */}
      {(eligible.length > 0) ? (
        <div className="space-y-2 pt-1 border-t border-slate-700">
          <div className="flex items-center gap-1">
            <TrendingUp size={12} className="text-slate-400" />
            <span className="text-xs text-slate-400 uppercase tracking-wider">Eligible Strategies</span>
            <span className="ml-auto text-[10px] font-mono text-slate-500">
              {activeInEligible.length}/{eligible.length} active
            </span>
          </div>
          <div className="flex flex-wrap gap-1">
            <button
              onClick={() => setStrategy("")}
              className={clsx(
                "text-[10px] font-mono px-1.5 py-0.5 rounded border",
                strategy === ""
                  ? "bg-indigo-900 border-indigo-500 text-indigo-200"
                  : "bg-slate-800 border-slate-600 text-slate-400 hover:border-slate-400"
              )}
              data-testid="strategy-chip-all"
            >
              ALL
            </button>
            {eligible.map(s => {
              const active = strategy === s.name;
              return (
                <button
                  key={s.name}
                  onClick={() => setStrategy(active ? "" : s.name)}
                  title={s.description || s.name}
                  className={clsx(
                    "text-[10px] font-mono px-1.5 py-0.5 rounded border transition",
                    active
                      ? "bg-indigo-900 border-indigo-500 text-indigo-200"
                      : liveActiveSet.has(s.name)
                        ? "bg-emerald-950 border-emerald-700 text-emerald-300 hover:border-emerald-500"
                        : "bg-slate-800 border-slate-600 text-slate-400 hover:border-slate-400"
                  )}
                  data-testid={`strategy-chip-${s.name}`}
                >
                  {s.name}
                </button>
              );
            })}
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

      {/* Top SPY option suggestion — recomputes whenever regime/strategy/lens change */}
      <TopSuggestionCard
        bench={bench}
        loading={benchLoading}
        error={benchErr}
        lens={lens}
        setLens={setLens}
        onOpenOptions={() => onNavigate?.("options")}
      />

      {/* Cycle stats (live only) */}
      <div className="grid grid-cols-3 gap-2 pt-1 border-t border-slate-700">
        <Stat label="Signals" value={String(data.signals_generated)} />
        <Stat label="Approved" value={String(data.orders_approved)} />
        <Stat label="Cycle"    value={`${data.cycle_duration_s.toFixed(1)}s`} />
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function TopSuggestionCard({
  bench, loading, error, lens, setLens, onOpenOptions,
}: {
  bench: RegimeBenchResult | null | undefined;
  loading: boolean;
  error: string | null;
  lens: "average" | "defensive";
  setLens: (l: "average" | "defensive") => void;
  onOpenOptions: () => void;
}) {
  const top = bench?.top_suggestion;
  return (
    <div className="pt-1 border-t border-slate-700 space-y-1.5">
      <div className="flex items-center gap-1">
        <Zap size={11} className="text-amber-400" />
        <span className="text-[10px] text-amber-400 uppercase tracking-wider">
          Top SPY {bench?.is_override ? `(${bench.regime})` : "(live regime)"} pick
        </span>
        <div className="ml-auto">
          <select
            value={lens}
            onChange={e => setLens(e.target.value as "average" | "defensive")}
            className="bg-slate-900 border border-slate-600 rounded text-[10px] font-mono px-1 py-0.5 text-slate-300 focus:outline-none"
            data-testid="lens-selector"
            title="Loss-aversion ranking lens"
          >
            {LENS_CHOICES.map(l => (
              <option key={l.value} value={l.value}>{l.label}</option>
            ))}
          </select>
        </div>
      </div>

      {loading && (
        <div className="text-[10px] text-slate-500 font-mono animate-pulse">scanning chain…</div>
      )}
      {error && (
        <div className="text-[10px] text-red-400 font-mono">bench error: {error.slice(0, 60)}</div>
      )}

      {top ? (
        <div className="rounded border border-slate-700 bg-slate-900/50 p-2 space-y-1">
          <div className="flex items-baseline justify-between">
            <div className="text-[11px] font-mono text-indigo-300">{top.strategy}</div>
            <div className="text-[10px] font-mono text-slate-500">
              score <span className="text-slate-200">{top.score?.toFixed(1) ?? "—"}</span>
            </div>
          </div>
          <div className="space-y-0.5">
            {(top.legs || []).slice(0, 3).map((l, i) => (
              <div key={i} className="text-[10px] font-mono text-slate-300 flex items-center gap-1">
                <span className={clsx(
                  "inline-block w-1.5 h-1.5 rounded-full",
                  l.side.startsWith("buy") ? "bg-emerald-500" : "bg-red-500"
                )} />
                <span className="text-slate-500">{l.side.replace("_", " ")}</span>
                <span className="ml-auto text-slate-200">{l.symbol}</span>
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between text-[10px] font-mono pt-0.5 border-t border-slate-800">
            <span className="text-slate-500">max loss <span className="text-red-400">${top.max_loss?.toFixed(0) ?? "—"}</span></span>
            <span className="text-slate-500">premium <span className="text-emerald-400">${top.est_premium?.toFixed(0) ?? "—"}</span></span>
          </div>
          <button
            onClick={onOpenOptions}
            className="w-full text-[10px] font-mono px-2 py-1 rounded bg-indigo-900 border border-indigo-700 text-indigo-200 hover:bg-indigo-800 transition flex items-center justify-center gap-1"
          >
            Open in Options <ExternalLink size={9} />
          </button>
        </div>
      ) : (
        !loading && (
          <div className="text-[10px] text-slate-500 font-mono">no qualifying trade for this regime/strategy</div>
        )
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-center">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className="text-xs font-mono text-slate-200">{value}</div>
    </div>
  );
}

function SpotStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="text-center">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className={clsx("text-xs font-mono", color ?? "text-slate-200")}>{value}</div>
    </div>
  );
}

function Skeleton() {
  return <div className="rounded-xl border border-slate-700 bg-slate-800 p-4 h-64 animate-pulse" />;
}

function ErrorCard({ msg }: { msg: string }) {
  return (
    <div className="rounded-xl border border-red-800 bg-red-950 p-4 text-xs text-red-300 font-mono">
      Agent unreachable: {msg}
    </div>
  );
}
