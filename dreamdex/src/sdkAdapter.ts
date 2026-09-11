/**
 * sdkAdapter.ts — the ONLY module allowed to import @somnia-chain/markets-sdk
 * (U8: code-reuse doctrine, M5). Stub mode keeps the relay runnable without
 * testnet keys; live mode forwards to the real SDK.
 *
 * U17 safety stance: when the adapter has no live path, it never pretends —
 * `isLive` must be true before any broadcast path exists.
 *
 * Live path (wired against the real unified SDK, v0.29):
 *   - `new SomniaMarkets({ indexerUrl, chain, wsRpcUrl, addresses, privateKey })`
 *     is the single entry point (SDK README). Testnet indexer = dev.smk.somnia.host.
 *   - `loadMarkets()` discovers markets via the indexer; we keep only BINARY
 *     markets whose `info.venueId` matches the configured venue.
 *   - Status is gated ON-CHAIN (M4): "Trading" derives from the window
 *     [tradingStart, expiry), never the indexer alone (indexer lags seconds).
 *   - Books: `fetchOrderBook("#YES")` = up side, `fetchOrderBook("#NO")` = down
 *     (the SDK inverts the YES book into NO terms).
 *   - Orders: `createOrder(ref, "limit", "buy", qty, price, { timeInForce:"IOC" })`
 *     — a taker bounded at our price. The SDK snaps price/qty to the venue's
 *     tick/lot grids itself (this replaces bot-kit `ec-core` quantize, which is
 *     not on npm; the unified SDK's precision helpers are the maintained path).
 */
import type { RelayConfig } from "./config.js";
import { SomniaMarkets, SOMNIA_TESTNET_ADDRESSES, SOMNIA_MAINNET_ADDRESSES } from "@somnia-chain/markets-sdk";
import { somniaShannon, somniaMainnet } from "@somnia-chain/markets-sdk/chains";
import { createPublicClient, http, parseAbi, type Address, type Hash } from "viem";

export interface BookLevel { bid: number; ask: number; last: number; }

/** Mirrors the EC market row the agent consumes (P9 §6 relay contract). */
export interface MarketRow {
  marketId: string;
  symbol: string;
  asset: string;        // "BTC" | "ETH"
  strike: number;
  intervalSec: number;
  closesAt: string;
  status: number;       // 0=Listed 1=Trading 2=Locked 3=Resolved 4=Voided 5=Finalized
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
  "via loadMarkets()/createOrder() (see README 'Wire the live path')";

// Testnet collateral (tUSDC) — the SDK's SOMNIA_TESTNET_ADDRESSES.collateral.
const TUSDC = "0x70a86D8842FB63C4Ad2b7cdddF530eBf1BB25d8E" as Address;
const TUSDC_ABI = parseAbi(["function balanceOf(address owner) view returns (uint256)"]);

export class SdkAdapter {
  private exchange: SomniaMarkets | null = null;
  private readonly publicClient: ReturnType<typeof createPublicClient>;

  constructor(private readonly cfg: RelayConfig) {
    this.publicClient = createPublicClient({
      chain: cfg.network === "mainnet" ? somniaMainnet : somniaShannon,
      transport: http(cfg.rpcUrl, { timeout: 30_000 }),
    });
  }

  get isLive(): boolean {
    return this.cfg.enabled && this.cfg.mode === "live" && this.cfg.hasKey;
  }

  /** Read-only balances: native SOMI (gas, 18-dec wei) + tUSDC (collateral, 6-dec). */
  async balances(): Promise<{ somiWei: string; tusdcRaw: string }> {
    const wallet = this.cfg.wallet as `0x${string}`;
    const somi = await this.publicClient.getBalance({ address: wallet });
    const tusdc = await this.publicClient.readContract({
      address: TUSDC as `0x${string}`,
      abi: TUSDC_ABI,
      functionName: "balanceOf",
      args: [wallet],
    });
    return { somiWei: somi.toString(), tusdcRaw: tusdc.toString() };
  }

  /** Lazily-built unified SDK exchange (only when live). */
  private sdk(): SomniaMarkets {
    if (!this.isLive) throw new Error(SDK_NOT_WIRED);
    if (!this.exchange) {
      this.exchange = new SomniaMarkets({
        indexerUrl: this.cfg.indexerUrl,
        chain: this.cfg.network === "mainnet" ? somniaMainnet : somniaShannon,
        wsRpcUrl: this.cfg.wsRpcUrl,
        addresses: this.cfg.network === "mainnet" ? SOMNIA_MAINNET_ADDRESSES : SOMNIA_TESTNET_ADDRESSES,
        privateKey: this.cfg.privateKey as `0x${string}` | undefined,
      });
    }
    return this.exchange;
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

  async broadcast(input: BroadcastInput): Promise<BroadcastResult> {
    if (!this.isLive) {
      return { txHash: `stub_${Date.now()}`, raw: "dry-run — never broadcast" };
    }
    return this.liveBroadcast(input);
  }

  /** Confirmations of a crediting tx on the authoritative chain (U14, C1). */
  async confirmationsOf(txHash: string): Promise<number> {
    if (!this.isLive) return this.cfg.requiredConfirmations; // stub: instantly deep
    try {
      const receipt = await this.publicClient.getTransactionReceipt({ hash: txHash as Hash });
      if (!receipt.blockNumber) return 0;
      const current = await this.publicClient.getBlockNumber();
      return Number(current - receipt.blockNumber) + 1;
    } catch {
      return 0; // not mined / unknown → 0 confirmations (never credit on 0)
    }
  }

  /** Live tUSDC collateral balance (human units) — feeds the M6 credit gate. */
  async collateralBalance(): Promise<number> {
    if (!this.isLive) return 10_000;
    const raw = await this.publicClient.readContract({
      address: TUSDC,
      abi: TUSDC_ABI,
      functionName: "balanceOf",
      args: [this.cfg.wallet as Address],
    });
    return Number(raw) / 1_000_000;
  }

  // ── Live paths (wired per README — unified SDK v0.29) ───────────────────
  private async liveSnapshot(): Promise<MarketRow[]> {
    const exchange = this.sdk();
    await exchange.loadMarkets();
    const nowSec = Date.now() / 1000;
    const venue = this.cfg.venueId.toLowerCase();
    const rows: MarketRow[] = [];

    for (const um of Object.values(await exchange.fetchMarkets())) {
      if (um.type !== "binary") continue;
      const info = um.info as unknown as {
        venueId?: string | null; asset?: string | null; strike?: string | null;
        tradingStart?: string | null; expiry?: string | null;
        intervalSec?: string | null; status?: string | null;
      };
      if (!info.venueId || info.venueId.toLowerCase() !== venue) continue;

      const tradingStart = Number(info.tradingStart ?? 0);
      const expiry = Number(info.expiry ?? 0);
      const intervalSec = Number(info.intervalSec ?? Math.max(1, expiry - tradingStart));
      const closesAt = new Date((expiry || Date.now() / 1000) * 1000).toISOString();

      const yesRef = um.outcomes?.find((o) => o.label === "YES")?.symbol;
      const noRef = um.outcomes?.find((o) => o.label === "NO")?.symbol;
      if (!yesRef || !noRef) continue;

      // U17 resilience: a market that locks/expires mid-read reverts its book
      // call — skip it (mark status 0) instead of aborting the whole snapshot.
      let yesBook: Awaited<ReturnType<typeof exchange.fetchOrderBook>> | null = null;
      let noBook: Awaited<ReturnType<typeof exchange.fetchOrderBook>> | null = null;
      try {
        const books = await Promise.all([
          exchange.fetchOrderBook(yesRef, 10),
          exchange.fetchOrderBook(noRef, 10),
        ]);
        yesBook = books[0];
        noBook = books[1];
      } catch (bookErr) {
        console.error(`[relay] market ${um.symbol} book read failed (skipping): ${(bookErr as Error).message.slice(0, 200)}`);
        rows.push({
          marketId: um.id, symbol: um.symbol, asset: info.asset ?? um.base,
          strike: Number(info.strike ?? 0),
          intervalSec, closesAt,
          status: 0, up: { bid: 0, ask: 0, last: 0 }, down: { bid: 0, ask: 0, last: 0 },
          askDepth: 0,
        });
        continue;
      }
      const upBid = yesBook.bids[0]?.[0] ?? 0;
      const upAsk = yesBook.asks[0]?.[0] ?? 0;
      const downBid = noBook.bids[0]?.[0] ?? 0;
      const downAsk = noBook.asks[0]?.[0] ?? 0;
      const askDepth = yesBook.asks.reduce((s, l) => s + l[1], 0);

      const trading = tradingStart > 0 && expiry > 0 && nowSec >= tradingStart && nowSec < expiry;
      const status = trading
        ? 1
        : mapStatus(info.status ?? (nowSec >= expiry ? "Locked" : "Listed"));

      rows.push({
        marketId: um.id,
        symbol: um.symbol,
        asset: info.asset ?? um.base,
        strike: Number(info.strike ?? 0),
        intervalSec: Number(info.intervalSec ?? Math.max(1, expiry - tradingStart)),
        closesAt: new Date((expiry || Date.now() / 1000) * 1000).toISOString(),
        status,
        up: { bid: upBid, ask: upAsk, last: upBid || upAsk || 0.5 },
        down: { bid: downBid, ask: downAsk, last: downBid || downAsk || 0.5 },
        askDepth,
      });
    }
    return rows;
  }

  private async liveBroadcast(input: BroadcastInput): Promise<BroadcastResult> {
    // U17: DRY_RUN=1 means "never broadcast" even with a live-armed config.
    if (this.cfg.dryRun) {
      return { txHash: `stub_${Date.now()}`, raw: "dry-run — live path armed but DRY_RUN=1 (never broadcast)" };
    }
    const exchange = this.sdk();
    await exchange.loadMarkets();
    const um = Object.values(await exchange.fetchMarkets()).find(
      (m) => m.type === "binary" && m.id.toLowerCase() === input.marketId.toLowerCase(),
    );
    if (!um) throw new Error(`liveBroadcast: unknown market ${input.marketId}`);
    const label = input.side === "up" ? "YES" : "NO";
    const ref = um.outcomes?.find((o) => o.label === label)?.symbol;
    if (!ref) throw new Error(`liveBroadcast: no ${label} outcome on ${um.symbol}`);

    const book = await exchange.fetchOrderBook(ref, 5);
    const bestAsk = book.asks[0]?.[0] ?? 0.5;
    // Taker bounded at the current ask; SDK snaps price/qty to tick/lot grids
    // (replaces bot-kit ec-core quantize — the unified SDK is the maintained path).
    const order = await exchange.createOrder(ref, "limit", "buy", input.qty, bestAsk, {
      timeInForce: "IOC",
    });
    const txHash = order.txHash ?? order.id;
    return { txHash, raw: order.status };
  }
}

/** BinaryMarketStatus → relay int status. */
function mapStatus(s: string): number {
  switch (s) {
    case "Trading": return 1;
    case "Listed": return 0;
    case "Locked":
    case "Settling": return 2;
    case "Resolved": return 3;
    case "Voided": return 4;
    case "Finalized": return 5;
    default: return 0;
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