export function fmt$  (v: number) { return `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }
export function fmtPct(v: number) { return `${(v * 100).toFixed(2)}%`; }
export function fmtN  (v: number | null | undefined, d = 4) { return v == null ? "N/A" : v.toFixed(d); }

export function relTime(iso: string | null): string {
  if (!iso) return "never";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60)  return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export const REGIME_META: Record<string, { color: string; bg: string; desc: string }> = {
  BullMarket:     { color: "text-emerald-400", bg: "bg-emerald-950 border-emerald-700", desc: "Strong uptrend, low vol" },
  RecoveryRegime: { color: "text-brand-400",    bg: "bg-brand-950 border-brand-700",       desc: "Recovering from drawdown" },
  LowVolatility:  { color: "text-brand-400",   bg: "bg-brand-950 border-brand-700",      desc: "Calm, range-bound" },
  HighVolatility: { color: "text-brand-400",  bg: "bg-brand-950 border-brand-700",   desc: "Elevated realised vol" },
  BearMarket:     { color: "text-brand-400",  bg: "bg-brand-950 border-brand-700",   desc: "Below 200-day MA" },
  CrisisRegime:   { color: "text-red-400",     bg: "bg-red-950 border-red-700",         desc: "High VIX + falling market" },
  SystemicStress: { color: "text-red-300",     bg: "bg-red-950 border-red-500",         desc: "VIX > 35 — systemic risk" },
};

export const LABEL_COLOR: Record<string, string> = {
  Concept:      "#6a84de",
  Strategy:     "#10b981",
  Regime:       "#4a63c8",
  Formula:      "#334a9e",
  Ticker:       "#ef4444",
  Category:     "#4a63c8",
  QuizQuestion: "#ef4444",
};
