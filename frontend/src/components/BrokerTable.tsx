import { useNavigate } from "react-router-dom";
import { LineChart } from "lucide-react";
import { alpacaApi, AlpacaPosition } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmt$, fmtN } from "@/lib/utils";
import clsx from "clsx";

export const COLUMN_HINTS: { key: string; label: string; hint: string; align: string }[] = [
  { key: "symbol", label: "Symbol", hint: "Alpaca asset/contract symbol. OCC format for options (e.g. AAPL260904C00330000), PAIR/USD for crypto (e.g. BTC/USD), plain ticker for equities/ETFs.", align: "text-left" },
  { key: "side",   label: "Side",   hint: "Position direction — LONG = positive quantity (you own), SHORT = negative quantity (you owe). Detected from signed qty the broker reports.", align: "text-left" },
  { key: "qty",    label: "Qty",    hint: "Signed quantity held. For options it's the number of contracts (×100 for notional); for crypto it's the base-unit amount (e.g. 0.001 BTC).", align: "text-right" },
  { key: "entry",  label: "Entry",  hint: "Volume-weighted average entry price per unit/contract — the price your open position was filled at.", align: "text-right" },
  { key: "last",   label: "Last",   hint: "Latest live mark price of the asset/contract from Alpaca.", align: "text-right" },
  { key: "mkt",    label: "Mkt Val",hint: "Current market value of the position = last × qty × 100 for options, last × qty for equity/crypto.", align: "text-right" },
  { key: "upl",    label: "UPL",    hint: "Unrealized P&L = (last − entry) × qty, sign-aware for shorts. Green positive, red negative, $0 flat.", align: "text-right" },
  { key: "dte",    label: "DTE",    hint: "Days-to-expiration for option contracts (— for equity/crypto). At 0 the contract expires today.", align: "text-right" },
];

export function isOptionSymbol(s: string) {
  return /^(?:[A-Z]{1,5}\d{6}[CP]\d{8})$/.test(s);
}

export function dteFromOCC(symbol: string): number | null {
  const m = symbol.match(/(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/);
  if (!m) return null;
  const [, yy, mm, dd] = m;
  const y = 2000 + parseInt(yy, 10), mo = parseInt(mm, 10) - 1, d = parseInt(dd, 10);
  const expiry = new Date(y, mo, d);
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return Math.round((expiry.getTime() - now.getTime()) / 86_400_000);
}

/** OCC → underlying root (e.g. AAPL260904C00330000 → AAPL). For equity/crypto passthrough. */
export function underlyingFromSymbol(symbol: string): string {
  if (isOptionSymbol(symbol)) {
    return symbol.replace(/\d{6}[CP]\d{8}$/, "");
  }
  return symbol.replace("/", "-"); // e.g. BTC/USD → BTC-USD
}

export function seriesIdForPosition(symbol: string): string {
  const root = underlyingFromSymbol(symbol);
  return `px:${root}:Close`;
}

function Row({ p, onAnalyze }: { p: AlpacaPosition; onAnalyze: (p: AlpacaPosition) => void }) {
  const sideSign = p.qty < 0 || p.side === "sell" ? -1 : 1;
  const upl = sideSign * (p.current_price - p.avg_entry_price) * Math.abs(p.qty);
  const up = upl >= 0;
  const isOpt = isOptionSymbol(p.symbol);
  const dte = isOpt ? dteFromOCC(p.symbol) : null;
  return (
    <tr className="border-b border-slate-800 hover:bg-slate-800/40">
      <td className="py-1.5 px-2 text-slate-100 font-bold whitespace-nowrap font-mono">{p.symbol}</td>
      <td className={clsx("py-1.5 px-2 font-mono", sideSign > 0 ? "text-emerald-400" : "text-red-400")}>
        {sideSign > 0 ? "LONG" : "SHORT"}
      </td>
      <td className="py-1.5 px-2 text-right text-slate-300 font-mono">{fmtN(p.qty)}</td>
      <td className="py-1.5 px-2 text-right text-slate-400 font-mono">{fmt$(p.avg_entry_price)}</td>
      <td className="py-1.5 px-2 text-right text-slate-300 font-mono">{fmt$(p.current_price)}</td>
      <td className="py-1.5 px-2 text-right text-slate-300 font-mono">{fmt$(p.market_value)}</td>
      <td className={clsx("py-1.5 px-2 text-right font-bold font-mono", up ? "text-emerald-400" : "text-red-400")}>
        {up ? "+" : ""}{fmt$(upl)}
      </td>
      <td className="py-1.5 px-2 text-right text-amber-300 font-mono">
        {isOpt ? (dte != null ? `${dte}D` : "—") : "—"}
      </td>
      <td className="py-1.5 px-2 text-center">
        <button
          onClick={() => onAnalyze(p)}
          title={`Open Analytics for ${underlyingFromSymbol(p.symbol)} (single position, in isolation)`}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-indigo-600/20 border border-indigo-500/30 text-indigo-300 hover:bg-indigo-600/40"
        >
          <LineChart size={10} /> Analyze
        </button>
      </td>
    </tr>
  );
}


export default function BrokerTable({ onNavigate, maxHeight = "max-h-[320px]" }: { onNavigate?: (tab: string) => void; maxHeight?: string }) {
  const navigate = useNavigate();
  const { data: positions } = usePolling<AlpacaPosition[]>(() => alpacaApi.positions(), 10_000);

  const handleAnalyze = (p: AlpacaPosition) => {
    navigate(`/analytics?series=${encodeURIComponent(seriesIdForPosition(p.symbol))}`);
  };

  if (!positions || positions.length === 0) {
    return <div className="text-center py-6 text-slate-500 text-sm font-mono">No open positions</div>;
  }

  return (
    <div className={`${maxHeight} overflow-y-auto`}>
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-slate-950 z-10">
          <tr className="text-slate-400 border-b border-slate-700">
            {COLUMN_HINTS.map(c => (
              <th key={c.key} className={`${c.align ?? "text-left"} py-2 px-2 group relative`} title={c.hint}>
                <span className="border-b border-dotted border-slate-600 hover:text-slate-200 inline-block">
                  {c.label}
                </span>
              </th>
            ))}
            <th className="text-center py-2 px-2 group relative" title="Analyze this position’s underlying in isolation on the Analytics page">
              <span className="flex items-center gap-1 border-b border-dotted border-slate-600 hover:text-slate-200 inline-block">
                <LineChart size={11} /> Action
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {positions.map(p => <Row key={p.symbol} p={p} onAnalyze={handleAnalyze} />)}
        </tbody>
      </table>
    </div>
  );
}
