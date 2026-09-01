import { useMemo, useState } from "react";
import { Search, Activity, ArrowRightLeft, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { optionsApi, OptionContractRow, AlpacaAsset } from "@/lib/api";
import { fmt$, fmtN } from "@/lib/utils";
import clsx from "clsx";

const MOODS = ["call", "put"] as const;

export default function OptionsPanel() {
  const [query, setQuery] = useState("");
  const [assets, setAssets] = useState<AlpacaAsset[]>([]);
  const [searching, setSearching] = useState(false);
  const [underlying, setUnderlying] = useState<string>("SPY");

  const [expiration, setExpiration] = useState<string>("");
  const [expirations, setExpirations] = useState<string[]>([]);
  const [mood, setMood] = useState<"call" | "put">("call");

  const [rows, setRows] = useState<OptionContractRow[]>([]);
  const [loadingChain, setLoadingChain] = useState(false);
  const [chainErr, setChainErr] = useState<string | null>(null);

  const [selected, setSelected] = useState<OptionContractRow | null>(null);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [intent, setIntent] = useState<"buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close">("buy_to_open");
  const [qty, setQty] = useState(1);
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState<string>("");
  const [placing, setPlacing] = useState(false);
  const [placed, setPlaced] = useState<{ order_id: string; status: string; contract: string; fill: number | null; mode: string } | null>(null);
  const [placeErr, setPlaceErr] = useState<string | null>(null);

  async function searchUnderlyings() {
    setSearching(true);
    setChainErr(null);
    try {
      const res = await optionsApi.underlyings(query.trim());
      setAssets(res.assets ?? []);
    } catch (e) { setChainErr(String(e)); }
    finally { setSearching(false); }
  }

  async function pickUnderlying(sym: string) {
    setUnderlying(sym);
    setQuery("");
    setAssets([]);
    setExpiration("");
    setRows([]);
    setSelected(null);
    try {
      const ex = await optionsApi.expirations(sym);
      setExpirations(ex.expirations ?? []);
      if ((ex.expirations ?? []).length) {
        const first = ex.expirations[0];
        setExpiration(first);
        await loadChain(sym, first, "call");
      }
    } catch (e) { setChainErr(String(e)); }
  }

  async function loadChain(sym: string, exp: string, type: "call" | "put") {
    setLoadingChain(true);
    setChainErr(null);
    setSelected(null);
    try {
      const res = await optionsApi.chain(sym, { expiration: exp, contract_type: type });
      setRows(res.rows ?? []);
    } catch (e) { setChainErr(String(e)); setRows([]); }
    finally { setLoadingChain(false); }
  }

  function onExpirationChange(exp: string) {
    setExpiration(exp);
    loadChain(underlying, exp, mood);
  }

  function onMoodChange(m: "call" | "put") {
    setMood(m);
    loadChain(underlying, expiration || "", m);
  }

  const atmApprox = useMemo(() => {
    if (!rows.length) return null;
    const mid = (r: OptionContractRow) => ((r.bid ?? 0) + (r.ask ?? 0)) / 2;
    let best = rows[0];
    for (const r of rows) if (mid(r) > mid(best)) best = r;
    return best;
  }, [rows]);

  async function submitOrder() {
    if (!selected) return;
    setPlacing(true); setPlaced(null); setPlaceErr(null);
    try {
      const res = await optionsApi.place({
        contract_symbol: selected.symbol,
        qty,
        side,
        position_intent: intent,
        order_type: orderType,
        limit_price: orderType === "limit" && limitPrice ? Number(limitPrice) : null,
        label: "ui-manual",
      });
      setPlaced({
        order_id: res.order_id,
        status: res.status,
        contract: res.contract_symbol,
        fill: res.filled_avg_price,
        mode: res.mode,
      });
    } catch (e) { setPlaceErr(String(e)); }
    finally { setPlacing(false); }
  }
  return (
    <div className="h-full overflow-y-auto p-3 space-y-3">
      <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
          <Activity size={14} className="text-indigo-400" />
          <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Options - Alpaca Paper</span>
          <span className="ml-auto flex items-center gap-1.5 text-[10px] font-mono text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />LIVE CHAINS
          </span>
        </div>

        {/* Underlying discovery */}
        <div className="p-3 space-y-2">
          <div className="flex gap-2">
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") searchUnderlyings(); }}
              placeholder="Search any underlying (SPY, QQQ, AAPL, TSLA, XLF...)"
              className="flex-1 bg-slate-950 border border-slate-700 rounded px-3 py-1.5 text-xs font-mono text-slate-200 placeholder:text-slate-600 outline-none focus:border-indigo-500"
            />
            <button onClick={searchUnderlyings} disabled={searching}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-indigo-600/30 border border-indigo-500/40 text-xs text-indigo-300 hover:bg-indigo-600/50 disabled:opacity-50">
              {searching ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />} Search
            </button>
          </div>

          {assets.length > 0 && (
            <div className="max-h-44 overflow-y-auto border border-slate-700 rounded bg-slate-950 divide-y divide-slate-800">
              {assets.map(a => (
                <button key={a.symbol} onClick={() => pickUnderlying(a.symbol)}
                  className="w-full flex items-center justify-between gap-2 px-3 py-1.5 text-left hover:bg-slate-800">
                  <span className="font-mono text-xs text-slate-200">{a.symbol}</span>
                  <span className="text-[10px] text-slate-500 truncate max-w-[60%]">{a.name}</span>
                  <span className={clsx("text-[10px] font-mono", a.tradable ? "text-emerald-400" : "text-slate-600")}>
                    {a.tradable ? "TRADABLE" : "N/A"}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* Selection: underlying + expiry + call/put */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500 font-mono">Underlying:</span>
            {["SPY", "QQQ", "AAPL", "TSLA"].map(s => (
              <button key={s} onClick={() => pickUnderlying(s)}
                className={clsx("px-2.5 py-1 rounded text-xs font-mono", underlying === s ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-300")}>
                {s}
              </button>
            ))}
            {!["SPY", "QQQ", "AAPL", "TSLA"].includes(underlying) && (
              <span className="px-2.5 py-1 rounded text-xs font-mono bg-indigo-600 text-white">{underlying}</span>
            )}

            <select value={expiration} onChange={e => onExpirationChange(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-200">
              {!expirations.length && <option value="">expirations...</option>}
              {expirations.map(e => <option key={e} value={e}>{e}</option>)}
            </select>

            <div className="flex rounded overflow-hidden border border-slate-700">
              {MOODS.map(m => (
                <button key={m} onClick={() => onMoodChange(m)}
                  className={clsx("px-3 py-1 text-xs font-mono uppercase",
                    mood === m ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-400")}>
                  {m}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Chain table */}
        <div className="px-3 pb-3">
          {loadingChain ? (
            <div className="flex items-center gap-2 text-xs text-slate-500 py-6 justify-center">
              <Loader2 size={14} className="animate-spin" /> Loading chain...
            </div>
          ) : chainErr ? (
            <div className="text-xs text-red-400 bg-red-950/30 border border-red-800 rounded p-2">{chainErr}</div>
          ) : rows.length === 0 ? (
            <div className="text-xs text-slate-500 py-4 text-center font-mono">No contracts for this selection</div>
          ) : (
            <div className="max-h-[46vh] overflow-y-auto border border-slate-700 rounded">
              <table className="w-full text-xs font-mono">
                <thead className="sticky top-0 bg-slate-950">
                  <tr className="text-slate-500 border-b border-slate-700">
                    <th className="text-left py-1.5 px-2">Strike</th>
                    <th className="text-right px-2">Bid</th>
                    <th className="text-right px-2">Ask</th>
                    <th className="text-right px-2">Mid</th>
                    <th className="text-right px-2">Spread%</th>
                    <th className="text-right px-2">IV</th>
                    <th className="text-right px-2">Delta</th>
                    <th className="text-right px-2">Theta</th>
                    <th className="text-right px-2">OI</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => {
                    const mid = ((r.bid ?? 0) + (r.ask ?? 0)) / 2;
                    const isAtm = atmApprox?.symbol === r.symbol;
                    return (
                      <tr key={r.symbol}
                        onClick={() => setSelected(r)}
                        className={clsx("border-b border-slate-800 cursor-pointer hover:bg-slate-800/60",
                          selected?.symbol === r.symbol ? "bg-indigo-600/10 ring-1 ring-inset ring-indigo-500/40" : "",
                          isAtm && selected?.symbol !== r.symbol ? "bg-slate-800/30" : "")}>
                        <td className="py-1.5 px-2 text-slate-200 font-bold">{fmtN(r.strike_price)}</td>
                        <td className="py-1 text-right text-emerald-400">{r.bid != null ? fmt$(r.bid) : "-"}</td>
                        <td className="py-1 text-right text-red-400">{r.ask != null ? fmt$(r.ask) : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{mid ? fmt$(mid) : "-"}</td>
                        <td className="py-1 text-right text-slate-400">{r.spread_pct != null ? `${(r.spread_pct * 100).toFixed(1)}%` : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{r.implied_volatility != null ? `${(r.implied_volatility * 100).toFixed(0)}%` : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{r.greeks?.delta != null ? r.greeks.delta.toFixed(2) : "-"}</td>
                        <td className="py-1 text-right text-slate-300">{r.greeks?.theta != null ? fmt$(r.greeks.theta) : "-"}</td>
                        <td className="py-1 text-right text-slate-400">{r.open_interest != null ? fmtN(r.open_interest) : "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Order ticket */}
      <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
          <ArrowRightLeft size={14} className="text-emerald-400" />
          <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Order Ticket</span>
        </div>
        <div className="p-3 space-y-3">
          {!selected ? (
            <div className="text-xs text-slate-500 font-mono">Select a contract row above to trade it.</div>
          ) : (
            <>
              <div className="text-xs font-mono text-slate-200 bg-slate-950 border border-slate-700 rounded px-2 py-2">
                {selected.symbol}
                <span className="ml-2 text-slate-500">
                  {selected.contract_type.toUpperCase()} x{selected.multiplier} {selected.expiration_date} Strike {fmtN(selected.strike_price)}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <label className="space-y-1">
                  <span className="text-[10px] text-slate-500 uppercase">Side</span>
                  <select value={side} onChange={e => setSide(e.target.value as "buy" | "sell")}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200">
                    <option value="buy">BUY</option>
                    <option value="sell">SELL</option>
                  </select>
                </label>
                <label className="space-y-1">
                  <span className="text-[10px] text-slate-500 uppercase">Intent</span>
                  <select value={intent} onChange={e => setIntent(e.target.value as typeof intent)}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200">
                    <option value="buy_to_open">BUY TO OPEN</option>
                    <option value="sell_to_open">SELL TO OPEN</option>
                    <option value="buy_to_close">BUY TO CLOSE</option>
                    <option value="sell_to_close">SELL TO CLOSE</option>
                  </select>
                </label>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <label className="space-y-1">
                  <span className="text-[10px] text-slate-500 uppercase">Contracts</span>
                  <input type="number" min={1} value={qty} onChange={e => setQty(Math.max(1, Number(e.target.value) || 1))}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200" />
                </label>
                <label className="space-y-1">
                  <span className="text-[10px] text-slate-500 uppercase">Type</span>
                  <select value={orderType} onChange={e => setOrderType(e.target.value as "market" | "limit")}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200">
                    <option value="market">MARKET</option>
                    <option value="limit">LIMIT</option>
                  </select>
                </label>
              </div>

              {orderType === "limit" && (
                <label className="space-y-1 block">
                  <span className="text-[10px] text-slate-500 uppercase">Limit Price (per contract)</span>
                  <input value={limitPrice} onChange={e => setLimitPrice(e.target.value)}
                    placeholder={(((selected.bid ?? 0) + (selected.ask ?? 0)) / 2).toFixed(2)}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono text-slate-200 placeholder:text-slate-600" />
                </label>
              )}

              <button onClick={submitOrder} disabled={placing}
                className="w-full flex items-center justify-center gap-2 py-2 rounded bg-emerald-600/30 border border-emerald-500/40 text-xs font-bold text-emerald-300 hover:bg-emerald-600/50 disabled:opacity-50">
                {placing ? <Loader2 size={12} className="animate-spin" /> : "Place Option Order"}
              </button>

              {placed && (
                <div className="flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/30 border border-emerald-800 rounded p-2">
                  <CheckCircle2 size={12} />
                  {placed.contract} {placed.status.toUpperCase()} {placed.fill != null ? fmt$(placed.fill) : ""} {placed.mode.toUpperCase()} id {placed.order_id}
                </div>
              )}
              {placeErr && (
                <div className="flex items-center gap-1.5 text-xs font-mono text-red-400 bg-red-950/30 border border-red-800 rounded p-2">
                  <XCircle size={12} /> {placeErr}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
