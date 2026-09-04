import { useState } from "react";
import clsx from "clsx";
import { signalsApi } from "@/lib/api";
import { fmt$, fmtN } from "@/lib/utils";
import { XCircle, Zap, Radio, CheckCircle2, ShieldCheck, AlertTriangle } from "lucide-react";

// ── types ────────────────────────────────────────────────────────────────────
export interface OrderTicketInitial {
  ticker: string;
  direction?: "buy" | "sell";
  quantity?: number;
  order_type?: "market" | "limit";
  limit_price?: number | null;
  venue?: string;
  signal_id?: string | null;
  strategy?: string | null;
  max_loss_pct_nav?: number | null;
  nav?: number | null;
  matchingNote?: string | null;
}

const OCC_RE = /^([A-Z]{1,5})(\d{6})([CP])(\d{8})$/;
function isOptionTicker(t?: string): boolean {
  return !!t && OCC_RE.test(t);
}
function parseOptionDetails(t?: string): { underlying: string; expiry: string; type: "C" | "P"; strike: number } | null {
  if (!t) return null;
  const m = t.match(OCC_RE);
  if (!m) return null;
  const [, root, yymmdd, cp, strikeRaw] = m;
  try {
    return { underlying: root, expiry: `20${yymmdd.slice(0, 2)}-${yymmdd.slice(2, 4)}-${yymmdd.slice(4, 6)}`, type: cp === "P" ? ("P" as const) : ("C" as const), strike: Number(strikeRaw) / 1000 };
  } catch {
    return null;
  }
}

// ── shared rich two-phase order ticket (preview → confirm, human-in-the-loop) ─
export default function OrderTicketModal({
  initial,
  onClose,
  onSuccess,
}: {
  initial: OrderTicketInitial;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [ticker, setTicker] = useState(initial.ticker ?? "");
  const [direction, setDirection] = useState<"buy" | "sell">(initial.direction ?? "buy");
  const [quantity, setQuantity] = useState(String(initial.quantity ?? 1));
  const [orderType, setOrderType] = useState<"market" | "limit">(initial.order_type ?? "market");
  const [limitPrice, setLimitPrice] = useState(initial.limit_price ? String(initial.limit_price) : "");
  const [venue, setVenue] = useState(initial.venue ?? "alpaca");
  const [intent, setIntent] = useState<"buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close">("buy_to_open");
  const [submitting, setSubmitting] = useState(false);
  const [proposalToken, setProposalToken] = useState<string | null>(null);
  const [previewInfo, setPreviewInfo] = useState<{ ref_price: number; estimated_notional_usd?: number; estimated_fee_usd?: number; max_loss_est_usd?: number; note?: string; notional?: number; fee_usd?: number } | null>(null);
  const [result, setResult] = useState<{ order_id: string; fill_price: number; fee_usd: number; mode: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isOpt = isOptionTicker(ticker.trim());
  const optDetails = isOpt ? parseOptionDetails(ticker.trim()) : null;
  const qty = Number(quantity) || 0;
  const limitNum = orderType === "limit" ? Number(limitPrice) : null;
  const liveNotional = qty * (limitNum && limitNum > 0 ? limitNum : 0);
  const maxLossPct = initial.max_loss_pct_nav;

  const buildPayload = (extra: { preview?: boolean; proposal_token?: string | null } = {}) => ({
    ticker: ticker.trim().toUpperCase(),
    direction,
    quantity: qty,
    order_type: orderType,
    limit_price: orderType === "limit" ? limitNum : null,
    venue,
    signal_id: initial.signal_id ?? null,
    ...extra,
  });

  const preview = async () => {
    if (!ticker.trim() || qty <= 0) return;
    setSubmitting(true);
    setError(null);
    setPreviewInfo(null);
    try {
      const res = await signalsApi.placeOrder(buildPayload({ preview: true }));
      setProposalToken(res.proposal_token ?? null);
      setPreviewInfo(res.risk_preview ?? null);
      if (!res.proposal_token) setError("Preview did not return a proposal token — cannot confirm.");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const confirm = async () => {
    if (!proposalToken) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res = await signalsApi.placeOrder(buildPayload({ preview: false, proposal_token: proposalToken }));
      setResult({ order_id: res.order_id, fill_price: res.fill_price, fee_usd: res.fee_usd, mode: res.mode });
      setProposalToken(null);
      onSuccess();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-slate-600 bg-slate-900 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-700 bg-slate-950">
          <ShieldCheck size={15} className="text-emerald-400" />
          <span className="text-sm font-semibold text-slate-100">{isOpt ? "Confirm Option Trade" : "Confirm Order"}</span>
          {initial.strategy && (
            <span className="text-[10px] font-mono text-violet-300 bg-violet-950/40 border border-violet-800 rounded px-1.5 py-0.5 truncate max-w-[140px]">{initial.strategy}</span>
          )}
          <button onClick={onClose} className="ml-auto p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200">
            <XCircle size={16} />
          </button>
        </div>

        <div className="p-4 space-y-3">
          <div className="text-xs font-mono text-slate-200 bg-slate-950 border border-slate-700 rounded px-3 py-2">
            <div className="text-slate-100 font-bold">{ticker.trim().toUpperCase() || "\u2014"}</div>
            <div className="text-slate-500">
              {isOpt && optDetails
                ? `${optDetails.type === "C" ? "CALL" : "PUT"} x100 \u00b7 ${optDetails.expiry} \u00b7 Strike ${fmtN(optDetails.strike, 2)} \u00b7 ${optDetails.underlying}`
                : `${direction === "buy" ? "LONG" : "SHORT"} \u00b7 venue ${venue}`}
            </div>
          </div>

          <div className="flex items-center gap-1.5 text-[10px] font-mono text-amber-400 bg-amber-950/20 border border-amber-800/40 rounded px-2 py-1.5">
            <AlertTriangle size={11} />
            Human-in-the-loop: {proposalToken ? "proposal locked \u2014 confirm to execute on paper" : "Preview issues a one-time token (10-min) before any execution"}
          </div>

          <label className="space-y-1 block">
            <span className="text-[10px] text-slate-500 uppercase">Ticker / Contract Symbol</span>
            <input value={ticker} onChange={(e) => setTicker(e.target.value)}
              placeholder="e.g. SPY or SPY250904C00770000"
              className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 font-mono" />
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">Side</span>
              <select value={direction} onChange={(e) => setDirection(e.target.value as "buy" | "sell")}
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">{isOpt ? "Contracts" : "Quantity"}</span>
              <input type="number" value={quantity} onChange={(e) => setQuantity(e.target.value)}
                step={isOpt ? "1" : "0.0001"} min="0"
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 font-mono" />
            </label>
          </div>

          {isOpt && (
            <label className="space-y-1 block">
              <span className="text-[10px] text-slate-500 uppercase">Intent</span>
              <select value={intent} onChange={(e) => setIntent(e.target.value as typeof intent)}
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                <option value="buy_to_open">BUY TO OPEN</option>
                <option value="sell_to_open">SELL TO OPEN</option>
                <option value="buy_to_close">BUY TO CLOSE</option>
                <option value="sell_to_close">SELL TO CLOSE</option>
              </select>
            </label>
          )}

          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">Order Type</span>
              <select value={orderType} onChange={(e) => setOrderType(e.target.value as "market" | "limit")}
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                <option value="market">Market</option>
                <option value="limit">Limit</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">Venue</span>
              <select value={venue} onChange={(e) => setVenue(e.target.value)}
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                <option value="alpaca">Alpaca Paper</option>
                <option value="kraken">Kraken (legacy)</option>
                <option value="ibkr">IBKR (legacy)</option>
              </select>
            </label>
          </div>

          {orderType === "limit" && (
            <label className="space-y-1 block">
              <span className="text-[10px] text-slate-500 uppercase">Limit Price ($)</span>
              <input type="number" value={limitPrice} onChange={(e) => setLimitPrice(e.target.value)}
                step="0.01" min="0"
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 font-mono" />
            </label>
          )}

          <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono rounded bg-slate-950 border border-slate-700 px-2 py-1.5">
            <div className="text-slate-300">Qty <b className="text-slate-100">{fmtN(qty, 4)}</b></div>
            <div className="text-slate-300">Notional <b className="text-slate-100">{liveNotional > 0 ? fmt$(liveNotional) : "\u2014"}</b></div>
            {initial.strategy && <div className="text-violet-300">{initial.strategy}</div>}
            {maxLossPct != null && (
              <div className={clsx(maxLossPct > (initial.nav ? 5 : 10) ? "text-rose-400" : "text-slate-300")}>
                max loss {(maxLossPct * 100).toFixed(1)}% NAV
              </div>
            )}
            {previewInfo && (
              <div className="col-span-2 text-slate-400">
                Preview: ref {fmt$(previewInfo.ref_price)} · est notional {fmt$(previewInfo.estimated_notional_usd ?? previewInfo.notional ?? 0)} · fee {fmt$(previewInfo.estimated_fee_usd ?? previewInfo.fee_usd ?? 0)}
              </div>
            )}
          </div>

          {initial.matchingNote && (
            <div className="text-[10px] font-mono text-slate-500">{initial.matchingNote}</div>
          )}

          {result && (
            <div className="flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/30 border border-emerald-800 rounded p-2">
              <CheckCircle2 size={12} />
              Filled {fmt$(result.fill_price)} fee {fmt$(result.fee_usd)} {result.mode.toUpperCase()} id {result.order_id.slice(0, 8)} …
            </div>
          )}
          {error && (
            <div className="flex items-center gap-1.5 text-xs font-mono text-red-400 bg-red-950/30 border border-red-800 rounded p-2">
              <AlertTriangle size={12} /> {error}
            </div>
          )}

          <div className="flex gap-2">
            <button onClick={onClose} disabled={submitting}
              className="flex-1 px-3 py-2 rounded bg-slate-800 border border-slate-600 text-xs font-bold text-slate-300 hover:bg-slate-700 disabled:opacity-50">
              Cancel
            </button>
            {!proposalToken ? (
              <button onClick={preview} disabled={submitting || !ticker.trim() || qty <= 0}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded bg-indigo-600/30 border border-indigo-500/40 text-xs font-bold text-indigo-300 hover:bg-indigo-600/50 disabled:opacity-50">
                {submitting ? <Radio size={12} className="animate-pulse" /> : <Zap size={12} />} Preview
              </button>
            ) : (
              <button onClick={confirm} disabled={submitting}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded bg-emerald-600/30 border border-emerald-500/40 text-xs font-bold text-emerald-300 hover:bg-emerald-600/50 disabled:opacity-50">
                {submitting ? <Radio size={12} className="animate-spin" /> : <Zap size={12} />} Confirm on Alpaca Paper
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

