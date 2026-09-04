import { Wallet, HelpCircle, ShieldAlert, ArrowRight } from "lucide-react";
import { alpacaApi, AlpacaPosition } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmt$, fmtN } from "@/lib/utils";
import clsx from "clsx";

/**
 * Broker positions table — real Alpaca paper book.
 * Every column header carries a hover tooltip (title) explaining what it shows,
 * so the table is self-documenting for UI/UX.
 */
const COLUMN_HINTS: { key: string; label: string; hint: string; align: string }[] = [
  { key: "symbol", label: "Symbol", hint: "Alpaca asset/contract symbol. OCC format for options (e.g. AAPL260904C00330000), PAIR/USD for crypto (e.g. BTC/USD), plain ticker for equities/ETFs.", align: "text-left" },
  { key: "side",   label: "Side",   hint: "Position direction — LONG = positive quantity (you own), SHORT = negative quantity (you owe). Detected from signed qty the broker reports.", align: "text-left" },
  { key: "qty",    label: "Qty",    hint: "Signed quantity held. For options it's the number of contracts (×100 for notional); for crypto it's the base-unit amount (e.g. 0.001 BTC).", align: "text-right" },
  { key: "entry",  label: "Entry",  hint: "Volume-weighted average entry price per unit/contract — the price your open position was filled at.", align: "text-right" },
  { key: "last",   label: "Last",   hint: "Latest live mark price of the asset/contract from Alpaca.", align: "text-right" },
  { key: "mkt",    label: "Mkt Val",hint: "Current market value of the position = last × qty × 100 for options, last × qty for equity/crypto.", align: "text-right" },
  { key: "upl",    label: "UPL",    hint: "Unrealized P&L = (last − entry) × qty, sign-aware for shorts. Green positive, red negative, $0 flat.", align: "text-right" },
  { key: "dte",    label: "DTE",    hint: "Days-to-expiration for option contracts (— for equity/crypto). At 0 the contract expires today.", align: "text-right" },
];

function isOptionSymbol(s: string) {
  return /^(?:[A-Z]{1,5}\d{6}[CP]\d{8})$/.test(s);
}

function dteFromOCC(symbol: string): number | null {
  const m = symbol.match(/(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/);
  if (!m) return null;
  const [, yy, mm, dd] = m;
  const y = 2000 + parseInt(yy, 10), mo = parseInt(mm, 10) - 1, d = parseInt(dd, 10);
  const expiry = new Date(y, mo, d);
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return Math.round((expiry.getTime() - now.getTime()) / 86_400_000);
}

export default function BrokerTablePanel({ onNavigate }: { onNavigate?: (tab: string) => void } = {}) {
  const { data: positions } = usePolling<AlpacaPosition[]>(() => alpacaApi.positions(), 10_000);

  const goRisk = () => {
    if (onNavigate) { onNavigate("risk"); return; }
    window.location.hash = "#/risk";
  };

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
        <Wallet size={14} className="text-indigo-400" />
        <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">
          Broker Positions
        </span>
        <span className="ml-auto flex items-center gap-1 text-[10px] text-slate-500 font-mono">
          <HelpCircle size={11} /> hover a column for meaning
        </span>
        <button
          onClick={goRisk}
          title="Open the Risk workspace (exposure, VaR, concentration, option book) for this broker account"
          className="flex items-center gap-1 px-2 py-1 rounded bg-rose-600/30 border border-rose-500/40 text-[10px] font-bold text-rose-300 hover:bg-rose-600/50"
        >
          <ShieldAlert size={10} /> Risk <ArrowRight size={10} />
        </button>
      </div>

      {!positions || positions.length === 0 ? (
        <div className="text-center py-6 text-slate-500 text-sm font-mono">No open positions</div>
      ) : (
        <div className="max-h-[320px] overflow-y-auto">
          <table className="w-full text-xs font-mono">
            <thead className="sticky top-0 bg-slate-950 z-10">
              <tr className="text-slate-400 border-b border-slate-700">
                {COLUMN_HINTS.map(c => (
                  <th
                    key={c.key}
                    className={`${c.align ?? "text-left"} py-2 px-2 group relative`}
                    title={c.hint}
                  >
                    <span className="border-b border-dotted border-slate-600 hover:text-slate-200 inline-block">
                      {c.label}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.map(p => {
                const sideSign = p.qty < 0 || p.side === "sell" ? -1 : 1;
                const upl = sideSign * (p.current_price - p.avg_entry_price) * Math.abs(p.qty);
                const up = upl >= 0;
                const isOpt = isOptionSymbol(p.symbol);
                const dte = isOpt ? dteFromOCC(p.symbol) : null;
                return (
                  <tr key={p.symbol} className="border-b border-slate-800 hover:bg-slate-800/40">
                    <td className="py-1.5 px-2 text-slate-100 font-bold whitespace-nowrap">{p.symbol}</td>
                    <td className={clsx("py-1.5 px-2", sideSign > 0 ? "text-emerald-400" : "text-red-400")}>
                      {sideSign > 0 ? "LONG" : "SHORT"}
                    </td>
                    <td className="py-1.5 px-2 text-right text-slate-300">{fmtN(p.qty)}</td>
                    <td className="py-1.5 px-2 text-right text-slate-400">{fmt$(p.avg_entry_price)}</td>
                    <td className="py-1.5 px-2 text-right text-slate-300">{fmt$(p.current_price)}</td>
                    <td className="py-1.5 px-2 text-right text-slate-300">{fmt$(p.market_value)}</td>
                    <td className={clsx("py-1.5 px-2 text-right font-bold", up ? "text-emerald-400" : "text-red-400")}>
                      {up ? "+" : ""}{fmt$(upl)}
                    </td>
                    <td className="py-1.5 px-2 text-right text-amber-300">
                      {isOpt ? (dte != null ? `${dte}D` : "—") : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}