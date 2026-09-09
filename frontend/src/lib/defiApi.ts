/**
 * defiApi.ts — typed client for the /defi/* endpoints (P11 Stage-5).
 * Read-only surface: candidates, governor, sectors, positions, evidence, status.
 */

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const BASE = `${API}/defi`;

export interface DeFiCandidate {
  market_id?: string;
  symbol?: string;
  asset?: string;
  sector?: string;          // D1..D8
  venue?: string;           // sepolia-evm | somnia-relay
  kind?: string;
  side?: string;
  estimate?: number;
  ask?: number;
  edge_pct?: number;
  net_edge_pct?: number;
  binary_kelly?: number;
  size_usd?: number;
  qty_contracts?: number;
  regime?: string;
  status?: string;
  closes_at?: string;
}

export interface DeFiGovernor {
  paused_evm?: boolean;
  paused_ec?: boolean;
  feeds?: Array<{ feed_id?: string; venue?: string; status?: string; stale_ms?: number }>;
  checked_at?: string;
}

export interface EvidenceSummary {
  head?: { cycle_id?: string; regime?: string; ts?: number; hash?: string; prev?: string; n?: number };
  root?: string;
  merkle_root?: string;
  verify_ok?: boolean;
  cached?: boolean;
}

export interface DeFiStatus {
  enabled?: boolean;
  mode?: string;
  venue?: string;
  relay_reachable?: boolean;
  dry_run?: boolean;
  gates?: {
    freeze?: boolean;
    min_lp_edge_pct?: number;
    min_lending_spread_pct?: number;
    min_ec_edge_pct?: number;
    max_defi_exposure_pct?: number;
  };
}

export interface DefiApiData {
  candidates?: { candidates?: DeFiCandidate[]; cached?: boolean };
  governor?: { governor?: DeFiGovernor; cached?: boolean };
  sectors?: { sectors?: Record<string, { count: number; venue?: string; size_usd: number }>; total_size_usd?: number; cached?: boolean };
  positions?: { positions?: unknown[]; drift_items?: unknown[]; evm_positions?: unknown[] };
  evidence?: EvidenceSummary;
  status?: DeFiStatus;
}

export async function fetchDefi(): Promise<DefiApiData> {
  const [c, g, se, p, ev, st] = await Promise.all([
    fetch(`${BASE}/candidates`).then((r) => r.json()),
    fetch(`${BASE}/governor`).then((r) => r.json()),
    fetch(`${BASE}/sectors`).then((r) => r.json()),
    fetch(`${BASE}/positions`).then((r) => r.json()),
    fetch(`${BASE}/evidence`).then((r) => r.json()),
    fetch(`${BASE}/status`).then((r) => r.json()),
  ]);
  return { candidates: c, governor: g, sectors: se, positions: p, evidence: ev, status: st };
}