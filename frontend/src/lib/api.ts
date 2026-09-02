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
  slippage?:    number;
  hold_days:    number;
  regime:       string;
  asset_class?: string;
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
  sortino_ratio?: number;
  regime_performance?: {
    regime: string;
    return_pct: number;
    sharpe: number;
    trades: number;
    win_rate: number;
  }[];
  total_fees?: number;
  total_slippage?: number;
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

export const signalsApi = {
  placeOrder: (req: { ticker: string; direction: string; quantity: number; order_type?: string; limit_price?: number | null; venue?: string }) =>
    apiFetch<{ order_id: string; status: string; mode: string; venue: string; ticker: string; direction: string; quantity: number; fill_price: number; fee_usd: number; created_at: string }>("/signals/place", { method: "POST", body: JSON.stringify(req) }),
  exportSignals: (format = "json", startDate?: string, endDate?: string) => {
    const p = new URLSearchParams();
    p.set("format", format);
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    return apiFetch<SignalExport[]>(`/signals/export?${p.toString()}`);
  },
  venuesStatus: () => apiFetch<{ venues: { name: string; type: string; status: string; mode: string; last_heartbeat: string | null }[] }>("/venues/status"),
};

// ── Alpaca paper-trading API (Phase 3: wire Alpaca into the UI) ─────────────────

export interface AlpacaAccount {
  status:         string;
  cash:           number;
  equity:         number;
  buying_power:   number;
}

export interface AlpacaPosition {
  symbol:           string;
  qty:              number;
  avg_entry_price:  number;
  current_price:    number;
  market_value:     number;
  side:              "buy" | "sell";
}

export const alpacaApi = {
  account:      () => apiFetch<AlpacaAccount>("/alpaca/account"),
  positions:    () => apiFetch<AlpacaPosition[]>("/alpaca/positions"),
  bars:        (symbol: string) => apiFetch<{ t: string; o: number; h: number; l: number; c: number; v: number }[]>(`/alpaca/bars/${encodeURIComponent(symbol)}`),
};

// ── Options trading (Alpaca) ──────────────────────────────────────────────────

export interface OptionGreeks {
  delta: number | null; gamma: number | null; theta: number | null;
  vega: number | null; rho: number | null;
}

export interface OptionContractRow {
  symbol:             string;
  underlying_symbol:  string;
  root_symbol:        string;
  expiration_date:    string;
  contract_type:      "call" | "put";
  strike_price:       number;
  multiplier:         number;
  style:              string;
  tradable:           boolean;
  bid?:                number | null;
  ask?:                number | null;
  last?:               number | null;
  volume?:             number | null;
  open_interest?:      number | null;
  implied_volatility?: number | null;
  greeks?:             OptionGreeks | null;
  spread_pct?:         number | null;
}

export interface AlpacaAsset {
  symbol: string; name: string | null; asset_class: string | null; tradable: boolean;
}

export interface OptionPlaceRequest {
  contract_symbol: string;
  qty: number;
  side: "buy" | "sell";
  position_intent: "buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close";
  order_type?: "market" | "limit";
  limit_price?: number | null;
  label?: string;
}

export interface OptionPlaceResult {
  order_id: string; alpaca_order_id: string; contract_symbol: string;
  underlying_symbol: string; expiration_date: string; contract_type: string;
  strike_price: number; side: string; position_intent: string;
  quantity: number; status: string; filled_avg_price: number | null;
  mode: string; created_at: string;
}

export interface OptionLeg {
  symbol:           string;
  strike:           number;
  contract_type:    "call" | "put";
  side:             "buy_to_open" | "sell_to_open" | "buy_to_close" | "sell_to_close";
  contracts:        number;
  mid:              number;
  delta?:           number | null;
  bid?:             number | null;
  ask?:             number | null;
  spread_pct?:      number | null;
  open_interest?:   number | null;
  implied_volatility?: number | null;
  premium_total?:   number;
  collateral_required?: number;
  net_credit?:      number;
  net_debit?:       number;
  max_profit?:      number;
  max_loss?:        number;
}

export interface OptionSuggestion {
  strategy:        string;
  signal_method:   string;
  regime:          string;
  regime_weight:   number;
  confidence:      number;
  graph_path:      string[];
  legs:            OptionLeg[];
  est_premium:     number;
  max_profit_low:  number;
  max_loss:        number;
  max_loss_pct_nav: number | null;
  risk_reward_pct: number | null;
  score:           number;
  loss_aversion_score?: number;
  rank?:           number;
  lens?:           string;
  hedge?:          { hedge_req: boolean; hedge_reason: string };
  notes:           string[];
  budget_pct:      number;
  liquidity_ok:    boolean;
}

export interface OptionSuggestionRejected {
  strategy: string; signal_method: string; max_loss: number;
  max_loss_pct_nav: number; reason: string;
}

export interface OptionSuggestionsResult {
  underlying:        string;
  expiration:        string | null;
  regime:            string;
  regime_confidence: number;
  spot_estimate:     number | null;
  dte:               number;
  chain_size:        number;
  lens:              string;
  nav:               number;
  max_loss_cap_pct:  number;
  active_strategies: string[];
  suggestions:       OptionSuggestion[];
  rejected:          OptionSuggestionRejected[];
}

export interface OptionPnl {
  underlying:         string;
  option_positions:   number;
  equity_positions:   number;
  contracts:          number;
  underlyings:        string[];
  premium_income_usd: number;
  premium_cost_usd:   number;
  net_premium_usd:    number;
  unrealized_pnl_usd: number;
  hedge_sleeve_mv_usd: number;
  net_option_pnl_usd: number;
}

// ── Financial Engineer Chat API ───────────────────────────────────────────────

export interface ChatSource {
  book?: string;
  chapter?: string;
  section?: string;
  concept?: string;
  formula?: string;
  strategy?: string;
}

export interface ChatMessage {
  role: string;
  content: string;
  sources?: ChatSource[];
  suggestions?: string[];
}

export interface ChatAnswer {
  answer: string;
  sources: ChatSource[];
  suggestions: string[];
}

export interface ChatContext {
  screen: string;
  hint: string;
  live: Record<string, unknown>;
  retrieval: {
    concepts: { name: string }[];
    sections: { book: string; chapter: string; title: string; body: string }[];
    formulas: { id: string; expression: string }[];
    strategies: { name: string; signal_method: string }[];
    sources: ChatSource[];
  };
  generated_at: string;
}

export const chatApi = {
  context: (screen: string) => apiFetch<ChatContext>(`/chat/context/${screen}`),
  ask: (screen: string, question: string, history: { role: string; content: string }[]) =>
    apiFetch<ChatAnswer>("/chat/ask", {
      method: "POST",
      body: JSON.stringify({ screen, question, history }),
    }),
  history: (screen: string) => apiFetch<ChatMessage[]>(`/chat/history/${screen}`),
  clearHistory: (screen: string) =>
    apiFetch<{ deleted: boolean }>(`/chat/history/${screen}`, { method: "DELETE" }),
};

export interface HedgeState {
  underlying:       string;
  regime:           string;
  confidence:       number;
  greeks:           { delta: number; gamma: number; theta: number; vega: number };
  positions:        { symbol: string; cls: string; qty: number; delta: number; gamma: number; theta: number; vega: number; iv?: number }[];
  spot:             number | null;
  hedge_shares:     number;
  band_shares:      number;
  needs_rebalance:  boolean;
  reason:           string;
  proposal:         { symbol: string; side: string; qty: number } | null;
  tail_sleeve:      { recommended: boolean; reason?: string; budget_usd?: number; suggest?: string; note?: string };
}

export const optionsApi = {
  underlyings: (q = "") => apiFetch<{ assets: AlpacaAsset[] }>(`/options/underlyings?q=${encodeURIComponent(q)}`),
  expirations: (underlying: string) => apiFetch<{ underlying: string; expirations: string[] }>(`/options/expirations?underlying=${encodeURIComponent(underlying)}`),
  strikes:     (underlying: string, expiration?: string, contract_type?: string) => {
    const p = new URLSearchParams({ underlying: underlying.toUpperCase() });
    if (expiration) p.set("expiration", expiration);
    if (contract_type) p.set("contract_type", contract_type);
    return apiFetch<{ underlying: string; strikes: number[] }>(`/options/strikes?${p.toString()}`);
  },
  chain:       (underlying: string, opts?: { expiration?: string; contract_type?: string; strike_gte?: number; strike_lte?: number }) => {
    const p = new URLSearchParams({ underlying: underlying.toUpperCase() });
    if (opts?.expiration) p.set("expiration", opts.expiration);
    if (opts?.contract_type) p.set("contract_type", opts.contract_type);
    if (opts?.strike_gte != null) p.set("strike_gte", String(opts.strike_gte));
    if (opts?.strike_lte != null) p.set("strike_lte", String(opts.strike_lte));
    return apiFetch<{ underlying: string; rows: OptionContractRow[] }>(`/options/chain?${p.toString()}`);
  },
  snapshot:    (contract: string) => apiFetch<OptionContractRow>(`/options/snapshot?contract=${encodeURIComponent(contract)}`),
  suggestions: (underlying: string, opts?: { expiration?: string; contract_type?: string; regime?: string; lens?: string; nav?: number }) => {
    const p = new URLSearchParams({ underlying: underlying.toUpperCase() });
    if (opts?.expiration) p.set("expiration", opts.expiration);
    if (opts?.contract_type) p.set("contract_type", opts.contract_type);
    if (opts?.regime) p.set("regime", opts.regime);
    if (opts?.lens) p.set("lens", opts.lens);
    if (opts?.nav != null) p.set("nav", String(opts.nav));
    return apiFetch<OptionSuggestionsResult>(`/options/suggestions?${p.toString()}`);
  },
  place:       (req: OptionPlaceRequest) =>
    apiFetch<OptionPlaceResult>("/options/place", { method: "POST", body: JSON.stringify(req) }),
  hedge:       {
    state:     (underlying = "SPY") =>
      apiFetch<{ hedge_state: HedgeState }>(`/options/hedge/state?underlying=${encodeURIComponent(underlying)}`),
    rebalance: (underlying = "SPY", confirm = false) =>
      apiFetch<{ status: string; message?: string; order?: Record<string, unknown>; hedge_state: HedgeState }>(
        `/options/hedge/rebalance?underlying=${encodeURIComponent(underlying)}&confirm=${confirm}`,
        { method: "POST" }),
  },
  pnl:         (underlying = "SPY") =>
    apiFetch<{ option_pnl: OptionPnl }>(`/options/pnl?underlying=${encodeURIComponent(underlying)}`),
};

export const marketApi = {
  downloadData: (req: { tickers: string[]; start: string; end: string; interval?: string; fred_series?: string[]; combine?: boolean }) =>
    apiFetch<{ prices?: Record<string, unknown>[]; prices_by_ticker?: Record<string, unknown[]>; fred?: Record<string, unknown>; tickers: string[]; rows: number; start: string; end: string; interval: string }>("/market/data", { method: "POST", body: JSON.stringify(req) }),
  listFredSeries: () => apiFetch<{ series: { id: string; name: string }[] }>("/market/fred-series"),
};

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
    tickers?: string; trade_threshold?: number;
    benchmark?: string; rf_rate?: number; // NEW
  }) => apiFetch<{ status: string; run_id?: string }>("/backtest/run", { method: "POST", body: JSON.stringify(params) }),
  cancelBacktest: () => apiFetch<{ ok: boolean }>("/backtest/cancel", { method: "POST" }),

  backtestSuggestions: () => apiFetch<TradeSuggestion[]>("/backtest/suggestions"),
  actionSuggestion: (suggestion_id: string, action: string, notes = "") =>
    apiFetch<{ ok: boolean }>("/backtest/suggestions/action", {
      method: "POST", body: JSON.stringify({ suggestion_id, action, notes }),
    }),
  newsLatest:  () => apiFetch<NewsResult>("/intelligence/news"),
  macroLatest: () => apiFetch<MacroResult>("/intelligence/macro"),
};

// ── Research API types ─────────────────────────────────────────────────────────

export interface GraphSummary {
  total_nodes: number;
  total_edges: number;
  by_label: Record<string, number>;
  orphaned_nodes: number;
  strategies_without_concepts: number;
  formula_coverage_pct: number;
  last_kg_update: string | null;
}

export interface GraphImportance {
  name: string;
  centrality: number;
}

export interface StrategyCatalog {
  name: string;
  status: string;
  asset_class: string;
  venue: string;
  description: string;
  regimes: string[];
  concepts: string[];
  formulas: string[];
  backtest_sharpe: number | null;
  backtest_return: number | null;
  backtest_trades: number;
  live_signals_7d: number;
}

export interface FormulaCatalog {
  id: string;
  name: string;
  expression: string;
  output: string;
  description: string;
  concepts: string[];
  strategies: string[];
  live_usage_30d: number;
}

export interface GraphGaps {
  orphaned_nodes: { labels: string[]; name: string; cnt: number }[];
  uncovered_strategies: { name: string; asset_class: string }[];
  sparse_regimes: { regime: string; strategy_count: number }[];
}

export interface AgentPerformance {
  summary: {
    total_cycles: number;
    avg_duration_s: number;
    avg_regime_confidence: number;
    cycles_with_signals: number;
    cycles_with_rejections: number;
  };
  agent_breakdown: {
    agent_name: string;
    appearances: number;
    successes: number;
  }[];
}

export interface SignalAttribution {
  order_id: string;
  strategy: string;
  ticker: string;
  direction: string;
  quantity: number;
  fill_price: number;
  signal_score: number;
  kelly_fraction: number;
  var_contribution: number;
  rejection_reason: string | null;
  quant_score?: number;
  sentiment_score?: number;
  news_overlay?: number;
  macro_overlay?: number;
  kg_formula_contribution?: number;
  contradiction_blocked?: boolean;
  kg_graph_path?: string[];
  slippage_bps?: number;
  created_at: string;
}

export interface RejectedSignals {
  total: number;
  by_reason: Record<string, { count: number; signals: unknown[] }>;
}

export interface AgentAudit {
  id: number;
  cycle_id: string;
  timestamp: string;
  duration_s: number;
  regime: string;
  regime_confidence: number;
  sub_agents: unknown[];
  signals: unknown[];
  rejections: unknown[];
}

export interface GraphEdgeDrift {
  id: number;
  source: string;
  target: string;
  rel_type: string;
  weight: number | null;
  agent_run: string;
  recorded_at: string;
}

export interface ExecutionFill {
  order_id: string;
  strategy: string;
  ticker: string;
  direction: string;
  quantity: number;
  fill_price: number;
  fee_usd: number;
  mode: string;
  signal_score: number;
  kelly_fraction: number;
  var_contribution: number;
  raw_response: unknown;
  created_at: string;
}

export interface OrderLifecycle {
  order_id: string;
  strategy: string;
  ticker: string;
  direction: string;
  quantity: number;
  fill_price: number;
  fee_usd: number;
  mode: string;
  signal_score: number;
  kelly_fraction: number;
  var_contribution: number;
  rejection_reason: string | null;
  signal_timestamp?: string;
  contradiction_blocked?: boolean;
  fill_timestamp?: string;
  created_at: string;
}

export interface GraphSimulateResult {
  scenario: string;
  params: Record<string, unknown>;
  affected_strategies: string[];
  predicted_new_activations: number;
  predicted_signal_changes: { strategy: string; current_score: number; projected_score: number; change_pct: string }[];
  contradiction_risk: { new_contradictions: number; severity: string };
}

export interface StrategyForecast {
  strategy: string;
  horizon_days: number;
  historical_scores: number;
  avg_historical_score: number | null;
  signal_decay_curve: { day: number; projected_score: number }[];
  regime_transition_probs: Record<string, number>;
}

export interface StressTestResult {
  nav_impact_pct: number;
  drawdown_impact_pct: number;
  positions_breaching_cap: string[];
  halt_triggered: boolean;
}

export interface GraphRecommendation {
  type: string;
  priority: string;
  reason: string;
  suggestion: string;
}

export interface PortfolioRebalance {
  current: Record<string, number>;
  optimal: Record<string, number>;
  trades_suggested: { ticker: string; action: string; target_weight: number; notional_usd: number }[];
}

export interface GraphEditResult {
  operation: string;
  validation_passed: boolean;
  affected_strategies: string[];
}

export interface GraphQueryResult {
  results: Record<string, unknown>[];
  execution_time_ms: number;
  result_count: number;
}

export interface SignalExport {
  signal_id: string;
  cycle_id: string;
  timestamp: string;
  strategy: string;
  ticker: string;
  venue: string;
  direction: string;
  score: number;
  quant_score: number;
  sentiment_score: number;
  news_overlay: number;
  macro_overlay: number;
  kg_formula_contribution: number;
  contradiction_blocked: boolean;
  kelly_fraction: number;
  var_contribution_pct: number;
  fill_price: number;
  fill_timestamp: string;
  slippage_bps: number;
}

export interface ParityStatus {
  total_cycles: number;
  discrepancies: number;
  last_discrepancy: string | null;
  tolerance: number;
  cpp_version: string;
  python_version: string;
  status: string;
  latest_discrepancies: unknown[];
}

export interface RegimeForecast {
  regimes: string[];
  transition_matrix: Record<string, Record<string, number>>;
  observation_period_days: number;
}

export interface BacktestOptimizeResult {
  strategy: string;
  regime: string | null;
  heatmap: Record<string, unknown>[];
  optimal: Record<string, unknown>;
}

export interface BacktestCompareResult {
  primary: Record<string, unknown>;
  comparison: Record<string, unknown> | null;
  delta?: { sharpe_delta: number; return_delta: number; drawdown_delta: number };
}

export interface ABTestResult {
  config_a: Record<string, unknown>;
  config_b: Record<string, unknown>;
  n_signals: number;
  signals: unknown[];
  note: string;
}

export interface AgentClusters {
  total_cycles: number;
  outlier_count: number;
  outliers: unknown[];
  avg_duration_s: number;
  std_duration_s: number;
}

export interface VenueStatus {
  venues: { name: string; type: string; status: string; mode: string; last_heartbeat: string | null }[];
}

// ── Research API calls ─────────────────────────────────────────────────────────

export const researchApi = {
  // Descriptive
  graphSummary:        () => apiFetch<GraphSummary>("/graph/summary"),
  graphImportance:     (algorithm = "pagerank", limit = 20) =>
    apiFetch<GraphImportance[]>(`/graph/importance?algorithm=${algorithm}&limit=${limit}`),
  strategies:          (assetClass?: string, status?: string) => {
    const params = new URLSearchParams();
    if (assetClass) params.set("asset_class", assetClass);
    if (status) params.set("status", status);
    return apiFetch<StrategyCatalog[]>(`/strategies?${params.toString()}`);
  },
  formulas:            (limit = 100) => apiFetch<FormulaCatalog[]>(`/formulas?limit=${limit}`),
  graphGaps:           () => apiFetch<GraphGaps>("/graph/gaps"),
  graphVersions:       (limit = 20) => apiFetch<unknown[]>(`/graph/versions?limit=${limit}`),
  agentPerformance:    (days = 30) => apiFetch<AgentPerformance>(`/agent/performance?days=${days}`),

  // Diagnostic
  signalAttribution:   (signalId: string) => apiFetch<SignalAttribution>(`/signals/${encodeURIComponent(signalId)}/attribution`),
  rejectedSignals:     (reason?: string, limit = 50) => {
    const params = new URLSearchParams();
    if (reason) params.set("reason", reason);
    params.set("limit", String(limit));
    return apiFetch<RejectedSignals>(`/signals/rejected?${params.toString()}`);
  },
  activationHistory:   (strategy: string) =>
    apiFetch<unknown[]>(`/strategies/${encodeURIComponent(strategy)}/activation-history`),
  edgeDrift:           (source: string, target: string, relType = "TRANSMITS_TO") =>
    apiFetch<GraphEdgeDrift[]>(`/graph/edge-drift?source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}&rel_type=${encodeURIComponent(relType)}`),
  agentAudit:          (limit = 20) => apiFetch<AgentAudit[]>(`/agent/audit?limit=${limit}`),
  contradictionsHistory: () => apiFetch<{ currently_suppressed: string[]; edit_history: unknown[] }>("/graph/contradictions/history"),
  executionFills:      (orderId?: string) => {
    const params = new URLSearchParams();
    if (orderId) params.set("order_id", orderId);
    return apiFetch<ExecutionFill[]>(`/execution/fills?${params.toString()}`);
  },
  orderLifecycle:      (orderId: string) => apiFetch<OrderLifecycle>(`/orders/${encodeURIComponent(orderId)}/lifecycle`),

  // Predictive
  graphSimulate:       (scenario: string, params: Record<string, unknown>) =>
    apiFetch<GraphSimulateResult>("/graph/simulate", { method: "POST", body: JSON.stringify({ scenario, params }) }),
  strategyForecast:    (name: string, horizonDays = 30) =>
    apiFetch<StrategyForecast>(`/strategies/${encodeURIComponent(name)}/forecast?horizon_days=${horizonDays}`),
  signalDecay:         (strategy?: string) => {
    const params = new URLSearchParams();
    if (strategy) params.set("strategy", strategy);
    return apiFetch<unknown[]>(`/signals/decay?${params.toString()}`);
  },
  contradictionRisk:   () => apiFetch<{ active_contradictions: unknown[]; regime_transition_probs: Record<string, number>; risk_level: string }>("/graph/contradiction-risk"),
  regimeForecast:      (days = 90) => apiFetch<RegimeForecast>(`/agent/regime-forecast?days=${days}`),
  graphSensitivity:    (source: string, target: string, relType: string, weightDelta = 0.1) =>
    apiFetch<unknown>("/graph/sensitivity", { method: "POST", body: JSON.stringify({ source, target, rel_type: relType, weight_delta: weightDelta }) }),
  stressTest:          (scenarios: { ticker: string; shock_pct: number }[]) =>
    apiFetch<StressTestResult>("/risk/stress-test", { method: "POST", body: JSON.stringify({ scenarios }) }),

  // Prescriptive
  graphRecommendations: () => apiFetch<GraphRecommendation[]>("/graph/recommendations"),
  coverageGaps:        () => apiFetch<{ regime_gaps: unknown[]; asset_class_gaps: unknown[] }>("/graph/coverage-gaps"),
  strategyOptimize:    (name: string, params: Record<string, unknown>) =>
    apiFetch<unknown>(`/strategies/${encodeURIComponent(name)}/optimize`, { method: "POST", body: JSON.stringify({ params }) }),
  portfolioRebalance:  () => apiFetch<PortfolioRebalance>("/portfolio/rebalance"),
  venuesOptimize:      () => apiFetch<{ venue_stats: unknown[]; recommendation: string }>("/venues/optimize"),
  graphEdit:           (operation: string, source?: string, target?: string, relType?: string, properties?: Record<string, unknown>) =>
    apiFetch<GraphEditResult>("/graph/edit", { method: "POST", body: JSON.stringify({ operation, source, target, rel_type: relType, properties: properties ?? {} }) }),
  alertsSuggest:       (behaviorPattern: string, metric: string, threshold: number) =>
    apiFetch<unknown>("/alerts/suggest", { method: "POST", body: JSON.stringify({ behavior_pattern: behaviorPattern, metric, threshold }) }),

  // Analytical
  graphQuery:          (query: string, params?: Record<string, unknown>) =>
    apiFetch<GraphQueryResult>("/graph/query", { method: "POST", body: JSON.stringify({ query, params: params ?? {} }) }),
  signalsExport:       (format = "json", startDate?: string, endDate?: string) => {
    const p = new URLSearchParams();
    p.set("format", format);
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    return apiFetch<SignalExport[]>(`/signals/export?${p.toString()}`);
  },
  causalChain:         (nodeName: string, nodeLabel = "Concept", direction = "both", maxDepth = 5) =>
    apiFetch<{ node: { name: string; label: string }; upstream_paths: unknown[]; downstream_paths: unknown[] }>(
      "/graph/causal-chain", { method: "POST", body: JSON.stringify({ node_name: nodeName, node_label: nodeLabel, direction, max_depth: maxDepth }) }
    ),
  graphCentrality:     (algorithm = "pagerank", limit = 20) =>
    apiFetch<GraphImportance[]>(`/graph/centrality?algorithm=${algorithm}&limit=${limit}`),
  graphTrends:         (days = 30) =>
    apiFetch<{ signal_trend: unknown[]; strategy_trend: unknown[] }>(`/graph/trends?days=${days}`),
  correlate:           (artifactTypes: string[], startDate: string, endDate: string) =>
    apiFetch<Record<string, unknown>>("/analysis/correlate", { method: "POST", body: JSON.stringify({ artifact_types: artifactTypes, start_date: startDate, end_date: endDate }) }),
  abTest:              (configA: Record<string, unknown>, configB: Record<string, unknown>, signalIds: string[]) =>
    apiFetch<ABTestResult>("/analysis/ab-test", { method: "POST", body: JSON.stringify({ config_a: configA, config_b: configB, signal_ids: signalIds }) }),
  agentClusters:       (days = 90) => apiFetch<AgentClusters>(`/agent/clusters?days=${days}`),

  // Deployment / Integration
  backtestOptimize:    (strategy: string, params: Record<string, unknown[]>, regime?: string) =>
    apiFetch<BacktestOptimizeResult>("/backtest/optimize", { method: "POST", body: JSON.stringify({ strategy, params, regime }) }),
  backtestCompare:     (runId: string) => apiFetch<BacktestCompareResult>(`/backtest/${runId}/compare`),
  backtestTrades:      (runId: string, limit = 500) =>
    apiFetch<unknown[]>(`/backtest/${runId}/trades?limit=${limit}`),
  backtestAttribution: (runId: string) => apiFetch<{ run_id: string; by_strategy: unknown[]; by_ticker: unknown[] }>(`/backtest/${runId}/attribution`),
  backtestAblation:    (runId: string) => apiFetch<{ primary: Record<string, unknown>; ablation_matrix: unknown[]; configs_compared: number }>(`/backtest/${runId}/ablation`),
  backtestByRegime:    (runId: string) => apiFetch<{ run_id: string; regime_breakdown: unknown[] }>(`/backtest/${runId}/by-regime`),
  backtestSaveTemplate:(name: string, params: Record<string, unknown>) =>
    apiFetch<{ id: number; name: string; status: string }>("/backtest/templates", { method: "POST", body: JSON.stringify({ name, params }) }),
  parityStatus:        () => apiFetch<ParityStatus>("/parity/status"),
  reconciliationStatus:() => apiFetch<{ venues: string[]; positions_by_venue: Record<string, unknown[]>; total_open_positions: number; status: string }>("/reconciliation/status"),
  venuesStatus:        () => apiFetch<VenueStatus>("/venues/status"),
};

// ── Analytics API types ────────────────────────────────────────────────────────

export interface AnalyticsSeries {
  id: string;
  name: string;
  ticker: string;
  metric: string;
  source: string;
  granularities: string[];
  default_granularity: string;
  type: string;
  description: string;
}

export interface AnalyticsDataPoint {
  timestamp: string;
  value: number | string | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  confidence?: number | null;
}

export interface AnalyticsDataResponse {
  series_id: string;
  data: AnalyticsDataPoint[];
  count: number;
  missing_gaps: { from: string; to: string; gap_days: number }[];
  metadata?: Record<string, unknown>;
}

export interface DescriptiveStats {
  series_id: string;
  n: number;
  basic: {
    mean: number;
    median: number;
    std: number;
    variance: number;
    skewness: number;
    excess_kurtosis: number;
    min: number;
    max: number;
    range: number;
    iqr: number;
    q1: number;
    q3: number;
  };
  percentiles: Record<string, number>;
  annualized: { ann_mean: number | null; ann_std: number | null };
  normality_tests: {
    jarque_bera: { statistic: number; p_value: number; interpretation: string };
    shapiro_wilk?: { statistic: number; p_value: number };
    anderson_darling: { statistic: number };
  };
  stationarity_tests: {
    adf?: { statistic: number; p_value: number; critical_values: unknown; interpretation: string };
    kpss?: { statistic: number; p_value: number; interpretation: string };
  };
  rolling: { window: number; series: { timestamp: string; mean: number; std: number; skew: number; kurt: number }[] };
  histogram: { bins: number[]; counts: number[]; bin_width: number };
}

export interface AutocorrelationResult {
  series_id: string;
  n: number;
  max_lag: number;
  acf: { lag: number; acf: number; ci_lower: number; ci_upper: number }[];
  pacf: { lag: number; pacf: number; ci_lower: number; ci_upper: number }[];
  ljung_box: { statistic: number; p_value: number; interpretation: string } | null;
  confidence_band_95: number;
}

export interface VolatilityAnalysis {
  series_id: string;
  n_returns: number;
  rolling_volatility: Record<string, { value: number }[]>;
  garch: {
    parameters: { omega: number; alpha: number; beta: number };
    persistence: number;
    half_life_days: number | null;
    log_likelihood: number;
    aic: number;
    bic: number;
    conditional_volatility: number[];
    interpretation: string;
  } | null;
  arch_lm: { statistic: number; p_value: number; interpretation: string } | null;
  volatility_term_structure: Record<string, number>;
  current_realized_vol_21d: number | null;
}

export interface SignalICResult {
  strategy: string;
  ticker: string | null;
  forward_horizon_days: number;
  n_observations: number;
  n_days: number;
  summary: {
    ic_mean: number;
    ic_std: number;
    information_ratio: number;
    t_statistic: number;
    interpretation: string;
  };
  ic_timeseries: { timestamp: string; ic: number }[];
}

export interface FactorExposure {
  market_model: {
    alpha: number;
    beta: number;
    alpha_tstat: number;
    beta_tstat: number;
    r_squared: number;
    adj_r_squared: number;
    f_statistic: number;
    f_p_value: number;
  };
  interpretation: string;
}

export interface PortfolioOptimizationResult {
  method: string;
  tickers: string[];
  optimal_weights: Record<string, number>;
  optimal_portfolio: { expected_return: number; expected_volatility: number; sharpe_ratio: number };
  equal_weight_portfolio: { expected_return: number; expected_volatility: number; sharpe_ratio: number };
  min_variance_portfolio?: { weights: Record<string, number>; expected_return: number; expected_volatility: number };
  efficient_frontier?: { return: number; volatility: number }[];
  covariance_matrix: Record<string, Record<string, number>>;
  correlation_matrix: Record<string, Record<string, number>>;
}

export interface AIInterpretation {
  panel: string;
  model: string;
  provider: string;
  interpretation: string;
  status: string;
}

export interface AnomalyResult {
  series_id: string;
  method: string;
  n_observations: number;
  n_anomalies: number;
  anomaly_rate: number;
  anomalies: { timestamp: string; value: number; anomaly_score?: number; method: string; cumulative_sum?: number }[];
}

export interface GrangerCausalityResult {
  tickers: string[];
  n_observations: number;
  max_lag_tested: number;
  results: {
    cause: string;
    effect: string;
    best_lag: number;
    f_statistic: number;
    p_value: number;
    significant: boolean;
    interpretation: string;
  }[];
  directionality: Record<string, { causes: string[]; caused_by: string[] }>;
  summary: { n_pairs_tested: number; n_significant: number; n_directional_assets: number };
}

export interface ForecastResult {
  ticker: string;
  model: string;
  horizon: number;
  conf_level: number;
  n_observations: number;
  order?: { p: number; d: number; q: number };
  seasonal?: string;
  tickers?: string[];
  best_lag?: number;
  coint_rank?: number;
  k_ar_diff?: number;
  forecasts?: Record<string, number[]>;
  impulse_responses?: Record<string, number[]>;
  fevd?: Record<string, Record<string, number>>;
  alpha?: number[][];
  beta?: number[][];
  aic: number;
  bic: number;
  forecast: number[];
  conf_int_lower: number[];
  conf_int_upper: number[];
  residuals: number[];
  residual_std: number;
  ljung_box_p?: number;
  rmse: number;
  mae: number;
  historical: number[] | Record<string, number[]>;
}

export interface GarchVariantResult {
  parameters: Record<string, { value: number; std_err: number | null; t_stat: number | null; p_value: number | null }>;
  aic: number;
  bic: number;
  log_likelihood: number;
  persistence: number;
  half_life_days: number | null;
  ljung_box_p: number;
  converged: boolean;
  error?: string;
}

export interface GarchResult {
  ticker: string;
  n_returns: number;
  p: number;
  q: number;
  models: Record<string, GarchVariantResult>;
  conditional_volatilities: Record<string, number[]>;
  news_impact_curves: Record<string, { shocks: number[]; conditional_variances: number[] }>;
  model_comparison: { variant: string; aic: number; bic: number; log_likelihood: number; persistence: number; half_life_days: number | null; converged: boolean }[];
  best_model: string | null;
}

export interface PCAResult {
  tickers: string[];
  n_observations: number;
  n_components: number;
  scree: { component: number; eigenvalue: number; explained_variance_pct: number; cumulative_pct: number }[];
  eigenvalues: number[];
  explained_variance_ratio: number[];
  cumulative_variance: number[];
  factor_loadings: Record<string, Record<string, number>>;
  risk_decomposition: Record<string, { n_components: number; variance_explained_pct: number }>;
  kaiser_significant_components: number;
  components_for_90pct_variance: number;
  pc1_interpretation: string;
  pc2_interpretation: string | null;
  pc1_loadings: Record<string, number>;
  projection: { pc1: number; pc2: number }[];
}

export interface CovHealthResult {
  tickers: string[];
  n_observations: number;
  n_assets: number;
  condition_number: number;
  is_ill_conditioned: boolean;
  shrinkage: { ledoit_wolf_alpha: number; oas_alpha: number; shrinkage_intensity_ratio: number };
  eigenvalue_spectrum: { values: number[]; fractions: number[]; distribution: { min: number; max: number; median: number; mean: number; std: number; condition_number: number; is_ill_conditioned: boolean } };
  correlation_matrices: { raw: number[][]; ledoit_wolf: number[][]; oas: number[][] };
  distance_matrix: number[][];
  minimum_spanning_tree: { edges: { from: string; to: string; correlation: number; distance: number }[]; total_distance: number; n_edges: number };
  all_pairs: { asset_i: string; asset_j: string; correlation: number; distance: number }[];
}

// ── Analytics API calls ────────────────────────────────────────────────────────

export const analyticsApi = {
  series:          () => apiFetch<AnalyticsSeries[]>("/analytics/series"),
  forecast:        (req: { ticker: string; model?: string; horizon?: number; conf_level?: number; max_p?: number; max_q?: number; max_d?: number; compare_tickers?: string[]; vecm_k_ar_diff?: number }) =>
    apiFetch<ForecastResult>("/analytics/forecast", { method: "POST", body: JSON.stringify(req) }),
  grangerCausality: (req: { ticker: string; compare_tickers?: string[] }) =>
    apiFetch<GrangerCausalityResult>("/analytics/granger-causality", { method: "POST", body: JSON.stringify({ ticker: req.ticker, compare_tickers: req.compare_tickers ?? ["SPY", "QQQ"] }) }),
  data:            (seriesId: string, startDate?: string, endDate?: string, granularity = "1d") => {
    const p = new URLSearchParams();
    p.set("series_id", seriesId);
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    p.set("granularity", granularity);
    return apiFetch<AnalyticsDataResponse>(`/analytics/data?${p.toString()}`);
  },
  descriptive:     (seriesId: string, startDate?: string, endDate?: string, rollingWindow = 21) => {
    const p = new URLSearchParams();
    p.set("series_id", seriesId);
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    p.set("rolling_window", String(rollingWindow));
    return apiFetch<DescriptiveStats>(`/analytics/descriptive?${p.toString()}`);
  },
  autocorrelation: (seriesId: string, startDate?: string, endDate?: string, maxLag = 50) => {
    const p = new URLSearchParams();
    p.set("series_id", seriesId);
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    p.set("max_lag", String(maxLag));
    return apiFetch<AutocorrelationResult>(`/analytics/autocorrelation?${p.toString()}`);
  },
  volatility:      (seriesId: string, startDate?: string, endDate?: string) => {
    const p = new URLSearchParams();
    p.set("series_id", seriesId);
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    return apiFetch<VolatilityAnalysis>(`/analytics/volatility?${p.toString()}`);
  },
  signalIC:        (strategy: string, ticker?: string, startDate?: string, endDate?: string, forwardHorizon = 5) => {
    const p = new URLSearchParams();
    p.set("strategy", strategy);
    if (ticker) p.set("ticker", ticker);
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    p.set("forward_horizon", String(forwardHorizon));
    return apiFetch<SignalICResult>(`/analytics/signals/ic?${p.toString()}`);
  },
  factors:         (seriesId: string, startDate?: string, endDate?: string) => {
    const p = new URLSearchParams();
    p.set("series_id", seriesId);
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    return apiFetch<FactorExposure>(`/analytics/factors?${p.toString()}`);
  },
  optimize:        (req: { tickers: string[]; method?: string; constraint_long_only?: boolean; max_weight?: number; risk_free_rate?: number }) =>
    apiFetch<PortfolioOptimizationResult>("/analytics/optimize", { method: "POST", body: JSON.stringify(req) }),
  interpret:       (panel: string, computedData: Record<string, unknown>, context?: Record<string, unknown>) =>
    apiFetch<AIInterpretation>("/analytics/interpret", { method: "POST", body: JSON.stringify({ panel, computed_data: computedData, context: context ?? {} }) }),
  garch:           (req: { ticker: string; variants?: string[]; p?: number; q?: number; power?: number; horizon?: number }) =>
    apiFetch<GarchResult>("/analytics/garch", { method: "POST", body: JSON.stringify(req) }),
  pca:             (req: { tickers: string[]; n_components?: number }) =>
    apiFetch<PCAResult>("/analytics/pca", { method: "POST", body: JSON.stringify(req) }),
  covarianceHealth:(req: { tickers: string[] }) =>
    apiFetch<CovHealthResult>("/analytics/covariance-health", { method: "POST", body: JSON.stringify(req) }),
  anomalies:       (seriesId: string, startDate?: string, endDate?: string, method = "isolation_forest") => {
    const p = new URLSearchParams();
    p.set("series_id", seriesId);
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    p.set("method", method);
    return apiFetch<AnomalyResult>(`/analytics/anomalies?${p.toString()}`);
  },
};

// ── Hypothesis Board Types ──────────────────────────────────────────────────────

export interface Hypothesis {
  hypothesis_id:       string;
  title:               string;
  description?:        string;
  primary_series:      string;
  benchmark_series?:   string;
  regime_filter?:      string;
  test_window_start?:  string;
  test_window_end?:    string;
  status:              string;  // IDEA | TESTING | VALIDATED | REJECTED | DEPLOYED | MONITORING
  status_path:         string[];
  evidence?:           any;
  ic_comparison?:      any;
  jobson_korkie?:      any;
  regime_conditional?: any;
  ai_synthesis?:       string;
  backtest_run_id?:    string;
  paper_signal_weights?: any;
  created_at:          string;
  updated_at:          string;
  evidence_list?:      HypothesisEvidence[];
  test_log?:           HypothesisTestLog[];
}

export interface HypothesisEvidence {
  evidence_type: string;  // 'chart' | 'test_result' | 'interpretation' | 'csv_export'
  tier:           string;  // 'descriptive' | 'diagnostic' | 'predictive' | 'prescriptive' | 'cognitive'
  series_id?:     string;
  label?:         string;
  data:           any;
  attached_at?:   string;
}

export interface HypothesisTestLog {
  test_type:        string;  // 'ic_t_test' | 'jobson_korkie' | 'granger_causality'
  raw_p_value:      number;
  bonferroni_p:     number;
  bh_corrected_p:   number;
  tests_in_family:  number;
  significant_raw:  boolean;
  significant_bonf: boolean;
  significant_bh:   boolean;
  test_detail?:     any;
  created_at?:      string;
}

export interface MultipleTestingContext {
  total_tests_logged:    number;
  active_hypotheses:     number;
  suggested_correction:  string;
}

// ── Hypothesis Board API ────────────────────────────────────────────────────────

export const hypothesisApi = {
  list:              (statusFilter?: string) => {
    const p = statusFilter ? `?status_filter=${statusFilter}` : "";
    return apiFetch<Hypothesis[]>(`/hypothesis${p}`);
  },
  get:               (id: string) => apiFetch<Hypothesis>(`/hypothesis/${id}`),
  create:            (body: { title: string; description?: string; primary_series: string; benchmark_series?: string; regime_filter?: string; test_window_start?: string; test_window_end?: string }) =>
    apiFetch<{ hypothesis_id: string; created_at: string }>("/hypothesis", { method: "POST", body: JSON.stringify(body) }),
  update:            (id: string, body: { title?: string; description?: string; status?: string; regime_filter?: string; test_window_start?: string; test_window_end?: string }) =>
    apiFetch<{ status: string; hypothesis_id: string }>(`/hypothesis/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  delete:            (id: string) => apiFetch<{ status: string; hypothesis_id: string }>(`/hypothesis/${id}`, { method: "DELETE" }),
  attachEvidence:    (id: string, body: { evidence_type: string; tier: string; series_id?: string; label?: string; data: any }) =>
    apiFetch<{ evidence_id: number }>(`/hypothesis/${id}/evidence`, { method: "POST", body: JSON.stringify(body) }),
  detachEvidence:    (id: string, evidenceId: number) =>
    apiFetch<{ status: string; evidence_id: number }>(`/hypothesis/${id}/evidence/${evidenceId}`, { method: "DELETE" }),
  logTest:           (id: string, body: { test_type: string; raw_p_value: number; tests_in_family?: number; test_detail?: any }) =>
    apiFetch<{ test_log_id: number; raw_p_value: number; bonferroni_p: number; bh_corrected_p: number; significant_raw: boolean; significant_bonf: boolean; significant_bh: boolean; tests_in_family: number }>(`/hypothesis/${id}/test-log`, { method: "POST", body: JSON.stringify(body) }),
  deployToBacktest:  (id: string) =>
    apiFetch<{ status: string; backtest_run_id: string; hypothesis_id: string }>(`/hypothesis/${id}/deploy-to-backtest`, { method: "POST" }),
  deployToPaper:     (id: string) =>
    apiFetch<{ status: string; hypothesis_id: string; channel: string }>(`/hypothesis/${id}/deploy-to-paper`, { method: "POST" }),
  multipleTestingContext: () =>
    apiFetch<MultipleTestingContext>("/hypothesis/multiple-testing-correction"),
};
