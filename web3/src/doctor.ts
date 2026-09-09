/**
 * doctor.ts — read-only sanity check (P11 stage 7 step 3; stellcasp parity).
 * Prints wallet, contracts, live EVM rows per sector. No transactions.
 */
import { loadConfig } from "./config.js";
import { EvmAdapter } from "./evmAdapter.js";

const cfg = loadConfig();
const sdk = new EvmAdapter(cfg);

console.log(`[doctor] network=${cfg.network} chainId=${cfg.chainId} mode=${cfg.mode} dryRun=${cfg.dryRun}`);
console.log(`[doctor] wallet=${cfg.wallet.slice(0, 6) || "(none)"} passport=${cfg.passportContract} verifier=${cfg.verifierContract}`);
console.log(`[doctor] live-path=${sdk.isLive ? "LIVE (viem)" : "STUB (no key / not live)"}`);

const rows = await sdk.snapshot();
if (rows.length === 0) {
  console.log("[doctor] no live markets (stub or empty venue)");
} else {
  for (const m of rows) {
    console.log(
      `[doctor] [${m.sector}] ${m.symbol} status=${m.status} up={${m.up.bid},${m.up.ask}} down={${m.down.bid},${m.down.ask}} depth=${m.askDepth} edge=${m.edgePct} lev=${m.leverageX}`,
    );
  }
}

if (!sdk.isLive) {
  console.log("\n[doctor] STUB MODE — nothing read from the chain. Set WEB3_ENABLED=1,");
  console.log("[doctor] WEB3_TRADING_MODE=live + a funded Sepolia key, then re-run.");
}