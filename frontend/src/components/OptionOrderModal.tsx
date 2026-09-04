import { useState } from "react";
import clsx from "clsx";
import { signalsApi, OptionLeg, OptionSuggestion } from "@/lib/api";
import { fmt$, fmtN } from "@/lib/utils";
import { ArrowRightLeft, XCircle, Zap, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";

const OCC_RE = /^([A-Z]{1,5})(\d{6})([CP])(\d{8})$/;
export function isOptionTicker(t?: string): boolean { return !!t && OCC_RE.test(t); }
export function parseOptionDetails(t?: string): { underlying: string; expiry: string; type: "C" | "P"; strike: number } | null {
  if (!t) return null;
  const m = t.match(OCC_RE);
  if (!m) return null;
  const [, root, yymmdd, cp, strikeRaw] = m;
  try { return { underlying: root, expiry: `20${yymmdd.slice(0,2)}-${yymmdd.slice(2,4)}-${yymmdd.slice(4,6)}`, type: cp === "P" ? "P" : "C", strike: Number(strikeRaw) / 1000 }; }
  catch { return null; }
}

export interface OptionOrderInitial {
  ticker: string;
  direction?: "buy" | "sell";
  quantity?: number;
  signal_id?: string | null;
  strategy?: string | null;
  matchingNote?: string | null;
  spreadLegs?: OptionLeg[];
  orderClass?: "simple" | "vertical";
  refMid?: number | null;
}

export default function OptionOrderModal({ initial, onClose, onSuccess }: { initial: OptionOrderInitial; onClose: () => void; onSuccess: () => void }) {
  const [ticker, setTicker] = useState(initial.ticker ?? "");
  const opt = isOptionTicker(ticker.trim()) ? parseOptionDetails(ticker.trim()) : null;
  const isO = !!opt;
  const mid0 = initial.refMid ?? 0;
  const [side, setSide] = useState<"buy" | "sell">(initial.direction ?? "buy");
  const [intent, setIntent] = useState<"buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close">(initial.direction === "sell" ? "sell_to_open" : "buy_to_open");
  const [qty, setQty] = useState<number>(typeof initial.quantity === "number" ? initial.quantity : 1);
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState<string>("");
  const [orderClass, setOrderClass] = useState<"simple" | "vertical">(initial.orderClass ?? "simple");
  const [spreadLegs, setSpreadLegs] = useState<OptionLeg[]>(initial.spreadLegs ?? []);
  const [placing, setPlacing] = useState(false);
  const [placed, setPlaced] = useState<{ order_id: string; status: string; contract: string; fill: number | null; mode: string } | null>(null);
  const [placeErr, setPlaceErr] = useState<string | null>(null);
  const [proposalToken, setProposalToken] = useState<string | null>(null);
  const [previewInfo, setPreviewInfo] = useState<{ ref_price: number; estimated_notional_usd?: number; estimated_fee_usd?: number; max_loss_est_usd?: number } | null>(null);

  const multiplier = 100;
  const mid = opt ? (limitPrice && Number(limitPrice) ? Number(limitPrice) : mid0 || 0) : (limitPrice && Number(limitPrice) ? Number(limitPrice) : 0);
  const isSpread = orderClass === "vertical" && spreadLegs.length > 1;
  const legMetrics = (() => {
    const legs = isSpread ? spreadLegs : [];
    if (legs.length === 0) {
      const notional = (mid || 0) * multiplier * qty;
      return { premium: mid || 0, net: side === "buy" ? -notional : notional, max_profit: side === "buy" ? null : notional, max_loss: side === "buy" ? notional : null };
    }
    let net = 0;
    for (const l of legs) { const ln = (l.mid ?? 0) * multiplier * Math.max(1, Number(l.contracts ?? 1) || 1); net += l.side.startsWith("buy") ? -ln : ln; }
    return { premium: null, net, max_profit: net >= 0 ? net : null, max_loss: net < 0 ? -net : null };
  })();

  function setLegQty(i: number, n: number) { setSpreadLegs(spreadLegs.map((l, idx) => (idx === i ? { ...l, contracts: Math.max(1, n || 1) } : l))); }
  function setLegSide(i: number, s: string) { setSpreadLegs(spreadLegs.map((l, idx) => (idx === i ? { ...l, side: s as OptionLeg["side"] } : l))); }
  function removeLeg(i: number) { setSpreadLegs(spreadLegs.filter((_, idx) => idx !== i)); }
  function addLeg() {
    const last = spreadLegs[spreadLegs.length - 1];
    const base = last ?? { symbol: ticker.trim(), strike: opt?.strike ?? 0, contract_type: opt?.type === "P" ? "put" : "call", mid: mid0, delta: null, contracts: 1, side: side === "buy" ? "buy_to_open" : "sell_to_open" };
    const inverse = (base.side ?? "buy_to_open").startsWith("buy") ? "sell_to_open" : "buy_to_open";
    setSpreadLegs([...spreadLegs, { ...base, side: inverse as OptionLeg["side"], contracts: 1 }]);
  }

  function body(extra: { preview?: boolean; proposal_token?: string | null } = {}) {
    return {
      ticker: (isSpread ? spreadLegs[0]?.symbol : ticker).trim().toUpperCase(),
      direction: isSpread ? (spreadLegs[0]?.side.startsWith("buy") ? "buy" : "sell") : side,
      quantity: isSpread ? Math.max(1, Number(spreadLegs[0]?.contracts ?? 1) || 1) : qty,
      order_type: orderType,
      limit_price: orderType === "limit" ? Number(limitPrice) || null : null,
      venue: "alpaca",
      signal_id: initial.signal_id ?? null,
      ...extra,
    };
  }

  const onSubmit = async () => {
    if (proposalToken) {
      setPlacing(true); setPlaceErr(null); setPlaced(null);
      try {
        const res = await signalsApi.placeOrder(body({ preview: false, proposal_token: proposalToken }));
        setPlaced({ order_id: res.order_id, status: res.status, contract: res.ticker, fill: res.fill_price || null, mode: res.mode });
        setProposalToken(null);
        onSuccess();
      } catch (e) { setPlaceErr(e instanceof Error ? e.message : String(e)); }
      finally { setPlacing(false); }
    } else {
      setPlacing(true); setPlaceErr(null); setProposalToken(null); setPreviewInfo(null);
      try {
        const res = await signalsApi.placeOrder(body({ preview: true }));
        if (!res.proposal_token) throw new Error("Preview did not return a proposal token \u2014 cannot confirm.");
        setProposalToken(res.proposal_token);
        setPreviewInfo(res.risk_preview ?? null);
      } catch (e) { setPlaceErr(e instanceof Error ? e.message : String(e)); }
      finally { setPlacing(false); }
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-slate-600 bg-slate-900 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-700 bg-slate-950">
          <ArrowRightLeft size={15} className="text-emerald-400" />
          <span className="text-sm font-semibold text-slate-100">{isO ? "Confirm Option Trade" : "Confirm Order"}</span>
          {initial.strategy && <span className="text-[10px] font-mono text-violet-300 bg-violet-950/40 border border-violet-800 rounded px-1.5 py-0.5 truncate max-w-[120px]">{initial.strategy}</span>}
          <button onClick={onClose} className="ml-auto p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200"><XCircle size={16} /></button>
        </div>

        <div className="p-4 space-y-3">
          {isO && (
            <div className="grid grid-cols-2 gap-2">
              <button onClick={() => setOrderClass("simple")}
                className={clsx("px-2 py-1.5 rounded border text-[11px] font-bold font-mono",
                  orderClass === "simple" ? "bg-indigo-600/30 border-indigo-500/50 text-indigo-200" : "bg-slate-950 border-slate-700 text-slate-400 hover:bg-slate-800")}>
                SIMPLE (1 leg)
              </button>
              <button onClick={() => { setOrderClass("vertical"); if (spreadLegs.length === 0) setSpreadLegs([{ symbol: ticker.trim(), strike: opt?.strike ?? 0, contract_type: opt?.type === "P" ? "put" : "call", mid: mid0, delta: null, contracts: 1, side: side === "buy" ? "buy_to_open" : "sell_to_open" }]); }}
                className={clsx("px-2 py-1.5 rounded border text-[11px] font-bold font-mono",
                  orderClass === "vertical" ? "bg-violet-600/30 border-violet-500/50 text-violet-200" : "bg-slate-950 border-slate-700 text-slate-400 hover:bg-slate-800")}>
                VERTICAL (spread)
              </button>
            </div>
          )}

          <div className="text-xs font-mono text-slate-200 bg-slate-950 border border-slate-700 rounded px-3 py-2">
            <div className="text-slate-100 font-bold">{(isSpread ? spreadLegs[0]?.symbol : ticker)?.trim().toUpperCase() || "\u2014"}</div>
            <div className="text-slate-500">{opt ? `${opt.type === "C" ? "CALL" : "PUT"} x100 \u00b7 ${opt.expiry} \u00b7 Strike ${fmtN(opt.strike, 2)} \u00b7 ${opt.underlying}` : `${side === "buy" ? "LONG" : "SHORT"} \u00b7 venue alpaca`}</div>
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

          {isO && isSpread && (
            <div className="rounded border border-violet-800/40 bg-violet-950/10 px-3 py-2 space-y-1.5">
              <div className="flex items-center gap-2">
                <div className="text-[10px] text-violet-300 uppercase tracking-widest font-mono">Spread legs</div>
                <button onClick={addLeg}
                  className="ml-auto text-[10px] font-mono px-1.5 py-0.5 rounded border border-violet-500/40 bg-violet-950/40 text-violet-300 hover:bg-violet-900/50">+ leg</button>
              </div>
              {spreadLegs.map((l, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px] font-mono text-slate-300">
                  <select value={l.side} onChange={(e) => setLegSide(i, e.target.value)}
                    className="bg-slate-950 border border-violet-700/60 rounded px-1 py-0.5 text-[10px] font-mono text-slate-200">
                    <option value="buy_to_open">BTO</option><option value="sell_to_open">STO</option>
                    <option value="buy_to_close">BTC</option><option value="sell_to_close">STC</option>
                  </select>
                  <span className="truncate flex-1 text-slate-400" title={l.symbol}>{l.symbol}</span>
                  <span>K {fmtN(l.strike, 2)}</span>
                  <span className="text-slate-500">mid {l.mid != null ? fmt$(l.mid) : "-"}</span>
                  <input type="number" min={1} value={l.contracts ?? 1} onChange={(e) => setLegQty(i, Number(e.target.value))}
                    className="w-14 bg-slate-950 border border-violet-700/60 rounded px-1 py-0.5 text-[10px] font-mono text-slate-200" />
                  <button onClick={() => removeLeg(i)} disabled={spreadLegs.length <= 1}
                    className="text-slate-500 hover:text-red-400 disabled:opacity-30 ml-0.5"><XCircle size={11} /></button>
                </div>
              ))}
              <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono pt-1.5 border-t border-violet-900/40">
                <div className="text-slate-300">{legMetrics.net >= 0 ? "Net CREDIT" : "Net DEBIT"} <b className={legMetrics.net >= 0 ? "text-emerald-400" : "text-amber-400"}>{fmt$(Math.abs(legMetrics.net))}</b></div>
                <div className="text-slate-300">maxP <b className="text-emerald-400">{legMetrics.max_profit != null ? fmt$(legMetrics.max_profit) : "-"}</b></div>
                <div className="text-slate-300">maxL <b className="text-red-400">{legMetrics.max_loss != null ? fmt$(legMetrics.max_loss) : "-"}</b></div>
                <div className="text-slate-300">RR <b className="text-slate-100">{legMetrics.max_profit != null && legMetrics.max_loss != null && legMetrics.max_loss > 0 ? (legMetrics.max_profit / legMetrics.max_loss).toFixed(2) : "-"}</b></div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">Side</span>
              <select value={side} onChange={(e) => setSide(e.target.value as "buy" | "sell")}
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                <option value="buy">Buy</option><option value="sell">Sell</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">{isO ? "Contracts" : "Quantity"}</span>
              <input type="number" value={qty} min={1} step={isO ? 1 : 0.0001}
                onChange={(e) => setQty(Math.max(isO ? 1 : 0, Number(e.target.value) || 0))}
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 font-mono" />
            </label>
          </div>

          {isO && (
            <label className="space-y-1 block">
              <span className="text-[10px] text-slate-500 uppercase">Intent</span>
              <select value={intent} onChange={(e) => setIntent(e.target.value as typeof intent)}
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                <option value="buy_to_open">BUY TO OPEN</option><option value="sell_to_open">SELL TO OPEN</option>
                <option value="buy_to_close">BUY TO CLOSE</option><option value="sell_to_close">SELL TO CLOSE</option>
              </select>
            </label>
          )}

          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">Order Type</span>
              <select value={orderType} onChange={(e) => setOrderType(e.target.value as "market" | "limit")}
                className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                <option value="market">Market</option><option value="limit">Limit</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[10px] text-slate-500 uppercase">Venue</span>
              <select value="alpaca" className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5">
                <option value="alpaca">Alpaca Paper</option>
              </select>
            </label>
          </div>

          {orderType === "limit" && (
            <label className="space-y-1 block">
              <span className="text-[10px] text-slate-500 uppercase">Limit Price ($)</span>
              <input type="number" value={limitPrice} onChange={(e) => setLimitPrice(e.target.value)}
                step="0.01" min="0" className="w-full bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 font-mono" />
            </label>
          )}

          <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
            <div className="rounded bg-slate-950 border border-slate-700 px-2 py-1.5 text-slate-300">
              Mid <b className="text-slate-100">{mid ? fmt$(mid) : "-"}</b>
            </div>
            <div className="rounded bg-slate-950 border border-slate-700 px-2 py-1.5 text-slate-300">
              Notional <b className="text-slate-100">{fmt$(Math.abs((mid || 0) * multiplier * qty))}</b>
            </div>
            <div className="rounded bg-slate-950 border border-slate-700 px-2 py-1.5 text-slate-300">
              maxP <b className="text-emerald-400">{legMetrics.max_profit != null ? fmt$(legMetrics.max_profit) : "-"}</b>
            </div>
            <div className="rounded bg-slate-950 border border-slate-700 px-2 py-1.5 text-slate-300">
              maxL <b className="text-red-400">{legMetrics.max_loss != null ? fmt$(legMetrics.max_loss) : "-"}</b>
            </div>
            {previewInfo && (
              <div className="col-span-2 text-slate-400 rounded bg-slate-950 border border-slate-700 px-2 py-1.5">
                Preview: ref {fmt$(previewInfo.ref_price)} \u00b7 est notional {fmt$(previewInfo.estimated_notional_usd ?? 0)} \u00b7 fee {fmt$(previewInfo.estimated_fee_usd ?? 0)} \u00b7 maxL {fmt$(previewInfo.max_loss_est_usd ?? 0)}
              </div>
            )}
          </div>

          {initial.matchingNote && <div className="text-[10px] font-mono text-slate-500">{initial.matchingNote}</div>}

          {placed && (
            <div className="flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/30 border border-emerald-800 rounded p-2">
              <CheckCircle2 size={12} />{placed.contract} {placed.status.toUpperCase()} {placed.fill != null ? fmt$(placed.fill) : ""} {placed.mode.toUpperCase()} id {placed.order_id}
            </div>
          )}
          {placeErr && (
            <div className="flex items-center gap-1.5 text-xs font-mono text-red-400 bg-red-950/30 border border-red-800 rounded p-2">
              <AlertTriangle size={12} /> {placeErr}
            </div>
          )}

          <div className="flex gap-2">
            <button onClick={onClose} disabled={placing}
              className="flex-1 px-3 py-2 rounded bg-slate-800 border border-slate-600 text-xs font-bold text-slate-300 hover:bg-slate-700 disabled:opacity-50">
              Cancel
            </button>
            <button onClick={onSubmit} disabled={placing || !ticker.trim()}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded bg-emerald-600/30 border border-emerald-500/40 text-xs font-bold text-emerald-300 hover:bg-emerald-600/50 disabled:opacity-50">
              {placing ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
              {proposalToken ? "Confirm on Alpaca Paper" : "1\u2009Preview"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
