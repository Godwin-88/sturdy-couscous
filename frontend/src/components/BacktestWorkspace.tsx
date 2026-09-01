import { useState, useEffect, useRef } from "react";
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell, Legend,
} from "recharts";
import {
  agentApi, researchApi, marketApi, BacktestResult, TradeSuggestion,
  TradeLogEntry, StrategyBreakdown, WalkForwardWindow,
  BacktestOptimizeResult, BacktestCompareResult,
} from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmtPct, fmtN, fmt$, relTime } from "@/lib/utils";
import {
  Play, BarChart2, CheckCircle, XCircle, ChevronDown,
  ChevronRight, TrendingUp, TrendingDown, AlertTriangle, BookOpen,
  Sliders, GitCompare, Layers, Database, Zap, RefreshCw, AlertCircle,
  LineChart as LineChartIcon, X, Database as DatabaseIcon,
} from "lucide-react";
import clsx from "clsx";

type RunMode = "grounded" | "ungrounded" | "both";
type SubTab = "run" | "results" | "optimize" | "compare" | "ablation" | "templates";

export default function BacktestWorkspace() {
  const [subTab, setSubTab] = useState<SubTab>("run");
  const [startDate,  setStartDate]  = useState("2021-01-01");
  const [endDate,    setEndDate]    = useState("2023-12-31");
  const [capital,    setCapital]    = useState("10000");
  const [mode,       setMode]       = useState<RunMode>("both");
  const [rebalFreq,  setRebalFreq]  = useState("5");
  const [feePct,     setFeePct]     = useState("0.001");
  const [slipPct,    setSlipPct]    = useState("0.0005");
  const [running,    setRunning]    = useState(false);
  const [progress,   setProgress]   = useState<{ pct: number; msg: string } | null>(null);
  const [grounded,   setGrounded]   = useState<BacktestResult | null>(null);
  const [ungrounded, setUngrounded] = useState<BacktestResult | null>(null);
  const [resultTab,  setResultTab]  = useState("summary");
  const [showParams, setShowParams] = useState(false);
  const [seedLoading, setSeedLoading] = useState(false);
  const [seedError, setSeedError] = useState<string | null>(null);
  const [seedSuccess, setSeedSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dataSourceOpen, setDataSourceOpen] = useState(false);
  const [selectedTickers, setSelectedTickers] = useState<string[]>(["SPY", "QQQ", "TLT", "GLD", "BTC-USD"]);
  const [tickerInput, setTickerInput] = useState("");
  const [fredSeries, setFredSeries] = useState<{ id: string; name: string }[]>([]);
  const [selectedFred, setSelectedFred] = useState<string[]>([]);
  const [combineData, setCombineData] = useState(true);
  const [dataPreview, setDataPreview] = useState<{ rows: number; tickers: string[]; preview: Record<string, unknown>[] | null } | null>(null);
  const [dataLoading, setDataLoading] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { data: suggestions, refresh: refreshSuggestions } =
    usePolling(agentApi.backtestSuggestions, 15_000);

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };
  useEffect(() => stopPoll, []);

  const pollStatus = async () => {
    try {
      const res = await agentApi.backtestStatus();
      if (res.progress) setProgress(res.progress);
      if (res.grounded)   setGrounded(res.grounded);
      if (res.ungrounded) setUngrounded(res.ungrounded);
      if (res.status === "done" || res.status.startsWith("error")) {
        setRunning(false);
        stopPoll();
        if (res.status.startsWith("error")) {
          setError(res.status.replace("error:", ""));
        }
        refreshSuggestions?.();
      }
    } catch (e: unknown) {
      setRunning(false);
      stopPoll();
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    setProgress({ pct: 0, msg: "Starting…" });
    setGrounded(null);
    setUngrounded(null);
    try {
      await agentApi.runBacktest({
        start_date: startDate, end_date: endDate,
        initial_capital: Number(capital),
        use_graph: mode !== "ungrounded",
        run_both:  mode === "both",
        rebal_freq: Number(rebalFreq),
        fee_pct:   Number(feePct),
        slip_pct:  Number(slipPct),
        tickers: selectedTickers.join(","),
        trade_threshold: 0.05,
      });
      pollRef.current = setInterval(pollStatus, 2000);
    } catch (e: unknown) {
      setRunning(false);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleSeedData = async () => {
    setSeedLoading(true);
    setSeedError(null);
    setSeedSuccess(false);
    try {
      await agentApi.marketQuotes("SPY,QQQ,IWM,DIA,TLT,GLD,USO,BTC-USD");
      setSeedSuccess(true);
    } catch (e: unknown) {
      setSeedError(e instanceof Error ? e.message : String(e));
    } finally {
      setSeedLoading(false);
    }
  };

  const handleQuickStart = async () => {
    setStartDate("2023-01-01");
    setEndDate("2023-12-31");
    setCapital("10000");
    setMode("grounded");
    setRebalFreq("5");
    setFeePct("0.001");
    setSlipPct("0.0005");
    setTimeout(() => {
      const runBtn = document.getElementById("bt-run-btn");
      if (runBtn) runBtn.click();
    }, 100);
  };

  const hasResults = grounded || ungrounded;
  const primary = grounded ?? ungrounded;

  const subTabs: { id: SubTab; label: string; icon: React.ReactNode }[] = [
    { id: "run",       label: "Run",       icon: <Play size={12} /> },
    { id: "results",   label: "Results",   icon: <BarChart2 size={12} /> },
    { id: "optimize",  label: "Optimize",  icon: <Sliders size={12} /> },
    { id: "compare",   label: "Compare",   icon: <GitCompare size={12} /> },
    { id: "ablation",  label: "Ablation",  icon: <Layers size={12} /> },
  ];

  const resultSubTabs: { id: string; label: string }[] = [
    { id: "summary",     label: "Summary"      },
    { id: "equity",      label: "Equity Curve" },
    { id: "drawdown",    label: "Drawdown"     },
    { id: "trades",      label: "Trade Log"    },
    { id: "strategies",  label: "Strategies"   },
    { id: "wf",          label: "Walk-Fwd"     },
    { id: "suggestions", label: "Suggestions"  },
  ];

  return (
    <div className="h-full flex flex-col">
      {/* Sub-tab navigation */}
      <div className="flex items-center gap-1 px-3 pt-2 pb-0 shrink-0">
        <div className="flex gap-0.5 bg-slate-800 rounded-lg p-0.5">
          {subTabs.map(t => (
            <button key={t.id} onClick={() => setSubTab(t.id)}
              className={clsx("flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-semibold font-mono rounded-md transition-colors",
                subTab === t.id ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
              )}>
              {t.icon}{t.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex gap-1">
          <button onClick={() => { setDataSourceOpen(true); marketApi.listFredSeries().then(r => setFredSeries(r.series)).catch(() => {}); }}
            className="flex items-center gap-1 px-2 py-1.5 rounded text-[10px] font-mono bg-indigo-800/60 border border-indigo-700/50 text-indigo-300 hover:bg-indigo-700">
            <DatabaseIcon size={12} />Data Sources
          </button>
          <button onClick={handleSeedData} disabled={seedLoading}
            className="flex items-center gap-1 px-2 py-1.5 rounded text-[10px] font-mono bg-slate-800 border border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-700 disabled:opacity-50">
            <Database size={12} />{seedLoading ? "Seeding..." : "Warm Cache"}
          </button>
          <button onClick={handleQuickStart}
            className="flex items-center gap-1 px-2 py-1.5 rounded text-[10px] font-mono bg-emerald-800 border border-emerald-700 text-emerald-300 hover:bg-emerald-700">
            <Zap size={12} />Quick Start
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {subTab === "run" && (
          <div className="max-w-3xl mx-auto space-y-4">
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
              <div className="flex items-center gap-2">
                <BarChart2 size={16} className="text-indigo-400" />
                <h2 className="text-sm font-semibold text-slate-200">Walk-Forward Backtest</h2>
                <button onClick={() => setShowParams(v => !v)}
                  className="ml-2 text-[10px] text-slate-500 hover:text-slate-300 font-mono">
                  {showParams ? "▲ hide params" : "▼ params"}
                </button>
                {running && progress && (
                  <div className="ml-auto flex items-center gap-2">
                    <div className="w-32 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div className="h-full bg-indigo-500 transition-all duration-500 rounded-full"
                           style={{ width: `${progress.pct}%` }} />
                    </div>
                    <span className="text-xs font-mono text-indigo-400 animate-pulse">
                      {progress.pct}% — {progress.msg.slice(0, 40)}
                    </span>
                  </div>
                )}
              </div>

              {selectedTickers.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[10px] text-slate-500 font-mono">Tickers:</span>
                  {selectedTickers.map(t => (
                    <span key={t} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-900/40 text-indigo-300 border border-indigo-700/50">{t}</span>
                  ))}
                  {selectedFred.length > 0 && (
                    <>
                      <span className="text-[10px] text-slate-500 font-mono ml-2">FRED:</span>
                      {selectedFred.map(f => (
                        <span key={f} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-300 border border-amber-700/50">{f}</span>
                      ))}
                    </>
                  )}
                  <span className="text-[10px] text-slate-600 font-mono ml-1">
                    {combineData ? "(combined)" : "(separate)"}
                  </span>
                </div>
              )}

              {seedSuccess && (
                <div className="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-950/30 border border-emerald-800 rounded p-2">
                  <Database size={12} /> Market data seeded successfully
                </div>
              )}
              {seedError && (
                <div className="flex items-center gap-1.5 text-xs text-amber-400 bg-amber-950/30 border border-amber-800 rounded p-2">
                  <AlertCircle size={12} /> {seedError}
                </div>
              )}
              {error && (
                <div className="flex items-center gap-1.5 text-xs text-red-400 bg-red-950/30 border border-red-800 rounded p-2">
                  <AlertCircle size={12} /> {error}
                </div>
              )}

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <LabeledInput label="Start"        type="date"   value={startDate}  onChange={setStartDate} />
                <LabeledInput label="End"          type="date"   value={endDate}    onChange={setEndDate} />
                <LabeledInput label="Capital ($)"  type="number" value={capital}    onChange={setCapital} />
                <div>
                  <div className="text-[10px] text-slate-400 mb-1 uppercase tracking-wider">Mode</div>
                  <select value={mode} onChange={e => setMode(e.target.value as RunMode)}
                    className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                    <option value="both">Both (KG vs baseline)</option>
                    <option value="grounded">KG-Grounded only</option>
                    <option value="ungrounded">Baseline only</option>
                  </select>
                </div>
              </div>

              {showParams && (
                <div className="grid grid-cols-3 gap-2 p-3 bg-slate-800/50 rounded-lg border border-slate-700">
                  <LabeledInput label="Rebal Freq (days)" type="number" value={rebalFreq} onChange={setRebalFreq} />
                  <LabeledInput label="Fee % (e.g. 0.001)" type="number" value={feePct}   onChange={setFeePct} />
                  <LabeledInput label="Slip % (e.g. 0.0005)" type="number" value={slipPct} onChange={setSlipPct} />
                </div>
              )}

              <div className="flex items-center gap-3">
                <button id="bt-run-btn" onClick={handleRun} disabled={running}
                  className={clsx("flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                    running ? "bg-slate-700 text-slate-500 cursor-not-allowed"
                            : "bg-indigo-600 hover:bg-indigo-500 text-white")}>
                  <Play size={14} className={running ? "animate-pulse" : ""} />
                  {running ? "Running…" : "Run Backtest"}
                </button>
                <button onClick={handleSeedData} disabled={seedLoading}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium bg-slate-700 hover:bg-slate-600 text-slate-300 disabled:opacity-50">
                  <Database size={12} /> {seedLoading ? "Seeding..." : "Pre-load Market Data"}
                </button>
              </div>
            </div>
          </div>
        )}

        {subTab === "results" && hasResults && (
          <div className="max-w-4xl mx-auto space-y-4">
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
              <div className="flex gap-0 border-b border-slate-700 overflow-x-auto">
                {resultSubTabs.map(t => {
                  const badge = t.id === "suggestions"
                    ? (suggestions ?? []).filter(s => s.status === "pending").length
                    : t.id === "trades" ? (primary?.n_trades ?? 0)
                    : 0;
                  return (
                    <button key={t.id} onClick={() => setResultTab(t.id)}
                      className={clsx("px-3 py-2 text-xs font-mono whitespace-nowrap transition-colors border-b-2 -mb-px",
                        resultTab === t.id
                          ? "border-indigo-500 text-indigo-400"
                          : "border-transparent text-slate-400 hover:text-slate-200")}>
                      {t.label}
                      {badge > 0 && (
                        <span className="ml-1 px-1.5 py-0.5 rounded-full bg-indigo-900 text-indigo-300 text-[9px]">
                          {badge}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              <div className="min-h-[300px]">
                {resultTab === "summary"     && <SummaryTab     g={grounded} u={ungrounded} />}
                {resultTab === "equity"      && <EquityTab      g={grounded} u={ungrounded} />}
                {resultTab === "drawdown"    && <DrawdownTab    g={grounded} u={ungrounded} />}
                {resultTab === "trades"      && <TradeLogTab    trades={primary?.trade_log ?? []} />}
                {resultTab === "strategies"  && <StrategyTab    g={grounded} u={ungrounded} />}
                {resultTab === "wf"          && <WalkFwdTab     g={grounded} />}
                {resultTab === "suggestions" && (
                  <SuggestionsTab
                    suggestions={suggestions ?? []}
                    onAction={async (id, action) => {
                      await agentApi.actionSuggestion(id, action);
                      refreshSuggestions?.();
                    }}
                  />
                )}
              </div>
            </div>
          </div>
        )}

        {subTab === "results" && !hasResults && (
          <div className="max-w-lg mx-auto">
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 text-center">
              <BarChart2 size={24} className="text-slate-600 mx-auto mb-2" />
              <p className="text-sm text-slate-500">No results yet</p>
              <p className="text-xs text-slate-600 mt-1">Run a backtest first to see results here.</p>
            </div>
          </div>
        )}

        {subTab === "optimize" && <OptimizeTab runId={primary?.start ?? null} />}
        {subTab === "compare"  && <CompareTab  runId={primary?.start ?? null} />}
        {subTab === "ablation" && <AblationTab runId={primary?.start ?? null} />}
      </div>

      {/* Data Source Picker Modal */}
      {dataSourceOpen && (
        <DataSourceModal
          fredSeries={fredSeries} selectedFred={selectedFred} setSelectedFred={setSelectedFred}
          selectedTickers={selectedTickers} setSelectedTickers={setSelectedTickers}
          tickerInput={tickerInput} setTickerInput={setTickerInput}
          combineData={combineData} setCombineData={setCombineData}
          startDate={startDate} endDate={endDate}
          dataPreview={dataPreview} setDataPreview={setDataPreview}
          dataLoading={dataLoading} setDataLoading={setDataLoading}
          dataError={dataError} setDataError={setDataError}
          onClose={() => setDataSourceOpen(false)}
        />
      )}
    </div>
  );
}

// ── Data Source Picker Modal ───────────────────────────────────────────────────
function DataSourceModal({
  fredSeries, selectedFred, setSelectedFred,
  selectedTickers, setSelectedTickers, tickerInput, setTickerInput,
  combineData, setCombineData,
  startDate, endDate,
  dataPreview, setDataPreview, dataLoading, setDataLoading, dataError, setDataError,
  onClose,
}: {
  fredSeries: { id: string; name: string }[];
  selectedFred: string[]; setSelectedFred: (v: string[]) => void;
  selectedTickers: string[]; setSelectedTickers: (v: string[]) => void;
  tickerInput: string; setTickerInput: (v: string) => void;
  combineData: boolean; setCombineData: (v: boolean) => void;
  startDate: string; endDate: string;
  dataPreview: { rows: number; tickers: string[]; preview: Record<string, unknown>[] | null } | null;
  setDataPreview: (v: { rows: number; tickers: string[]; preview: Record<string, unknown>[] | null } | null) => void;
  dataLoading: boolean; setDataLoading: (v: boolean) => void;
  dataError: string | null; setDataError: (v: string | null) => void;
  onClose: () => void;
}) {
  const addTicker = () => {
    const t = tickerInput.trim().toUpperCase();
    if (t && !selectedTickers.includes(t)) {
      setSelectedTickers([...selectedTickers, t]);
    }
    setTickerInput("");
  };

  const removeTicker = (t: string) => setSelectedTickers(selectedTickers.filter(x => x !== t));

  const toggleFred = (id: string) => {
    if (selectedFred.includes(id)) {
      setSelectedFred(selectedFred.filter(x => x !== id));
    } else {
      setSelectedFred([...selectedFred, id]);
    }
  };

  const previewData = async () => {
    if (selectedTickers.length === 0) return;
    setDataLoading(true);
    setDataError(null);
    try {
      const res = await marketApi.downloadData({
        tickers: selectedTickers,
        start: startDate,
        end: endDate,
        interval: "1d",
        fred_series: selectedFred,
        combine: combineData,
      });
      setDataPreview({
        rows: res.rows,
        tickers: res.tickers,
        preview: res.prices ? res.prices.slice(0, 5) : null,
      });
    } catch (e: unknown) {
      setDataError(e instanceof Error ? e.message : String(e));
    } finally {
      setDataLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-900 rounded-xl border border-slate-700 w-full max-w-2xl mx-4 shadow-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 sticky top-0 bg-slate-900 z-10">
          <div className="flex items-center gap-2">
            <DatabaseIcon size={14} className="text-indigo-400" />
            <span className="text-sm font-semibold text-slate-200">Data Sources</span>
          </div>
          <button onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-200"><X size={14} /></button>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 font-semibold">yfinance Tickers</div>
            <div className="flex items-center gap-2 mb-2">
              <input value={tickerInput} onChange={e => setTickerInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && addTicker()}
                placeholder="e.g. SPY, QQQ, BTC-USD, EURUSD=X"
                className="flex-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
              <button onClick={addTicker}
                className="px-2 py-1.5 rounded text-[10px] font-mono bg-indigo-700 hover:bg-indigo-600 text-white">
                + Add
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {selectedTickers.map(t => (
                <span key={t} className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-900/40 text-indigo-300 border border-indigo-700/50">
                  {t}
                  <button onClick={() => removeTicker(t)} className="text-indigo-400 hover:text-red-400"><X size={10} /></button>
                </span>
              ))}
              {selectedTickers.length === 0 && <span className="text-[10px] text-slate-600">No tickers added yet</span>}
            </div>
          </div>

          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 font-semibold">FRED Economic Data</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 max-h-40 overflow-y-auto">
              {fredSeries.map(s => (
                <label key={s.id} className="flex items-center gap-1.5 text-[10px] font-mono text-slate-300 cursor-pointer hover:bg-slate-800 rounded px-1.5 py-1">
                  <input type="checkbox" checked={selectedFred.includes(s.id)} onChange={() => toggleFred(s.id)}
                    className="accent-indigo-500" />
                  <span className="truncate">{s.id}</span>
                  <span className="text-slate-500 truncate hidden sm:inline">— {s.name}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
              <input type="checkbox" checked={combineData} onChange={e => setCombineData(e.target.checked)}
                className="accent-indigo-500" />
              Combine into single table
            </label>
            <span className="text-[10px] text-slate-500">(uncheck to get separate arrays)</span>
          </div>

          <button onClick={previewData} disabled={dataLoading || selectedTickers.length === 0}
            className={clsx("flex items-center gap-2 px-3 py-1.5 rounded text-xs font-medium",
              dataLoading ? "bg-slate-700 text-slate-500" : "bg-indigo-700 hover:bg-indigo-600 text-white")}>
            <LineChartIcon size={12} /> {dataLoading ? "Loading..." : "Preview Data"}
          </button>

          {dataError && <div className="text-xs text-red-400 bg-red-950/30 border border-red-800 rounded p-2">{dataError}</div>}

          {dataPreview && (
            <div className="space-y-2">
              <div className="text-xs text-emerald-400 font-mono">
                {dataPreview.rows} rows × {dataPreview.tickers.length} tickers
              </div>
              {dataPreview.preview && dataPreview.preview.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-[10px] font-mono">
                    <thead>
                      <tr className="text-slate-500 border-b border-slate-700">
                        <th className="text-left py-1 px-1">date</th>
                        {dataPreview.tickers.map(t => <th key={t} className="text-right py-1 px-1">{t}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {dataPreview.preview.map((row, i) => (
                        <tr key={i} className="border-t border-slate-800">
                          <td className="py-0.5 px-1 text-slate-400">{String(row.date).slice(0, 10)}</td>
                          {dataPreview.tickers.map(t => (
                            <td key={t} className="py-0.5 px-1 text-right text-slate-300">
                              {row[t] !== null && row[t] !== undefined ? Number(row[t]).toFixed(2) : "—"}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Summary tab ────────────────────────────────────────────────────────────────
function SummaryTab({ g, u }: { g: BacktestResult | null; u: BacktestResult | null }) {
  const metrics: { label: string; key: keyof BacktestResult; fmt: (v: number) => string; good: "high" | "low" }[] = [
    { label: "Total Return",   key: "total_return",   fmt: fmtPct,          good: "high" },
    { label: "Sharpe Ratio",   key: "sharpe_ratio",   fmt: v => fmtN(v, 2), good: "high" },
    { label: "Calmar Ratio",   key: "calmar_ratio",   fmt: v => fmtN(v, 2), good: "high" },
    { label: "Max Drawdown",   key: "max_drawdown",   fmt: fmtPct,          good: "low"  },
    { label: "Ann. Vol",       key: "ann_volatility", fmt: fmtPct,          good: "low"  },
    { label: "Final NAV",      key: "final_nav",      fmt: fmt$,            good: "high" },
    { label: "# Trades",       key: "n_trades",       fmt: String,          good: "high" },
    { label: "Win Rate",       key: "win_rate",       fmt: fmtPct,          good: "high" },
    { label: "Profit Factor",  key: "profit_factor",  fmt: v => fmtN(v, 2), good: "high" },
    { label: "Avg Hold Days",  key: "avg_hold_days",  fmt: v => `${v}d`,    good: "high" },
  ];

  return (
    <div className="space-y-4">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="text-slate-400 border-b border-slate-700">
            <th className="text-left py-2">Metric</th>
            <th className="text-right py-2 text-indigo-400">KG-Grounded</th>
            {u && <th className="text-right py-2 text-slate-400">Baseline</th>}
            {u && <th className="text-right py-2 text-slate-500">Δ</th>}
          </tr>
        </thead>
        <tbody>
          {metrics.map(m => {
            const gv = g ? Number(g[m.key]) : null;
            const uv = u ? Number(u[m.key]) : null;
            const delta = gv !== null && uv !== null ? gv - uv : null;
            const pos = delta !== null ? (m.good === "high" ? delta >= 0 : delta <= 0) : null;
            return (
              <tr key={m.key} className="border-t border-slate-800">
                <td className="py-1.5 text-slate-400">{m.label}</td>
                <td className="py-1.5 text-right text-indigo-300">{gv !== null ? m.fmt(gv) : "—"}</td>
                {u && <td className="py-1.5 text-right text-slate-400">{uv !== null ? m.fmt(uv) : "—"}</td>}
                {u && <td className={clsx("py-1.5 text-right font-bold",
                  pos === null ? "text-slate-600" : pos ? "text-emerald-400" : "text-red-400")}>
                  {delta !== null ? `${delta >= 0 ? "+" : ""}${m.fmt(delta)}` : "—"}
                </td>}
              </tr>
            );
          })}
        </tbody>
      </table>

      {g?.jk_p_value != null && (
        <div className={clsx("rounded border px-3 py-2 text-xs font-mono",
          g.jk_significant ? "bg-emerald-950 border-emerald-700 text-emerald-300"
                           : "bg-slate-800 border-slate-600 text-slate-400")}>
          <span className="font-bold">Jobson-Korkie test: </span>
          {g.jk_significant
            ? `Statistically significant outperformance vs benchmark (p = ${g.jk_p_value.toFixed(4)})`
            : `Not statistically significant vs benchmark (p = ${g.jk_p_value.toFixed(4)})`}
        </div>
      )}

      {g?.regime_distribution && Object.keys(g.regime_distribution).length > 0 && (
        <div>
          <div className="text-[10px] text-slate-500 uppercase mb-2">Regime Distribution</div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(g.regime_distribution).map(([regime, pct]) => (
              <span key={regime} className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
                {regime} {fmtPct(pct)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Equity curve tab ──────────────────────────────────────────────────────────
function EquityTab({ g, u }: { g: BacktestResult | null; u: BacktestResult | null }) {
  const data = mergeByDate(
    g?.equity_curve?.map(p => ({ date: p.date, grounded: p.nav })) ?? [],
    u?.equity_curve?.map(p => ({ date: p.date, ungrounded: p.nav })) ?? [],
    g?.benchmark_curve?.map(p => ({ date: p.date, benchmark: p.nav })) ?? [],
  );
  if (!data.length) return <Empty />;
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#64748b" }} tickLine={false} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 9, fill: "#64748b" }} tickLine={false} tickFormatter={v => `$${(v/1000).toFixed(1)}k`} />
        <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                 formatter={(v: number, name: string) => [fmt$(v), name]} />
        <Legend wrapperStyle={{ fontSize: 10, color: "#94a3b8" }} />
        {g && <Line type="monotone" dataKey="grounded"  name="KG-Grounded" stroke="#6366f1" strokeWidth={2} dot={false} connectNulls />}
        {u && <Line type="monotone" dataKey="ungrounded" name="Baseline"   stroke="#475569" strokeWidth={1.5} dot={false} connectNulls strokeDasharray="4 2" />}
        {g?.benchmark_curve && <Line type="monotone" dataKey="benchmark" name="SPY Buy&Hold" stroke="#f59e0b" strokeWidth={1.5} dot={false} connectNulls strokeDasharray="6 3" />}
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Drawdown tab ──────────────────────────────────────────────────────────────
function DrawdownTab({ g, u }: { g: BacktestResult | null; u: BacktestResult | null }) {
  const data = mergeByDate(
    g?.drawdown_series?.map(p => ({ date: p.date, grounded: p.dd })) ?? [],
    u?.drawdown_series?.map(p => ({ date: p.date, ungrounded: p.dd })) ?? [],
  );
  if (!data.length) return <Empty />;
  return (
    <div className="space-y-1">
      <div className="text-[10px] text-slate-500">Underwater curve (% below high-water mark)</div>
      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#64748b" }} tickLine={false} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 9, fill: "#64748b" }} tickLine={false} tickFormatter={v => `${v.toFixed(0)}%`} />
          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                   formatter={(v: number, name: string) => [`${v.toFixed(2)}%`, name]} />
          <ReferenceLine y={0} stroke="#475569" />
          {g && <Area type="monotone" dataKey="grounded"   name="KG-Grounded" stroke="#6366f1" fill="url(#ddGrad)" strokeWidth={2} dot={false} connectNulls />}
          {u && <Line type="monotone" dataKey="ungrounded" name="Baseline"     stroke="#475569" strokeWidth={1.5} dot={false} connectNulls strokeDasharray="4 2" />}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Trade log tab ─────────────────────────────────────────────────────────────
function TradeLogTab({ trades }: { trades: TradeLogEntry[] }) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<keyof TradeLogEntry>("exit_date");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);

  const filtered = trades
    .filter(t => !filter || t.ticker.includes(filter.toUpperCase()) || t.strategy.includes(filter) || t.regime.includes(filter))
    .sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      const cmp = typeof av === "number" && typeof bv === "number"
        ? av - bv
        : String(av).localeCompare(String(bv));
      return sortDir * (cmp > 0 ? 1 : cmp < 0 ? -1 : 0);
    });

  const toggleSort = (key: keyof TradeLogEntry) => {
    if (sortKey === key) setSortDir(d => d === 1 ? -1 : 1);
    else { setSortKey(key); setSortDir(-1); }
  };

  if (!trades.length) return <Empty msg="No closed trades yet" />;

  const totalPnl = trades.reduce((s, t) => s + t.pnl, 0);
  const winners  = trades.filter(t => t.pnl > 0).length;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <input value={filter} onChange={e => setFilter(e.target.value)}
          placeholder="Filter by ticker / strategy / regime…"
          className="flex-1 bg-slate-800 border border-slate-700 text-xs text-slate-300 rounded px-2 py-1.5" />
        <span className="text-xs font-mono text-slate-400">{filtered.length}/{trades.length} trades</span>
        <span className={clsx("text-xs font-mono font-bold", totalPnl >= 0 ? "text-emerald-400" : "text-red-400")}>
          Net P&L: {totalPnl >= 0 ? "+" : ""}{fmt$(totalPnl)}
        </span>
        <span className="text-xs font-mono text-slate-400">WR: {fmtPct(winners / trades.length)}</span>
      </div>
      <div className="overflow-auto max-h-64">
        <table className="w-full text-xs font-mono">
          <thead className="sticky top-0 bg-slate-800 z-10">
            <tr className="text-slate-400">
              {(["ticker","strategy","regime","entry_date","exit_date","entry_price","exit_price","qty","pnl","hold_days"] as (keyof TradeLogEntry)[]).map(k => (
                <th key={k} onClick={() => toggleSort(k)}
                  className="py-1.5 px-2 text-left text-[10px] uppercase tracking-wider cursor-pointer hover:text-slate-200">
                  {k.replace(/_/g, " ")}{sortKey === k ? (sortDir === 1 ? " ↑" : " ↓") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((t, i) => (
              <tr key={i} className="border-t border-slate-800 hover:bg-slate-800/50">
                <td className="py-1 px-2 font-bold text-slate-100">{t.ticker}</td>
                <td className="py-1 px-2 text-slate-400 max-w-[100px] truncate" title={t.strategy}>{t.strategy}</td>
                <td className="py-1 px-2 text-slate-500 text-[10px]">{t.regime}</td>
                <td className="py-1 px-2 text-slate-500">{t.entry_date}</td>
                <td className="py-1 px-2 text-slate-500">{t.exit_date}</td>
                <td className="py-1 px-2 text-right text-slate-400">{fmt$(t.entry_price)}</td>
                <td className="py-1 px-2 text-right text-slate-400">{fmt$(t.exit_price)}</td>
                <td className="py-1 px-2 text-right text-slate-300">{t.qty.toFixed(4)}</td>
                <td className={clsx("py-1 px-2 text-right font-bold", t.pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                  {t.pnl >= 0 ? "+" : ""}{fmt$(t.pnl)}
                </td>
                <td className="py-1 px-2 text-right text-slate-400">{t.hold_days}d</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Strategy breakdown tab ────────────────────────────────────────────────────
function StrategyTab({ g, u }: { g: BacktestResult | null; u: BacktestResult | null }) {
  const data = g?.strategy_breakdown ?? u?.strategy_breakdown ?? [];
  if (!data.length) return <Empty />;
  return (
    <div className="space-y-4">
      <ResponsiveContainer width="100%" height={Math.max(100, data.length * 36)}>
        <BarChart layout="vertical" data={data} margin={{ top: 0, right: 60, bottom: 0, left: 120 }}>
          <XAxis type="number" tick={{ fontSize: 9, fill: "#64748b" }} tickFormatter={v => fmt$(v)} />
          <YAxis type="category" dataKey="strategy" tick={{ fontSize: 10, fill: "#cbd5e1" }} width={115} />
          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                   formatter={(v: number, name: string) => [name === "total_pnl" ? fmt$(v) : fmtPct(v), name]} />
          <ReferenceLine x={0} stroke="#475569" />
          <Bar dataKey="total_pnl" name="Total P&L" radius={[0, 3, 3, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.total_pnl >= 0 ? "#6366f1" : "#ef4444"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="text-slate-400 border-b border-slate-700">
            <th className="text-left py-1.5">Strategy</th>
            <th className="text-right py-1.5">P&L</th>
            <th className="text-right py-1.5">Trades</th>
            <th className="text-right py-1.5">Win Rate</th>
            <th className="text-right py-1.5">Avg P&L</th>
          </tr>
        </thead>
        <tbody>
          {data.sort((a, b) => b.total_pnl - a.total_pnl).map((s, i) => (
            <tr key={i} className="border-t border-slate-800">
              <td className="py-1.5 text-slate-300">{s.strategy}</td>
              <td className={clsx("py-1.5 text-right font-bold", s.total_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                {s.total_pnl >= 0 ? "+" : ""}{fmt$(s.total_pnl)}
              </td>
              <td className="py-1.5 text-right text-slate-400">{s.n_trades}</td>
              <td className={clsx("py-1.5 text-right", s.win_rate > 0.5 ? "text-emerald-400" : "text-red-400")}>{fmtPct(s.win_rate)}</td>
              <td className={clsx("py-1.5 text-right", s.avg_pnl >= 0 ? "text-slate-300" : "text-red-400")}>{fmt$(s.avg_pnl)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Walk-forward windows tab ──────────────────────────────────────────────────
function WalkFwdTab({ g }: { g: BacktestResult | null }) {
  const windows = g?.walk_forward_windows ?? [];
  if (!windows.length) return <Empty msg="Walk-forward windows not available for this date range" />;
  return (
    <div className="space-y-3">
      <div className="text-[10px] text-slate-500">Out-of-sample performance per walk-forward window.</div>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={windows} margin={{ top: 4, right: 8, bottom: 0, left: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="id" tick={{ fontSize: 9, fill: "#64748b" }} tickFormatter={v => `W${v + 1}`} />
          <YAxis tick={{ fontSize: 9, fill: "#64748b" }} tickFormatter={v => fmtPct(v)} />
          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                   formatter={(v: number, name: string) => [name === "total_return" ? fmtPct(v) : fmtN(v, 2), name]} />
          <ReferenceLine y={0} stroke="#475569" />
          <Bar dataKey="total_return" name="Return" radius={[3, 3, 0, 0]}>
            {windows.map((w, i) => (
              <Cell key={i} fill={w.total_return >= 0 ? "#6366f1" : "#ef4444"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Suggestions tab ───────────────────────────────────────────────────────────
function SuggestionsTab({ suggestions, onAction }: {
  suggestions: TradeSuggestion[];
  onAction: (id: string, action: string) => Promise<void>;
}) {
  const [pending, setPending] = useState<string>("");
  const act = async (id: string, action: string) => {
    setPending(id + action);
    await onAction(id, action);
    setPending("");
  };
  const queue = suggestions.filter(s => s.status === "pending");
  const acted = suggestions.filter(s => s.status !== "pending");

  return (
    <div className="space-y-3">
      {queue.length === 0 && acted.length === 0 && (
        <div className="text-xs text-slate-500 py-4 text-center">No suggestions yet — run a backtest to generate KG-backed trade ideas.</div>
      )}
      {queue.map(s => (
        <div key={s.id} className="rounded-lg border border-indigo-800/50 bg-indigo-950/30 p-3 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-indigo-300">{s.ticker}</span>
                <span className={clsx("text-xs font-bold px-1.5 py-0.5 rounded",
                  s.direction === "buy" ? "bg-emerald-900/60 text-emerald-300" : "bg-red-900/60 text-red-300")}>
                  {s.direction.toUpperCase()}
                </span>
                <span className="text-[10px] text-slate-500 font-mono">{s.regime}</span>
              </div>
              <div className="text-xs text-slate-400 mt-0.5">{s.strategy}</div>
            </div>
            <div className="flex gap-2 shrink-0">
              <button disabled={!!pending} onClick={() => act(s.id, "approve")}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-medium disabled:opacity-50">
                <CheckCircle size={12} /> Approve
              </button>
              <button disabled={!!pending} onClick={() => act(s.id, "reject")}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs font-medium disabled:opacity-50">
                <XCircle size={12} /> Reject
              </button>
            </div>
          </div>
          <div className="text-[11px] text-slate-400 leading-relaxed">{s.rationale}</div>
          <div className="flex gap-4 text-[10px] font-mono text-slate-500">
            <span>Backtest P&L: <span className="text-emerald-400">{fmt$(s.backtest_pnl)}</span></span>
            <span>Trades: {s.backtest_trades}</span>
            <span>Win Rate: <span className={s.win_rate > 0.5 ? "text-emerald-400" : "text-red-400"}>{fmtPct(s.win_rate)}</span></span>
          </div>
        </div>
      ))}
      {acted.length > 0 && (
        <div className="mt-4 space-y-1">
          <div className="text-[10px] text-slate-600 uppercase tracking-wider mb-2">Actioned</div>
          {acted.map(s => (
            <div key={s.id} className="flex items-center gap-2 px-3 py-1.5 rounded border border-slate-800 bg-slate-800/30 text-xs font-mono">
              {s.status === "approve" ? <CheckCircle size={11} className="text-emerald-500" /> : <XCircle size={11} className="text-slate-500" />}
              <span className="text-slate-400">{s.ticker}</span>
              <span className="text-slate-500">{s.strategy}</span>
              <span className={clsx("ml-auto text-[10px]", s.status === "approve" ? "text-emerald-500" : "text-slate-600")}>
                {s.status.toUpperCase()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Optimize tab ──────────────────────────────────────────────────────────────
function OptimizeTab({ runId }: { runId: string | null }) {
  const [strategy, setStrategy] = useState("");
  const [paramSpec, setParamSpec] = useState('{"lookback": [10, 20, 30], "threshold": [0.5, 0.7]}');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestOptimizeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (!strategy.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const params = JSON.parse(paramSpec);
      const res = await researchApi.backtestOptimize(strategy, params);
      setResult(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
        <div className="flex items-center gap-2">
          <Sliders size={14} className="text-indigo-400" />
          <span className="text-sm font-semibold text-slate-200">Parameter Grid Search</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">Strategy Name</label>
            <input value={strategy} onChange={e => setStrategy(e.target.value)}
              placeholder="e.g. Momentum Breakout"
              className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider">Parameter Grid (JSON)</label>
            <textarea value={paramSpec} onChange={e => setParamSpec(e.target.value)} rows={3}
              className="w-full mt-1 bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 font-mono" />
          </div>
        </div>
        <button onClick={run} disabled={loading || !strategy.trim()}
          className={clsx("flex items-center gap-2 px-3 py-1.5 rounded text-xs font-medium",
            loading ? "bg-slate-700 text-slate-500" : "bg-indigo-600 hover:bg-indigo-500 text-white")}>
          <Sliders size={12} /> {loading ? "Optimizing..." : "Run Grid Search"}
        </button>
        {error && <div className="text-xs text-red-400 font-mono">{error}</div>}
        {result && (
          <div className="space-y-3">
            <div className="rounded-lg bg-emerald-950/40 border border-emerald-800/60 p-3">
              <span className="text-xs text-emerald-300 font-bold">Optimal Params</span>
              <div className="text-xs font-mono text-emerald-200 mt-1">{JSON.stringify(result.optimal)}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Compare tab ───────────────────────────────────────────────────────────────
function CompareTab({ runId }: { runId: string | null }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestCompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    researchApi.backtestCompare(runId).then(setResult).catch(e => setError(String(e))).finally(() => setLoading(false));
  }, [runId]);

  if (loading) return <div className="text-xs text-slate-500 animate-pulse">Loading comparison...</div>;
  if (error) return <div className="text-xs text-red-400">{error}</div>;
  if (!result) return <Empty msg="Run a backtest first to enable comparison" />;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
        <div className="flex items-center gap-2">
          <GitCompare size={14} className="text-indigo-400" />
          <span className="text-sm font-semibold text-slate-200">KG vs Baseline Comparison</span>
        </div>
        {result.delta && (
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg bg-slate-800 border border-slate-700 p-3 text-center">
              <div className="text-[10px] text-slate-500 uppercase">Sharpe Δ</div>
              <div className={clsx("text-lg font-bold font-mono", result.delta.sharpe_delta >= 0 ? "text-emerald-400" : "text-red-400")}>
                {result.delta.sharpe_delta >= 0 ? "+" : ""}{result.delta.sharpe_delta.toFixed(4)}
              </div>
            </div>
            <div className="rounded-lg bg-slate-800 border border-slate-700 p-3 text-center">
              <div className="text-[10px] text-slate-500 uppercase">Return Δ</div>
              <div className={clsx("text-lg font-bold font-mono", result.delta.return_delta >= 0 ? "text-emerald-400" : "text-red-400")}>
                {result.delta.return_delta >= 0 ? "+" : ""}{fmtPct(result.delta.return_delta)}
              </div>
            </div>
            <div className="rounded-lg bg-slate-800 border border-slate-700 p-3 text-center">
              <div className="text-[10px] text-slate-500 uppercase">Drawdown Δ</div>
              <div className={clsx("text-lg font-bold font-mono", result.delta.drawdown_delta <= 0 ? "text-emerald-400" : "text-red-400")}>
                {result.delta.drawdown_delta >= 0 ? "+" : ""}{fmtPct(result.delta.drawdown_delta)}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Ablation tab ──────────────────────────────────────────────────────────────
function AblationTab({ runId }: { runId: string | null }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ primary: Record<string, unknown>; ablation_matrix: unknown[]; configs_compared: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    researchApi.backtestAblation(runId).then(setResult).catch(e => setError(String(e))).finally(() => setLoading(false));
  }, [runId]);

  if (loading) return <div className="text-xs text-slate-500 animate-pulse">Loading ablation matrix...</div>;
  if (error) return <div className="text-xs text-red-400">{error}</div>;
  if (!result) return <Empty msg="No ablation data available" />;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-4">
        <div className="flex items-center gap-2">
          <Layers size={14} className="text-indigo-400" />
          <span className="text-sm font-semibold text-slate-200">Ablation Matrix ({result.configs_compared} configs)</span>
        </div>
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function mergeByDate(...arrays: { date: string; [k: string]: unknown }[][]): Record<string, unknown>[] {
  const map = new Map<string, Record<string, unknown>>();
  for (const arr of arrays) {
    for (const row of arr) {
      const existing = map.get(row.date) ?? { date: row.date };
      map.set(row.date, { ...existing, ...row });
    }
  }
  return Array.from(map.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

function Empty({ msg = "No data available" }: { msg?: string }) {
  return <div className="flex items-center justify-center h-40 text-slate-500 text-sm">{msg}</div>;
}

function LabeledInput({ label, type, value, onChange }: { label: string; type: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <div className="text-[10px] text-slate-400 mb-1 uppercase tracking-wider">{label}</div>
      <input type={type} value={value} onChange={e => onChange(e.target.value)}
        className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
    </div>
  );
}