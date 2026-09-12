import { TrendingDown, DollarSign, ArrowUp, ArrowDown, Scale, Layers, Activity, Gauge } from "lucide-react";

const ASSET_CLASS_ORDER = ["equity", "vol", "rates", "commodity", "crypto", "fx", "other"];
const ASSET_CLASS_COLOR: Record<string, string> = {
  equity:    "text-brand-500",
  vol:       "text-red-500",
  rates:     "text-brand-500",
  commodity: "text-brand-500",
  crypto:    "text-brand-500",
  fx:        "text-brand-500",
  other:     "text-slate-500",
};
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { agentApi, alpacaApi, AlpacaPortfolio, AlpacaPosition, MarketQuote } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmt$, fmtPct } from "@/lib/utils";
import clsx from "clsx";

export default function PnLDashboard({ onNavigate }: { onNavigate?: (tab: string) => void } = {}) {
  const { data: portfolio } = usePolling<AlpacaPortfolio>(alpacaApi.portfolio, 10_000);
  const { data: brokerPositions } = usePolling<AlpacaPosition[]>(() => alpacaApi.positions(), 10_000);
  const { data: quotes }    = usePolling<MarketQuote[]>(agentApi.marketQuotes, 60_000);


  // Real NAV curve, ending at today's live equity (Alpaca's weekly history can lag a day).
  const navHistory = (portfolio?.nav_history ?? []).map(pt => ({
    t: new Date(pt.t).toLocaleDateString("en-US", { month: "numeric", day: "numeric" }),
    nav: pt.equity,
  })).slice(-60);
  if (portfolio?.nav && navHistory.length > 0) {
    const lastEquity = navHistory[navHistory.length - 1].nav;
    if (Math.abs(lastEquity - (portfolio.nav ?? 0)) > 1) {
      navHistory.push({
        t: "now",
        nav: portfolio.nav ?? 0,
      });
    }
  }
  const navSource = portfolio?.source ?? "ledger";

  // ── Exposure metrics (review-table parity) ─────────────────────────────
  // Gross exposure = sum of |market value| (shorts count); Net = signed sum.
  const grossExposure = (brokerPositions ?? []).reduce((s, p) => s + Math.abs(p.market_value), 0);
  const netExposure   = (brokerPositions ?? []).reduce((s, p) => s + p.market_value, 0);
  const nav = portfolio?.nav ?? portfolio?.equity ?? 0;
  const grossPct = nav ? grossExposure / nav : 0;
  const netPct   = nav ? netExposure / nav : 0;
  const leverageEl = grossExposure !== 0 && nav > 0 ? (grossExposure / nav - 1) : 0;
  const cash = portfolio?.cash ?? 0;
  const buyingPower = portfolio?.buying_power;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden transition-all duration-200 hover:border-slate-500 hover:shadow-lg hover:shadow-emerald-500/10 hover:-translate-y-0.5 cursor-pointer">
      {/* Market data strip */}
      {quotes && quotes.length > 0 && (
        <div className="flex items-center border-b border-slate-700 bg-slate-950 overflow-x-auto">
          {ASSET_CLASS_ORDER.map(cls => {
            const group = quotes.filter(q => q.asset_class === cls && !q.error);
            if (group.length === 0) return null;
            return (
              <div key={cls} className="flex items-center border-r border-slate-800 shrink-0">
                <span className={`px-1.5 text-[9px] font-mono uppercase tracking-widest shrink-0 ${ASSET_CLASS_COLOR[cls] ?? "text-slate-600"}`}>
                  {cls}
                </span>
                {group.map(q => <QuoteTile key={q.ticker} q={q} />)}
              </div>
            );
          })}
        </div>
      )}

      {/* Data-source badge — real broker vs internal ledger */}
      <div className="flex items-center gap-1.5 px-3 py-1 bg-slate-950 border-b border-slate-700">
        {navSource === "alpaca" ? (
          <>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[10px] font-mono uppercase tracking-widest text-emerald-400">
              Alpaca Paper · Real Broker NAV
            </span>
          </>
        ) : (
          <>
            <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400">
              Internal ledger NAV (Alpaca not configured)
            </span>
          </>
        )}
      </div>

      {/* Stats row — ALL core risk metrics, always visible above the NAV chart */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 divide-x divide-slate-700 border-b border-slate-700">
        <StatCell
          icon={<DollarSign size={14} />}
          label="NAV"
          value={portfolio ? fmt$(portfolio.nav) : "—"}
          sub={navSource === "alpaca" ? "Alpaca" : "ledger"}
        />
        <StatCell
          icon={<Scale size={14} />}
          label="Gross Exposure"
          value={grossExposure > 0 ? fmt$(grossExposure) : "—"}
          sub={grossExposure > 0 && nav ? `${(grossPct * 100).toFixed(1)}% NAV · ${leverageEl > 0.005 ? `${(leverageEl * 100).toFixed(0)}% lev` : "no lev"}` : undefined}
          warn={leverageEl > 0.10}
        />
        <StatCell
          icon={<Layers size={14} />}
          label="Net Exposure"
          value={Math.abs(netExposure) > 0 ? fmt$(netExposure) : "—"}
          sub={Math.abs(netExposure) > 0 && nav ? `${(netPct * 100).toFixed(1)}% NAV${Math.abs(netPct - grossPct) > 0.005 ? " · hedged" : ""}` : undefined}
          positive={Math.abs(netPct - grossPct) > 0.005}
        />
        <StatCell
          icon={<Activity size={14} />}
          label="Cash"
          value={portfolio ? fmt$(cash) : "—"}
          sub={portfolio ? (cash < 0 ? "margin used" : "available") : undefined}
          positive={cash >= 0}
        />
        <StatCell
          icon={<Gauge size={14} />}
          label="Buying Power"
          value={buyingPower != null ? fmt$(buyingPower) : "—"}
          sub={buyingPower != null && nav ? `${(buyingPower / nav).toFixed(2)}× NAV` : undefined}
          positive={(buyingPower ?? 0) > 0}
        />
        <StatCell
          icon={<TrendingDown size={14} />}
          label="Drawdown"
          value={portfolio ? fmtPct(portfolio.drawdown_pct) : "—"}
          sub="limit 10%"
          positive={false}
          warn={(portfolio?.drawdown_pct ?? 0) > 0.05}
        />
      </div>

      {/* Tab bar — chart is the primary, positions now live in their own table below */}
      <div className="flex border-b border-slate-700">
        <span className="px-4 py-2 text-xs font-mono uppercase tracking-wider text-brand-400 border-b-2 border-brand-500 bg-slate-800">
          NAV
        </span>
      </div>

      {/* Content — real NAV chart */}
      <div className="p-3">
        <NavChart data={navHistory} />
      </div>
    </div>
  );
}

function QuoteTile({ q }: { q: MarketQuote }) {
  if (q.error) return null;
  const up = q.daily_chg >= 0;
  return (
    <div className="flex items-center gap-2 px-2 py-1.5 shrink-0 border-r border-slate-800/50 last:border-r-0">
      <span className="text-xs font-mono font-bold text-slate-300">{q.display ?? q.ticker}</span>
      <span className="text-xs font-mono text-slate-200">{q.last.toFixed(2)}</span>
      <span className={clsx("flex items-center gap-0.5 text-[10px] font-mono",
        up ? "text-emerald-400" : "text-red-400")}>
        {up ? <ArrowUp size={8} /> : <ArrowDown size={8} />}
        {Math.abs(q.daily_chg * 100).toFixed(2)}%
      </span>
      <span className="text-[10px] font-mono text-slate-500" title="Realized Vol">
        σ {(q.realized_vol * 100).toFixed(1)}%
      </span>
      {q.iv_rank != null && (
        <span className="text-[10px] font-mono text-brand-400" title="IV Rank">
          IVR {(q.iv_rank * 100).toFixed(0)}
        </span>
      )}
    </div>
  );
}

function StatCell({
  icon, label, value, sub, positive, warn,
}: {
  icon: React.ReactNode; label: string; value: string;
  sub?: string; positive?: boolean; warn?: boolean;
}) {
  return (
    <div className="p-3 flex flex-col gap-0.5">
      <div className="flex items-center gap-1 text-slate-400 text-xs">
        {icon}{label}
      </div>
      <div className={clsx(
        "text-lg font-mono font-bold",
        warn ? "text-red-400 animate-pulse-slow" :
        positive === true  ? "text-emerald-400" :
        positive === false ? "text-red-400" : "text-slate-100"
      )}>
        {value}
      </div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

function PositionsTable({ positions }: { positions: AlpacaPosition[] }) {
  if (positions.length === 0) {
    return <div className="text-center py-6 text-slate-500 text-sm">No open positions</div>;
  }
  return (
    <table className="w-full text-xs font-mono">
      <thead>
        <tr className="text-slate-400 border-b border-slate-700">
          <th className="text-left pb-2">Symbol</th>
          <th className="text-left pb-2">Side</th>
          <th className="text-right pb-2">Qty</th>
          <th className="text-right pb-2">Entry</th>
          <th className="text-right pb-2">Last</th>
          <th className="text-right pb-2">Mkt Val</th>
          <th className="text-right pb-2">UPL</th>
        </tr>
      </thead>
      <tbody>
        {positions.map(p => {
          const sideSign = p.qty < 0 || p.side === "sell" ? -1 : 1;
          const upl = sideSign * (p.current_price - p.avg_entry_price) * Math.abs(p.qty);
          const up = upl >= 0;
          return (
            <tr key={p.symbol} className="border-b border-slate-800 hover:bg-slate-800/50">
              <td className="py-1.5 text-slate-100 font-bold">{p.symbol}</td>
              <td className={clsx("py-1.5", sideSign > 0 ? "text-emerald-400" : "text-red-400")}>
                {sideSign > 0 ? "LONG" : "SHORT"}
              </td>
              <td className="py-1.5 text-right text-slate-300">{p.qty.toFixed(4)}</td>
              <td className="py-1.5 text-right text-slate-400">{fmt$(p.avg_entry_price)}</td>
              <td className="py-1.5 text-right text-slate-300">{fmt$(p.current_price)}</td>
              <td className="py-1.5 text-right text-slate-300">{fmt$(p.market_value)}</td>
              <td className={clsx("py-1.5 text-right font-bold", up ? "text-emerald-400" : "text-red-400")}>
                {up ? "+" : ""}{fmt$(upl)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function NavChart({ data }: { data: { t: string; nav: number }[] }) {
  if (data.length === 0) {
    return <div className="text-center py-6 text-slate-500 text-sm">No broker history yet — run a few paper cycles and this chart populates from Alpaca</div>;
  }
  const isUp = data[data.length - 1].nav >= data[0].nav;
  const color = isUp ? "#10b981" : "#ef4444";
  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="navGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor={color} stopOpacity={0.3} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#0c143a" />
        <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#525f8e" }} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: "#525f8e" }} tickLine={false}
               tickFormatter={v => `$${(v/1000).toFixed(1)}k`} />
        <Tooltip
          contentStyle={{ background: "#0c143a", border: "1px solid #182250", borderRadius: 8 }}
          labelStyle={{ color: "#7d89b8", fontSize: 11 }}
          formatter={(v: number) => [fmt$(v), "NAV"]}
        />
        <Area type="monotone" dataKey="nav" stroke={color} strokeWidth={2}
              fill="url(#navGrad)" dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
