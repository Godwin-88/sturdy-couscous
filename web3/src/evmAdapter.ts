/**
 * evmAdapter.ts — EVM DeFi adapter (Venue B, Ethereum Sepolia — chain 11155111).
 * Ported from stellcasp zkkyc/adapters/ethereum.py (EP-08 F-08.2) and
 * ethereum/contracts/*.sol. This is the ONLY module that talks to Sepolia.
 *
 * Stub mode keeps the relay runnable without testnet keys; live mode reads
 * on-chain via viem publicClient and writes via walletClient. DRY_RUN defaults
 * to 1 — nothing on-chain until explicitly flipped (U17).
 */
import type { Web3RelayConfig } from "./config.js";

export interface EvmBookLevel { bid: number; ask: number; last: number; }

/** Mirrors the EVM DeFi market row the agent consumes (P11 §6 relay contract). */
export interface EvmMarketRow {
  marketId: string;
  symbol: string;
  sector: "amm_lp" | "lending" | "yield" | "perp";
  asset: string;
  status: number;          // 1=Trading
  up: EvmBookLevel;        // provide/lend yield view
  down: EvmBookLevel;      // borrow/carry view
  askDepth: number;        // liquidity floor (U11)
  edgePct: number;         // precomputed fee−IL−gas (D1) or spread (D2/D4)
  leverageX: number;       // D3/U32
}

export interface EvmOrderInput {
  marketId: string;
  side: "up" | "down";
  qty: number;
  gasBumpPct: number;      // U3
}

export interface EvmBroadcastResult { txHash: string; raw?: string; }

export const EVM_NOT_WIRED =
  "viem live path not wired in stub mode — implement liveSnapshot/liveBroadcast " +
  "via publicClient/walletClient against Sepolia (see README 'Wire the live path')";

export class EvmAdapter {
  constructor(private readonly cfg: Web3RelayConfig) {}

  get isLive(): boolean {
    return this.cfg.enabled && this.cfg.mode === "live" && this.cfg.hasKey;
  }

  async snapshot(): Promise<EvmMarketRow[]> {
    if (!this.isLive) return stubMarkets();
    return this.liveSnapshot();
  }

  async acceptsOrders(marketId: string): Promise<boolean> {
    const rows = await this.snapshot();
    const found = rows.find((r) => r.marketId === marketId);
    return found ? found.status === 1 : false;
  }

  async broadcast(_i: EvmOrderInput): Promise<EvmBroadcastResult> {
    if (!this.isLive) {
      return { txHash: `stub_${Date.now()}`, raw: "dry-run — never broadcast" };
    }
    return this.liveBroadcast(_i);
  }

  /** Confirmations of a crediting tx on the authoritative chain (U14, C1). */
  async confirmationsOf(_txHash: string): Promise<number> {
    if (!this.isLive) return this.cfg.requiredConfirmations; // stub: instantly deep
    throw new Error(EVM_NOT_WIRED);
  }

  // ── Live paths (viem; TODO: wire per README once Sepolia env is funded) ──
  private async liveSnapshot(): Promise<EvmMarketRow[]> {
    // const client = createPublicClient({ chain: sepolia, transport: http(this.cfg.rpcUrl) });
    // read Uniswap V3 pool / Aave pool / perp funding rows; build edgePct per gate.
    throw new Error(EVM_NOT_WIRED);
  }

  private async liveBroadcast(_i: EvmOrderInput): Promise<EvmBroadcastResult> {
    // const wallet = createWalletClient({ account: privateKeyToAccount(key), chain: sepolia });
    // encode + sendRawTransaction via viem (RFC-6979 internally) → { txHash }
    throw new Error(EVM_NOT_WIRED);
  }
}

/** Synthetic Trading rows for the whole stack without testnet access. */
function stubMarkets(): EvmMarketRow[] {
  const now = Date.now();
  void now;
  return [
    {
      marketId: "0x0000000000000000000000000000000000000000000000000000000000000101",
      symbol: "UNI-ETH-05/USDCso#0.30", sector: "amm_lp", asset: "ETH",
      status: 1,
      up: { bid: 0.182, ask: 0.186, last: 0.184 },
      down: { bid: 0.160, ask: 0.164, last: 0.162 },
      askDepth: 8, edgePct: 0.06, leverageX: 1.0,
    },
    {
      marketId: "0x0000000000000000000000000000000000000000000000000000000000000102",
      symbol: "AAVE-USDCso#0.55", sector: "lending", asset: "USDC",
      status: 1,
      up: { bid: 0.035, ask: 0.036, last: 0.0355 },
      down: { bid: 0.021, ask: 0.022, last: 0.0215 },
      askDepth: 10, edgePct: 0.025, leverageX: 1.0,
    },
    {
      marketId: "0x0000000000000000000000000000000000000000000000000000000000000103",
      symbol: "YV-ETH-LP#0.80", sector: "yield", asset: "ETH-LP",
      status: 1,
      up: { bid: 0.210, ask: 0.216, last: 0.213 },
      down: { bid: 0.140, ask: 0.145, last: 0.142 },
      askDepth: 6, edgePct: 0.05, leverageX: 1.8,
    },
    {
      marketId: "0x0000000000000000000000000000000000000000000000000000000000000104",
      symbol: "PERP-ETH-SEP#0.12", sector: "perp", asset: "ETH-PERP",
      status: 1,
      up: { bid: 0.062, ask: 0.064, last: 0.063 },
      down: { bid: -0.058, ask: -0.056, last: -0.057 },
      askDepth: 5, edgePct: 0.12, leverageX: 1.2,
    },
  ];
}