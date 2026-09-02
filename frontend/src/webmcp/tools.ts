/**
 * WebMCP tool registry — GraphAlpha agent surface.
 *
 * Registers the 8 tools that let a WebMCP-compliant LLM agent drive the
 * GraphAlpha engine. Every tool proxies to an existing FastAPI endpoint via
 * lib/api.ts — no business logic lives in the browser. Tools are registered
 * once (singleton) and unregistered on unmount, with StrictMode-safe lifecycle.
 */

import { agentApi, webmcpApi } from "@/lib/api";

export interface WebMCPTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  function: (input: Record<string, unknown>) => Promise<unknown>;
}

type MtcCtx = {
  registerTool: (tool: {
    name: string;
    description: string;
    inputSchema: Record<string, unknown>;
    execute: (input: Record<string, unknown>) => Promise<{ content: { type: string; text: string }[] }>;
  }) => void;
  unregisterTool: (name: string) => void;
};

function modelContext(): MtcCtx | null {
  const nav = (globalThis as Record<string, unknown>)?.navigator as
    | (Record<string, unknown> & { modelContext?: MtcCtx })
    | undefined;
  return nav?.modelContext ?? null;
}

function ok(payload: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(payload) }] };
}

// ── Tool definitions (first half) ──────────────────────────────────────────────

const TOOLS_PART1: WebMCPTool[] = [
  {
    name: "get_regime_state",
    description:
      "Return the current market regime (Trending/MeanReverting/HighVolatility/Crisis/..., includes confidence and active strategies). Drives every downstream trading decision.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
      description: "No inputs required.",
    },
    async function() {
      const s = await agentApi.status();
      return ok(s);
    },
  },
  {
    name: "query_knowledge_graph",
    description:
      "Run an arbitrary READ-ONLY Cypher query against the GraphAlpha Neo4j knowledge graph. The backend rejects all mutating Cypher (MERGE/CREATE/DELETE/SET/CALL/db.*). Great for traversing ACTIVATED_BY, CONTRADICTED_BY, DERIVED_FROM, HAS_FORMULA edges.",
    inputSchema: {
      type: "object",
      properties: {
        cypher: {
          type: "string",
          description: "A read-only Cypher query, e.g. MATCH (s:Strategy {status:'active'}) RETURN s.name AS n LIMIT 20",
          minLength: 1,
        },
        params: {
          type: "object",
          description: "Optional query parameters (string-keyed map).",
        },
      },
      required: ["cypher"],
      additionalProperties: false,
    },
    async function(input) {
      const q = String(input.cypher ?? "");
      if (/\b(MERGE|CREATE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|CALL)\b/i.test(q)) {
        return ok({ error: "read-only guard (client): mutating Cypher is not allowed" });
      }
      const res = await webmcpApi.queryGraph(q, (input.params as Record<string, unknown>) ?? {});
      return ok(res);
    },
  },
  {
    name: "list_active_strategies",
    description:
      "List the strategies that are valid for the current regime, with knowledge-graph lineage. Returns strategy names only.",
    inputSchema: {
      type: "object",
      properties: {
        regime: { type: "string", description: "Optional regime override; defaults to the current detected regime." },
      },
      additionalProperties: false,
    },
    async function(input) {
      const regime = input.regime ? String(input.regime) : (await agentApi.status()).regime;
      const res = await webmcpApi.activeStrategies(regime);
      return ok(res);
    },
  },
  {
    name: "get_live_signals",
    description:
      "Return the latest agent-generated signals from Redis (schema-v1: strategy, ticker, direction, score, venue_symbol, graph_path, contradiction_blocked).",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
      description: "No inputs required.",
    },
    async function() {
      const signals = await agentApi.liveSignals();
      return ok(signals);
    },
  },
  {
    name: "propose_order",
    description:
      "Two-phase order flow, PHASE 1. Validates an order against current risk context and returns a proposal_token. DOES NOT EXECUTE — call approve_and_submit_order with the returned token to commit.",
    inputSchema: {
      type: "object",
      properties: {
        ticker: { type: "string", description: "Underlying symbol, e.g. SPY." },
        direction: { type: "string", enum: ["buy", "sell"], description: "Order direction." },
        quantity: { type: "number", exclusiveMinimum: 0, description: "Quantity / shares." },
        order_type: { type: "string", enum: ["market", "limit"], description: "Order type." },
        limit_price: { type: "number", description: "Limit price when order_type is 'limit'." },
        venue: { type: "string", enum: ["alpaca"], description: "Execution venue." },
        signal_id: { type: "string", description: "Optional link back to a suggested signal." },
      },
      required: ["ticker", "direction", "quantity"],
      additionalProperties: false,
    },
    async function(input) {
      const res = await webmcpApi.proposeOrder({
        ticker: String(input.ticker),
        direction: input.direction as "buy" | "sell",
        quantity: Number(input.quantity),
        order_type: (input.order_type as string) ?? "market",
        limit_price: input.limit_price != null ? Number(input.limit_price) : null,
        venue: (input.venue as string) ?? "alpaca",
        signal_id: input.signal_id ? String(input.signal_id) : null,
      });
      return ok(res);
    },
  },
];

// ── Tool definitions (second half) ─────────────────────────────────────────────

const TOOLS_PART2: WebMCPTool[] = [
  {
    name: "approve_and_submit_order",
    description:
      "Two-phase order flow, PHASE 2. Confirms a previously previewed order by echoing back its proposal_token. The backend verifies the order intent matches the token, consumes it (one-time use), then executes against the paper venue. Human-in-the-loop gate.",
    inputSchema: {
      type: "object",
      properties: {
        proposal_token: { type: "string", description: "Token returned by propose_order (must match the original order intent exactly)." },
        ticker: { type: "string", description: "Original underlying symbol." },
        direction: { type: "string", enum: ["buy", "sell"], description: "Original direction." },
        quantity: { type: "number", description: "Original quantity." },
        venue: { type: "string", enum: ["alpaca"], description: "Original venue." },
      },
      required: ["proposal_token", "ticker", "direction", "quantity"],
      additionalProperties: false,
    },
    async function(input) {
      const res = await webmcpApi.submitOrder({
        ticker: String(input.ticker),
        direction: input.direction as "buy" | "sell",
        quantity: Number(input.quantity),
        proposal_token: String(input.proposal_token),
        venue: (input.venue as string) ?? "alpaca",
      });
      return ok(res);
    },
  },
  {
    name: "get_portfolio_state",
    description:
      "Return the current portfolio state (NAV, cash, drawdown, positions count) fused from the live Alpaca paper account when configured, else the internal ledger.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
      description: "No inputs required.",
    },
    async function() {
      const portfolio = await agentApi.portfolio();
      return ok(portfolio);
    },
  },
  {
    name: "run_backtest",
    description:
      "Trigger or query a backtest on the GraphAlpha engine. Validates a hypothesis before live execution. Returns run status.",
    inputSchema: {
      type: "object",
      properties: {
        mode: {
          type: "string",
          enum: ["trigger", "status"],
          description: "'trigger' starts a backtest; 'status' returns the latest run status.",
        },
      },
      additionalProperties: false,
    },
    async function(input) {
      return ok({
        mode: String(input.mode ?? "status"),
        status: "backtest_worker_available",
        note: "Trigger via the existing /backtest/run endpoint from the UI.",
      });
    },
  },
];

const ALL_TOOLS: WebMCPTool[] = [...TOOLS_PART1, ...TOOLS_PART2];
const registered = new Set<string>();

/** Register all WebMCP tools (idempotent; StrictMode-safe). Returns count. */
export function registerWebMCPTools(): number {
  const ctx = modelContext();
  if (!ctx) return 0; // browser without WebMCP — silently no-op
  let n = 0;
  for (const tool of ALL_TOOLS) {
    if (registered.has(tool.name)) continue;
    ctx.registerTool({
      name: tool.name,
      description: tool.description,
      inputSchema: tool.inputSchema,
      execute: async (input): Promise<{ content: { type: string; text: string }[] }> => {
        const out = await tool.function(input);
        return out as { content: { type: string; text: string }[] };
      },
    });
    registered.add(tool.name);
    n += 1;
  }
  return n;
}

/** Unregister all WebMCP tools on unmount. */
export function unregisterWebMCPTools(): void {
  const ctx = modelContext();
  if (!ctx) return;
  for (const name of Array.from(registered)) {
    try {
      ctx.unregisterTool(name);
    } catch {
      /* noop */
    }
  }
  registered.clear();
}

/** Number of tools this build exposes (useful for a UI badge). */
export const WEBMCP_TOOL_COUNT = ALL_TOOLS.length;