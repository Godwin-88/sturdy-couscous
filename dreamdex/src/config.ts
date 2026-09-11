import "./env.js";

/** RelayConfig — typed view of the relay environment (see .env.example). */
export interface RelayConfig {
  enabled: boolean;
  mode: "paper" | "live";
  network: string;
  venueId: string;
  rpcUrl: string;
  indexerUrl: string;      // Envio/Hasura GraphQL — market discovery (SDK)
  wsRpcUrl: string;        // chain WebSocket — on-chain reads/writes (SDK)
  wallet: string;
  privateKey?: string;     // SOMNIA_PRIVATE_KEY (0x-prefixed); relay container only
  hasKey: boolean;
  autoClaim: boolean;
  autoClaimIntervalMs: number;
  dryRun: boolean;
  port: number;
  apiKey: string;
  rateLimitPerMin: number;
  heartbeatMs: number;
  requiredConfirmations: number; // U14
}

function boolOf(v: string | undefined, dflt: boolean): boolean {
  return v === undefined ? dflt : (v === "1" || v.toLowerCase() === "true");
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): RelayConfig {
  return {
    enabled: boolOf(env["DREAMDEX_ENABLED"], false),
    mode: env["DREAMDEX_TRADING_MODE"] === "live" ? "live" : "paper",
    network: env["DREAMDEX_NETWORK"] ?? "testnet",
    venueId: env["VENUE_ID"] ?? "",
    rpcUrl: env["SOMNIA_RPC_URL"] ?? "https://dream-rpc.somnia.network",
    indexerUrl: env["SOMNIA_INDEXER_URL"] ?? (env["DREAMDEX_NETWORK"] === "mainnet"
      ? "https://prd.smk.somnia.host/v1/graphql"
      : "https://dev.smk.somnia.host/v1/graphql"),
    wsRpcUrl: env["SOMNIA_WS_RPC_URL"] ?? (env["DREAMDEX_NETWORK"] === "mainnet"
      ? "wss://api.infra.mainnet.somnia.network/ws"
      : "wss://api.infra.testnet.somnia.network/ws"),
    wallet: env["SOMNIA_WALLET_ADDRESS"] ?? "",
    privateKey: env["SOMNIA_PRIVATE_KEY"]?.trim() || undefined,
    hasKey: Boolean(env["SOMNIA_PRIVATE_KEY"]),
    autoClaim: boolOf(env["AUTO_CLAIM"], true),
    autoClaimIntervalMs: parseInt(env["AUTO_CLAIM_INTERVAL_MS"] ?? "600000", 10),
    dryRun: boolOf(env["DRY_RUN"], true),
    port: parseInt(env["RELAY_PORT"] ?? "8450", 10),
    apiKey: env["RELAY_API_KEY"] ?? "change-me",
    rateLimitPerMin: parseInt(env["RELAY_RATE_LIMIT_PER_MIN"] ?? "5", 10),
    heartbeatMs: parseInt(env["HEARTBEAT_MS"] ?? "30000", 10),
    requiredConfirmations: parseInt(env["REQUIRED_CONFIRMATIONS"] ?? "3", 10),
  };
}