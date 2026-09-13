// CreditGraph API domain types (mirrors backend/app/models.py + endpoint contracts)

export type RiskRegime =
  | "trending"
  | "mean_reverting"
  | "high_volatility"
  | "low_volatility"
  | "crisis"
  | "systemic_stress"
  | "recovery"
  | "neutral";

export type DecisionStatus =
  | "recommended"
  | "approved"
  | "rejected"
  | "overridden"
  | "executed";

export type ExecutionStatus =
  | "pending"
  | "in_block"
  | "finalized"
  | "failed"
  | "timeout";

export interface AssessmentRequest {
  requested_amount: number;
  regime: RiskRegime;
  risk_free_rate?: number;
  confidence?: number;
}

export interface CreditAssessment {
  borrower_id: string;
  credit_score: number;
  probability_of_default: number;
  expected_loss: number;
  loan_to_value: number;
  required_collateral_ratio: number;
  stress_ltv: number;
  market_regime: RiskRegime;
  principal_risk_factors: string[];
  models: string[];
  created_at: string;
}

export interface CreditDecision {
  decision_id: string;
  borrower_id: string;
  requested_amount: number;
  recommended_amount: number;
  collateral_value: number;
  required_collateral_ratio: number;
  credit_score: number;
  probability_of_default: number;
  expected_loss: number;
  risk_regime: RiskRegime;
  stress_result: number;
  principal_risk_factors: string[];
  supporting_evidence: string[];
  attestation_references: string[];
  model_versions: string[];
  created_at: string;
  expires_at: string | null;
  decision_status: DecisionStatus;
  approval_status: string;
  execution_transaction: string | null;
}

export interface CreditExecution {
  execution_id: string;
  decision_id: string;
  borrower_id: string;
  to: string;
  amount: number;
  amount_planck: string | null;
  status: ExecutionStatus;
  tx_hash: string | null;
  block: string | null;
  block_hash: string | null;
  extrinsic_index: number | null;
  failure: string | null;
  source: string;
  created_at: string;
  confirmed_at: string | null;
}

export interface ExecuteCreditRequest {
  decision_id: string;
  to: string;
  amount?: number;
  amount_planck?: string;
}

export type AttestationStatus = "verified" | "unverified" | "invalid";

export interface Evidence {
  evidence_id: string;
  source_chain: string;
  tx_id: string;
  timestamp: string;
  attestation_id: string;
  status: AttestationStatus;
  verifier: string | null;
  verified_at: string | null;
  header_number: number | null;
  chain_key: number | null;
  proof: Record<string, unknown>;
  reason: string | null;
}

export interface GraphRagEntity {
  name: string;
  label?: string;
  type?: string;
  [k: string]: unknown;
}

export interface DecisionModelVersion {
  model_id: string;
  model_name: string | null;
  model_version: string | null;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  observed_at: string | null;
}

export interface DecisionGraphContext {
  market_regime: string | null;
  wallet_addresses: string[];
  override_reason: string | null;
  overridden_by: string | null;
  original_status: string | null;
}

export interface DecisionOverrideRequest {
  reason: string;
  overridden_by: string;
}

export interface DecisionReconstructResponse {
  decision_id: string;
  found: boolean;
  timestamp: string | null;
  decision: CreditDecision & {
    override_reason?: string | null;
    overridden_by?: string | null;
    original_decision_status?: string | null;
    overridden_at?: string | null;
  };
  input_entities: Record<string, unknown>;
  evidence_references: string[];
  attestation_references: string[];
  graph_context: DecisionGraphContext;
  model_versions: DecisionModelVersion[];
  model_parameters: Record<string, Record<string, unknown>>;
  risk_outputs: {
    credit_score: number;
    probability_of_default: number;
    expected_loss: number;
    stress_result: number;
    required_collateral_ratio: number;
    recommended_amount: number;
    model_outputs: Record<string, Record<string, unknown>>;
  };
}

export interface QuantitativeOutput {
  label: string;
  value: number | string;
  unit: string;
  source: string;
}

export interface GraphQueryResponse {
  query: string;
  intent: string;
  entities: GraphRagEntity[];
  evidence: Record<string, unknown>[];
  relationships: string[];
  paths: string[][];
  quantitative: QuantitativeOutput[];
  explanation: string;
  traversal_error: string | null;
}

export interface HealthResponse {
  status: string;
  service?: string;
}

export interface DbStatus {
  neo4j: "ok" | "down";
  redis: "ok" | "down";
}

export interface StressResult {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    stressed_exposure: number;
    stressed_loss: number;
  };
  timestamp: string;
}

export interface VaRResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    var: number;
    quantile: number;
  };
  timestamp: string;
}

export interface CVaRResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    cvar: number;
  };
  timestamp: string;
}

export interface ExpectedLossResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    expected_loss: number;
  };
  timestamp: string;
}

export interface ScenarioRunResponse {
  scenario: string;
  label: string;
  shock_pct: number;
  vix: number;
  stressed: StressResult;
}

export interface ScenarioGenerateResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    pnl: number[];
    count: number;
    min: number;
    max: number;
  };
  timestamp: string;
}

export interface ScenarioAnalyzeResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    var: {
      var: number;
      quantile: number;
    };
    cvar: {
      cvar: number;
    };
    stress: {
      stressed_exposure: number;
      stressed_loss: number;
    };
    expected_loss: {
      expected_loss: number;
    };
  };
  timestamp: string;
}

export interface ExecutionAccountResponse {
  configured: boolean;
  address?: string;
  ss58Format?: number;
  reason?: string;
}

export interface WalletResolveResponse {
  address: string;
  chain: string;
  supported: boolean;
  assets: Array<{
    asset_id: string;
    symbol: string;
    chain: string;
    price_usd: number;
    volatility_annualized: number;
    quantity: number;
  }>;
  transactions: Array<Record<string, unknown>>;
  discovered_at: string;
}

export interface BorrowerWalletsResponse {
  borrower_id: string;
  wallets: Array<WalletResolveResponse & { exposure: Record<string, unknown> }>;
  wallet_count: number;
}

export interface WalletExposureResponse {
  address: string;
  assets: Array<{
    asset_id: string;
    symbol: string;
    chain: string;
    price_usd: number;
    volatility_annualized: number;
    quantity: number;
  }>;
  liabilities: Array<{
    protocol: string;
    outstanding: number;
    asset_symbol: string;
  }>;
  exposures: Array<{
    protocol: string;
    asset: string;
    exposure_amount: number;
  }>;
  totals: {
    asset_value: number;
    liabilities: number;
    exposure: number;
    net_worth: number;
  };
}

export interface BayesianUpdateResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    posterior_pd: number;
    posterior_alpha: number;
    posterior_beta: number;
    confidence_interval_95: { lower: number; upper: number };
  };
  timestamp: string;
}

export interface BayesianPosteriorResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    base_pd: number;
    posterior_pd: number;
  };
  timestamp: string;
}

// ── Fund (RWA) domain — attested-NAV financing loop (P11 / BUIDL-CTC) ──────
// Mirrors /fund/status + /fund/attestation-report payloads.

export interface FundPositionSnapshot {
  symbol?: string;
  qty?: number;
  market_value?: number;
  asset_class?: string;
  unrealized_pl?: number;
  [k: string]: unknown;
}

export interface FundAttestationReport {
  nav?: number;
  equity?: number;
  cash?: number;
  buying_power?: number;
  digest?: string;
  anchor_tx?: string | null;
  mode?: string;
  offline?: boolean;
  chain_linked?: boolean;
  verified?: boolean;
  positions?: FundPositionSnapshot[];
  currency?: string;
  generated_at?: string;
  [k: string]: unknown;
}

export interface FundCc3Execution {
  reachable: boolean;
  account: string | null;
  free_planck: string | null;
  free_ctc: number | null;
  ss58_format?: number;
}

export interface FundCreditDecision {
  decision_id: string;
  recommended_amount?: number | null;
  collateral_value?: number | null;
  credit_score?: number | null;
  probability_of_default?: number | null;
  decision_status?: string | null;
  approval_status?: string | null;
  execution_transaction?: string | null;
  created_at?: string | null;
}

export interface FundStatus {
  borrower_id: string;
  nav_anchor_contract: string | null;
  relay_configured: boolean;
  offline_ok: boolean;
  cc3_execution: FundCc3Execution | null;
  attestation_reachable: boolean;
  latest_report: FundAttestationReport | null;
  latest_decision: FundCreditDecision | null;
  [k: string]: unknown;
}

export interface FundReport {
  report: FundAttestationReport | null;
  cached: boolean;
}

// ── H6-9 Lending pool on the claim (Credit → Lending) ───────────────────────
export interface LendingPoolEvent {
  kind: string;
  at: number;
  amount?: number;
  lender?: string;
  decision_id?: string;
}

export interface LendingPoolState {
  pool_id: string;
  borrower_id: string;
  status: "open" | "frozen" | "liquidatable";
  warning: "ltv_warning" | "ltv_breach" | null;
  total_deposits: number;
  active_loan: number;
  utilization: number | null;
  borrow_rate_pct: number | null;
  lend_rate_pct: number | null;
  reserve_factor: number;
  max_ltv_pct: number;
  collateral_value: number | null;
  ltv_pct: number | null;
  borrowable: number | null;
  liquidation_warn_pct: number;
  liquidation_ltv_pct: number;
  disbursement_tx: string | null;
  last_borrow_decision: string | null;
  events: LendingPoolEvent[];
  updated_at?: number;
}

export interface LendingLiquidation {
  health: "healthy" | "warning" | "liquidatable";
  ltv_pct: number;
  collateral_value: number | null;
  active_loan: number;
  warn_threshold_pct: number;
  liquidate_threshold_pct: number;
  closing_liquidation_price: number | null;
}

export interface CorrelationMatrixResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    symbols: string[];
    groups: Record<string, string>;
    matrix: Record<string, Record<string, number>>;
    pairs: Array<{
      asset_a: string;
      asset_b: string;
      group_a: string;
      group_b: string;
      correlation: number;
      same_group: boolean;
      above_threshold: boolean;
    }>;
    highly_correlated_pairs: Array<{
      asset_a: string;
      asset_b: string;
      group_a: string;
      group_b: string;
      correlation: number;
      same_group: boolean;
      above_threshold: boolean;
    }>;
    average_correlation: number;
    max_pair_correlation: number;
    unclassified_symbols: string[];
  };
  provenance: {
    basis: string;
    data_source: string;
    deterministic: boolean;
    llm_influenced: boolean;
    spec_reference: string;
  };
  timestamp: string;
}

export interface PortfolioExposureResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    borrowers: Array<{
      borrower_id: string;
      market_regime: string;
      total_collateral_value: number;
      total_liabilities: number;
      total_exposure: number;
      net_worth: number;
      protocols: string[];
    }>;
    protocols: Array<{
      protocol: string;
      total_exposure: number;
      borrower_count: number;
      share_of_portfolio: number;
    }>;
    totals: {
      total_collateral_value: number;
      total_liabilities: number;
      total_exposure: number;
      net_exposure: number;
    };
    concentration: {
      largest_borrower: {
        borrower_id: string;
        exposure: number;
        share: number;
      } | null;
      largest_protocol: {
        protocol: string;
        exposure: number;
        share: number;
      } | null;
    };
  };
  provenance: {
    basis: string;
    data_source: string;
    deterministic: boolean;
    llm_influenced: boolean;
    spec_reference: string;
  };
  timestamp: string;
}

export interface CounterpartyExposureResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    protocol: string;
    total_exposure: number;
    borrower_count: number;
    share_of_portfolio: number;
    borrowers: Array<{
      borrower_id: string;
      market_regime: string;
      protocol_exposure: number;
      borrower_total_exposure: number;
      exposure_share: number;
    }>;
    risk_level: string;
  };
  timestamp: string;
}

export interface ContagionResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    source_borrower_id: string;
    primary_collateral_loss: number;
    contagion_collateral_loss: number;
    total_collateral_loss: number;
    loss_as_share_of_portfolio: number;
    infected_borrower_count: number;
    defaulted_borrower_count: number;
    defaulted_borrowers: string[];
    cascade_depth: number;
    rings: Array<{
      ring: number;
      borrowers: string[];
      effective_shock: number;
      collateral_loss: number;
    }>;
    severity: string;
  };
  timestamp: string;
}

export interface PortfolioVarResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    portfolio_value: number;
    portfolio_volatility_annual: number;
    portfolio_volatility_horizon: number;
    z_score: number;
    var: number;
    var_pct_of_portfolio: number;
    positions: Array<{
      borrower_id: string;
      market_regime: string;
      exposure: number;
      annual_volatility: number;
    }>;
  };
  timestamp: string;
}

export interface SystemicStressResponse {
  model_id: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: {
    shock_pct: number;
    total_collateral_loss: number;
    loss_pct_of_collateral: number;
    base_collateral: number;
    stressed_collateral: number;
    base_liabilities: number;
    base_net_worth: number;
    stressed_net_worth: number;
    net_worth_impairment: number;
    insolvent_borrower_count: number;
    insolvent_borrowers: Array<{
      borrower_id: string;
      stressed_collateral: number;
      total_liabilities: number;
      shortfall: number;
    }>;
    severity: string;
    borrowers: Array<{
      borrower_id: string;
      market_regime: string;
      base_collateral: number;
      stressed_collateral: number;
      loss: number;
      insolvent: boolean;
    }>;
  };
  timestamp: string;
}

export interface GovernanceModel {
  model_id: string;
  name: string;
  version: string;
  owner: string;
  description: string | null;
  parameters: Record<string, unknown>;
  effective_date: string;
  status: string;
  registered_at: string;
}

export interface PolicyUpdateResponse {
  policy_id: string;
  previous_value: unknown;
  new_value: unknown;
  user: string;
  reason: string;
  effective_date: string;
  updated_at: string;
}

export interface AuditLogEntry {
  entity_type: string;
  entity_id: string;
  action: string;
  actor: string;
  timestamp: string;
  details: Record<string, unknown>;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}