/**
 * claim.ts — settlement claim via the withdrawal pattern (U2/M3) with a
 * confirmation-count gate (U14/C1).
 *
 * The relay is the caller: it pulls the claim for itself. `claimed=true`
 * is recorded ONLY after the crediting tx is deep enough (no zero-conf
 * crediting — Bolfing §6.8) and the wallet balance actually rose (M6).
 * Gas is a liveness lever (U3): claims resubmit with an increasing bump.
 */
import type { RelayConfig } from "./config.js";
import { SdkAdapter } from "./sdkAdapter.js";
import { FillsLedger } from "./fills.js";

export interface ClaimResult {
  ok: boolean;
  intentId: string;
  claimed: boolean;
  reason: string;
  confirmations: number;
  txHash?: string;
}

export class ClaimService {
  constructor(
    private readonly cfg: RelayConfig,
    private readonly sdk: SdkAdapter,
    private readonly fills: FillsLedger,
    private readonly balanceReader: () => Promise<number>,
  ) {}

  /** Poll every open fill and credit those that are deep + funded. */
  async sweep(): Promise<ClaimResult[]> {
    const out: ClaimResult[] = [];
    for (const f of this.fills.all) {
      if (f.state !== "filled") continue;
      const before = await this.balanceReader();
      // would-be claim tx: gas bumped per U3, confirmations resolved in fills.maybeCredit
      const res = await this.sdk.broadcast({
        marketId: f.marketId, side: f.side, qty: f.qty,
        gasBumpPct: 20, // U3: CLAIM_GAS_BUMP_PCT
      });
      const after = await this.balanceReader();
      const credited = await this.fills.maybeCredit(f.intentId, before, after);
      out.push({
        ok: true,
        intentId: f.intentId,
        claimed: credited,
        confirmations: f.confirmations,
        txHash: res.txHash,
        reason: credited
          ? "credited (confirmations met + balance moved)"
          : `pending (conf ${f.confirmations}/${this.cfg.requiredConfirmations}` +
            `${f.reorgDetected ? ", reorg detected" : ""})`,
      });
    }
    return out;
  }
}