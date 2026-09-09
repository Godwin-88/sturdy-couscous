/**
 * cryptoHygiene.ts — U16 / C3 CI gate: signing MUST flow exclusively through
 * viem. This script fails the build if any relay source hand-rolls ECDSA
 * (raw sign, static k, non-RFC-6979 nonce, bespoke ABI).
 *
 * Run via: `npm run crypto-hygiene` (part of `npm test`).
 */
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";

const SRC = new URL("../src/", import.meta.url).pathname;

// Patterns that indicate a hand-rolled signing path (U16 forbid list).
const FORBIDDEN = [
  /\b(?:new\s+)?(?:secp256k1|ecrecover|ecsign|sign_?raw)\b/i,
  /\b(?:static|fixed|hardcoded)\s+.*\b(?:nonce|k)\s*[=:]\s*["']/i,
  /\bAbiCoder\b|\bencodeAbi\b|\bdecodeAbi\b/,
  /\bcreateTransaction\b.*\bsign(?:ature)?\b/i,
];

async function scan(dir: string): Promise<number> {
  let violations = 0;
  for (const entry of await readdir(dir)) {
    if (!entry.endsWith(".ts")) continue;
    if (entry === "cryptoHygiene.ts") continue; // the scanner may legitimately name the primitives
    const src = await readFile(join(dir, entry), "utf8");
    for (const re of FORBIDDEN) {
      if (re.test(src)) {
        violations += 1;
        console.log(`⚠  ${entry}: forbidden pattern ${re}`);
      }
    }
  }
  return violations;
}

const n = await scan(SRC);
if (n > 0) {
  console.error(`[crypto-hygiene] FAIL: ${n} forbidden signing pattern(s). Sign via viem only (U16).`);
  process.exit(1);
}
console.log("[crypto-hygiene] OK — no hand-rolled signing paths (U16).");