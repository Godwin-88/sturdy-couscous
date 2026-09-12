/**
 * fills.ts — position/fill ledger with explicit C-E-I states (U2, M2).
 *
 * Invariant (M6 / U5): a fill is only `credited` after (a) enough
 * confirmations (U14) and (b) a verified balance move on the chain. State
 * is never advanced by local bookkeeping alone.
 */
import type { MarketRow } from "./sdkAdapter.js";
import { SdkAdapter } from "./sdkAdapter.js";

export type FillState = "pending" | "reverted" | "filled" | "credited" | "rejected";

export interface Fill {
  intentId: string;
  marketId: string;
  marketSymbol?: string;
  side: "up" | "down";
  qty: number;
  estPrice: number;
  fillPrice?: number;
  state: FillState;
  confirmations: number;
  reorgDetected: boolean;
  txHash?: string;
  reason?: string;
  ts: string;
}

export class FillsLedger {
  private fills: Fill[] = [];

  constructor(private readonly sdk: SdkAdapter, private readonly requiredConfs: number) {}

  get all(): Fill[] {
    return this.fills;
  }

  find(intentId: string): Fill | undefined {
    return this.fills.find((f) => f.intentId === intentId);
  }

  /** U2 — persist the intent BEFORE any external call (Effect-before-Interact). */
  stage(intentId: string, market: MarketRow, side: "up" | "down", qty: number): Fill {
    const existing = this.find(intentId);
    if (existing) return existing; // idempotent replay
    const fill: Fill = {
      intentId, marketId: market.marketId, side, qty,
      estPrice: side === "up" ? market.up.ask : market.down.ask,
      state: "pending", confirmations: 0, reorgDetected: false,
      ts: new Date().toISOString(),
    };
    this.fills.push(fill);
    return fill;
  }

  /** U2 — called only AFTER broadcast returns successfully (Interact → Confirm). */
  confirmFill(intentId: string, txHash: string, fillPrice: number): void {
    const f = this.find(intentId);
    if (!f || f.state !== "pending") return;
    f.txHash = txHash;
    f.fillPrice = fillPrice;
    f.state = "filled";
  }

  revertFill(intentId: string, reason: string): void {
    const f = this.find(intentId);
    if (!f || f.state !== "pending") return;
    f.state = "reverted";
    f.reason = reason;
  }

  /**
   * Record a rejection / revert that never produced a fill. Gives the UI a
   * visible trail for on-chain verdicts (OrderAlreadyExpired, IOC no-fill, …)
   * so a failed attempt is never silent (U5: reconcile, show the outcome).
   */
  recordRejection(market: MarketRow, side: "up" | "down", qty: number, reason: string, estPrice?: number): void {
    this.fills.push({
      intentId: `rej_${Date.now()}_${this.fills.length}`,
      marketId: market.marketId,
      marketSymbol: market.symbol,
      side, qty,
      estPrice: estPrice ?? (side === "up" ? market.up.ask : market.down.ask),
      state: "rejected",
      confirmations: 0, reorgDetected: false,
      reason,
      ts: new Date().toISOString(),
    });
  }

  /**
   * U14 + U5 — poll confirmations; only then credit. Returns true when the
   * fill transitioned to `credited` this call.
   */
  async maybeCredit(intentId: string, balanceBefore: number, balanceAfter: number): Promise<boolean> {
    const f = this.find(intentId);
    if (!f || f.state !== "filled") return false;

    const txs = f.txHash ? [f.txHash] : [];
    let confs = 0;
    let reorg = false;
    for (const tx of txs) {
      const c = await this.sdk.confirmationsOf(tx);
      if (c === 0 && confs > 0) reorg = true; // authoritative height regressed (fork)
      confs = Math.max(confs, c);
    }
    f.confirmations = confs;
    f.reorgDetected = reorg;

    // Safety over liveness (U17): a reorg or insufficient depth never credits.
    if (reorg || confs < this.requiredConfs) return false;
    // M6: verify the funds actually moved before crediting.
    if (balanceAfter <= balanceBefore) return false;
    f.state = "credited";
    return true;
  }

  /** U5 — reconciliation drift: chain position view vs local ledger. */
  driftItems(): string[] {
    const out: string[] = [];
    for (const f of this.fills) {
      if (f.state === "pending") out.push(`pending ${f.intentId}`);
      if (f.state === "filled" && f.confirmations < this.requiredConfs) {
        out.push(`unconfirmed ${f.intentId} (${f.confirmations}/${this.requiredConfs})`);
      }
    }
    return out;
  }
}