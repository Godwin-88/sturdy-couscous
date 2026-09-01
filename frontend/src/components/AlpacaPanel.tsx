import { Wallet, ShieldCheck, ShieldAlert, ArrowRight, RefreshCw } from "lucide-react";
import { alpacaApi, AlpacaAccount, AlpacaPosition } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmt$, fmtN } from "@/lib/utils";
import clsx from "clsx";
import { useNavigate } from "react-router-dom";

type AlpacaState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "unconfigured" }
  | { kind: "paper"; account: AlpacaAccount; positions: AlpacaPosition[] };

export default function AlpacaPanel() {
  const navigate = useNavigate();
  const { data: account, error: acctErr, loading: acctLoading, refresh: refreshAccount } = usePolling<AlpacaAccount>(
    () => alpacaApi.account(),
    10_000,
  );
  const { data: positions } = usePolling<AlpacaPosition[]>(() => alpacaApi.positions(), 10_000);
  const state: AlpacaState = acctLoading
    ? { kind: "loading" }
    : acctErr
    ? { kind: "error", message: acctErr }
    : !account || !account.status || account.status === "unconfigured"
    ? { kind: "unconfigured" }
    : { kind: "paper", account, positions: positions ?? [] };

  const goPlaceOrder = () => navigate("/signals");

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700 bg-slate-950">
        <div className="flex items-center gap-2">
          <Wallet size={14} className="text-emerald-400" />
          <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Alpaca Paper Trading</span>
        </div>
        <div className="flex items-center gap-2">
          {state.kind === "paper" && (
            <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-mono">
              <ShieldCheck size={11} /> PAPER CONNECTED
            </span>
          )}
          {state.kind === "unconfigured" && (
            <span className="flex items-center gap-1 text-[10px] text-slate-500 font-mono">
              <ShieldAlert size={11} /> UNCONFIGURED
            </span>
          )}
          {state.kind === "error" && (
            <span className="flex items-center gap-1 text-[10px] text-red-400 font-mono">
              <ShieldAlert size={11} /> ERROR
            </span>
          )}
          <button onClick={refreshAccount} className="p-1 rounded text-slate-500 hover:text-slate-300">
            <RefreshCw size={12} />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="p-3 space-y-3">
        {state.kind === "loading" && (
          <div className="text-xs text-slate-500">Connecting to Alpaca…</div>
        )}
        {state.kind === "error" && (
          <div className="text-xs text-red-400 bg-red-950/30 border border-red-800 rounded p-2">
            {state.message}
          </div>
        )}
        {state.kind === "unconfigured" && (
          <div className="text-xs text-slate-400 space-y-1">
            <p>Add <code className="text-amber-300">ALPACA_API_KEY_ID</code> + <code className="text-amber-300">ALPACA_API_SECRET_KEY</code> to your <code>.env</code> to paper-trade from the UI.</p>
            <p className="text-slate-500">Until then, orders simulate fills (venue defaults to Alpaca paper).</p>
          </div>
        )}
{state.kind === "paper" && (
          <>
            {/* Account metrics */}
            <div className="grid grid-cols-3 gap-2">
              <Metric label="Equity" value={fmt$(state.account.equity)} />
              <Metric label="Cash" value={fmt$(state.account.cash)} />
              <Metric label="Buying Power" value={fmt$(state.account.buying_power)} />
            </div>

            {/* Positions */}
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
                Positions ({state.positions.length})
              </div>
              {state.positions.length === 0 ? (
                <div className="text-xs text-slate-500 font-mono">No open positions</div>
              ) : (
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-700">
                      <th className="text-left pb-1">Symbol</th>
                      <th className="text-left pb-1">Side</th>
                      <th className="text-right pb-1">Qty</th>
                      <th className="text-right pb-1">Entry</th>
                      <th className="text-right pb-1">Mkt Val</th>
                      <th className="text-right pb-1">UPL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.positions.map(p => {
                      const upl = (p.current_price - p.avg_entry_price) * p.qty;
                      const sideUp = p.side === "buy";
                      return (
                        <tr key={p.symbol} className="border-b border-slate-800">
                          <td className="py-1 text-slate-100 font-bold">{p.symbol}</td>
                          <td className={clsx("py-1", sideUp ? "text-emerald-400" : "text-red-400")}>{p.side.toUpperCase()}</td>
                          <td className="py-1 text-right text-slate-300">{fmtN(p.qty)}</td>
                          <td className="py-1 text-right text-slate-400">{fmt$(p.avg_entry_price)}</td>
                          <td className="py-1 text-right text-slate-300">{fmt$(p.market_value)}</td>
                          <td className={clsx("py-1 text-right font-bold", upl >= 0 ? "text-emerald-400" : "text-red-400")}>
                            {upl >= 0 ? "+" : ""}{fmt$(upl)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}

        {/* CTA — Place Order (routes to Signals tab, venue defaults to alpaca) */}
        <button
          onClick={goPlaceOrder}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium bg-emerald-700 hover:bg-emerald-600 text-white transition-colors"
        >
          <ArrowRight size={12} /> Place Order on Alpaca
        </button>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-800 rounded-lg p-2 border border-slate-700 text-center">
      <div className="text-[10px] text-slate-500 uppercase">{label}</div>
      <div className="text-sm font-bold font-mono text-slate-100">{value}</div>
    </div>
  );
}