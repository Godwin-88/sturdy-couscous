/**
 * anchor.ts — evidence-chain Merkle-root anchor onto the EVM venue (U26).
 *
 * In DRY_RUN mode this logs the intent and returns a stub receipt — nothing is
 * published. In live mode it MUST go through viem (U16) to the ZKPassport /
 * UltraHonkVerifier contract family ported from stellcasp ethereum/contracts.
 */
import type { Web3RelayConfig } from "./config.js";
import { EvmAdapter } from "./evmAdapter.js";

export interface AnchorInput {
  root: string;       // sha256 hex of the daily decision-root
  cycleId: string;    // sha256(prev_root, nonce, regime)
}

export interface AnchorResult {
  ok: boolean;
  dryRun: boolean;
  txHash?: string;
  root: string;
  cycleId: string;
  reason?: string;
}

export const ANCHOR_NOT_WIRED =
  "viem anchor publish not wired in stub mode — wire writeZKPassportRoot() " +
  "via walletClient against Sepolia (see README 'Wire the live path')";

export class AnchorService {
  constructor(
    private readonly cfg: Web3RelayConfig,
    private readonly sdk: EvmAdapter,
  ) {}

  async publish(input: AnchorInput): Promise<AnchorResult> {
    if (this.cfg.dryRun || !this.sdk.isLive) {
      return {
        ok: true, dryRun: true, txHash: `stub_anchor_${Date.now()}`,
        root: input.root, cycleId: input.cycleId,
      };
    }
    return this.livePublish(input);
  }

  private async livePublish(_input: AnchorInput): Promise<AnchorResult> {
    // walletClient(privateKey, { chain: sepolia }) →
    //   write to WEB3_PASSPORT_CONTRACT with keccak(root, cycleId) (U16, RFC-6979)
    throw new Error(ANCHOR_NOT_WIRED);
  }
}