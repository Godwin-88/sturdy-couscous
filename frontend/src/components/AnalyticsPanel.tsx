// GraphAlpha Analytics Intelligence Platform — Frontend Component
// Phase 1: Universal Time Series Selector + Descriptive Statistics

import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import {
  analyticsApi,
  type AnalyticsSeries,
  type AnalyticsDataResponse,
  type DescriptiveStats,
  type AutocorrelationResult,
  type VolatilityAnalysis,
  type SignalICResult,
  type FactorExposure,
  type PortfolioOptimizationResult,
  type AIInterpretation,
  type AnomalyResult,
  type ForecastResult,
  type GarchResult,
  type PCAResult,
  type CovHealthResult,
  type OptionChainProfile,
} from "@/lib/api";
import { fmtN, fmtPct, fmt$ } from "@/lib/utils";
import {
  BarChart2, TrendingUp, Activity, ShieldAlert, Brain,
  RefreshCw, ChevronDown, ChevronRight, Search, Gauge, Link2,
} from "lucide-react";
import clsx from "clsx";
import { setScreenContext } from "@/lib/screenContext";

type Tier = "descriptive" | "diagnostic" | "predictive" | "prescriptive" | "cognitive";

const TIERS: { id: Tier; label: string; icon: React.ReactNode; desc: string }[] = [
  { id: "descriptive",  label: "Descriptive",  icon: <BarChart2   size={13} />, desc: "What happened?" },
  { id: "diagnostic",   label: "Diagnostic",   icon: <Activity    size={13} />, desc: "Why did it happen?" },
  { id: "predictive",   label: "Predictive",   icon: <TrendingUp  size={13} />, desc: "What will happen?" },
  { id: "prescriptive", label: "Prescriptive", icon: <ShieldAlert size={13} />, desc: "What should we do?" },
  { id: "cognitive",    label: "Cognitive",    icon: <Brain       size={13} />, desc: "What does it mean?" },
];

const DATE_PRESETS = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
  { label: "YTD", days: 0 }, // special
  { label: "All", days: -1 }, // special
];

export default function AnalyticsPanel() {
  // ── State ────────────────────────────────────────────────────────────────
  const [series, setSeries] = useState<AnalyticsSeries[]>([]);
  const [selectedSeries, setSelectedSeries] = useState<string>("");
  const [startDate, setStartDate] = useState<string>("2024-01-01");
  const [endDate, setEndDate] = useState<string>(() => {
    const d = new Date();
    return d.toISOString().split("T")[0];
  });
  const [activeTier, setActiveTier] = useState<Tier>("descriptive");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Tier data
  const [dataResp, setDataResp] = useState<AnalyticsDataResponse | null>(null);
  const [descriptive, setDescriptive] = useState<DescriptiveStats | null>(null);
  const [autocorr, setAutocorr] = useState<AutocorrelationResult | null>(null);
  const [volatility, setVolatility] = useState<VolatilityAnalysis | null>(null);
  const [signalIC, setSignalIC] = useState<SignalICResult | null>(null);
  const [factors, setFactors] = useState<FactorExposure | null>(null);
  const [optimization, setOptimization] = useState<PortfolioOptimizationResult | null>(null);
  const [interpretation, setInterpretation] = useState<AIInterpretation | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyResult | null>(null);

  // ── Chain-context deep-link state (from Options panel "Analyze" / sidebar) ──
  const [searchParams] = useSearchParams();
  const chainUnderlying = searchParams.get("underlying") ?? "";
  const chainExpiration = searchParams.get("expiration") ?? "";
  const chainContractType = searchParams.get("contract_type") ?? "";
  const chainStrikeParam = searchParams.get("strike");
  const deepLinkApplied = useRef(false);

  const [chainProfile, setChainProfile] = useState<OptionChainProfile | null>(null);
  const [chainLoading, setChainLoading] = useState(false);
  const [chainError, setChainError] = useState<string | null>(null);

  // ── Load available series on mount ───────────────────────────────────────
  useEffect(() => {
    analyticsApi.series().then(setSeries).catch(() => null);
  }, []);

  // Honor URL deep-links once the catalogue is in: select the target series
  // (px:{underlying}:Close by default when a chain context exists), synthesise
  // an entry when the ticker isn't on the watchlist, and apply start/end.
  useEffect(() => {
    if (deepLinkApplied.current || series.length === 0) return;
    deepLinkApplied.current = true;

    const urlSeries = searchParams.get("series");
    let target = urlSeries ? urlSeries : "";
    if (target.startsWith("yf:")) target = `px:${target.slice(3)}`;
    if (!target && chainUnderlying) target = `px:${chainUnderlying}:Close`;

    if (target) {
      const known = series.some(s => s.id === target);
      if (!known) {
        const parts = target.split(":");
        if (parts.length === 3 && parts[0] === "px") {
          setSeries(prev => [...prev, {
            id: target,
            name: `${parts[1]} ${parts[2]}`,
            ticker: parts[1],
            metric: parts[2],
            source: "alpaca",
            granularities: ["1d", "1wk"],
            default_granularity: "1d",
            type: parts[2] === "Volume" ? "volume" : "price",
            description: `${parts[1]} ${parts[2]} (deep-linked series)`,
          }]);
        }
      }
      setSelectedSeries(target);
    }

    const start = searchParams.get("start");
    const end = searchParams.get("end");
    if (start) setStartDate(start);
    if (end) setEndDate(end);
  }, [series.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Publish analytics screen context (anchors the Financial Engineer chat on
  // the chain being analyzed) and fetch the chain profile card.
  useEffect(() => {
    if (!chainUnderlying) {
      setChainProfile(null);
      setChainError(null);
      return;
    }
    setScreenContext("analytics", {
      screen: "analytics",
      underlying: chainUnderlying,
      expiration: chainExpiration || undefined,
      contract_type: (chainContractType as "call" | "put" | undefined) || undefined,
      strike: chainStrikeParam ? Number(chainStrikeParam) : undefined,
      extra: { chain_link: true },
    });
    setChainLoading(true);
    setChainError(null);
    analyticsApi.optionsChain(chainUnderlying, {
      expiration: chainExpiration || undefined,
      contract_type: chainContractType || undefined,
    })
      .then(setChainProfile)
      .catch(e => { setChainError(String(e)); setChainProfile(null); })
      .finally(() => setChainLoading(false));
  }, [chainUnderlying, chainExpiration, chainContractType, chainStrikeParam]);

  // ── Fetch data when series or date changes ───────────────────────────────
  const fetchData = useCallback(async () => {
    if (!selectedSeries) return;
    setLoading(true);
    setError(null);
    try {
      const data = await analyticsApi.data(selectedSeries, startDate, endDate);
      setDataResp(data);

      if (activeTier === "descriptive") {
        const [desc, ac] = await Promise.all([
          analyticsApi.descriptive(selectedSeries, startDate, endDate),
          analyticsApi.autocorrelation(selectedSeries, startDate, endDate),
        ]);
        setDescriptive(desc);
        setAutocorr(ac);
      } else if (activeTier === "diagnostic") {
        const [vol, ic, fac] = await Promise.all([
          analyticsApi.volatility(selectedSeries, startDate, endDate),
          analyticsApi.signalIC("MomentumXLE", selectedSeries.split(":")[1], startDate, endDate).catch(() => null),
          analyticsApi.factors(selectedSeries, startDate, endDate).catch(() => null),
        ]);
        setVolatility(vol);
        setSignalIC(ic);
        setFactors(fac);
      } else if (activeTier === "prescriptive") {
        const ticker = selectedSeries.split(":")[1];
        if (ticker) {
          const opt = await analyticsApi.optimize({
            tickers: [ticker, "SPY", "TLT", "GLD"],
            method: "mvo",
          }).catch(() => null);
          setOptimization(opt);
        }
      } else if (activeTier === "cognitive") {
        const [anom, interp] = await Promise.all([
          analyticsApi.anomalies(selectedSeries, startDate, endDate).catch(() => null),
          analyticsApi.interpret("descriptive", (descriptive ?? {}) as Record<string, unknown>, { ticker: selectedSeries.split(":")[1] }).catch(() => null),
        ]);
        setAnomalies(anom);
        setInterpretation(interp);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [selectedSeries, startDate, endDate, activeTier]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDatePreset = (days: number) => {
    const end = new Date();
    setEndDate(end.toISOString().split("T")[0]);
    if (days === -1) {
      setStartDate("2020-01-01");
    } else if (days === 0) {
      // YTD
      setStartDate(`${end.getFullYear()}-01-01`);
    } else {
      const start = new Date(end);
      start.setDate(start.getDate() - days);
      setStartDate(start.toISOString().split("T")[0]);
    }
  };

  return (
    <div className="space-y-4">
      {/* ── Universal Time Series Selector ─────────────────────────────────── */}
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Search size={14} className="text-indigo-400" />
          <span className="text-xs font-semibold text-slate-200 uppercase tracking-wider">Time Series Selector</span>
          {chainUnderlying && (
            <span className="ml-auto flex items-center gap-1 text-[10px] font-mono text-violet-300 bg-violet-950/40 border border-violet-500/30 rounded px-2 py-0.5">
              <Link2 size={10} />
              chain: {chainUnderlying}
              {chainExpiration ? ` · ${chainExpiration}` : ""}
              {chainContractType ? ` · ${chainContractType}` : ""}
              {chainStrikeParam ? ` · ${chainStrikeParam}` : ""}
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">Series</label>
            <select
              value={selectedSeries}
              onChange={e => setSelectedSeries(e.target.value)}
              className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5"
            >
              <option value="">Select a series...</option>
              {series.map(s => (
                <option key={s.id} value={s.id}>{s.name} ({s.source})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">Start Date</label>
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
              className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">End Date</label>
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
              className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">Quick Range</label>
            <div className="flex gap-1 mt-1 flex-wrap">
              {DATE_PRESETS.map(p => (
                <button key={p.label} onClick={() => handleDatePreset(p.days)}
                  className="px-2 py-1 rounded text-[10px] font-mono bg-slate-800 border border-slate-600 text-slate-400 hover:bg-slate-700">
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        {dataResp && (
          <div className="flex items-center gap-3 text-[10px] font-mono text-slate-500">
            <span>{dataResp.count} data points</span>
            {dataResp.missing_gaps && dataResp.missing_gaps.length > 0 && (
              <span className="text-amber-400">{dataResp.missing_gaps.length} gaps detected</span>
            )}
            {(() => {
              const meta = dataResp.metadata as Record<string, unknown> | undefined;
              if (!meta?.start) return null;
              const start = String(meta.start).slice(0, 10);
              const end = String(meta.end ?? "").slice(0, 10);
              return <span>{start} → {end}</span>;
            })()}
          </div>
        )}
      </div>

      {/* ── Chain Profile card (descriptive/diagnostic context for the chain) ── */}
      {chainUnderlying && (
        <div className="rounded-xl border border-indigo-500/30 bg-slate-900 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
            <Gauge size={14} className="text-indigo-400" />
            <span className="text-xs font-semibold text-slate-200 uppercase tracking-wider">Chain Profile</span>
            <span className="text-[10px] font-mono text-slate-500 truncate">
              {chainUnderlying}{chainExpiration ? ` · ${chainExpiration}` : ""}{chainContractType ? ` · ${chainContractType}s` : ""}
              {chainStrikeParam ? ` · ${chainStrikeParam}` : ""} — context for the underlying series below
            </span>
            <span className="ml-auto shrink-0 text-[10px] font-mono text-slate-500">
              {chainProfile ? `${chainProfile.source} · ${chainProfile.n_contracts} contracts` : "…"}
            </span>
          </div>
          {chainLoading && (
            <div className="p-4 text-xs text-slate-500 animate-pulse font-mono">Building chain profile…</div>
          )}
          {chainError && !chainLoading && (
            <div className="p-3 text-xs font-mono text-red-400 bg-red-950/30 border-t border-red-800">{chainError}</div>
          )}
          {chainProfile && !chainLoading && <ChainProfileCard profile={chainProfile} />}
        </div>
      )}

      {/* ── Tier Navigation ────────────────────────────────────────────────── */}
      <div className="flex gap-0 border-b border-slate-700 overflow-x-auto">
        {TIERS.map(t => (
          <button key={t.id} onClick={() => setActiveTier(t.id)}
            className={clsx(
              "flex items-center gap-1.5 px-4 py-2 text-xs font-mono whitespace-nowrap transition-colors border-b-2 -mb-px",
              activeTier === t.id
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            )}>
            {t.icon} {t.label}
            <span className="text-[9px] text-slate-600 ml-1">{t.desc}</span>
          </button>
        ))}
        <button onClick={fetchData} disabled={loading || !selectedSeries}
          className="ml-auto px-3 py-2 text-xs text-slate-400 hover:text-indigo-400">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* ── Error ──────────────────────────────────────────────────────────── */}
      {error && (
        <div className="rounded-lg bg-red-950 border border-red-800 p-3 text-xs text-red-300 font-mono">
          {error}
        </div>
      )}

      {/* ── Loading ────────────────────────────────────────────────────────── */}
      {loading && (
        <div className="flex items-center justify-center h-32 text-xs text-slate-500 animate-pulse">
          Computing {activeTier} analysis...
        </div>
      )}

      {/* ── Tier Content ───────────────────────────────────────────────────── */}
      {!loading && selectedSeries && (
        <div className="space-y-4">
          {activeTier === "descriptive" && (
            <>
              {descriptive && <DescriptivePanel stats={descriptive} />}
              {autocorr && <AutocorrelationPanel data={autocorr} />}
            </>
          )}
          {activeTier === "diagnostic" && (
            <DiagnosticWrapper ticker={selectedSeries.split(":")[1]} />
          )}
          {activeTier === "predictive" && (
            <PredictivePanel
              key={selectedSeries}
              ticker={selectedSeries.split(":")[1]}
            />
          )}
          {activeTier === "prescriptive" && (
            <>
              {optimization && <OptimizationPanel data={optimization} />}
            </>
          )}
          {activeTier === "cognitive" && (
            <>
              {anomalies && <AnomalyPanel data={anomalies} />}
              {interpretation && <InterpretationPanel data={interpretation} />}
            </>
          )}
        </div>
      )}

      {/* ── Empty state ────────────────────────────────────────────────────── */}
      {!selectedSeries && !loading && (
        <div className="rounded-xl border border-slate-700 bg-slate-900 p-8 text-center">
          <BarChart2 size={24} className="mx-auto text-slate-600 mb-2" />
          <div className="text-sm text-slate-400">Select a time series above to begin analysis</div>
          <div className="text-xs text-slate-600 mt-1">
            Choose from {series.length} available series across alpaca-primary market data, signal metrics, portfolio state, and regime history
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// CHAIN PROFILE CARD — descriptive/diagnostic context for a selected chain
// ═══════════════════════════════════════════════════════════════════════════════

function ChainProfileCard({ profile }: { profile: OptionChainProfile }) {
  const iv = profile.iv;
  const em = profile.expected_move;
  const skewVal = profile.skew.risk_reversal_25d;
  const strikeLabel = (s: number) => (s % 1 === 0 ? s.toFixed(0) : s.toFixed(2));
  return (
    <div className="p-3 grid grid-cols-1 lg:grid-cols-3 gap-3">
      {/* IV + smile */}
      <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-2">
        <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Implied Volatility</div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] font-mono">
          <span className="text-slate-500">ATM strike</span><span className="text-slate-200 text-right">{iv.atm_strike != null ? fmt$(iv.atm_strike) : "—"}</span>
          <span className="text-slate-500">ATM IV</span><span className="text-indigo-300 text-right">{iv.atm_iv != null ? fmtPct(iv.atm_iv) : "—"}</span>
          <span className="text-slate-500">Median IV</span><span className="text-slate-200 text-right">{iv.median_iv != null ? fmtPct(iv.median_iv) : "—"}</span>
          <span className="text-slate-500">IV range</span>
          <span className="text-slate-200 text-right">{iv.min_iv != null && iv.max_iv != null ? `${fmtPct(iv.min_iv)} – ${fmtPct(iv.max_iv)}` : "—"}</span>
        </div>
        {iv.smile.length > 0 && (
          <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
            {iv.smile.slice(0, 12).map(p => (
              <div key={p.strike} className="flex items-center gap-2 text-[10px] font-mono">
                <span className="text-slate-500 w-14 shrink-0">{(p.contract_type === "put" ? "P " : "C ") + strikeLabel(p.strike)}</span>
                <div className="flex-1 h-1 bg-slate-800 rounded overflow-hidden">
                  <div
                    className="h-full bg-indigo-500"
                    style={{ width: `${iv.max_iv ? Math.min((p.iv / iv.max_iv) * 100, 100) : 0}%` }}
                  />
                </div>
                <span className="text-slate-400 w-12 text-right">{fmtPct(p.iv)}</span>
                {p.spread_pct != null && <span className="text-amber-400 w-12 text-right">Δ{p.spread_pct.toFixed(2)}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

{/* Skew + expected move */}
      <div className="space-y-2">
        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-1.5">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">25Δ Risk Reversal</div>
          <div className="grid grid-cols-3 gap-1 text-[11px] font-mono text-center">
            <div><div className="text-[9px] text-slate-500">call IV</div><div className="text-emerald-300">{profile.skew.iv_25d_call != null ? fmtPct(profile.skew.iv_25d_call) : "—"}</div></div>
            <div><div className="text-[9px] text-slate-500">put IV</div><div className="text-rose-300">{profile.skew.iv_25d_put != null ? fmtPct(profile.skew.iv_25d_put) : "—"}</div></div>
            <div><div className="text-[9px] text-slate-500">RR 25Δ</div>
              <div className={skewVal != null && skewVal > 0 ? "text-emerald-300" : "text-rose-300"}>
                {skewVal != null ? `${skewVal > 0 ? "+" : ""}${(skewVal * 100).toFixed(1)}pt` : "—"}
              </div>
            </div>
          </div>
          <div className="text-[10px] text-slate-500 leading-snug">{profile.skew.note}</div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-1.5">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Expected Move</div>
          <div className="text-[11px] font-mono text-slate-200 space-y-1">
            <div className="flex justify-between"><span className="text-slate-500">1σ (ATM {em.method === "atm_straddle" ? "straddle" : "IV"})</span><span>{em.move_pct != null ? fmtPct(em.move_pct) : "—"}</span></div>
            {em.ann_pct != null && <div className="flex justify-between"><span className="text-slate-500">Ann. equiv</span><span>{fmtPct(em.ann_pct)}</span></div>}
            {em.straddle_mid != null && <div className="flex justify-between"><span className="text-slate-500">Straddle mid</span><span>{fmt$(em.straddle_mid)}</span></div>}
            {em.days != null && <div className="flex justify-between"><span className="text-slate-500">To expiry</span><span>{em.days} dte</span></div>}
          </div>
          <div className="text-[10px] text-slate-500 border-t border-slate-700 pt-1 leading-snug">
            Why it matters: the chain prices where the market expects {profile.underlying} at expiry — {em.move_pct != null ? `±${fmtPct(em.move_pct)} (1σ)` : "the ATM option"} is the market's own forecast, while the smile/skew show how much buyers pay for upside vs. downside insurance.
          </div>
        </div>
      </div>
// ═══════════════════════════════════════════════════════════════════════════════
{/* OI + spreads + greeks */}
      <div className="space-y-2">
        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-1.5">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Open Interest</div>
          {profile.oi.top_strikes.length > 0 ? (
            <div className="space-y-1">
              {profile.oi.top_strikes.map(s => (
                <div key={s.strike} className="flex items-center gap-2 text-[10px] font-mono">
                  <span className="text-slate-500 w-16 shrink-0">{(s.contract_type === "put" ? "P " : "C ") + strikeLabel(s.strike)}</span>
                  <div className="flex-1 h-1 bg-slate-800 rounded overflow-hidden">
                    <div className="h-full bg-violet-500" style={{ width: `${profile.oi.total ? Math.min((s.oi / profile.oi.total) * 100, 100) : 0}%` }} />
                  </div>
                  <span className="text-slate-300 w-16 text-right">{Math.round(s.oi).toLocaleString()}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[10px] text-slate-600">no OI data in snapshot</div>
          )}
          {profile.oi.total ? <div className="text-[10px] text-slate-500 font-mono">total {Math.round(profile.oi.total).toLocaleString()} contracts</div> : null}
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-1">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Spreads · Greeks (median)</div>
          <div className="grid grid-cols-3 gap-1 text-[10px] font-mono text-center">
            <div><div className="text-slate-500">avg spread</div><div className="text-amber-300">{profile.spreads.avg_spread_pct != null ? fmtPct(profile.spreads.avg_spread_pct) : "—"}</div></div>
            <div><div className="text-slate-500">Δ</div><div className="text-slate-200">{profile.greeks.delta.median != null ? profile.greeks.delta.median.toFixed(3) : "—"}</div></div>
            <div><div className="text-slate-500">Γ</div><div className="text-indigo-300">{profile.greeks.gamma.median != null ? profile.greeks.gamma.median.toFixed(4) : "—"}</div></div>
          </div>
        </div>
        {profile.term_structure.length > 1 && (
          <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-1">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Term Structure</div>
            {profile.term_structure.map(t => (
              <div key={t.expiration} className="flex justify-between text-[10px] font-mono">
                <span className="text-slate-500">{t.expiration} ({t.dte != null ? `${t.dte}d` : "–"})</span>
                <span className="text-slate-200">{t.atm_iv != null ? fmtPct(t.atm_iv) : "—"}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
// TIER 1: Descriptive Panel
// ═══════════════════════════════════════════════════════════════════════════════

function DescriptivePanel({ stats }: { stats: DescriptiveStats }) {
  const b = stats.basic;
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <BarChart2 size={14} className="text-indigo-400" />
        <span className="text-xs font-semibold text-slate-200">Statistical Summary</span>
        <span className="text-[10px] text-slate-500 ml-auto">n = {stats.n}</span>
      </div>

      {/* Basic stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <StatCard label="Mean" value={fmtN(b.mean, 4)} />
        <StatCard label="Median" value={fmtN(b.median, 4)} />
        <StatCard label="Std Dev" value={fmtN(b.std, 4)} />
        <StatCard label="Variance" value={fmtN(b.variance, 4)} />
        <StatCard label="Skewness" value={fmtN(b.skewness, 4)} highlight={Math.abs(b.skewness) > 1} />
        <StatCard label="Excess Kurtosis" value={fmtN(b.excess_kurtosis, 4)} highlight={Math.abs(b.excess_kurtosis) > 2} />
        <StatCard label="Min" value={fmtN(b.min, 4)} />
        <StatCard label="Max" value={fmtN(b.max, 4)} />
        <StatCard label="Q1 (25%)" value={fmtN(b.q1, 4)} />
        <StatCard label="Q3 (75%)" value={fmtN(b.q3, 4)} />
        <StatCard label="IQR" value={fmtN(b.iqr, 4)} />
        <StatCard label="Range" value={fmtN(b.range, 4)} />
      </div>

      {/* Percentiles */}
      <div>
        <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Percentiles</div>
        <div className="grid grid-cols-7 gap-1">
          {Object.entries(stats.percentiles).map(([k, v]) => (
            <div key={k} className="bg-slate-800 rounded p-1.5 text-center border border-slate-700">
              <div className="text-[9px] text-slate-500">{k}</div>
              <div className="text-[10px] font-mono text-slate-200">{fmtN(v, 4)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Annualized stats */}
      {stats.annualized.ann_mean !== null && (
        <div className="grid grid-cols-2 gap-2">
          <StatCard label="Ann. Mean Return" value={fmtPct(stats.annualized.ann_mean)} />
          <StatCard label="Ann. Volatility" value={fmtPct(stats.annualized.ann_std ?? 0)} />
        </div>
      )}

      {/* Normality tests */}
      <div className="space-y-2">
        <div className="text-[10px] text-slate-500 uppercase tracking-wider">Normality Tests</div>
        {stats.normality_tests.jarque_bera && (
          <TestResult
            label="Jarque-Bera"
            stat={stats.normality_tests.jarque_bera.statistic}
            pValue={stats.normality_tests.jarque_bera.p_value}
            interpretation={stats.normality_tests.jarque_bera.interpretation}
          />
        )}
        {stats.stationarity_tests.adf && (
          <TestResult
            label="ADF (Stationarity)"
            stat={stats.stationarity_tests.adf.statistic}
            pValue={stats.stationarity_tests.adf.p_value}
            interpretation={stats.stationarity_tests.adf.interpretation}
          />
        )}
        {stats.stationarity_tests.kpss && (
          <TestResult
            label="KPSS (Stationarity)"
            stat={stats.stationarity_tests.kpss.statistic}
            pValue={stats.stationarity_tests.kpss.p_value}
            interpretation={stats.stationarity_tests.kpss.interpretation}
          />
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ACF/PACF Panel
// ═══════════════════════════════════════════════════════════════════════════════

function AutocorrelationPanel({ data }: { data: AutocorrelationResult }) {
  const maxAcf = Math.max(...data.acf.map(a => Math.abs(a.acf)), 0.1);
  const maxPacf = Math.max(...data.pacf.map(p => Math.abs(p.pacf)), 0.1);

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Activity size={14} className="text-indigo-400" />
        <span className="text-xs font-semibold text-slate-200">Autocorrelation (ACF/PACF)</span>
        {data.ljung_box && (
          <span className={clsx("text-[10px] font-mono ml-auto",
            data.ljung_box.p_value < 0.05 ? "text-amber-400" : "text-slate-500")}>
            Ljung-Box p={data.ljung_box.p_value.toFixed(4)}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* ACF plot */}
        <div>
          <div className="text-[10px] text-slate-500 mb-1">ACF (Autocorrelation Function)</div>
          <div className="h-32 relative">
            {data.acf.slice(1, 30).map((a, i) => {
              const barH = Math.abs(a.acf) / maxAcf * 100;
              return (
                <div key={i} className="absolute bottom-0 flex flex-col items-center"
                  style={{ left: `${(i / 29) * 100}%`, width: `${100 / 30}%` }}>
                  <div className={clsx("w-[3px] rounded-t",
                    Math.abs(a.acf) > data.confidence_band_95 ? "bg-indigo-400" : "bg-slate-600")}
                    style={{ height: `${barH}%` }} />
                </div>
              );
            })}
            <div className="absolute top-1/2 left-0 right-0 h-px bg-slate-600" />
            <div className="absolute top-[25%] left-0 right-0 h-px bg-slate-700/50 border-t border-dashed" />
            <div className="absolute top-[75%] left-0 right-0 h-px bg-slate-700/50 border-t border-dashed" />
          </div>
        </div>

        {/* PACF plot */}
        <div>
          <div className="text-[10px] text-slate-500 mb-1">PACF (Partial Autocorrelation)</div>
          <div className="h-32 relative">
            {data.pacf.slice(1, 30).map((p, i) => {
              const barH = Math.abs(p.pacf) / maxPacf * 100;
              return (
                <div key={i} className="absolute bottom-0 flex flex-col items-center"
                  style={{ left: `${(i / 29) * 100}%`, width: `${100 / 30}%` }}>
                  <div className={clsx("w-[3px] rounded-t",
                    Math.abs(p.pacf) > data.confidence_band_95 ? "bg-emerald-400" : "bg-slate-600")}
                    style={{ height: `${barH}%` }} />
                </div>
              );
            })}
            <div className="absolute top-1/2 left-0 right-0 h-px bg-slate-600" />
            <div className="absolute top-[25%] left-0 right-0 h-px bg-slate-700/50 border-t border-dashed" />
            <div className="absolute top-[75%] left-0 right-0 h-px bg-slate-700/50 border-t border-dashed" />
          </div>
        </div>
      </div>

      {data.ljung_box && (
        <div className={clsx("text-[10px] font-mono leading-relaxed px-2 py-1 rounded",
          data.ljung_box.p_value < 0.05 ? "bg-amber-950/40 text-amber-300" : "text-slate-500")}>
          {data.ljung_box.interpretation}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIER 2: Diagnostic Panels
// ═══════════════════════════════════════════════════════════════════════════════

function VolatilityPanel({ data }: { data: VolatilityAnalysis }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Activity size={14} className="text-indigo-400" />
        <span className="text-xs font-semibold text-slate-200">Volatility Analysis</span>
        <span className="text-[10px] text-slate-500 ml-auto">21d vol: {fmtPct(data.current_realized_vol_21d ?? 0)}</span>
      </div>

      {/* Volatility term structure */}
      <div>
        <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Volatility Term Structure</div>
        <div className="grid grid-cols-4 gap-2">
          {Object.entries(data.volatility_term_structure).map(([k, v]) => (
            <StatCard key={k} label={k} value={fmtPct(v)} />
          ))}
        </div>
      </div>

      {/* GARCH results */}
      {data.garch && !("error" in data.garch) && (
        <div className="space-y-2">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">GARCH(1,1) Model</div>
          <div className="grid grid-cols-3 gap-2">
            <StatCard label="α (ARCH)" value={fmtN(data.garch.parameters.alpha, 4)} />
            <StatCard label="β (GARCH)" value={fmtN(data.garch.parameters.beta, 4)} />
            <StatCard label="Persistence" value={fmtN(data.garch.persistence, 4)} />
          </div>
          {data.garch.half_life_days && (
            <div className="text-[10px] text-slate-400 font-mono">
              Volatility half-life: {data.garch.half_life_days.toFixed(1)} days
            </div>
          )}
          <div className="text-[10px] font-mono leading-relaxed text-slate-400 bg-slate-800/50 rounded p-2">
            {data.garch.interpretation}
          </div>
        </div>
      )}

      {/* ARCH LM test */}
      {data.arch_lm && (
        <TestResult
          label="ARCH LM (Volatility Clustering)"
          stat={data.arch_lm.statistic}
          pValue={data.arch_lm.p_value}
          interpretation={data.arch_lm.interpretation}
        />
      )}
    </div>
  );
}

function SignalICPanel({ data }: { data: SignalICResult }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <TrendingUp size={14} className="text-indigo-400" />
        <span className="text-xs font-semibold text-slate-200">Signal Information Coefficient</span>
        <span className="text-[10px] text-slate-500 ml-auto">{data.strategy} · {data.forward_horizon_days}d horizon</span>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <StatCard label="Mean IC" value={fmtN(data.summary.ic_mean, 4)}
          highlight={data.summary.ic_mean < 0} />
        <StatCard label="IC Std" value={fmtN(data.summary.ic_std, 4)} />
        <StatCard label="IR" value={fmtN(data.summary.information_ratio, 4)}
          highlight={data.summary.information_ratio < 0} />
        <StatCard label="t-stat" value={fmtN(data.summary.t_statistic, 2)}
          highlight={Math.abs(data.summary.t_statistic) < 2} />
      </div>

      <div className={clsx("text-[10px] font-mono leading-relaxed px-2 py-1 rounded",
        data.summary.ic_mean > 0 ? "bg-emerald-950/40 text-emerald-300" : "bg-red-950/40 text-red-300")}>
        {data.summary.interpretation}
      </div>

      <div className="text-[10px] text-slate-500">
        {data.n_observations} observations across {data.n_days} days
      </div>
    </div>
  );
}

function FactorPanel({ data }: { data: FactorExposure }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <BarChart2 size={14} className="text-indigo-400" />
        <span className="text-xs font-semibold text-slate-200">Factor Exposure (Market Model)</span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <StatCard label="Alpha (α)" value={fmtN(data.market_model.alpha, 4)}
          highlight={data.market_model.alpha_tstat < 2} />
        <StatCard label="Beta (β)" value={fmtN(data.market_model.beta, 4)} />
        <StatCard label="R²" value={fmtPct(data.market_model.r_squared)} />
        <StatCard label="Adj. R²" value={fmtPct(data.market_model.adj_r_squared)} />
      </div>

      <div className="text-[10px] font-mono leading-relaxed text-slate-400 bg-slate-800/50 rounded p-2">
        {data.interpretation}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIER 2: Diagnostic Wrapper (sub-tab navigation)
// ═══════════════════════════════════════════════════════════════════════════════

type DiagTab = "volatility" | "garch" | "pca" | "covhealth" | "signals" | "factors";

const DIAG_TABS: { id: DiagTab; label: string }[] = [
  { id: "volatility", label: "Volatility" },
  { id: "garch",      label: "GARCH" },
  { id: "pca",        label: "PCA" },
  { id: "covhealth",  label: "Cov Health" },
  { id: "signals",    label: "Signal IC" },
  { id: "factors",    label: "Factors" },
];

function DiagnosticWrapper({ ticker }: { ticker: string }) {
  const [diagTab, setDiagTab] = useState<DiagTab>("volatility");
  const [loading, setLoading] = useState(false);
  const [volatility, setVolatility] = useState<VolatilityAnalysis | null>(null);
  const [signalIC, setSignalIC] = useState<SignalICResult | null>(null);
  const [factors, setFactors] = useState<FactorExposure | null>(null);

  useEffect(() => {
    if (diagTab === "volatility" || diagTab === "signals" || diagTab === "factors") {
      setLoading(true);
      Promise.all([
        diagTab === "volatility" ? analyticsApi.volatility(`yf:${ticker}:Close`, "2024-01-01").then(setVolatility).catch(() => null) : Promise.resolve(),
        diagTab === "signals" ? analyticsApi.signalIC("MomentumXLE", ticker, "2024-01-01").then(setSignalIC).catch(() => null) : Promise.resolve(),
        diagTab === "factors" ? analyticsApi.factors(`yf:${ticker}:Close`, "2024-01-01").then(setFactors).catch(() => null) : Promise.resolve(),
      ]).finally(() => setLoading(false));
    }
  }, [diagTab, ticker]);

  return (
    <div className="space-y-4">
      <div className="flex gap-0 border-b border-slate-700 overflow-x-auto">
        {DIAG_TABS.map(t => (
          <button key={t.id} onClick={() => setDiagTab(t.id)}
            className={clsx(
              "px-3 py-1.5 text-[10px] font-mono whitespace-nowrap border-b-2 -mb-px transition-colors",
              diagTab === t.id ? "border-indigo-500 text-indigo-400" : "border-transparent text-slate-500 hover:text-slate-300"
            )}>
            {t.label}
          </button>
        ))}
      </div>

      {loading && <div className="flex items-center justify-center h-16 text-xs text-slate-500 animate-pulse">Loading...</div>}

      {diagTab === "volatility" && volatility && <VolatilityPanel data={volatility} />}
      {diagTab === "garch" && <GarchPanel ticker={ticker} />}
      {diagTab === "pca" && <PCAPanel ticker={ticker} />}
      {diagTab === "covhealth" && <CovHealthPanel ticker={ticker} />}
      {diagTab === "signals" && signalIC && <SignalICPanel data={signalIC} />}
      {diagTab === "factors" && factors && <FactorPanel data={factors} />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIER 2b: GARCH Variant Panel
// ═══════════════════════════════════════════════════════════════════════════════

function GarchPanel({ ticker }: { ticker: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GarchResult | null>(null);
  const [p, setP] = useState(1);
  const [q, setQ] = useState(1);
  const [power, setPower] = useState(2.0);
  const [selectedVariants, setSelectedVariants] = useState<Record<string, boolean>>({
    garch: true, egarch: true, gjrgarch: true, aparch: true, igarch: false, garchm: false,
  });

  const variants = Object.entries(selectedVariants).filter(([, v]) => v).map(([k]) => k);

  const runGarch = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const res = await analyticsApi.garch({ ticker, variants, p, q, power });
      setResult(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [ticker, variants.join(","), p, q, power]);

  useEffect(() => {
    runGarch();
  }, [runGarch]);

  if (!ticker) {
    return <div className="rounded-xl border border-slate-700 bg-slate-900 p-6 text-center text-sm text-slate-500">Select a yfinance series.</div>;
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-indigo-400" />
          <span className="text-xs font-semibold text-slate-200">Multi-Variant GARCH Engine</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-6 gap-3">
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">p (ARCH)</label>
            <input type="number" min={1} max={10} value={p} onChange={e => setP(Number(e.target.value))}
              className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">q (GARCH)</label>
            <input type="number" min={1} max={10} value={q} onChange={e => setQ(Number(e.target.value))}
              className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">APARCH Power</label>
            <input type="number" min={0.5} max={5} step={0.5} value={power} onChange={e => setPower(Number(e.target.value))}
              className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
          </div>
          <div className="flex items-end">
            <button onClick={runGarch} disabled={loading}
              className="w-full px-3 py-1.5 rounded text-xs font-mono bg-indigo-700 text-indigo-200 border border-indigo-600 hover:bg-indigo-600 disabled:opacity-50">
              {loading ? "Fitting..." : "Run GARCH"}
            </button>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-700">
          {Object.entries(selectedVariants).map(([k, v]) => (
            <label key={k} className="flex items-center gap-1 cursor-pointer">
              <input type="checkbox" checked={v} onChange={e => setSelectedVariants(prev => ({ ...prev, [k]: e.target.checked }))}
                className="accent-indigo-500 w-3 h-3" />
              <span className="text-[10px] font-mono text-slate-400">{k.toUpperCase()}</span>
            </label>
          ))}
        </div>
      </div>

      {error && <div className="rounded-lg bg-red-950 border border-red-800 p-3 text-xs text-red-300 font-mono">{error}</div>}
      {loading && <div className="flex items-center justify-center h-16 text-xs text-slate-500 animate-pulse">Fitting GARCH variants...</div>}

      {result && !loading && (
        <>
          {/* Model comparison */}
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Activity size={14} className="text-indigo-400" />
              <span className="text-xs font-semibold text-slate-200">Model Comparison</span>
              <span className="text-[10px] text-slate-500 ml-auto">Best: {result.best_model?.toUpperCase()}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[10px] font-mono">
                <thead><tr className="text-slate-500">
                  <th className="text-left py-1 px-1">Variant</th>
                  <th className="text-right py-1 px-1">AIC</th>
                  <th className="text-right py-1 px-1">BIC</th>
                  <th className="text-right py-1 px-1">LogLik</th>
                  <th className="text-right py-1 px-1">Persistence</th>
                  <th className="text-right py-1 px-1">Half-Life</th>
                  <th className="text-right py-1 px-1">Converged</th>
                </tr></thead>
                <tbody>
                  {result.model_comparison.map(m => (
                    <tr key={m.variant} className={clsx("border-t border-slate-800", m.variant === result.best_model && "bg-indigo-950/20")}>
                      <td className="py-1 px-1 text-slate-300">{m.variant.toUpperCase()}</td>
                      <td className="py-1 px-1 text-right text-slate-300">{fmtN(m.aic, 1)}</td>
                      <td className="py-1 px-1 text-right text-slate-400">{fmtN(m.bic, 1)}</td>
                      <td className="py-1 px-1 text-right text-slate-400">{fmtN(m.log_likelihood, 1)}</td>
                      <td className="py-1 px-1 text-right text-slate-400">{fmtN(m.persistence, 3)}</td>
                      <td className="py-1 px-1 text-right text-slate-400">{m.half_life_days ? `${fmtN(m.half_life_days, 1)}d` : "∞"}</td>
                      <td className="py-1 px-1 text-right">{m.converged ? <span className="text-emerald-400">✓</span> : <span className="text-red-400">✗</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Conditional volatility chart */}
          {result.best_model && result.conditional_volatilities[result.best_model] && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Activity size={14} className="text-indigo-400" />
                <span className="text-xs font-semibold text-slate-200">Conditional Volatility — {result.best_model.toUpperCase()}</span>
              </div>
              <div className="h-24 relative">
                <svg viewBox="0 0 400 100" className="w-full h-full" preserveAspectRatio="none">
                  {(() => {
                    const cv = result.conditional_volatilities[result.best_model].slice(-500);
                    const maxV = Math.max(...cv, 0.001);
                    const path = cv.map((v, i) =>
                      `${i === 0 ? "M" : "L"}${(i / (cv.length - 1 || 1)) * 395 + 2.5},${100 - (v / maxV) * 85 - 7.5}`
                    ).join(" ");
                    return <path d={path} fill="none" stroke="#818cf8" strokeWidth="1" />;
                  })()}
                </svg>
              </div>
            </div>
          )}

          {/* News impact curves */}
          {result.best_model && result.news_impact_curves[result.best_model] && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <TrendingUp size={14} className="text-indigo-400" />
                <span className="text-xs font-semibold text-slate-200">News Impact Curve</span>
              </div>
              <div className="h-24 relative">
                <svg viewBox="0 0 400 100" className="w-full h-full" preserveAspectRatio="none">
                  {(() => {
                    const nic = result.news_impact_curves[result.best_model];
                    const maxN = Math.max(...nic.conditional_variances, 0.001);
                    const path = nic.conditional_variances.map((v, i) =>
                      `${i === 0 ? "M" : "L"}${(i / (nic.shocks.length - 1 || 1)) * 395 + 2.5},${100 - (v / maxN) * 85 - 7.5}`
                    ).join(" ");
                    return (
                      <>
                        <line x1={200} y1={10} x2={200} y2={100} stroke="#475569" strokeWidth="0.5" strokeDasharray="2,2" />
                        <path d={path} fill="none" stroke="#34d399" strokeWidth="1.5" />
                      </>
                    );
                  })()}
                </svg>
              </div>
              <div className="flex justify-between text-[9px] text-slate-600"><span>Negative shock (-3σ)</span><span>0</span><span>Positive shock (+3σ)</span></div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIER 2c: PCA Panel
// ═══════════════════════════════════════════════════════════════════════════════

function PCAPanel({ ticker }: { ticker: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PCAResult | null>(null);
  const [compare, setCompare] = useState("SPY,QQQ,TLT,GLD,IWM");

  const runPCA = useCallback(async () => {
    const tickers = [ticker, ...compare.split(",").map(t => t.trim()).filter(Boolean)];
    setLoading(true);
    setError(null);
    try {
      const res = await analyticsApi.pca({ tickers });
      setResult(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [ticker, compare]);

  useEffect(() => { runPCA(); }, [runPCA]);

  if (!ticker) return <div className="rounded-xl border border-slate-700 bg-slate-900 p-6 text-center text-sm text-slate-500">Select a yfinance series.</div>;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <BarChart2 size={14} className="text-indigo-400" />
          <span className="text-xs font-semibold text-slate-200">PCA for Finance</span>
        </div>
        <div className="flex gap-3">
          <input type="text" value={compare} onChange={e => setCompare(e.target.value)}
            placeholder="SPY,QQQ,TLT,GLD,IWM"
            className="flex-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 font-mono" />
          <button onClick={runPCA} disabled={loading}
            className="px-3 py-1.5 rounded text-xs font-mono bg-indigo-700 text-indigo-200 border border-indigo-600 hover:bg-indigo-600 disabled:opacity-50">
            {loading ? "..." : "Run"}
          </button>
        </div>
      </div>

      {error && <div className="rounded-lg bg-red-950 border border-red-800 p-3 text-xs text-red-300 font-mono">{error}</div>}
      {loading && <div className="flex items-center justify-center h-16 text-xs text-slate-500 animate-pulse">Computing PCA...</div>}

      {result && !loading && (
        <>
          {/* Summary */}
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <BarChart2 size={14} className="text-indigo-400" />
              <span className="text-xs font-semibold text-slate-200">PCA Summary</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <StatCard label="Assets" value={String(result.n_observations)} />
              <StatCard label="Sig. Components (Kaiser)" value={String(result.kaiser_significant_components)} />
              <StatCard label="90% Variance" value={`${result.components_for_90pct_variance} PCs`} />
              <StatCard label="PC1" value={result.pc1_interpretation} />
            </div>
          </div>

          {/* Scree plot */}
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <BarChart2 size={14} className="text-indigo-400" />
              <span className="text-xs font-semibold text-slate-200">Scree Plot</span>
            </div>
            <div className="h-32 relative">
              <svg viewBox="0 0 400 120" className="w-full h-full" preserveAspectRatio="none">
                {result.scree.map((s, i) => {
                  const barH = (s.eigenvalue / result.scree[0].eigenvalue) * 80;
                  return (
                    <g key={s.component}>
                      <rect x={i * (380 / result.scree.length) + 10} y={110 - barH}
                        width={Math.max(10, 380 / result.scree.length - 5)} height={barH}
                        fill={i < result.kaiser_significant_components ? "#818cf8" : "#475569"}
                        rx={1} />
                    </g>
                  );
                })}
              </svg>
            </div>
            <div className="text-[9px] text-slate-600 text-center">Component →</div>
          </div>

          {/* Risk decomposition */}
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <ShieldAlert size={14} className="text-indigo-400" />
              <span className="text-xs font-semibold text-slate-200">Risk Decomposition</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              {Object.entries(result.risk_decomposition).map(([k, v]) => (
                <StatCard key={k} label={`Top ${v.n_components} PCs`} value={fmtPct(v.variance_explained_pct / 100)} />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIER 2d: Covariance Health Panel
// ═══════════════════════════════════════════════════════════════════════════════

function CovHealthPanel({ ticker }: { ticker: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CovHealthResult | null>(null);
  const [compare, setCompare] = useState("SPY,QQQ,TLT,GLD,IWM");

  const run = useCallback(async () => {
    const tickers = [ticker, ...compare.split(",").map(t => t.trim()).filter(Boolean)];
    setLoading(true);
    setError(null);
    try {
      const res = await analyticsApi.covarianceHealth({ tickers });
      setResult(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [ticker, compare]);

  useEffect(() => { run(); }, [run]);

  if (!ticker) return <div className="rounded-xl border border-slate-700 bg-slate-900 p-6 text-center text-sm text-slate-500">Select a yfinance series.</div>;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-indigo-400" />
          <span className="text-xs font-semibold text-slate-200">Covariance Health</span>
        </div>
        <div className="flex gap-3">
          <input type="text" value={compare} onChange={e => setCompare(e.target.value)}
            placeholder="SPY,QQQ,TLT,GLD,IWM"
            className="flex-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 font-mono" />
          <button onClick={run} disabled={loading}
            className="px-3 py-1.5 rounded text-xs font-mono bg-indigo-700 text-indigo-200 border border-indigo-600 hover:bg-indigo-600 disabled:opacity-50">
            {loading ? "..." : "Run"}
          </button>
        </div>
      </div>

      {error && <div className="rounded-lg bg-red-950 border border-red-800 p-3 text-xs text-red-300 font-mono">{error}</div>}
      {loading && <div className="flex items-center justify-center h-16 text-xs text-slate-500 animate-pulse">Computing covariance...</div>}

      {result && !loading && (
        <>
          {/* Condition number + shrinkage */}
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <ShieldAlert size={14} className="text-indigo-400" />
              <span className="text-xs font-semibold text-slate-200">Matrix Health</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <StatCard label="Condition #" value={fmtN(result.condition_number, 0)}
                highlight={result.is_ill_conditioned} />
              <StatCard label="Status" value={result.is_ill_conditioned ? "ILL-CONDITIONED" : "OK"}
                highlight={result.is_ill_conditioned} />
              <StatCard label="LW α" value={fmtN(result.shrinkage.ledoit_wolf_alpha, 4)} />
              <StatCard label="OAS α" value={fmtN(result.shrinkage.oas_alpha, 4)} />
            </div>
          </div>

          {/* MST */}
          {result.minimum_spanning_tree.edges.length > 0 && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Activity size={14} className="text-indigo-400" />
                <span className="text-xs font-semibold text-slate-200">Minimum Spanning Tree</span>
                <span className="text-[10px] text-slate-500 ml-auto">Total distance: {fmtN(result.minimum_spanning_tree.total_distance, 3)}</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-[10px] font-mono">
                  <thead><tr className="text-slate-500">
                    <th className="text-left py-1 px-1">From</th>
                    <th className="text-left py-1 px-1">To</th>
                    <th className="text-right py-1 px-1">Correlation</th>
                    <th className="text-right py-1 px-1">Distance</th>
                  </tr></thead>
                  <tbody>
                    {result.minimum_spanning_tree.edges.map((e, i) => (
                      <tr key={i} className="border-t border-slate-800">
                        <td className="py-1 px-1 text-slate-300">{e.from}</td>
                        <td className="py-1 px-1 text-slate-300">{e.to}</td>
                        <td className={clsx("py-1 px-1 text-right", Math.abs(e.correlation) > 0.7 ? "text-amber-400" : "text-slate-400")}>
                          {fmtN(e.correlation, 3)}
                        </td>
                        <td className="py-1 px-1 text-right text-slate-400">{fmtN(e.distance, 3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Top correlated pairs */}
          {result.all_pairs.length > 0 && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <BarChart2 size={14} className="text-indigo-400" />
                <span className="text-xs font-semibold text-slate-200">Top Correlations</span>
              </div>
              <div className="overflow-x-auto max-h-32">
                <table className="w-full text-[10px] font-mono">
                  <thead className="sticky top-0 bg-slate-800">
                    <tr className="text-slate-500">
                      <th className="text-left py-1 px-1">Pair</th>
                      <th className="text-right py-1 px-1">Correlation</th>
                      <th className="text-right py-1 px-1">Distance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...result.all_pairs].sort((a, b) => Math.abs(b.correlation) - Math.abs(a.correlation)).slice(0, 10).map((p, i) => (
                      <tr key={i} className="border-t border-slate-800">
                        <td className="py-1 px-1 text-slate-300">{p.asset_i} / {p.asset_j}</td>
                        <td className={clsx("py-1 px-1 text-right", Math.abs(p.correlation) > 0.7 ? "text-amber-400" : "text-slate-400")}>
                          {fmtN(p.correlation, 3)}
                        </td>
                        <td className="py-1 px-1 text-right text-slate-400">{fmtN(p.distance, 3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIER 3: Predictive Panel (ARIMA / ETS Forecasting)
// ═══════════════════════════════════════════════════════════════════════════════

function PredictivePanel({ ticker }: { ticker: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ForecastResult | null>(null);
  const [model, setModel] = useState<"arima" | "ets" | "var" | "vecm">("arima");
  const [horizon, setHorizon] = useState(21);
  const [confLevel, setConfLevel] = useState(0.95);
  const [compareTickers, setCompareTickers] = useState("SPY,QQQ");
  const [vecmLags, setVecmLags] = useState(2);

  const runForecast = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const tickers = compareTickers.split(",").map(t => t.trim()).filter(Boolean);
      const res = await analyticsApi.forecast({
        ticker,
        model,
        horizon,
        conf_level: confLevel,
        max_p: 5,
        max_q: 5,
        max_d: 2,
        ...((model === "var" || model === "vecm") ? { compare_tickers: tickers, vecm_k_ar_diff: vecmLags } : {}),
      });
      setResult(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [ticker, model, horizon, confLevel, compareTickers, vecmLags]);

  useEffect(() => {
    runForecast();
  }, [runForecast]);

  if (!ticker) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-6 text-center text-sm text-slate-500">
        Select a yfinance series (e.g. SPY, QQQ) to run forecasts.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Model controls */}
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <TrendingUp size={14} className="text-indigo-400" />
          <span className="text-xs font-semibold text-slate-200">Forecast Configuration</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">Model</label>
            <select value={model} onChange={e => setModel(e.target.value as "arima" | "ets" | "var" | "vecm")}
              className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
              <option value="arima">ARIMA (Auto-Regressive)</option>
              <option value="ets">ETS (Exponential Smoothing)</option>
              <option value="var">VAR (Vector Auto-Regression)</option>
              <option value="vecm">VECM (Cointegration)</option>
            </select>
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">Horizon (days)</label>
            <input type="number" min={1} max={252} value={horizon}
              onChange={e => setHorizon(Number(e.target.value))}
              className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">Confidence Level</label>
            <select value={confLevel} onChange={e => setConfLevel(Number(e.target.value))}
              className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
              <option value={0.8}>80%</option>
              <option value={0.9}>90%</option>
              <option value={0.95}>95%</option>
              <option value={0.99}>99%</option>
            </select>
          </div>
          <div className="flex items-end">
            <button onClick={runForecast} disabled={loading}
              className="w-full px-3 py-1.5 rounded text-xs font-mono bg-indigo-700 text-indigo-200 border border-indigo-600 hover:bg-indigo-600 disabled:opacity-50">
              {loading ? "Computing..." : "Run Forecast"}
            </button>
          </div>
        </div>
        {(model === "var" || model === "vecm") && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-slate-700">
            <div>
              <label className="text-[10px] text-slate-500 uppercase tracking-wider">Compare Tickers</label>
              <input type="text" value={compareTickers}
                onChange={e => setCompareTickers(e.target.value)}
                placeholder="SPY,QQQ,TLT"
                className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 font-mono" />
            </div>
            {model === "vecm" && (
              <div>
                <label className="text-[10px] text-slate-500 uppercase tracking-wider">VECM Lags (differences)</label>
                <input type="number" min={1} max={10} value={vecmLags}
                  onChange={e => setVecmLags(Number(e.target.value))}
                  className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
              </div>
            )}
            {model === "var" && (
              <div className="flex items-end">
                <div className="text-[10px] text-slate-400 font-mono">
                  Lag selection via AIC auto-tuning
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-950 border border-red-800 p-3 text-xs text-red-300 font-mono">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-24 text-xs text-slate-500 animate-pulse">
          Fitting {model.toUpperCase()} model...
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <>
          {/* Model summary */}
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <TrendingUp size={14} className="text-indigo-400" />
              <span className="text-xs font-semibold text-slate-200">Model Summary</span>
              <span className="text-[10px] text-slate-500 ml-auto">{result.ticker} · {result.model.toUpperCase()}</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {result.order && (
                <StatCard label="ARIMA Order" value={`(${result.order.p},${result.order.d},${result.order.q})`} />
              )}
              {result.seasonal && (
                <StatCard label="Seasonal" value={result.seasonal} />
              )}
              <StatCard label="AIC" value={fmtN(result.aic, 2)} />
              <StatCard label="BIC" value={fmtN(result.bic, 2)} />
              <StatCard label="RMSE" value={fmtN(result.rmse, 4)} />
              <StatCard label="MAE" value={fmtN(result.mae, 4)} />
              <StatCard label="Residual σ" value={fmtN(result.residual_std, 4)} />
              <StatCard label="Observations" value={String(result.n_observations)} />
            </div>
            {result.ljung_box_p !== undefined && (
              <div className={clsx("text-[10px] font-mono px-2 py-1 rounded",
                result.ljung_box_p < 0.05 ? "bg-amber-950/40 text-amber-300" : "text-slate-500")}>
                Ljung-Box p={fmtN(result.ljung_box_p, 4)} — {result.ljung_box_p < 0.05 ? "Residuals show autocorrelation (model may be misspecified)" : "Residuals appear white noise"}
              </div>
            )}
          </div>

          {/* Forecast chart — single series (ARIMA/ETS) */}
          {Array.isArray(result.historical) && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <TrendingUp size={14} className="text-indigo-400" />
                <span className="text-xs font-semibold text-slate-200">Forecast ({result.horizon}d ahead)</span>
                <span className="text-[10px] text-slate-500 ml-auto">{fmtPct(result.conf_level)} confidence</span>
              </div>
              <div className="h-48 relative">
                <svg viewBox="0 0 800 200" className="w-full h-full" preserveAspectRatio="none">
                  {(() => {
                    const hist = result.historical as number[];
                    const all = [
                      ...hist,
                      ...result.forecast,
                      ...result.conf_int_lower,
                      ...result.conf_int_upper,
                    ].filter(v => v !== null && v !== undefined && isFinite(v));
                    if (all.length === 0) return null;
                    const min = Math.min(...all);
                    const max = Math.max(...all);
                    const range = max - min || 1;
                    const histLen = hist.length;
                    const totalLen = histLen + result.forecast.length;

                    const toY = (v: number) => 200 - ((v - min) / range) * 180 - 10;
                    const toX = (i: number) => (i / (totalLen - 1 || 1)) * 780 + 10;

                    const histPath = hist.map((v, i) =>
                      `${i === 0 ? "M" : "L"}${toX(i)},${toY(v)}`
                    ).join(" ");
                    const fcPath = result.forecast.map((v, i) =>
                      `${i === 0 ? "M" : "L"}${toX(histLen + i)},${toY(v)}`
                    ).join(" ");

                    return (
                      <>
                        {result.conf_int_lower.length > 0 && (
                          <path
                            d={result.conf_int_lower.map((lower, i) => {
                              const upper = result.conf_int_upper[i];
                              const x = toX(histLen + i);
                              return `${i === 0 ? "M" : "L"}${x},${toY(lower)}`;
                            }).join(" ") + [...result.conf_int_upper].reverse().map((upper, i) => {
                              const x = toX(histLen + result.conf_int_upper.length - 1 - i);
                              return `L${x},${toY(upper)}`;
                            }).join(" ") + "Z"}
                            fill="rgba(99, 102, 241, 0.15)"
                          />
                        )}
                        <path d={histPath} fill="none" stroke="#94a3b8" strokeWidth="1.5" />
                        <path d={fcPath} fill="none" stroke="#818cf8" strokeWidth="2" />
                        <line x1={toX(histLen - 1)} y1={0} x2={toX(histLen - 1)} y2={200}
                          stroke="#475569" strokeWidth="1" strokeDasharray="4,4" />
                      </>
                    );
                  })()}
                </svg>
                <div className="flex justify-between text-[9px] text-slate-600 mt-1">
                  <span>Historical</span>
                  <span>| Forecast →</span>
                </div>
              </div>
            </div>
          )}

          {/* Multi-ticker forecast chart (VAR/VECM) */}
          {!Array.isArray(result.historical) && result.forecasts && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <TrendingUp size={14} className="text-indigo-400" />
                <span className="text-xs font-semibold text-slate-200">Multi-Ticker Forecast</span>
                <span className="text-[10px] text-slate-500 ml-auto">{result.tickers?.join(", ")}</span>
              </div>
              <div className="h-48 relative">
                <svg viewBox="0 0 800 200" className="w-full h-full" preserveAspectRatio="none">
                  {(() => {
                    const hist = result.historical as Record<string, number[]>;
                    const tickers = result.tickers ?? Object.keys(hist);
                    const colors = ["#818cf8", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#60a5fa"];
                    const all: number[] = [];
                    for (const tk of tickers) {
                      if (hist[tk]) all.push(...hist[tk]);
                      if (result.forecasts?.[tk]) all.push(...result.forecasts[tk]);
                    }
                    const valid = all.filter(v => isFinite(v));
                    if (valid.length === 0) return null;
                    const min = Math.min(...valid);
                    const max = Math.max(...valid);
                    const range = max - min || 1;
                    const toY = (v: number) => 200 - ((v - min) / range) * 180 - 10;

                    return (
                      <>
                        {tickers.map((tk, idx) => {
                          const data = hist[tk] ?? [];
                          const fc = result.forecasts?.[tk] ?? [];
                          const totalLen = data.length + fc.length;
                          const toX = (i: number) => (i / (totalLen - 1 || 1)) * 780 + 10;
                          const histPath = data.map((v, i) =>
                            `${i === 0 ? "M" : "L"}${toX(i)},${toY(v)}`
                          ).join(" ");
                          const fcPath = fc.map((v, i) =>
                            `${i === 0 ? "M" : "L"}${toX(data.length + i)},${toY(v)}`
                          ).join(" ");
                          const color = colors[idx % colors.length];
                          return (
                            <g key={tk}>
                              <path d={histPath} fill="none" stroke={color} strokeWidth="1" opacity={0.7} />
                              <path d={fcPath} fill="none" stroke={color} strokeWidth="1.5" />
                            </g>
                          );
                        })}
                      </>
                    );
                  })()}
                </svg>
                <div className="flex flex-wrap gap-2 mt-1">
                  {(result.tickers ?? Object.keys(result.historical as Record<string, number[]>)).map((tk, idx) => (
                    <span key={tk} className="text-[9px] font-mono flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: ["#818cf8", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#60a5fa"][idx % 6] }} />
                      {tk}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Residual diagnostics */}
          {result.residuals.length > 0 && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Activity size={14} className="text-indigo-400" />
                <span className="text-xs font-semibold text-slate-200">Residual Diagnostics</span>
              </div>
              <div className="h-24 relative">
                <svg viewBox="0 0 400 100" className="w-full h-full" preserveAspectRatio="none">
                  {(() => {
                    const res = result.residuals;
                    const maxR = Math.max(...res.map(Math.abs), 0.001);
                    const path = res.map((v, i) =>
                      `${i === 0 ? "M" : "L"}${(i / (res.length - 1 || 1)) * 390 + 5},${50 - (v / maxR) * 40}`
                    ).join(" ");
                    return (
                      <>
                        <line x1={0} y1={50} x2={400} y2={50} stroke="#475569" strokeWidth="0.5" />
                        <path d={path} fill="none" stroke="#34d399" strokeWidth="1" />
                      </>
                    );
                  })()}
                </svg>
              </div>
              <div className="text-[10px] text-slate-500 font-mono">
                Residuals should appear as white noise (no pattern, constant variance)
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIER 4: Prescriptive Panel
// ═══════════════════════════════════════════════════════════════════════════════

function OptimizationPanel({ data }: { data: PortfolioOptimizationResult }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <ShieldAlert size={14} className="text-indigo-400" />
        <span className="text-xs font-semibold text-slate-200">Portfolio Optimization ({data.method.toUpperCase()})</span>
      </div>

      {/* Optimal weights */}
      <div>
        <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Optimal Weights</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {Object.entries(data.optimal_weights).map(([ticker, weight]) => (
            <StatCard key={ticker} label={ticker} value={fmtPct(weight)}
              highlight={weight > 0.2} />
          ))}
        </div>
      </div>

      {/* Portfolio comparison */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-slate-800 rounded-lg p-3 border border-slate-700">
          <div className="text-[10px] text-slate-500 uppercase">Optimal</div>
          <div className="text-xs font-mono text-emerald-400 mt-1">
            Sharpe: {fmtN(data.optimal_portfolio.sharpe_ratio, 2)}
          </div>
          <div className="text-[10px] font-mono text-slate-400">
            Vol: {fmtPct(data.optimal_portfolio.expected_volatility)}
          </div>
        </div>
        <div className="bg-slate-800 rounded-lg p-3 border border-slate-700">
          <div className="text-[10px] text-slate-500 uppercase">Equal Weight</div>
          <div className="text-xs font-mono text-slate-300 mt-1">
            Sharpe: {fmtN(data.equal_weight_portfolio.sharpe_ratio, 2)}
          </div>
          <div className="text-[10px] font-mono text-slate-400">
            Vol: {fmtPct(data.equal_weight_portfolio.expected_volatility)}
          </div>
        </div>
      </div>

      {/* Correlation matrix */}
      {data.correlation_matrix && (
        <div>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Correlation Matrix</div>
          <div className="overflow-x-auto">
            <table className="w-full text-[10px] font-mono">
              <thead>
                <tr className="text-slate-500">
                  <th className="text-left py-1 pr-2"></th>
                  {Object.keys(data.correlation_matrix).map(t => (
                    <th key={t} className="text-right py-1 px-1">{t}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.correlation_matrix).map(([t1, row]) => (
                  <tr key={t1} className="border-t border-slate-800">
                    <td className="py-1 pr-2 text-slate-300">{t1}</td>
                    {Object.entries(row).map(([t2, v]) => (
                      <td key={t2} className={clsx("py-1 px-1 text-right",
                        Math.abs(v) > 0.7 ? "text-amber-400 font-bold" :
                        Math.abs(v) > 0.4 ? "text-slate-300" : "text-slate-500")}>
                        {fmtN(v, 2)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIER 5: Cognitive Panels
// ═══════════════════════════════════════════════════════════════════════════════

function AnomalyPanel({ data }: { data: AnomalyResult }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Activity size={14} className="text-indigo-400" />
        <span className="text-xs font-semibold text-slate-200">Anomaly Detection</span>
        <span className={clsx("text-[10px] font-mono ml-auto",
          data.n_anomalies > 0 ? "text-amber-400" : "text-slate-500")}>
          {data.n_anomalies} anomalies ({fmtPct(data.anomaly_rate)})
        </span>
      </div>
      <div className="text-[10px] text-slate-500">Method: {data.method}</div>
      {data.anomalies.length > 0 && (
        <div className="overflow-auto max-h-32">
          <table className="w-full text-[10px] font-mono">
            <thead className="sticky top-0 bg-slate-800">
              <tr className="text-slate-500">
                <th className="text-left py-1 px-1">Date</th>
                <th className="text-right py-1 px-1">Value</th>
                <th className="text-right py-1 px-1">Score</th>
              </tr>
            </thead>
            <tbody>
              {data.anomalies.slice(0, 20).map((a, i) => (
                <tr key={i} className="border-t border-slate-800">
                  <td className="py-1 px-1 text-slate-400">{a.timestamp.slice(0, 10)}</td>
                  <td className="py-1 px-1 text-right text-amber-300">{fmtN(a.value, 4)}</td>
                  <td className="py-1 px-1 text-right text-slate-400">
                    {a.anomaly_score ? fmtN(a.anomaly_score, 2) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function InterpretationPanel({ data }: { data: AIInterpretation }) {
  return (
    <div className="rounded-xl border border-indigo-800/50 bg-indigo-950/20 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Brain size={14} className="text-indigo-400" />
        <span className="text-xs font-semibold text-indigo-300">AI Interpretation</span>
        <span className="text-[10px] text-slate-500 ml-auto">{data.model} · {data.provider}</span>
      </div>
      {data.status === "unconfigured" ? (
        <div className="text-xs text-slate-500 font-mono">
          Set AI_API_KEY, AI_BASE_URL, and AI_MODEL in .env to enable AI interpretation.
        </div>
      ) : data.status === "error" ? (
        <div className="text-xs text-red-400 font-mono">{data.interpretation}</div>
      ) : (
        <div className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap font-sans">
          {data.interpretation}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Shared Components
// ═══════════════════════════════════════════════════════════════════════════════

function StatCard({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={clsx("bg-slate-800 rounded-lg p-2 border",
      highlight ? "border-amber-700/50" : "border-slate-700")}>
      <div className="text-[9px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={clsx("text-xs font-bold font-mono mt-0.5",
        highlight ? "text-amber-400" : "text-slate-200")}>
        {value}
      </div>
    </div>
  );
}

function TestResult({ label, stat, pValue, interpretation }: {
  label: string; stat: number; pValue: number; interpretation: string;
}) {
  const significant = pValue < 0.05;
  return (
    <div className={clsx("rounded p-2 border text-[10px] font-mono",
      significant ? "bg-amber-950/30 border-amber-800/50" : "bg-slate-800/50 border-slate-700")}>
      <div className="flex items-center gap-2 mb-0.5">
        <span className="text-slate-400 font-semibold">{label}</span>
        <span className="text-slate-500">stat={fmtN(stat, 2)}</span>
        <span className={significant ? "text-amber-400" : "text-emerald-400"}>
          p={fmtN(pValue, 4)}
        </span>
        <span className={clsx("ml-auto text-[9px] px-1 py-0.5 rounded",
          significant ? "bg-amber-900/60 text-amber-300" : "bg-emerald-900/60 text-emerald-300")}>
          {significant ? "SIGNIFICANT" : "NOT SIGNIFICANT"}
        </span>
      </div>
      <div className="text-slate-400 leading-relaxed">{interpretation}</div>
    </div>
  );
}