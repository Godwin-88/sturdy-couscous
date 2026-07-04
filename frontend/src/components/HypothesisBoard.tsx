// GraphAlpha Hypothesis Board
// Full lifecycle: IDEA → TESTING → VALIDATED → REJECTED → DEPLOYED → MONITORING

import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import clsx from "clsx";
import {
  Brain, Plus, Trash2, Play, Send, CheckCircle, XCircle,
  AlertTriangle, BarChart2, Activity, TrendingUp, ShieldAlert,
  ExternalLink, RefreshCw, ChevronDown, ChevronRight,
} from "lucide-react";
import { hypothesisApi, type Hypothesis, type HypothesisTestLog } from "@/lib/api";
import { fmtN, fmtPct } from "@/lib/utils";

interface Props {
  initialMode?: "view" | "create";
}

const STATUS_COLORS: Record<string, string> = {
  IDEA: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  TESTING: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  VALIDATED: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  REJECTED: "text-red-400 border-red-500/30 bg-red-500/10",
  DEPLOYED: "text-purple-400 border-purple-500/30 bg-purple-500/10",
  MONITORING: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
};

const STATUS_ORDER = ["IDEA", "TESTING", "VALIDATED", "REJECTED", "DEPLOYED", "MONITORING"];

export default function HypothesisBoard({ initialMode = "view" }: Props) {
  const [searchParams] = useSearchParams();
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [selected, setSelected] = useState<Hypothesis | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<"view" | "create">(initialMode);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [mtContext, setMtContext] = useState<{ total_tests_logged: number; active_hypotheses: number; suggested_correction: string } | null>(null);

  // Create form state
  const [formTitle, setFormTitle] = useState(searchParams.get("ticker") ? `"${searchParams.get("ticker")}" signal predicts return` : "");
  const [formDesc, setFormDesc] = useState("");
  const [formSeries, setFormSeries] = useState(searchParams.get("series") || "");
  const [formBenchmark, setFormBenchmark] = useState("");
  const [formRegime, setFormRegime] = useState("");
  const [formStart, setFormStart] = useState("");
  const [formEnd, setFormEnd] = useState("");

  const load = () => {
    setLoading(true);
    Promise.all([
      hypothesisApi.list(statusFilter || undefined),
      hypothesisApi.multipleTestingContext(),
    ]).then(([h, ctx]) => {
      setHypotheses(h);
      setMtContext(ctx);
    }).catch(() => null).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [statusFilter]);

  const handleCreate = async () => {
    if (!formTitle.trim() || !formSeries.trim()) return;
    try {
      const result = await hypothesisApi.create({
        title: formTitle,
        description: formDesc || undefined,
        primary_series: formSeries,
        benchmark_series: formBenchmark || undefined,
        regime_filter: formRegime || undefined,
        test_window_start: formStart || undefined,
        test_window_end: formEnd || undefined,
      });
      setMode("view");
      load();
      // Select the newly created hypothesis
      const h = await hypothesisApi.get(result.hypothesis_id);
      setSelected(h);
    } catch (e) {
      alert("Failed to create hypothesis");
    }
  };

  const handleStatusTransition = async (id: string, newStatus: string) => {
    try {
      await hypothesisApi.update(id, { status: newStatus });
      load();
      if (selected?.hypothesis_id === id) {
        const h = await hypothesisApi.get(id);
        setSelected(h);
      }
    } catch (e) {
      alert("Failed to update status");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this hypothesis and all attached evidence?")) return;
    try {
      await hypothesisApi.delete(id);
      if (selected?.hypothesis_id === id) setSelected(null);
      load();
    } catch (e) {
      alert("Failed to delete");
    }
  };

  const handleDeployToBacktest = async (id: string) => {
    try {
      const result = await hypothesisApi.deployToBacktest(id);
      alert(`Deployed to backtest: ${result.backtest_run_id}`);
      load();
    } catch (e) {
      alert("Failed to deploy to backtest");
    }
  };

  const handleDeployToPaper = async (id: string) => {
    if (!confirm("Deploy this hypothesis as a live paper-trading signal weight?")) return;
    try {
      const result = await hypothesisApi.deployToPaper(id);
      alert(`Deployed to paper trading via ${result.channel}`);
      load();
    } catch (e) {
      alert("Failed to deploy to paper");
    }
  };

  return (
    <div className="h-full flex gap-3">
      {/* ── Left: Hypothesis list ────────────────────────────────────────── */}
      <div className="w-80 shrink-0 flex flex-col gap-3 overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain size={16} className="text-purple-400" />
            <span className="text-sm font-bold text-slate-100 font-mono">Hypothesis Board</span>
          </div>
          <div className="flex items-center gap-1">
            <button onClick={load} className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200">
              <RefreshCw size={13} />
            </button>
            <button onClick={() => setMode("create")} className="flex items-center gap-1 px-2 py-1.5 text-xs font-mono rounded bg-purple-600/20 text-purple-400 hover:bg-purple-600/30 border border-purple-500/30">
              <Plus size={12} /> New
            </button>
          </div>
        </div>

        {/* Multiple testing context */}
        {mtContext && mtContext.active_hypotheses > 1 && (
          <div className="rounded-lg border border-amber-800/50 bg-amber-950/20 p-2 text-[10px] font-mono text-amber-300">
            ⚠ {mtContext.active_hypotheses} active hypotheses · {mtContext.total_tests_logged} tests logged
            <br />Suggested correction: {mtContext.suggested_correction}
          </div>
        )}

        {/* Status filter */}
        <div className="flex flex-wrap gap-1">
          <button onClick={() => setStatusFilter("")}
            className={clsx("px-2 py-1 text-[10px] font-mono rounded border transition-colors",
              !statusFilter ? "border-slate-500 text-slate-200 bg-slate-800" : "border-slate-700 text-slate-400 hover:text-slate-200"
            )}>All</button>
          {STATUS_ORDER.map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={clsx("px-2 py-1 text-[10px] font-mono rounded border transition-colors",
                statusFilter === s ? STATUS_COLORS[s] : "border-slate-700 text-slate-400 hover:text-slate-200"
              )}>{s}</button>
          ))}
        </div>

        {/* Hypothesis list */}
        {loading ? (
          <div className="text-xs text-slate-500 animate-pulse text-center py-8">Loading...</div>
        ) : hypotheses.length === 0 ? (
          <div className="text-xs text-slate-500 text-center py-8">
            No hypotheses yet. Click "New" to create one.
          </div>
        ) : (
          <div className="space-y-1">
            {hypotheses.map(h => (
              <button
                key={h.hypothesis_id}
                onClick={() => { setSelected(h); setMode("view"); }}
                className={clsx(
                  "w-full text-left p-2.5 rounded-lg border transition-colors",
                  selected?.hypothesis_id === h.hypothesis_id
                    ? "border-purple-500/50 bg-purple-500/10"
                    : "border-slate-700 bg-slate-900 hover:bg-slate-800"
                )}
              >
                <div className="flex items-center gap-2">
                  <span className={clsx("text-[10px] font-mono px-1.5 py-0.5 rounded border", STATUS_COLORS[h.status] || "text-slate-400")}>
                    {h.status}
                  </span>
                  <span className="text-xs text-slate-400 font-mono truncate">{h.primary_series}</span>
                </div>
                <div className="text-xs font-medium text-slate-200 mt-1 truncate">{h.title}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">
                  {new Date(h.created_at).toLocaleDateString()}
                  {h.test_log && h.test_log.length > 0 && ` · ${h.test_log.length} tests`}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Right: Detail / Create form ──────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {mode === "create" ? (
          <CreateForm
            formTitle={formTitle} setFormTitle={setFormTitle}
            formDesc={formDesc} setFormDesc={setFormDesc}
            formSeries={formSeries} setFormSeries={setFormSeries}
            formBenchmark={formBenchmark} setFormBenchmark={setFormBenchmark}
            formRegime={formRegime} setFormRegime={setFormRegime}
            formStart={formStart} setFormStart={setFormStart}
            formEnd={formEnd} setFormEnd={setFormEnd}
            onSubmit={handleCreate}
            onCancel={() => setMode("view")}
          />
        ) : selected ? (
          <HypothesisDetail
            hypothesis={selected}
            onStatusTransition={handleStatusTransition}
            onDelete={handleDelete}
            onDeployToBacktest={handleDeployToBacktest}
            onDeployToPaper={handleDeployToPaper}
            onRefresh={() => {
              hypothesisApi.get(selected.hypothesis_id).then(setSelected);
            }}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-slate-500 text-xs font-mono">
            Select a hypothesis or create a new one
          </div>
        )}
      </div>
    </div>
  );
}

// ── Create Form ──────────────────────────────────────────────────────────────
function CreateForm({
  formTitle, setFormTitle,
  formDesc, setFormDesc,
  formSeries, setFormSeries,
  formBenchmark, setFormBenchmark,
  formRegime, setFormRegime,
  formStart, setFormStart,
  formEnd, setFormEnd,
  onSubmit, onCancel,
}: {
  formTitle: string; setFormTitle: (v: string) => void;
  formDesc: string; setFormDesc: (v: string) => void;
  formSeries: string; setFormSeries: (v: string) => void;
  formBenchmark: string; setFormBenchmark: (v: string) => void;
  formRegime: string; setFormRegime: (v: string) => void;
  formStart: string; setFormStart: (v: string) => void;
  formEnd: string; setFormEnd: (v: string) => void;
  onSubmit: () => void; onCancel: () => void;
}) {
  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <div className="flex items-center gap-2">
        <Brain size={16} className="text-purple-400" />
        <span className="text-sm font-bold text-slate-100 font-mono">New Hypothesis</span>
      </div>

      <div className="space-y-3">
        <div>
          <label className="text-[10px] text-slate-500 uppercase font-semibold">Title *</label>
          <input value={formTitle} onChange={e => setFormTitle(e.target.value)}
            className="w-full mt-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:border-purple-500"
            placeholder='e.g. "XLE signal predicts return in HighVolatility regime"' />
        </div>

        <div>
          <label className="text-[10px] text-slate-500 uppercase font-semibold">Description</label>
          <textarea value={formDesc} onChange={e => setFormDesc(e.target.value)} rows={3}
            className="w-full mt-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:border-purple-500"
            placeholder="Describe the hypothesis..." />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] text-slate-500 uppercase font-semibold">Primary Series *</label>
            <input value={formSeries} onChange={e => setFormSeries(e.target.value)}
              className="w-full mt-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:border-purple-500"
              placeholder="e.g. price:XLE" />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase font-semibold">Benchmark Series</label>
            <input value={formBenchmark} onChange={e => setFormBenchmark(e.target.value)}
              className="w-full mt-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:border-purple-500"
              placeholder="e.g. price:SPY" />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-[10px] text-slate-500 uppercase font-semibold">Regime Filter</label>
            <input value={formRegime} onChange={e => setFormRegime(e.target.value)}
              className="w-full mt-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:border-purple-500"
              placeholder="e.g. HighVolatility" />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase font-semibold">Test Window Start</label>
            <input type="date" value={formStart} onChange={e => setFormStart(e.target.value)}
              className="w-full mt-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-purple-500" />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase font-semibold">Test Window End</label>
            <input type="date" value={formEnd} onChange={e => setFormEnd(e.target.value)}
              className="w-full mt-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-purple-500" />
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 pt-2">
        <button onClick={onSubmit}
          className="flex items-center gap-1.5 px-4 py-2 text-xs font-mono font-medium rounded-lg bg-purple-600 text-white hover:bg-purple-500 transition-colors">
          <Brain size={13} /> Create Hypothesis
        </button>
        <button onClick={onCancel}
          className="px-4 py-2 text-xs font-mono text-slate-400 hover:text-slate-200 transition-colors">
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── Hypothesis Detail ────────────────────────────────────────────────────────
function HypothesisDetail({
  hypothesis,
  onStatusTransition,
  onDelete,
  onDeployToBacktest,
  onDeployToPaper,
  onRefresh,
}: {
  hypothesis: Hypothesis;
  onStatusTransition: (id: string, status: string) => void;
  onDelete: (id: string) => void;
  onDeployToBacktest: (id: string) => void;
  onDeployToPaper: (id: string) => void;
  onRefresh: () => void;
}) {
  const h = hypothesis;
  const currentIdx = STATUS_ORDER.indexOf(h.status);
  const nextStatus = currentIdx >= 0 && currentIdx < STATUS_ORDER.length - 1 ? STATUS_ORDER[currentIdx + 1] : null;

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className={clsx("text-[10px] font-mono px-1.5 py-0.5 rounded border", STATUS_COLORS[h.status])}>
              {h.status}
            </span>
            <span className="text-xs text-slate-500 font-mono">{h.primary_series}</span>
          </div>
          <h2 className="text-base font-bold text-slate-100">{h.title}</h2>
          {h.description && <p className="text-xs text-slate-400">{h.description}</p>}
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onRefresh} className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200">
            <RefreshCw size={13} />
          </button>
          <button onClick={() => onDelete(h.hypothesis_id)} className="p-1.5 rounded hover:bg-red-900/30 text-slate-400 hover:text-red-400">
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* Lifecycle progress */}
      <div className="flex items-center gap-1">
        {STATUS_ORDER.map((s, i) => (
          <div key={s} className="flex items-center gap-1">
            <span className={clsx(
              "text-[9px] font-mono px-1.5 py-0.5 rounded border",
              i <= currentIdx ? STATUS_COLORS[s] : "border-slate-700 text-slate-600"
            )}>{s}</span>
            {i < STATUS_ORDER.length - 1 && <span className="text-slate-700 text-[9px]">→</span>}
          </div>
        ))}
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2">
        {nextStatus && nextStatus !== "REJECTED" && (
          <button onClick={() => onStatusTransition(h.hypothesis_id, nextStatus)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono rounded-lg bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700">
            <Play size={12} /> Move to {nextStatus}
          </button>
        )}
        {h.status !== "REJECTED" && (
          <button onClick={() => onStatusTransition(h.hypothesis_id, "REJECTED")}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono rounded-lg bg-red-900/20 text-red-400 hover:bg-red-900/30 border border-red-800/50">
            <XCircle size={12} /> Reject
          </button>
        )}
        {h.status === "VALIDATED" && (
          <>
            <button onClick={() => onDeployToBacktest(h.hypothesis_id)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono rounded-lg bg-amber-600/20 text-amber-400 hover:bg-amber-600/30 border border-amber-500/30">
              <BarChart2 size={12} /> Deploy to Backtest
            </button>
            <button onClick={() => onDeployToPaper(h.hypothesis_id)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono rounded-lg bg-purple-600/20 text-purple-400 hover:bg-purple-600/30 border border-purple-500/30">
              <Send size={12} /> Deploy to Paper
            </button>
          </>
        )}
      </div>

      {/* Metadata */}
      <div className="grid grid-cols-4 gap-3">
        <MetaBox label="Created" value={new Date(h.created_at).toLocaleDateString()} />
        <MetaBox label="Updated" value={new Date(h.updated_at).toLocaleDateString()} />
        {h.benchmark_series && <MetaBox label="Benchmark" value={h.benchmark_series} />}
        {h.regime_filter && <MetaBox label="Regime Filter" value={h.regime_filter} />}
        {h.test_window_start && <MetaBox label="Test Start" value={h.test_window_start} />}
        {h.test_window_end && <MetaBox label="Test End" value={h.test_window_end} />}
        {h.backtest_run_id && <MetaBox label="Backtest Run" value={h.backtest_run_id.slice(0, 8) + "..."} />}
      </div>

      {/* Test Log */}
      {h.test_log && h.test_log.length > 0 && (
        <div className="rounded-xl border border-slate-700 bg-slate-900 p-3 space-y-2">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Statistical Tests</div>
          <div className="space-y-1">
            {h.test_log.map((t, i) => (
              <div key={i} className="flex items-center gap-3 text-xs font-mono bg-slate-800 rounded-lg p-2">
                <span className="text-slate-400 w-24">{t.test_type}</span>
                <span className="text-slate-300">p = {fmtN(t.raw_p_value, 4)}</span>
                <span className={clsx(
                  t.significant_bonf ? "text-emerald-400" : t.significant_raw ? "text-amber-400" : "text-red-400"
                )}>
                  {t.significant_bonf ? "✓ Bonf" : t.significant_bh ? "✓ BH" : t.significant_raw ? "~ Raw" : "✗ Not sig"}
                </span>
                {t.tests_in_family > 1 && (
                  <span className="text-slate-500">({t.tests_in_family} tests in family)</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Evidence */}
      {h.evidence_list && h.evidence_list.length > 0 && (
        <div className="rounded-xl border border-slate-700 bg-slate-900 p-3 space-y-2">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Attached Evidence</div>
          <div className="space-y-1">
            {h.evidence_list.map((e, i) => (
              <div key={i} className="flex items-center gap-2 text-xs font-mono text-slate-300 bg-slate-800 rounded-lg p-2">
                <span className={clsx(
                  "text-[9px] px-1 py-0.5 rounded",
                  e.tier === "descriptive" && "text-blue-400 bg-blue-500/10",
                  e.tier === "diagnostic" && "text-amber-400 bg-amber-500/10",
                  e.tier === "predictive" && "text-emerald-400 bg-emerald-500/10",
                  e.tier === "prescriptive" && "text-purple-400 bg-purple-500/10",
                  e.tier === "cognitive" && "text-cyan-400 bg-cyan-500/10",
                )}>{e.tier}</span>
                <span>{e.label || e.evidence_type}</span>
                {e.series_id && <span className="text-slate-500">({e.series_id})</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI Synthesis */}
      {h.ai_synthesis && (
        <div className="rounded-xl border border-cyan-800/50 bg-cyan-950/20 p-3">
          <div className="text-[10px] text-cyan-400 uppercase tracking-wider font-semibold mb-1">AI Synthesis</div>
          <p className="text-xs text-cyan-200 font-mono whitespace-pre-wrap">{h.ai_synthesis}</p>
        </div>
      )}
    </div>
  );
}

function MetaBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-2">
      <div className="text-[9px] text-slate-500 uppercase font-semibold">{label}</div>
      <div className="text-xs font-mono text-slate-300 truncate">{value}</div>
    </div>
  );
}