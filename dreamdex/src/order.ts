/**
 * order.ts — Checks-Effects-Interactions state machine for EC orders (U2, M2).
 *
 *   Check   → market is Trading (on-chain), qty in bounds, ask-depth sane
 *   Effect  → stage the intent (idempotent), NEVER before Check passes
 *   Interact→ broadcast (dry-run in paper mode)
 *   Confirm → record fill/revert ONLY after broadcast returns
 *
 * Three-nonce taxonomy (U16/C3) documented here:
 *   (1) tx account nonce  — sequential per-key replay protection
 *   (2) ECDSA k           — RFC-6979 deterministic, handled by viem
 *   (3) intentId          — the idempotency key below (sha256 of the order)
 */
import { createHash } from "node:crypto";
import type { RelayConfig } from "./config.js";
import { SdkAdapter, type MarketRow, type BroadcastResult } from "./sdkAdapter.js";
import { FillsLedger } from "./fills.js";

export interface OrderInput {
  marketId: string;
  side: "up" | "down";
  qty: number;
  gasBumpPct?: number; // U3 default 0 (claims may bump, orders rarely)
}

export interface OrderResult {
  ok: boolean;
  intentId: string;
  symbol?: string;
  side: "up" | "down";
  qty: number;
  estPrice: number;
  dryRun: boolean;
  txHash?: string;
  state: string;
  reason?: string;
}

const MAX_QTY = 10_000;

export class OrderService {
  constructor(
    private readonly cfg: RelayConfig,
    private readonly sdk: SdkAdapter,
    private readonly fills: FillsLedger,
  ) {}

  intentIdOf(input: OrderInput): string {
    const raw = `${input.marketId}|${input.side}|${input.qty}|${this.cfg.wallet}`;
    return createHash("sha256").update(raw).digest("hex").slice(0, 32);
  }

  async place(input: OrderInput): Promise<OrderResult> {
    const intentId = this.intentIdOf(input);

    // ── Check ─────────────────────────────────────────────────────────────
    if (input.qty < 1 || input.qty > MAX_QTY) {
      return { ok: false, intentId, side: input.side, qty: input.qty, estPrice: 0,
               dryRun: this.cfg.dryRun, state: "rejected", reason: "qty out of bounds" };
    }
    const rows = await this.sdk.snapshot();
    const market = rows.find((r) => r.marketId === input.marketId);
    if (!market) {
      return { ok: false, intentId, side: input.side, qty: input.qty, estPrice: 0,
               dryRun: this.cfg.dryRun, state: "rejected", reason: "unknown market" };
    }
    if (market.status !== 1) {
      this.fills.recordRejection(market, input.side, input.qty, `market status ${market.status}`);
      return { ok: false, intentId, side: input.side, qty: input.qty, estPrice: 0,
               dryRun: this.cfg.dryRun, state: "rejected", reason: `market status ${market.status}` };
    }
    if (market.askDepth < 1) {
      this.fills.recordRejection(market, input.side, input.qty, "ask-depth too shallow (U11)");
      return { ok: false, intentId, side: input.side, qty: input.qty, estPrice: 0,
               dryRun: this.cfg.dryRun, state: "rejected", reason: "ask-depth too shallow (U11)" };
    }

    // stale-row guard: prefer a fresh on-chain gate (M4: authoritative state)
    if (!(await this.sdk.acceptsOrders(input.marketId))) {
      const gate = (await this.sdk.snapshot()).find((r) => r.marketId === input.marketId);
      const why = gate ? `not Trading on-chain (status ${gate.status})` : "market not found on chain";
      this.fills.recordRejection(market, input.side, input.qty, why);
      return { ok: false, intentId, side: input.side, qty: input.qty, estPrice: 0,
               dryRun: this.cfg.dryRun, state: "rejected", reason: why };
    }

    // ── Effect (persist intent before any external call) ───────────────────
    const fill = this.fills.stage(intentId, market, input.side, input.qty);
    const estPrice = fill.estPrice;

    // ── Interact (broadcast; dry-run in paper mode) ────────────────────────
    let res: BroadcastResult;
    try {
      res = await this.sdk.broadcast({
        marketId: input.marketId, side: input.side, qty: input.qty,
        gasBumpPct: input.gasBumpPct ?? 0,
      });
    } catch (e) {
      // On-chain revert verdicts (OrderAlreadyExpired, ImmediateOrCancelNoFill, …)
      // are recorded as visible rejections, never thrown as a silent crash.
      const msg = e instanceof Error ? e.message : String(e);
      this.fills.revertFill(intentId, msg);
      return { ok: false, intentId, symbol: market.symbol, side: input.side, qty: input.qty,
               estPrice, dryRun: this.cfg.dryRun, state: "rejected", reason: msg };
    }

    // ── Confirm (state ONLY after broadcast returns/reverts) ───────────────
    if (res.txHash.startsWith("stub_") && this.cfg.dryRun) {
      this.fills.confirmFill(intentId, res.txHash, estPrice);
      return { ok: true, intentId, symbol: market.symbol, side: input.side, qty: input.qty,
               estPrice, dryRun: true, txHash: res.txHash, state: "filled" };
    }
    // live path would catch revert here and call fills.revertFill(...)
    this.fills.confirmFill(intentId, res.txHash, estPrice);
    return { ok: true, intentId, symbol: market.symbol, side: input.side, qty: input.qty,
             estPrice, dryRun: false, txHash: res.txHash, state: "filled" };
  }
}