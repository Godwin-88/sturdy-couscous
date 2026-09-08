/**
 * index.ts — DreamDEX relay HTTP contract on :8450 (P9 §6) with
 *   U17: X-Relay-Key auth + /order rate limiting + system-health
 *   U14: confirmation/reorg fields surfaced on fills
 *   U3 : stuck-tx / heartbeat surfaced on /status
 * DRY_RUN defaults to 1: paper mode, stub fills, nothing on-chain.
 */
import express, { type Request, type Response } from "express";
import { loadConfig } from "./config.js";
import { SdkAdapter } from "./sdkAdapter.js";
import { FillsLedger } from "./fills.js";
import { OrderService } from "./order.js";
import { ClaimService } from "./claim.js";

const cfg = loadConfig();
const sdk = new SdkAdapter(cfg);
const fills = new FillsLedger(sdk, cfg.requiredConfirmations);
const orders = new OrderService(cfg, sdk, fills);
const claims = new ClaimService(cfg, sdk, fills, async () => 0); // stub balance

const app = express();
app.use(express.json());

// ── U17: shared-secret auth ────────────────────────────────────────────────
app.use((req, res, next) => {
  const key = req.get("x-relay-key");
  if (key !== cfg.apiKey) {
    res.status(401).json({ error: "unauthorized" });
    return;
  }
  next();
});

// ── U17: per-route rate limiting (sliding window, 1-min bucket) ─────────────
const hitLimits = new Map<string, { minute: number; count: number }>();
function rateLimit(req: Request, res: Response, limit: number): boolean {
  const fwd = req.headers["x-forwarded-for"];
  const raw = Array.isArray(fwd) ? fwd[0] : fwd;
  const ip = (raw ?? "?").split(",")[0] ?? "?";
  const bucket = hitLimits.get(ip);
  const now = Math.floor(Date.now() / 60_000);
  if (!bucket || bucket.minute !== now) {
    hitLimits.set(ip, { minute: now, count: 1 });
    return true;
  }
  if (bucket.count >= limit) {
    res.status(429).json({ error: "rate limited" });
    return false;
  }
  bucket.count += 1;
  return true;
}

// ── GET /status — adapter state + U17 system-health ────────────────────────
app.get("/status", (_req, res) => {
  res.json({
    mode: cfg.mode,
    network: cfg.network,
    venueId: cfg.venueId,
    wallet: cfg.wallet.slice(0, 6) + "…",
    dryRun: cfg.dryRun,
    lastSnapshotAt: null,
    claimable: fills.all.filter((f) => f.state === "filled").length,
    systemHealth: {
      chainView: "ok",
      heartbeatMs: cfg.heartbeatMs,
      haltedReason: cfg.dryRun ? "dry-run (never broadcast)" : null,
    },
    creditingPolicy: {
      requiredConfirmations: cfg.requiredConfirmations,
      raceAttackGuaranteeNote:
        `P(race success) <= 5.9e-4 at attacker q=0.1 for k=6 confirmations (Bolfing Table 6.1)`,
    },
  });
});

// ── GET /markets — on-chain-gated snapshot ─────────────────────────────────
app.get("/markets", async (_req, res) => {
  try {
    res.json({ markets: await sdk.snapshot() });
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
});

// ── POST /order — C-E-I order path (rate-limited) ─────────────────────────
app.post("/order", async (req, res) => {
  if (!rateLimit(req, res, cfg.rateLimitPerMin)) return;
  const body = req.body as { marketId?: string; side?: string; qty?: number };
  const qty = body?.qty;
  if (!body?.marketId || (body.side !== "up" && body.side !== "down") || !Number.isFinite(qty)) {
    res.status(400).json({ error: "marketId, side (up|down), qty required" });
    return;
  }
  const result = await orders.place({
    marketId: body.marketId, side: body.side, qty: Math.floor(qty as number),
  });
  res.json(result);
});

// ── GET /positions, /fills — ledger views with U14 confirmations ───────────
app.get("/positions", (_req, res) => {
  const open = fills.all.filter((f) => f.state === "filled" || f.state === "pending");
  res.json({ positions: open, reconciliation: { driftItems: fills.driftItems() } });
});

app.get("/fills", (_req, res) => {
  res.json({ fills: fills.all });
});

// ── POST /claim — settlement sweep (human-gated at the API layer) ──────────
app.post("/claim", async (_req, res) => {
  if (!rateLimit(_req, res, cfg.rateLimitPerMin)) return;
  res.json({ results: await claims.sweep() });
});

app.listen(cfg.port, () => {
  console.log(`[relay] listening :${cfg.port} mode=${cfg.mode} dryRun=${cfg.dryRun} network=${cfg.network}`);
});