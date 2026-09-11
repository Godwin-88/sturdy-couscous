/**
 * fund.ts — one-command Somnia Shannon (50312) DreamDEX testnet funder.
 *
 * Mints testnet collateral (tUSDC) from the DreamDEX token faucet to the
 * wallet that owns SOMNIA_PRIVATE_KEY, then prints a live balance report.
 *
 * WHY THIS EXISTS / VERIFIED FACTS (from @somnia-chain/markets-sdk source +
 * live RPC reads, not chat sources):
 *   - Faucet is NOT a separate contract: the tUSDC token contract itself
 *     exposes `faucet(uint256 amount)` (sdk actionsAbi testUsdcAbi).
 *   - TestUSDC (tUSDC) on Shannon testnet = 0x70a86D8842FB63C4Ad2b7cdddF530eBf1BB25d8E
 *     (= sdk SOMNIA_TESTNET_ADDRESSES.collateral / .testUsdc). Verified live:
 *     symbol "tUSDC", decimals 6.
 *   - Gas trap: Somnia's gas schedule is far dearer than mainnet — even an
 *     ERC-20 approve can OOG under a 1M limit. The SDK uses a fixed 10,000,000
 *     gas ceiling and a 60 gwei maxFeePerGas ceiling (~0.6 SOMI envelope per
 *     write; unspent margin refunds). We mirror that exactly here.
 *   - A non-faucet `faucet` mint needs ~1 SOMI of gas headroom.
 *
 * USAGE (key stays local, never in chat):
 *   cd dreamdex
 *   cp .env.example .env          # set SOMNIA_PRIVATE_KEY (bot key) there
 *   npm run fund                  # mints 10,000 tUSDC (override: FAUCET_USD=50000)
 *
 * The script NEVER logs the private key. It only logs the derived address and
 * balances.
 */
import { createPublicClient, createWalletClient, http, parseAbi, formatUnits, type Address } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import "./env.js";

const RPC_URL = process.env.SOMNIA_RPC_URL ?? "https://dream-rpc.somnia.network";
const CHAIN_ID = 50312; // Somnia Shannon testnet (verified live: 0xc488)

// Verified on-chain values (Somnia Shannon testnet).
const TUSDC = "0x70a86D8842FB63C4Ad2b7cdddF530eBf1BB25d8E" as Address;
const TUSDC_DECIMALS = 6n; // verified live via decimals() == 0x06
const TUSDC_ABI = parseAbi([
  "function faucet(uint256 amount)",
  "function balanceOf(address owner) view returns (uint256)",
]);

// SDK-faithful gas discipline (see header). Fixed ceilings, never estimated.
const GAS_CEILING = 10_000_000n; // sdk DEFAULT_GAS
const MAX_FEE_PER_GAS = 60_000_000_000n; // 60 gwei ceiling (sdk DEFAULT_FEES)
const MAX_PRIORITY_FEE_PER_GAS = 0n;

const somniaShannon = {
  id: CHAIN_ID,
  name: "Somnia Shannon Testnet",
  network: "somnia-shannon",
  nativeCurrency: { name: "SOMI", symbol: "SOMI", decimals: 18 },
  rpcUrls: { default: { http: [RPC_URL] } },
} as const;

async function main(): Promise<void> {
  const key = process.env.SOMNIA_PRIVATE_KEY?.trim();
  if (!key) {
    console.error(
      "✗ SOMNIA_PRIVATE_KEY is not set.\n" +
        "  Set it in dreamdex/.env (cp .env.example .env, then edit). This is a " +
        "BOT-ONLY key — never commit it. The script never prints it."
    );
    process.exit(1);
  }

  const account = privateKeyToAccount(key as `0x${string}`);
  const address = account.address;

  const publicClient = createPublicClient({
    chain: somniaShannon,
    transport: http(RPC_URL, { timeout: 30_000 }),
  });
  const walletClient = createWalletClient({
    account,
    chain: somniaShannon,
    transport: http(RPC_URL, { timeout: 30_000 }),
  });

  // Parse the mint size in human tUSDC units (6dp).
  const raw = BigInt(Math.round(parseFloat(process.env.FAUCET_USD ?? "10000") * 10 ** Number(TUSDC_DECIMALS)));

  console.log(`Network : ${somniaShannon.name} (chain ${CHAIN_ID})`);
  console.log(`RPC     : ${RPC_URL}`);
  console.log(`Account : ${address}`);

  const somiBefore = await publicClient.getBalance({ address });
  const tusdcBefore = await publicClient.readContract({
    address: TUSDC,
    abi: TUSDC_ABI,
    functionName: "balanceOf",
    args: [address],
  });
  console.log(`Before  : tUSDC ${formatUnits(tusdcBefore, Number(TUSDC_DECIMALS))} | SOMI ${formatUnits(somiBefore, 18)}`);

  console.log(`Minting ${formatUnits(raw, Number(TUSDC_DECIMALS))} tUSDC via faucet()...`);
  const txHash = await walletClient.writeContract({
    address: TUSDC,
    abi: TUSDC_ABI,
    functionName: "faucet",
    args: [raw],
    gas: GAS_CEILING,
    maxFeePerGas: MAX_FEE_PER_GAS,
    maxPriorityFeePerGas: MAX_PRIORITY_FEE_PER_GAS,
  });
  console.log(`Tx      : ${txHash}`);

  const receipt = await publicClient.waitForTransactionReceipt({ hash: txHash, timeout: 120_000 });
  console.log(`Status  : ${receipt.status === "success" ? "SUCCESS ✓" : "REVERTED ✗"} (block ${receipt.blockNumber})`);

  if (receipt.status !== "success") {
    console.error("✗ Faucet mint reverted. Check gas/state. See explorer:");
    console.error(`  https://shannon-explorer.somnia.network/tx/${txHash}`);
    process.exit(2);
  }

  const somiAfter = await publicClient.getBalance({ address });
  const tusdcAfter = await publicClient.readContract({
    address: TUSDC,
    abi: TUSDC_ABI,
    functionName: "balanceOf",
    args: [address],
  });
  console.log(`After   : tUSDC ${formatUnits(tusdcAfter, Number(TUSDC_DECIMALS))} | SOMI ${formatUnits(somiAfter, 18)}`);
  console.log(`Explorer: https://shannon-explorer.somnia.network/address/${address}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
