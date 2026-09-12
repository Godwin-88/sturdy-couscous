import {
  ApiError,
  type AssessmentRequest,
  type BayesianPosteriorResponse,
  type BayesianUpdateResponse,
  type ContagionResponse,
  type CorrelationMatrixResponse,
  type CounterpartyExposureResponse,
  type CreditAssessment,
  type CreditDecision,
  type CreditExecution,
  type DbStatus,
  type Evidence,
  type ExecuteCreditRequest,
  type ExecutionAccountResponse,
  type GraphQueryResponse,
  type HealthResponse,
  type PortfolioExposureResponse,
  type PortfolioVarResponse,
  type ScenarioRunResponse,
  type ScenarioGenerateResponse,
  type ScenarioAnalyzeResponse,
  type StressResult,
  type SystemicStressResponse,
  type VaRResponse,
  type CVaRResponse,
  type ExpectedLossResponse,
  type GovernanceModel,
  type AuditLogEntry,
  type PolicyUpdateResponse,
  type BorrowerWalletsResponse,
  type WalletExposureResponse,
  type WalletResolveResponse,
  type DecisionOverrideRequest,
  type DecisionReconstructResponse,
  type FundStatus,
  type FundReport,
} from "../types/credit";

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const BASE = `${API}/api/v1`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = (body as { detail?: string }).detail ?? `HTTP ${res.status}`;
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export const api = {
  health: () => get<HealthResponse>("/health"),
  db: () => get<DbStatus>("/db"),

  seedDemoBorrower: () =>
    post<{ borrower_id: string; status: string }>("/risk/borrowers/seed"),
  listBorrowers: () => get<string[]>("/risk/borrowers"),
  assess: (borrowerId: string, req: AssessmentRequest) =>
    post<CreditAssessment>(`/risk/borrowers/${borrowerId}/assessment`, req),
  decide: (borrowerId: string, req: AssessmentRequest) =>
    post<CreditDecision>(`/risk/borrowers/${borrowerId}/decision`, req),

  verifyEvidence: (txHash: string, chainKey?: number, borrowerId?: string) =>
    post<Evidence>("/risk/evidence/verify", {
      tx_hash: txHash,
      chain_key: chainKey,
      borrower_id: borrowerId,
    }),

  listEvidence: (borrowerId?: string) => {
    const q = borrowerId ? `?borrower_id=${encodeURIComponent(borrowerId)}` : "";
    return get<Evidence[]>(`/risk/evidence${q}`);
  },

  approveDecision: (decisionId: string) =>
    post<{ decision_id: string; status: string }>("/risk/execution/approve", {
      decision_id: decisionId,
    }),
  execute: (req: ExecuteCreditRequest) =>
    post<CreditExecution>("/risk/execution/execute", req),
  monitor: (txHash: string) =>
    post<{ status: string; tx_hash?: string; block?: string }>(
      "/risk/execution/monitor",
      { tx_hash: txHash },
    ),
  executionAccount: () => get<ExecutionAccountResponse>("/risk/execution/account"),
  executionBalance: (address: string) =>
    get<{ address: string; freePlanck: string }>(`/risk/execution/balance?address=${encodeURIComponent(address)}`),

  queryGraph: (query: string) => post<GraphQueryResponse>("/risk/query", { query }),

  stress: (baseExposure: number, shockPct: number, recoveryRate: number) => {
    const q = new URLSearchParams({
      base_exposure: String(baseExposure),
      shock_pct: String(shockPct),
      recovery_rate: String(recoveryRate),
    });
    return request<StressResult>(`/risk/scenario/stress?${q.toString()}`, {
      method: "POST",
      body: "{}",
    });
  },
  var: (pnl: number[], confidence?: number) =>
    post<VaRResponse>("/risk/scenario/var", { pnl, confidence }),
  cvar: (pnl: number[], confidence?: number) =>
    post<CVaRResponse>("/risk/scenario/cvar", { pnl, confidence }),
  expectedLoss: (exposure: number, pd: number, lgd?: number) => {
    const q = new URLSearchParams({
      exposure: String(exposure),
      pd: String(pd),
      lgd: String(lgd ?? 0.4),
    });
    return request<ExpectedLossResponse>(`/risk/scenario/expected-loss?${q.toString()}`, {
      method: "POST",
      body: "{}",
    });
  },
  runScenario: (body: { name: string; shock_pct: number; vix?: number }) =>
    post<ScenarioRunResponse>("/risk/scenario/run", body),

  generateScenario: (body: {
    source: string;
    borrower_id?: string;
    regime: string;
    exposure: number;
    confidence?: number;
    custom_pnl?: number[];
    days?: number;
  }) => post<ScenarioGenerateResponse>("/risk/quant/scenario/generate", body),

  analyzeScenario: (body: {
    pnl: number[];
    exposure: number;
    shock_pct: number;
    recovery_rate: number;
    pd: number;
    lgd: number;
    confidence: number;
  }) => post<ScenarioAnalyzeResponse>("/risk/quant/scenario/analyze", body),

  overrideDecision: (decisionId: string, reason: string) =>
    post<Record<string, unknown>>(`/risk/decisions/${decisionId}/override`, {
      reason,
      overridden_by: "user",
    } as DecisionOverrideRequest),
  reconstructDecision: (decisionId: string) =>
    get<DecisionReconstructResponse>(`/risk/decisions/${decisionId}/reconstruct`),
  listDecisions: (borrowerId?: string) => {
    const q = borrowerId ? `?borrower_id=${encodeURIComponent(borrowerId)}` : "";
    return get<Record<string, unknown>[]>(`/risk/decisions${q}`);
  },

  resolveWallet: (address: string, chain?: string) =>
    post<WalletResolveResponse>("/risk/wallet/resolve", {
      wallet_address: address,
      chain,
    }),
  borrowerWallets: (borrowerId: string) =>
    get<BorrowerWalletsResponse>(`/risk/borrowers/${borrowerId}/wallets`),
  aggregateWallet: (address: string, chain?: string) =>
    post<WalletExposureResponse>("/risk/wallet/aggregate", {
      wallet_address: address,
      chain,
    }),

  bayesianUpdate: (priorPd: number, evidence: Array<{ type: string; strength: number }>) =>
    post<BayesianUpdateResponse>("/risk/bayesian/update", {
      prior_pd: priorPd,
      evidence,
    }),
  bayesianPosterior: (ficoScore: number, leverage: number, regime: string, evidencePosterior: number) =>
    post<BayesianPosteriorResponse>("/risk/bayesian/posterior", {
      fico_score: ficoScore,
      leverage,
      regime,
      evidence_posterior: evidencePosterior,
    }),

  correlationMatrix: (symbols: string[], threshold?: number) =>
    post<CorrelationMatrixResponse>("/risk/correlation/matrix", {
      asset_symbols: symbols,
      threshold,
    }),
  borrowerCorrelation: (borrowerId: string, threshold?: number) =>
    get<CorrelationMatrixResponse>(`/risk/borrowers/${borrowerId}/correlation?threshold=${threshold ?? 0.5}`),
  correlatedGroups: (threshold?: number) =>
    get<CorrelationMatrixResponse>(`/risk/correlation/groups?threshold=${threshold ?? 0.5}`),

  portfolioExposure: () => get<PortfolioExposureResponse>("/risk/portfolio/exposure"),
  counterpartyExposure: (protocol: string) =>
    get<CounterpartyExposureResponse>(`/risk/portfolio/counterparty/${encodeURIComponent(protocol)}`),
  contagionAnalysis: (borrowerId: string, shockPct?: number) =>
    post<ContagionResponse>("/risk/portfolio/contagion", {
      borrower_id: borrowerId,
      shock_pct: shockPct,
    }),
  portfolioVar: (confidence?: number) =>
    post<PortfolioVarResponse>("/risk/portfolio/var", { confidence }),
  systemicStress: (shockPct?: number) =>
    get<SystemicStressResponse>(`/risk/portfolio/systemic-stress?shock_pct=${shockPct ?? -0.55}`),

  registerModel: (model: {
    model_id: string;
    name: string;
    version: string;
    owner: string;
    description?: string;
    parameters?: Record<string, unknown>;
    status?: string;
  }) => post<GovernanceModel>("/risk/governance/models", model),
  getModelGovernance: (modelId: string) =>
    get<GovernanceModel>(`/risk/governance/models/${modelId}`),
  listGovernanceModels: () => get<GovernanceModel[]>("/risk/governance/models"),
  updatePolicy: (policy: {
    policy_id: string;
    previous_value: unknown;
    new_value: unknown;
    user: string;
    reason: string;
  }) => post<PolicyUpdateResponse>("/risk/governance/policies", policy),
  getAuditLog: (entityType: string, entityId: string) =>
    get<AuditLogEntry[]>(`/risk/governance/audit/${entityType}/${entityId}`),
};

// ── Fund (RWA) — root-level /fund endpoints (NOT under /api/v1) ────────────
async function rootRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = (body as { detail?: string }).detail ?? `HTTP ${res.status}`;
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const fundApi = {
  status: () => rootRequest<FundStatus>("/fund/status"),
  report: () => rootRequest<FundReport>("/fund/attestation-report"),
};