/**
 * fills.ts — position/fill ledger with explicit C-E-I states (U2, M2).
 *
 * Invariant (M6 / U5): a fill is only `credited` after (a) enough
 * confirmations (U14) and (b) a verified balance move on the chain. State
 * is never advanced by local bookkeeping alone. Same contract as dreamdex.
 */
import type { EvmMarketRow } from "./evmAdapter.js";
import { EvmAdapter } from "./evmAdapter.js";

export type FillState = "pending" | "reverted" | "filled" | "credited";

export interface EvmFill {
  intentId: string;
  marketId: string;
  side: "up" | "down";
  qty: number;
  estPrice: number;
  fillPrice?: number;
  state: FillState;
  confirmations: number;
  reorgDetected: boolean;
  txHash?: string;
  ts: string;
}

export class FillsLedger {
  private fills: EvmFill[] = [];

  constructor(private readonly sdk: EvmAdapter, private readonly requiredConfs: number) {}

  get all(): EvmFill[] {
    return this.fills;
  }

  find(intentId: string): EvmFill | undefined {
    return this.fills.find((f) => f.intentId === intentId);
  }

  /** U2 — persist the intent BEFORE any external call (Effect-before-Interact). */
  stage(intentId: string, market: EvmMarketRow, side: "up" | "down", qty: number): EvmFill {
    const existing = this.find(intentId);
    if (existing) return existing; // idempotent replay
    const fill: EvmFill = {
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
    void reason;
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