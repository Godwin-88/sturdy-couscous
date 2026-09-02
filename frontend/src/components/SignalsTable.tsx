import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { agentApi, researchApi, signalsApi, Signal, SignalLineage, RejectedSignals, ExecutionFill } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmt$, relTime } from "@/lib/utils";
import { RefreshCw, ChevronDown, ChevronRight, BookOpen, BarChart, Brain, Search, X, AlertCircle, Plus, Download, Radio, Wallet, ExternalLink, Activity, Clock } from "lucide-react";
import clsx from "clsx";
import OrderDetailDrawer from "@/components/OrderDetailDrawer";

type SubTab = "all" | "rejected" | "fills";

function isOptionTicker(ticker: string): boolean {
  return /^[A-Z]{1,5}\d{6}[CP]\d{8}$/.test(ticker);
}

function parseOptionDetails(ticker: string): { underlying: string; expiry: string; type: "C" | "P"; strike: number } | null {
  const m = ticker.match(/^([A-Z]{1,5})(\d{6})([CP])(\d{8})$/);
  if (!m) return null;
  const [, , yymmdd, cp, strikeRaw] = m;
  return {
    underlying: m[1],
    expiry: `20${yymmdd.slice(0, 2)}-${yymmdd.slice(2, 4)}-${yymmdd.slice(4, 6)}`,
    type: cp as "C" | "P",
    strike: parseInt(strikeRaw, 10) / 1000,
  };
}

function dteFromExpiry(expiry: string): number {
  const exp = new Date(expiry);
  const now = new Date();
  return Math.max(0, Math.ceil((exp.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)));
}

export default function SignalsTable() {
  const navigate = useNavigate();
  const [limit, setLimit] = useState(50);
  const [subTab, setSubTab] = useState<SubTab>("all");
  const { data, loading, refresh } = usePolling<Signal[]>(
    () => agentApi.signals(limit), 20_000, [limit]
  );
  const [rejected, setRejected] = useState<RejectedSignals | null>(null);
  const [fills, setFills] = useState<ExecutionFill[] | null>(null);
  const [subLoading, setSubLoading] = useState(false);

  // Expanded lineage state
  const [expanded, setExpanded] = useState<string | null>(null);
  const [lineage, setLineage]   = useState<Record<string, SignalLineage>>({});
  const [lineageLoading, setLineageLoading] = useState<string | null>(null);

  // Detail drawer state
  const [detailOrder, setDetailOrder] = useState<Signal | null>(null);

  // Place Order modal
  const [placeOpen, setPlaceOpen] = useState(false);

  // Venue status
  const [venueStatus, setVenueStatus] = useState<{ name: string; type: string; status: string; mode: string; last_heartbeat: string | null }[] | null>(null);
  useEffect(() => {
    signalsApi.venuesStatus().then(res => setVenueStatus(res.venues)).catch(() => {});
  }, []);

  const toggleLineage = async (strategy: string) => {
    if (expanded === strategy) { setExpanded(null); return; }
    setExpanded(strategy);
    if (!lineage[strategy]) {
      setLineageLoading(strategy);
      try {
        const result = await agentApi.signalLineage(strategy);
        setLineage(prev => ({ ...prev, [strategy]: result }));
      } finally {
        setLineageLoading(null);
      }
    }
  };

  const switchSubTab = async (tab: SubTab) => {
    setSubTab(tab);
    if (tab === "rejected" && !rejected) {
      setSubLoading(true);
      try {
        const r = await researchApi.rejectedSignals();
        setRejected(r);
      } finally { setSubLoading(false); }
    }
    if (tab === "fills" && !fills) {
      setSubLoading(true);
      try {
        const f = await researchApi.executionFills();
        setFills(f);
      } finally { setSubLoading(false); }
    }
  };

  const subTabs: { id: SubTab; label: string }[] = [
    { id: "all",      label: "All Orders" },
    { id: "rejected", label: "Rejected" },
    { id: "fills",    label: "Fills" },
  ];

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-700 shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-slate-200">Order History</span>
          {/* Sub-tab navigation */}
          <div className="flex gap-0.5 bg-slate-800 rounded-lg p-0.5">
            {subTabs.map(t => (
              <button key={t.id} onClick={() => switchSubTab(t.id)}
                className={clsx("px-2.5 py-1 text-[10px] font-semibold font-mono rounded-md transition-colors",
                  subTab === t.id
                    ? "bg-indigo-600 text-white"
                    : "text-slate-400 hover:text-slate-200"
                )}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Venue status badge */}
          {venueStatus && venueStatus.map(v => (
            <span key={v.name} className={clsx("flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono border",
              v.mode === "live" ? "bg-red-900/30 text-red-300 border-red-700/50" : "bg-slate-800 text-slate-400 border-slate-700")}
              title={`${v.name}: ${v.mode} mode — ${v.status}`}>
              <Radio size={8} className={v.mode === "live" ? "text-red-400 animate-pulse" : "text-slate-500"} />
              {v.name}
            </span>
          ))}
          <button onClick={() => setPlaceOpen(true)}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono bg-emerald-800/60 border border-emerald-700/50 text-emerald-300 hover:bg-emerald-700">
            <Plus size={10} /> Order
          </button>
          <button onClick={() => {
            signalsApi.exportSignals().then(data => {
              const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a"); a.href = url; a.download = `signals_export.json`; a.click();
              URL.revokeObjectURL(url);
            }).catch(() => {});
          }}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono bg-slate-800 border border-slate-700 text-slate-400 hover:text-slate-200">
            <Download size={10} /> Export
          </button>
          <select value={limit} onChange={e => setLimit(Number(e.target.value))}
            className="bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-1.5 py-0.5">
            {[25, 50, 100, 200].map(n => <option key={n} value={n}>{n} rows</option>)}
          </select>
          <button onClick={refresh} className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-700">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto min-h-0">
        {subTab === "all" && (
          <table className="w-full text-xs font-mono">
            <thead className="sticky top-0 bg-slate-800 z-10">
              <tr className="text-slate-400">
                <th className="py-2 px-2 w-6" />
                {["Time","Strategy","Ticker","Type","Side","Qty","Fill $","Δ","Prem","DTE","Score","Mode","Actions"].map(h => (
                  <th key={h} className={clsx("py-2 px-3 font-medium text-[10px] uppercase tracking-wider",
                    ["Qty","Fill $","Δ","Prem","DTE","Score"].includes(h) ? "text-right" : "text-left"
                  )}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(!data || data.length === 0) && (
                <tr><td colSpan={14} className="text-center py-8 text-slate-500">No orders yet — agent is generating signals</td></tr>
              )}
              {(data ?? []).map(s => {
                const isExpanded = expanded === s.strategy;
                const lg = lineage[s.strategy];
                const isLoadingLg = lineageLoading === s.strategy;
                const isOpt = isOptionTicker(s.ticker);
                const optDetails = isOpt ? parseOptionDetails(s.ticker) : null;
                const dte = optDetails ? dteFromExpiry(optDetails.expiry) : null;
                return [
                  <tr key={s.order_id} className={clsx("border-t border-slate-800 hover:bg-slate-800/60", isOpt && "bg-violet-950/10")}>
                    <td className="py-1.5 px-2">
                      <button onClick={() => toggleLineage(s.strategy)}
                        className="p-0.5 rounded text-slate-500 hover:text-indigo-400" title="View KG lineage">
                        {isExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                      </button>
                    </td>
                    <td className="py-1.5 px-3 text-slate-500">{relTime(s.created_at)}</td>
                    <td className="py-1.5 px-3 text-slate-300 max-w-[140px] truncate" title={s.strategy}>{s.strategy}</td>
                    <td className="py-1.5 px-3 text-slate-100 font-bold">
                      <div className="flex items-center gap-1.5">
                        {isOpt && <Activity size={10} className="text-violet-400 shrink-0" />}
                        <span className="truncate">{isOpt && optDetails ? optDetails.underlying : s.ticker}</span>
                      </div>
                    </td>
                    <td className="py-1.5 px-3">
                      {isOpt && optDetails ? (
                        <span className={clsx("text-[10px] font-bold px-1 py-0.5 rounded",
                          optDetails.type === "C" ? "bg-emerald-900/50 text-emerald-300" : "bg-red-900/50 text-red-300")}>
                          {optDetails.type === "C" ? "CALL" : "PUT"}
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-500">EQUITY</span>
                      )}
                    </td>
                    <td className={clsx("py-1.5 px-3 font-bold", s.direction === "buy" ? "text-emerald-400" : "text-red-400")}>
                      {s.direction.toUpperCase()}
                    </td>
                    <td className="py-1.5 px-3 text-right text-slate-300">{s.quantity.toFixed(4)}</td>
                    <td className="py-1.5 px-3 text-right text-slate-300">{s.fill_price ? fmt$(s.fill_price) : "—"}</td>
                    <td className="py-1.5 px-3 text-right text-violet-300">
                      {isOpt && optDetails ? <span className="text-[10px]">{optDetails.strike.toFixed(1)}</span> : "—"}
                    </td>
                    <td className="py-1.5 px-3 text-right text-amber-300">
                      {isOpt ? <span className="text-[10px]">{s.fill_price ? fmt$(s.fill_price) : "—"}</span> : "—"}
                    </td>
                    <td className="py-1.5 px-3 text-right">
                      {dte != null ? (
                        <span className={clsx("text-[10px] font-bold", dte <= 7 ? "text-red-400" : dte <= 30 ? "text-amber-400" : "text-slate-300")}>
                          {dte}d
                        </span>
                      ) : "—"}
                    </td>
                    <td className={clsx("py-1.5 px-3 text-right font-bold",
                      (s.signal_score ?? 0) > 0 ? "text-emerald-400" : "text-red-400")}>
                      {(s.signal_score ?? 0) >= 0 ? "+" : ""}{(s.signal_score ?? 0).toFixed(3)}
                    </td>
                    <td className="py-1.5 px-3">
                      <span className={clsx("px-1.5 py-0.5 rounded text-[10px]",
                        s.mode === "live" ? "bg-red-900 text-red-300 border border-red-700" : "bg-slate-700 text-slate-400")}>
                        {s.mode}
                      </span>
                    </td>
                    <td className="py-1.5 px-2">
                      <div className="flex items-center gap-1">
                        <button onClick={() => setDetailOrder(s)}
                          className="p-1 rounded text-slate-500 hover:text-indigo-400 hover:bg-slate-700" title="View details">
                          <Search size={11} />
                        </button>
                        <button onClick={() => navigate(`/analytics?series=${encodeURIComponent(s.strategy)}&ticker=${s.ticker}`)}
                          className="p-1 rounded text-slate-500 hover:text-emerald-400 hover:bg-slate-700" title="Analyze">
                          <BarChart size={11} />
                        </button>
                        <button onClick={() => navigate(`/hypothesis/new?series=${encodeURIComponent(s.strategy)}&ticker=${s.ticker}`)}
                          className="p-1 rounded text-slate-500 hover:text-purple-400 hover:bg-slate-700" title="Create hypothesis">
                          <Brain size={11} />
                        </button>
                      </div>
                    </td>
                  </tr>,
                  isExpanded && (
                    <tr key={`${s.order_id}-lineage`} className="bg-slate-950/80">
                      <td colSpan={14} className="px-6 py-3">
                        {isLoadingLg ? (
                          <div className="text-xs text-slate-500 animate-pulse">Loading KG lineage...</div>
                        ) : lg ? (
                          <LineageDrawer lineage={lg} />
                        ) : (
                          <div className="text-xs text-slate-500">No lineage data found</div>
                        )}
                      </td>
                    </tr>
                  ),
                ];
              })}
            </tbody>
          </table>
        )}

        {subTab === "rejected" && (
          <div className="p-4">
            {subLoading ? (
              <div className="text-xs text-slate-500 animate-pulse text-center py-8">Loading rejected signals...</div>
            ) : rejected && Object.keys(rejected.by_reason).length > 0 ? (
              <div className="space-y-4">
                {Object.entries(rejected.by_reason).map(([reason, group]) => (
                  <div key={reason} className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
                    <div className="flex items-center justify-between px-3 py-2 bg-slate-800/80 border-b border-slate-700">
                      <div className="flex items-center gap-2">
                        <AlertCircle size={12} className="text-red-400" />
                        <span className="text-xs font-semibold text-slate-200 font-mono">{reason}</span>
                      </div>
                      <span className="text-[10px] text-slate-500">{group.count} signals</span>
                    </div>
                    <div className="divide-y divide-slate-700/50">
                      {(group.signals as Signal[]).slice(0, 10).map((s: Signal) => (
                        <div key={s.order_id} className="flex items-center gap-3 px-3 py-1.5 text-[10px] font-mono hover:bg-slate-700/30">
                          <span className="text-slate-500 w-20">{relTime(s.created_at)}</span>
                          <span className="text-slate-300 w-24 truncate">{s.strategy}</span>
                          <span className="text-slate-100 font-bold">{s.ticker}</span>
                          <span className={clsx(s.direction === "buy" ? "text-emerald-400" : "text-red-400")}>{s.direction.toUpperCase()}</span>
                          <span className="text-slate-500 ml-auto">{s.quantity.toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-slate-500 text-center py-8">No rejected signals found.</div>
            )}
          </div>
        )}

        {subTab === "fills" && (
          <div className="p-4">
            {subLoading ? (
              <div className="text-xs text-slate-500 animate-pulse text-center py-8">Loading fills...</div>
            ) : fills && fills.length > 0 ? (
              <table className="w-full text-xs font-mono">
                <thead className="sticky top-0 bg-slate-800 z-10">
                  <tr className="text-slate-400">
                    {["Time","Strategy","Ticker","Side","Qty","Fill $","Fee $","Score","Kelly","VaR"].map(h => (
                      <th key={h} className={clsx("py-2 px-3 font-medium text-[10px] uppercase tracking-wider text-left",
                        ["Qty","Fill $","Fee $","Score","Kelly","VaR"].includes(h) ? "text-right" : "text-left"
                      )}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {fills.map(f => (
                    <tr key={f.order_id} className="border-t border-slate-800 hover:bg-slate-800/60">
                      <td className="py-1.5 px-3 text-slate-500">{relTime(f.created_at)}</td>
                      <td className="py-1.5 px-3 text-slate-300 max-w-[120px] truncate">{f.strategy}</td>
                      <td className="py-1.5 px-3 text-slate-100 font-bold">{f.ticker}</td>
                      <td className={clsx("py-1.5 px-3 font-bold", f.direction === "buy" ? "text-emerald-400" : "text-red-400")}>
                        {f.direction.toUpperCase()}
                      </td>
                      <td className="py-1.5 px-3 text-right text-slate-300">{f.quantity.toFixed(4)}</td>
                      <td className="py-1.5 px-3 text-right text-slate-300">{fmt$(f.fill_price)}</td>
                      <td className="py-1.5 px-3 text-right text-slate-300">{fmt$(f.fee_usd)}</td>
                      <td className={clsx("py-1.5 px-3 text-right font-bold",
                        f.signal_score > 0 ? "text-emerald-400" : "text-red-400")}>
                        {f.signal_score >= 0 ? "+" : ""}{f.signal_score.toFixed(3)}
                      </td>
                      <td className="py-1.5 px-3 text-right text-slate-300">{f.kelly_fraction?.toFixed(3) ?? "—"}</td>
                      <td className="py-1.5 px-3 text-right text-slate-300">{f.var_contribution?.toFixed(3) ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="text-xs text-slate-500 text-center py-8">No fills data available.</div>
            )}
          </div>
        )}
      </div>

      {/* Place Order Modal */}
      {placeOpen && (
        <PlaceOrderModal onClose={() => setPlaceOpen(false)} onSuccess={() => { refresh(); setPlaceOpen(false); }} />
      )}

      {/* Detail Drawer */}
      {detailOrder && (
        <OrderDetailDrawer
          orderId={detailOrder.order_id}
          strategy={detailOrder.strategy}
          ticker={detailOrder.ticker}
          direction={detailOrder.direction}
          onClose={() => setDetailOrder(null)}
          onAnalyze={() => {
            setDetailOrder(null);
            navigate(`/analytics?series=${encodeURIComponent(detailOrder.strategy)}&ticker=${detailOrder.ticker}`);
          }}
          onHypothesis={() => {
            setDetailOrder(null);
            navigate(`/hypothesis/new?series=${encodeURIComponent(detailOrder.strategy)}&ticker=${detailOrder.ticker}`);
          }}
        />
      )}
    </div>
  );
}

// ── Place Order Modal (Unified: Equity + Options) ──────────────────────────────
function PlaceOrderModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [ticker, setTicker] = useState("");
  const [direction, setDirection] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState("0.01");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState("");
  const [venue, setVenue] = useState("alpaca");
  const [intent, setIntent] = useState<"buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close">("buy_to_open");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ order_id: string; fill_price: number; fee_usd: number; mode: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isOpt = isOptionTicker(ticker.trim());
  const optDetails = isOpt ? parseOptionDetails(ticker.trim()) : null;

  const submit = async () => {
    if (!ticker.trim() || !quantity) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      if (isOpt) {
        const res = await signalsApi.placeOrder({
          ticker: ticker.trim().toUpperCase(),
          direction,
          quantity: Number(quantity),
          order_type: orderType,
          limit_price: orderType === "limit" ? Number(limitPrice) || null : null,
          venue,
        });
        setResult(res);
      } else {
        const res = await signalsApi.placeOrder({
          ticker: ticker.trim().toUpperCase(),
          direction,
          quantity: Number(quantity),
          order_type: orderType,
          limit_price: orderType === "limit" ? Number(limitPrice) || null : null,
          venue,
        });
        setResult(res);
      }
      onSuccess();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-900 rounded-xl border border-slate-700 w-full max-w-md mx-4 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
          <div className="flex items-center gap-2">
            {isOpt ? <Activity size={14} className="text-violet-400" /> : <Wallet size={14} className="text-emerald-400" />}
            <span className="text-sm font-semibold text-slate-200">{isOpt ? "Place Option Order" : "Place Order"}</span>
            {isOpt && <span className="text-[10px] font-mono text-violet-400 bg-violet-900/40 px-1.5 py-0.5 rounded">OPTION</span>}
          </div>
          <button onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-200"><X size={14} /></button>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="col-span-2">
              <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Ticker / Contract Symbol</div>
              <input value={ticker} onChange={e => setTicker(e.target.value)}
                placeholder="e.g. SPY or SPY250904C00770000"
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 font-mono" />
              {isOpt && optDetails && (
                <div className="flex items-center gap-2 mt-1.5 text-[10px] font-mono">
                  <span className={clsx("px-1 py-0.5 rounded", optDetails.type === "C" ? "bg-emerald-900/50 text-emerald-300" : "bg-red-900/50 text-red-300")}>
                    {optDetails.type === "C" ? "CALL" : "PUT"}
                  </span>
                  <span className="text-slate-400">Strike {optDetails.strike.toFixed(1)}</span>
                  <span className="text-slate-500">Exp {optDetails.expiry}</span>
                  <span className={clsx("font-bold", dteFromExpiry(optDetails.expiry) <= 7 ? "text-red-400" : "text-slate-400")}>
                    {dteFromExpiry(optDetails.expiry)} DTE
                  </span>
                </div>
              )}
            </div>
            <div>
              <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Side</div>
              <select value={direction} onChange={e => setDirection(e.target.value as "buy" | "sell")}
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">{isOpt ? "Contracts" : "Quantity"}</div>
              <input type="number" value={quantity} onChange={e => setQuantity(e.target.value)}
                step={isOpt ? "1" : "0.0001"} min="0"
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
            </div>
          </div>

          {isOpt && (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Intent</div>
                <select value={intent} onChange={e => setIntent(e.target.value as typeof intent)}
                  className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                  <option value="buy_to_open">BUY TO OPEN</option>
                  <option value="sell_to_open">SELL TO OPEN</option>
                  <option value="buy_to_close">BUY TO CLOSE</option>
                  <option value="sell_to_close">SELL TO CLOSE</option>
                </select>
              </div>
              <div>
                <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Order Type</div>
                <select value={orderType} onChange={e => setOrderType(e.target.value as "market" | "limit")}
                  className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                  <option value="market">Market</option>
                  <option value="limit">Limit</option>
                </select>
              </div>
            </div>
          )}

          {!isOpt && (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Order Type</div>
                <select value={orderType} onChange={e => setOrderType(e.target.value as "market" | "limit")}
                  className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                  <option value="market">Market</option>
                  <option value="limit">Limit</option>
                </select>
              </div>
              <div>
                <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Venue</div>
                <select value={venue} onChange={e => setVenue(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                  <option value="alpaca">Alpaca Paper</option>
                  <option value="kraken">Kraken (legacy)</option>
                  <option value="ibkr">IBKR (legacy)</option>
                </select>
              </div>
            </div>
          )}

          {orderType === "limit" && (
            <div>
              <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Limit Price ($)</div>
              <input type="number" value={limitPrice} onChange={e => setLimitPrice(e.target.value)}
                step="0.01" min="0"
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5" />
            </div>
          )}

          {error && (
            <div className="text-xs text-red-400 bg-red-950/30 border border-red-800 rounded p-2">{error}</div>
          )}
          {result && (
            <div className="text-xs text-emerald-400 bg-emerald-950/30 border border-emerald-800 rounded p-2 space-y-1">
              <div className="flex items-center gap-1.5 font-bold"><ExternalLink size={11} /> Order placed</div>
              <div className="font-mono text-slate-400">ID: {result.order_id.slice(0, 8)}…</div>
              <div className="font-mono text-slate-400">Fill: {fmt$(result.fill_price)} | Fee: {fmt$(result.fee_usd)} | Mode: {result.mode}</div>
            </div>
          )}

          <button onClick={submit} disabled={submitting || !ticker.trim() || !quantity}
            className={clsx("w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors",
              submitting ? "bg-slate-700 text-slate-500" : isOpt ? "bg-violet-700 hover:bg-violet-600 text-white" : "bg-emerald-700 hover:bg-emerald-600 text-white")}>
            <Radio size={12} className={submitting ? "animate-pulse" : ""} />
            {submitting ? "Submitting..." : isOpt ? "Submit Option Order" : "Submit Order"}
          </button>
        </div>
      </div>
    </div>
  );
}

function LineageDrawer({ lineage }: { lineage: SignalLineage }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <BookOpen size={12} className="text-indigo-400" />
        <span className="text-xs font-semibold text-indigo-300">{lineage.strategy}</span>
        {lineage.strategy_desc && <span className="text-xs text-slate-500">— {lineage.strategy_desc}</span>}
        <div className="flex gap-1 ml-auto">
          {lineage.regimes.map(r => (
            <span key={r} className="text-[10px] px-1.5 py-0.5 rounded bg-purple-900/60 text-purple-300 border border-purple-700 font-mono">{r}</span>
          ))}
        </div>
      </div>

      {lineage.concepts.length > 0 && (
        <div>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Derived Concepts ({lineage.concepts.length})</div>
          <div className="grid grid-cols-2 gap-1.5">
            {lineage.concepts.map((c, i) => (
              <div key={i} className="bg-slate-800 rounded p-2 border border-slate-700">
                <div className="flex items-center justify-between gap-1 mb-0.5">
                  <span className="text-[11px] font-semibold text-slate-200">{c.name}</span>
                  <span className={clsx("text-[9px] px-1 py-0.5 rounded font-mono",
                    c.difficulty === "hard" ? "bg-red-900/50 text-red-300" :
                    c.difficulty === "medium" ? "bg-yellow-900/50 text-yellow-300" :
                    "bg-slate-700 text-slate-400"
                  )}>{c.difficulty}</span>
                </div>
                {c.definition && <div className="text-[10px] text-slate-500 line-clamp-2">{c.definition}</div>}
                <div className="text-[9px] text-indigo-500 mt-0.5">{c.category}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {lineage.formulas.length > 0 && (
        <div>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Formulas ({lineage.formulas.length})</div>
          <div className="space-y-1">
            {lineage.formulas.map((f, i) => (
              <div key={i} className="flex items-start gap-2 bg-slate-800/60 rounded px-2 py-1.5 border border-slate-700/50">
                <span className="text-[10px] text-slate-400 font-semibold shrink-0">{f.name}</span>
                <code className="text-[10px] text-emerald-300 font-mono break-all">{f.expression}</code>
                {f.output && <span className="text-[9px] text-slate-500 shrink-0 ml-auto">→ {f.output}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}