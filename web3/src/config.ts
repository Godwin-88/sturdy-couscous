import "dotenv/config";

/**
 * Web3RelayConfig — typed view of the P11 §9 EVM relay environment.
 * Mirrors dreamdex/src/config.ts — same parse discipline, WEB3_* names.
 */
export interface Web3RelayConfig {
  enabled: boolean;
  mode: "paper" | "live";
  network: string;
  chainId: number;
  rpcUrl: string;
  passportContract: string;
  verifierContract: string;
  wallet: string;
  hasKey: boolean;
  dryRun: boolean;
  port: number;
  apiKey: string;
  rateLimitPerMin: number;
  heartbeatMs: number;
  requiredConfirmations: number; // U14
  // D1–D4 gates (reject sub-threshold intents before any broadcast)
  minLpEdgePct: number;
  minLendingSpreadPct: number;
  minFundingCarryPct: number;
  maxLeverageX: number;
}

function boolOf(v: string | undefined, dflt: boolean): boolean {
  return v === undefined ? dflt : (v === "1" || v.toLowerCase() === "true");
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Web3RelayConfig {
  return {
    enabled: boolOf(env["WEB3_ENABLED"], false),
    mode: env["WEB3_TRADING_MODE"] === "live" ? "live" : "paper",
    network: env["WEB3_NETWORK"] ?? "sepolia",
    chainId: parseInt(env["WEB3_CHAIN_ID"] ?? "11155111", 10),
    rpcUrl: env["WEB3_RPC_URL"] ?? "https://rpc.sepolia.org",
    passportContract: env["WEB3_PASSPORT_CONTRACT"] ?? "0x0",
    verifierContract: env["WEB3_VERIFIER_CONTRACT"] ?? "0x0",
    wallet: env["WEB3_WALLET_ADDRESS"] ?? "",
    hasKey: Boolean(env["WEB3_ORACLE_AUTHORITY_PRIVATE_KEY"]),
    dryRun: boolOf(env["DRY_RUN"], true),
    port: parseInt(env["RELAY_PORT"] ?? "8460", 10),
    apiKey: env["RELAY_API_KEY"] ?? "change-me",
    rateLimitPerMin: parseInt(env["RELAY_RATE_LIMIT_PER_MIN"] ?? "5", 10),
    heartbeatMs: parseInt(env["HEARTBEAT_MS"] ?? "30000", 10),
    requiredConfirmations: parseInt(env["REQUIRED_CONFIRMATIONS"] ?? "3", 10),
    minLpEdgePct: parseFloat(env["MIN_LP_EDGE_PCT"] ?? "0.05"),
    minLendingSpreadPct: parseFloat(env["MIN_LENDING_SPREAD_PCT"] ?? "0.02"),
    minFundingCarryPct: parseFloat(env["MIN_FUNDING_CARRY_PCT"] ?? "0.10"),
    maxLeverageX: parseFloat(env["MAX_LEVERAGE_X"] ?? "2.0"),
  };
}