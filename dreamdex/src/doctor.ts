/**
 * doctor.ts — read-only sanity check (P9 §13 step 3; bot-kit parity).
 * Prints wallet, balances, live order book per market. No transactions.
 */
import { loadConfig } from "./config.js";
import { SdkAdapter } from "./sdkAdapter.js";

const cfg = loadConfig();
const sdk = new SdkAdapter(cfg);

console.log(`[doctor] network=${cfg.network} mode=${cfg.mode} dryRun=${cfg.dryRun}`);
console.log(`[doctor] wallet=${cfg.wallet.slice(0, 6)}… venueId=${cfg.venueId}`);
console.log(`[doctor] live-path=${sdk.isLive ? "LIVE (SDK)" : "STUB (no key / not live)"}`);

try {
  const b = await sdk.balances();
  const somi = (Number(b.somiWei) / 1e18).toFixed(4);
  const tusdc = (Number(b.tusdcRaw) / 1e6).toFixed(4);
  console.log(`[doctor] balances somi=${somi} tusdc=${tusdc}`);
  if (Number(b.tusdcRaw) === 0) console.log("[doctor] WARNING: tUSDC=0 — fund via npm run fund (or Simple Swap faucet) before ordering");
  if (Number(b.somiWei) < 2e15) console.log("[doctor] WARNING: SOMI gas low (<0.002) — top up from https://testnet.somnia.network");
} catch (e) {
  console.log(`[doctor] balances unavailable: ${(e as Error).message}`);
}

const rows = await sdk.snapshot();
if (rows.length === 0) {
  console.log("[doctor] no live markets (stub or empty venue)");
} else {
  for (const m of rows) {
    console.log(
      `[doctor] ${m.symbol} status=${m.status} up={${m.up.bid},${m.up.ask}} down={${m.down.bid},${m.down.ask}} depth=${m.askDepth}`,
    );
  }
}

if (!sdk.isLive) {
  console.log("\n[doctor] STUB MODE — nothing read from the chain. Set DREAMDEX_ENABLED=1,");
  console.log("[doctor] DREAMDEX_TRADING_MODE=live + a funded testnet key, then re-run.");
}