/**
 * sdkAdapter.ts — the ONLY module allowed to import @somnia-chain/markets-sdk
 * and @dreamdex-bot-kit/ec-core (U8: code-reuse doctrine, M5). Stub mode keeps
 * the relay runnable without testnet keys; live mode forwards to the real SDK.
 *
 * U17 safety stance: when the adapter has no live path, it never pretends —
 * `isLive` must be true before any broadcast path exists.
 */
import type { RelayConfig } from "./config.js";

export interface BookLevel { bid: number; ask: number; last: number; }

/** Mirrors the EC market row the agent consumes (P9 §6 relay contract). */
export interface MarketRow {
  marketId: string;
  symbol: string;
  asset: string;        // "BTC" | "ETH"
  strike: number;
  intervalSec: number;
  closesAt: string;
  status: number;       // 0=Listed 1=Trading 2=Locked 3=Resolved 4=Voided
  up: BookLevel;
  down: BookLevel;
  askDepth: number;     // liquidity floor for U11
}

export interface BroadcastInput {
  marketId: string;
  side: "up" | "down";
  qty: number;
  gasBumpPct: number;   // U3
}

export interface BroadcastResult { txHash: string; raw?: string; }

export const SDK_NOT_WIRED =
  "markets-sdk not wired in stub mode — implement sdkAdapter.liveSnapshot/liveBroadcast " +
  "via loadMarkets()/placeLimit() (see README 'Wire the live path')";

export class SdkAdapter {
  constructor(private readonly cfg: RelayConfig) {}

  get isLive(): boolean {
    return this.cfg.enabled && this.cfg.mode === "live" && this.cfg.hasKey;
  }

  async snapshot(): Promise<MarketRow[]> {
    if (!this.isLive) return stubMarkets();
    return this.liveSnapshot();
  }

  /** Returns whether a market is accepting orders, gated ON-CHAIN (M4: never the indexer). */
  async acceptsOrders(marketId: string): Promise<boolean> {
    const rows = await this.snapshot();
    const found = rows.find((r) => r.marketId === marketId);
    return found ? found.status === 1 : false;
  }

  async broadcast(_input: BroadcastInput): Promise<BroadcastResult> {
    if (!this.isLive) {
      return { txHash: `stub_${Date.now()}`, raw: "dry-run — never broadcast" };
    }
    return this.liveBroadcast(_input);
  }

  /** Confirmations of a crediting tx on the authoritative chain (U14, C1). */
  async confirmationsOf(_txHash: string): Promise<number> {
    if (!this.isLive) return this.cfg.requiredConfirmations; // stub: instantly deep
    throw new Error(SDK_NOT_WIRED);
  }

  // ── Live paths (TODO: wire per README once testnet env is funded) ────────
  private async liveSnapshot(): Promise<MarketRow[]> {
    // const mkts = await loadMarkets({ venueId: this.cfg.venueId, network });
    // gate each on getMarketOnchain(marketId).status === 1; read book via SDK.
    throw new Error(SDK_NOT_WIRED);
  }

  private async liveBroadcast(_i: BroadcastInput): Promise<BroadcastResult> {
    // viem WalletClient(privateKey, { chainId: network === "testnet" ? 50312 : 5031 })
    // -> ec-core placeLimit (tick/lot quantize) -> assertTxOk -> { txHash }
    throw new Error(SDK_NOT_WIRED);
  }
}

/** Synthetic Trading window so the whole stack runs without testnet access. */
function stubMarkets(): MarketRow[] {
  const now = Date.now();
  return [
    {
      marketId: "0x0000000000000000000000000000000000000000000000000000000000000001",
      symbol: "BTC-0-01JAN00-0000/USDso#YES",
      asset: "BTC", strike: 100_000, intervalSec: 300,
      closesAt: new Date(now + 300_000).toISOString(), status: 1,
      up: { bid: 0.52, ask: 0.54, last: 0.53 },
      down: { bid: 0.46, ask: 0.48, last: 0.47 },
      askDepth: 12,
    },
  ];
}