/**
 * Centralised API config and typed fetcher.
 * All components import from here — one place to change the base URL.
 */

export const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export const WS_BASE = API_BASE.replace(/^http/, "ws");

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json() as Promise<T>;
}

// ── Typed API calls ────────────────────────────────────────────────────────────

export interface AgentStatus {
  regime:            string;
  regime_confidence: number;
  active_strategies: string[];
  signals_generated: number;
  orders_approved:   number;
  last_cycle_at:     string | null;
  halted:            boolean;
  cycle_duration_s:  number;
}

export interface Position {
  ticker:          string;
  direction:       string;
  quantity:        number;
  avg_entry_price: number;
  current_price:   number;
  unrealised_pnl:  number;
  status:          string;
}

export interface Portfolio {
  nav:              number;
  cash:             number;
  drawdown_pct:     number;
  halted:           boolean;
  updated_at?:      string;
}

export interface Signal {
  order_id:     string;
  strategy:     string;
  ticker:       string;
  direction:    string;
  quantity:     number;
  fill_price:   number;
  mode:         string;
  signal_score: number;
  created_at:   string;
}

export interface GraphNode {
  id:         number;
  labels:     string[];
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  source:   number;
  target:   number;
  rel_type: string;
  props?:   Record<string, unknown>;
}

export interface Contradiction {
  strategy_a:    string;
  strategy_b:    string;
  via_concept_a: string;
  via_concept_b: string;
}

export interface BacktestResult {
  total_return:   number;
  sharpe_ratio:   number;
  calmar_ratio:   number;
  max_drawdown:   number;
  ann_volatility: number;
  n_days:         number;
  final_nav:      number;
  use_graph:      boolean;
  jk_z_stat?:    number;
  jk_p_value?:   number;
  jk_significant?: boolean;
  start:          string;
  end:            string;
}

export const agentApi = {
  status:         () => apiFetch<AgentStatus>("/agent/status"),
  positions:      () => apiFetch<Position[]>("/positions"),
  portfolio:      () => apiFetch<Portfolio>("/positions/portfolio"),
  signals:        (limit = 50) => apiFetch<Signal[]>(`/signals?limit=${limit}`),
  liveSignals:    () => apiFetch<Signal[]>("/signals/live"),
  graphNodes:     (nodeType?: string, limit = 300) =>
    apiFetch<GraphNode[]>(`/graph/nodes?${nodeType ? `node_type=${nodeType}&` : ""}limit=${limit}`),
  graphEdges:     (limit = 800) => apiFetch<GraphEdge[]>(`/graph/edges?limit=${limit}`),
  contradictions: () => apiFetch<Contradiction[]>("/graph/contradictions"),
  regimeGraph:    (regime: string) =>
    apiFetch<Record<string, unknown>[]>(`/graph/regime?regime=${regime}`),
  backtestStatus: () => apiFetch<{ status: string; result: BacktestResult | null }>("/backtest/status"),
  runBacktest:    (params: { start_date: string; end_date: string; initial_capital: number; use_graph: boolean }) =>
    apiFetch<{ status: string }>("/backtest/run", { method: "POST", body: JSON.stringify(params) }),
};
