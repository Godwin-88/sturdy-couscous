import { useMemo } from "react";
import { Activity, BarChart3, Gauge } from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { GreekSurfacePlot } from "@/components/Greeks3DVisualization";
import { pnlSurface, greekSurface, legSumPnl, PnLLeg } from "@/lib/optionmath";
import { OptionContractRow, OptionLeg } from "@/lib/api";
import { fmt$, fmtN } from "@/lib/utils";

interface OptionDiagramsProps {
  selected: OptionContractRow | null;
  side: "buy" | "sell";
  qty: number;
  spot: number | null;
  dte: number;
  rows: OptionContractRow[];
  mood: "call" | "put";
  legs?: OptionLeg[];
}

function toPnlLegs(props: OptionDiagramsProps): PnLLeg[] {
  if (props.legs && props.legs.length > 0) {
    return props.legs.map(l => ({
      strike: l.strike,
      contract_type: l.contract_type,
      side: l.side.startsWith("buy") ? "long" : "short",
      contracts: l.contracts > 0 ? l.contracts : 1,
      multiplier: 100,
      premium: l.mid ?? (l.bid != null && l.ask != null ? (l.bid + l.ask) / 2 : 0),
      iv: l.implied_volatility ?? 0.2,
    }));
  }
  if (!props.selected) return [];
  const s = props.selected;
  const prem = s.bid != null && s.ask != null
    ? (s.bid + s.ask) / 2
    : (s.last ?? 0);
  return [{
    strike: s.strike_price,
    contract_type: s.contract_type,
    side: props.side === "buy" ? "long" : "short",
    contracts: props.qty > 0 ? props.qty : 1,
    multiplier: s.multiplier ?? 100,
    premium: prem,
    iv: s.implied_volatility ?? 0.2,
  }];
}

export default function OptionDiagrams(props: OptionDiagramsProps) {
  const pnlLegs = useMemo(() => toPnlLegs(props), [props.selected, props.side, props.qty, props.legs]);
  const spot0 = useMemo(() => {
    if (props.spot != null && props.spot > 0) return props.spot;
    if (props.selected) return props.selected.strike_price;
    if (props.rows.length) {
      const strikes = props.rows.map(r => r.strike_price);
      return (Math.min(...strikes) + Math.max(...strikes)) / 2;
    }
    return 100;
  }, [props.spot, props.selected, props.rows]);
  const dte = Math.max(1, Math.round(props.dte));

  const payoffData = useMemo(() => {
    if (pnlLegs.length === 0) return [];
    const lo = spot0 * 0.75;
    const hi = spot0 * 1.3;
    const out: { s: number; pnl: number }[] = [];
    for (let i = 0; i < 32; i++) {
      const s = lo + ((hi - lo) * i) / 31;
      out.push({ s, pnl: legSumPnl(pnlLegs, s, 0) });
    }
    return out;
  }, [pnlLegs, spot0]);

  const pnl3d = useMemo(
    () => pnlSurface(pnlLegs, spot0, dte, { xSteps: 14, ySteps: 5, pct: 0.25 }),
    [pnlLegs, spot0, dte],
  );

  const deltaSurface = useMemo(() => {
    if (props.rows.length === 0) return null;
    const centered = [...props.rows]
      .map(r => ({ strike: r.strike_price, iv: r.implied_volatility, diff: Math.abs(r.strike_price - spot0) }))
      .sort((a, b) => a.diff - b.diff)
      .slice(0, 12)
      .map(r => ({ strike: r.strike, iv: r.iv }));
    const dtes = dte >= 7
      ? [Math.max(1, Math.round(dte * 0.2)), Math.max(2, Math.round(dte * 0.5)), dte]
      : [1, 3, dte];
    return greekSurface(centered, spot0, dtes, "delta", props.mood);
  }, [props.rows, spot0, dte, props.mood]);

  const hasDiagrams = pnlLegs.length > 0;
  const negative = payoffData.some(p => p.pnl < 0);
  const netPremium = pnlLegs.reduce((s, l) => s + l.premium * l.contracts * l.multiplier, 0);

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
        <BarChart3 size={14} className="text-emerald-400" />
        <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">Option Diagrams — 3D</span>
        <span className="ml-auto text-[10px] font-mono text-slate-500">drag to rotate · spot-market diagrams</span>
      </div>

      {!hasDiagrams && deltaSurface == null ? (
        <div className="p-4 flex flex-col items-center justify-center gap-2">
          <Activity size={20} className="text-slate-600" />
          <span className="text-xs text-slate-500">Select a contract (or open a suggestion in the ticket) to render pay-off + 3D surfaces.</span>
        </div>
      ) : (
        <div className="p-2.5 grid grid-cols-1 lg:grid-cols-3 gap-2.5">
          {/* 2D Payoff at expiry */}
          <div className="rounded-lg border border-slate-700 bg-slate-900 overflow-hidden">
            <div className="flex items-center gap-2 px-2 py-1.5 border-b border-slate-700 bg-slate-950">
              <Gauge size={11} className="text-violet-400" />
              <span className="text-[10px] font-mono text-slate-300 uppercase">Payoff at Expiry</span>
              <span className="ml-auto text-[10px] font-mono text-slate-500">{pnlLegs.length} leg{pnlLegs.length > 1 ? "s" : ""}</span>
            </div>
            <div className="p-1.5">
              {payoffData.length === 0 ? (
                <div className="text-[10px] font-mono text-slate-500 py-3 text-center">No position to plot</div>
              ) : (
                <ResponsiveContainer width="100%" height={120}>
                  <AreaChart data={payoffData} margin={{ top: 4, right: 4, bottom: 2, left: 2 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="s" tick={{ fontSize: 8, fill: "#64748b" }} tickLine={false}
                           tickFormatter={v => fmtN(v, 0)} />
                    <YAxis tick={{ fontSize: 8, fill: "#64748b" }} tickLine={false}
                           tickFormatter={v => `$ ${v}`} />
                    <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                             labelFormatter={v => `@ $ ${fmtN(v, 0)}`}
                             formatter={(value: unknown) => { const n = Number(value); return `${n >= 0 ? "+" : "−"} $ ${fmt$(Math.abs(n))}`; }} />
                    <Area type="monotone" dataKey="pnl"
                          stroke={negative ? "#f43f5e" : "#10b981"}
                          strokeWidth={1.5}
                          fill={negative ? "#f43f5e22" : "#10b98122"} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
              <div className="text-[9px] font-mono text-slate-600 mt-1">
                P&L = expiry intrinsic − premium · spot {fmt$(spot0)} · {fmt$(netPremium)} net premium
              </div>
            </div>
          </div>

          {/* 3D P&L surface */}
          <div className="rounded-lg border border-slate-700 bg-slate-900 overflow-hidden">
            <div className="flex items-center gap-2 px-2 py-1.5 border-b border-slate-700 bg-slate-950">
              <BarChart3 size={11} className="text-emerald-400" />
              <span className="text-[10px] font-mono text-slate-300 uppercase">3D P&L Surface</span>
              <span className="ml-auto text-[10px] font-mono text-slate-500">spot × DTE</span>
            </div>
            <div className="p-1.5">
              {pnlLegs.length === 0 ? (
                <div className="text-[10px] font-mono text-slate-500 py-3 text-center">Select a position</div>
              ) : (
                <GreekSurfacePlot
                  spotRange={pnl3d.x}
                  dteRange={pnl3d.y}
                  values={pnl3d.values}
                  label="Position P&L"
                  colorScheme="pnl"
                />
              )}
              <div className="text-[9px] font-mono text-slate-600 mt-1">
                Black-Scholes mark-to-market over spot × days-to-expiry (red = loss, green = profit)
              </div>
            </div>
          </div>

          {/* 3D delta surface */}
          <div className="rounded-lg border border-slate-700 bg-slate-900 overflow-hidden">
            <div className="flex items-center gap-2 px-2 py-1.5 border-b border-slate-700 bg-slate-950">
              <BarChart3 size={11} className="text-indigo-400" />
              <span className="text-[10px] font-mono text-slate-300 uppercase">3D Δ Surface</span>
              <span className="ml-auto text-[10px] font-mono text-slate-500">strike × DTE</span>
            </div>
            <div className="p-1.5">
              {deltaSurface == null ? (
                <div className="text-[10px] font-mono text-slate-500 py-3 text-center">Load a chain to plot Δ</div>
              ) : (
                <GreekSurfacePlot
                  spotRange={deltaSurface.x}
                  dteRange={deltaSurface.y}
                  values={deltaSurface.values}
                  label={`Delta Surface (${props.mood.toUpperCase()})`}
                  colorScheme="delta"
                />
              )}
              <div className="text-[9px] font-mono text-slate-600 mt-1">
                Chain strikes × DTE — how Δ flattens as expiry approaches; feed the dynamic hedge
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
