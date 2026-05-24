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

// ── Types ──────────────────────────────────────────────────────────────────────

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
  nav:          number;
  cash:         number;
  drawdown_pct: number;
  halted:       boolean;
  updated_at?:  string;
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
  suppressed:    boolean;
}

export interface TradeLogEntry {
  ticker:       string;
  strategy:     string;
  direction:    string;
  entry_date:   string;
  exit_date:    string;
  entry_price:  number;
  exit_price:   number;
  qty:          number;
  pnl:          number;
  fee:          number;
  hold_days:    number;
  regime:       string;
}

export interface StrategyBreakdown {
  strategy:  string;
  total_pnl: number;
  n_trades:  number;
  win_rate:  number;
  avg_pnl:   number;
}

export interface WalkForwardWindow {
  id:           number;
  train_start:  string;
  train_end:    string;
  test_start:   string;
  test_end:     string;
  sharpe_ratio: number;
  total_return: number;
  max_drawdown: number;
  n_trades:     number;
  final_nav:    number;
}

export interface TradeSuggestion {
  id:              string;
  strategy:        string;
  ticker:          string;
  direction:       string;
  regime:          string;
  rationale:       string;
  backtest_pnl:    number;
  backtest_trades: number;
  win_rate:        number;
  status:          string;
  created_at:      string;
  notes?:          string;
}

export interface BacktestResult {
  total_return:         number;
  sharpe_ratio:         number;
  calmar_ratio:         number;
  max_drawdown:         number;
  ann_volatility:       number;
  n_days:               number;
  final_nav:            number;
  use_graph:            boolean;
  start:                string;
  end:                  string;
  n_trades:             number;
  win_rate:             number;
  avg_hold_days:        number;
  profit_factor:        number;
  equity_curve?:        { date: string; nav: number }[];
  benchmark_curve?:     { date: string; nav: number }[];
  drawdown_series?:     { date: string; dd: number }[];
  trade_log?:           TradeLogEntry[];
  strategy_breakdown?:  StrategyBreakdown[];
  walk_forward_windows?: WalkForwardWindow[];
  regime_distribution?: Record<string, number>;
  suggestions?:         TradeSuggestion[];
  jk_z_stat?:           number;
  jk_p_value?:          number;
  jk_significant?:      boolean;
}

export interface MarketQuote {
  ticker:       string;
  display:      string;
  asset_class:  string;
  last:         number;
  prev_close:   number;
  daily_chg:    number;
  realized_vol: number;
  iv_rank:      number | null;
  volume:       number | null;
  error?:       string;
}

export interface SignalLineage {
  strategy:      string;
  strategy_desc: string | null;
  concepts:      { name: string; definition: string; category: string; difficulty: string }[];
  formulas:      { id: string; name: string; expression: string; output: string }[];
  regimes:       string[];
  categories:    string[];
}

export interface EligibleStrategy {
  name:        string;
  description: string;
  db_status:   string;
  active:      boolean;
}

export interface RiskMetrics {
  nav:                number;
  gross_exposure:     number;
  net_exposure:       number;
  gross_pct_nav:      number;
  net_pct_nav:        number;
  drawdown_current:   number;
  drawdown_limit:     number;
  drawdown_remaining: number;
  kelly_fraction:     number | null;
  concentration:      { ticker: string; mkt_val: number; pct_nav: number; direction: string; pnl: number }[];
  n_positions:        number;
  halted:             boolean;
}

export interface NewsResult {
  ticker_sentiment:  Record<string, number>;
  concept_sentiment: Record<string, number>;
  articles:          number;
  top_headlines:     string[];
}

export interface MacroEvent {
  name:     string;
  date:     string;
  impact:   "HIGH" | "MEDIUM" | "LOW";
  concepts: string[];
}

export interface MacroResult {
  events:            number;
  pre_event_signals: Record<string, number>;
  upcoming:          MacroEvent[];
}

// ── API calls ──────────────────────────────────────────────────────────────────

export const agentApi = {
  status:         () => apiFetch<AgentStatus>("/agent/status"),
  risk:           () => apiFetch<RiskMetrics>("/agent/risk"),
  positions:      () => apiFetch<Position[]>("/positions"),
  portfolio:      () => apiFetch<Portfolio>("/positions/portfolio"),
  signals:        (limit = 50) => apiFetch<Signal[]>(`/signals?limit=${limit}`),
  liveSignals:    () => apiFetch<Signal[]>("/signals/live"),
  graphNodes:     (nodeType?: string, limit = 300) =>
    apiFetch<GraphNode[]>(`/graph/nodes?${nodeType ? `node_type=${nodeType}&` : ""}limit=${limit}`),
  graphEdges:     (limit = 800) => apiFetch<GraphEdge[]>(`/graph/edges?limit=${limit}`),
  contradictions: () => apiFetch<Contradiction[]>("/graph/contradictions"),
  suppressContradiction: (a: string, b: string) =>
    apiFetch<unknown>(`/graph/contradictions/suppress?strategy_a=${encodeURIComponent(a)}&strategy_b=${encodeURIComponent(b)}`, { method: "POST" }),
  unsuppressContradiction: (a: string, b: string) =>
    apiFetch<unknown>(`/graph/contradictions/suppress?strategy_a=${encodeURIComponent(a)}&strategy_b=${encodeURIComponent(b)}`, { method: "DELETE" }),
  signalLineage:  (strategy: string) =>
    apiFetch<SignalLineage>(`/graph/signal-lineage?strategy=${encodeURIComponent(strategy)}`),
  eligibleStrategies: (regime: string) =>
    apiFetch<EligibleStrategy[]>(`/graph/eligible-strategies?regime=${encodeURIComponent(regime)}`),
  regimeGraph:    (regime: string) =>
    apiFetch<Record<string, unknown>[]>(`/graph/regime?regime=${regime}`),
  marketQuotes:   (tickers?: string) =>
    apiFetch<MarketQuote[]>(`/market/quotes${tickers ? `?tickers=${tickers}` : ""}`),
  backtestStatus: () => apiFetch<{
    status: string; progress: { pct: number; msg: string };
    result: BacktestResult | null;
    grounded: BacktestResult | null;
    ungrounded: BacktestResult | null;
  }>("/backtest/status"),
  runBacktest: (params: {
    start_date: string; end_date: string; initial_capital: number;
    use_graph: boolean; run_both: boolean;
    rebal_freq: number; fee_pct: number; slip_pct: number;
  }) => apiFetch<{ status: string }>("/backtest/run", { method: "POST", body: JSON.stringify(params) }),
  backtestSuggestions: () => apiFetch<TradeSuggestion[]>("/backtest/suggestions"),
  actionSuggestion: (suggestion_id: string, action: string, notes = "") =>
    apiFetch<{ ok: boolean }>("/backtest/suggestions/action", {
      method: "POST", body: JSON.stringify({ suggestion_id, action, notes }),
    }),
  newsLatest:  () => apiFetch<NewsResult>("/intelligence/news"),
  macroLatest: () => apiFetch<MacroResult>("/intelligence/macro"),
};
