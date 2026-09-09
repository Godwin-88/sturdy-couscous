/**
 * order.ts — Checks-Effects-Interactions state machine for EVM DeFi orders (U2, M2).
 *
 *   Check   → sector gate (D1–D4) passes, market status=1, qty in bounds,
 *             edge/threshold met (fee−IL−gas ≥ MIN_LP_EDGE_PCT, etc.), leverage cap
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
import type { Web3RelayConfig } from "./config.js";
import { EvmAdapter, type EvmMarketRow } from "./evmAdapter.js";
import { FillsLedger } from "./fills.js";

export interface OrderInput {
  marketId: string;
  side: "up" | "down";
  qty: number;
  gasBumpPct?: number; // U3 default 0
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
    private readonly cfg: Web3RelayConfig,
    private readonly sdk: EvmAdapter,
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
      return { ok: false, intentId, side: input.side, qty: input.qty, estPrice: 0,
               dryRun: this.cfg.dryRun, state: "rejected", reason: `market status ${market.status}` };
    }
    if (market.askDepth < 1) {
      return { ok: false, intentId, side: input.side, qty: input.qty, estPrice: 0,
               dryRun: this.cfg.dryRun, state: "rejected", reason: "ask-depth too shallow (U11)" };
    }
    // Sector-specific edge / leverage gates (D1–D4):
    const gate = this.sectorGate(market);
    if (!gate.ok) {
      return { ok: false, intentId, side: input.side, qty: input.qty, estPrice: 0,
               dryRun: this.cfg.dryRun, state: "rejected", reason: gate.reason };
    }
    if (!(await this.sdk.acceptsOrders(input.marketId))) {
      return { ok: false, intentId, side: input.side, qty: input.qty, estPrice: 0,
               dryRun: this.cfg.dryRun, state: "rejected", reason: "not Trading on-chain" };
    }

    // ── Effect (persist intent before any external call) ───────────────────
    const fill = this.fills.stage(intentId, market, input.side, input.qty);
    const estPrice = fill.estPrice;

    // ── Interact (broadcast; dry-run in paper mode) ────────────────────────
    const res = await this.sdk.broadcast({
      marketId: input.marketId, side: input.side, qty: input.qty,
      gasBumpPct: input.gasBumpPct ?? 0,
    });

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

  private sectorGate(market: EvmMarketRow): { ok: boolean; reason?: string } {
    switch (market.sector) {
      case "amm_lp":
        if (market.edgePct < this.cfg.minLpEdgePct) {
          return { ok: false, reason: `D1 edge ${market.edgePct} < MIN_LP_EDGE_PCT ${this.cfg.minLpEdgePct}` };
        }
        return { ok: true };
      case "lending":
        if (market.edgePct < this.cfg.minLendingSpreadPct) {
          return { ok: false, reason: `D2 spread ${market.edgePct} < MIN_LENDING_SPREAD_PCT ${this.cfg.minLendingSpreadPct}` };
        }
        return { ok: true };
      case "yield":
        if (market.leverageX > this.cfg.maxLeverageX) {
          return { ok: false, reason: `D3 leverage ${market.leverageX} > MAX_LEVERAGE_X ${this.cfg.maxLeverageX}` };
        }
        return { ok: true };
      case "perp":
        if (Math.abs(market.edgePct) < this.cfg.minFundingCarryPct) {
          return { ok: false, reason: `D4 |carry| ${Math.abs(market.edgePct)} < MIN_FUNDING_CARRY_PCT ${this.cfg.minFundingCarryPct}` };
        }
        return { ok: true };
      default:
        return { ok: false, reason: "unknown sector" };
    }
  }
}