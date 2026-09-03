import type { OrderDraft } from "@/lib/api";

/**
 * Live "page session context" shared between screen components and the
 * Financial Engineer chat. Components publish what the user is currently
 * looking at (e.g. the Options panel publishes the selected underlying/
 * expiry/strike); the chat reads it so the agent anchors on the same data.
 */

export interface ScreenContextData {
  /** Current screen id (options / dashboard / signals / …) */
  screen: string;
  /** Optional: underlying asset actually on screen (MCHP, SPY, QQQ …) */
  underlying?: string;
  /** Optional: selected expiry (ISO date) */
  expiration?: string;
  /** Optional: call | put */
  contract_type?: "call" | "put";
  /** Optional: full selected contract symbol (e.g. MCHP260913C00085000) */
  contract_symbol?: string;
  /** Optional: selected strike */
  strike?: number;
  /** Optional: loss-aversion lens */
  lens?: "average" | "defensive";
  /** Optional: a pre-filled order draft from the Financial Engineer chat */
  prefillDraft?: OrderDraft;
  /** Optional: free-form extra context (spot, dte, liquidity notes …) */
  extra?: Record<string, unknown>;
}

const store = new Map<string, ScreenContextData>();

export function setScreenContext(screen: string, data: Partial<ScreenContextData>): void {
  store.set(screen, { screen, ...data });
}

export function getScreenContext(screen: string): ScreenContextData | undefined {
  return store.get(screen);
}

/** Short human label for the chip, e.g. "Analyzing: MCHP · 2026-09-04 calls · strike 85.00" */
export function screenContextLabel(ctx: ScreenContextData | undefined): string {
  if (!ctx) return "";
  const parts: string[] = [ctx.underlying || ""];
  if (ctx.expiration) parts.push(ctx.expiration);
  if (ctx.contract_type) parts.push(ctx.contract_type + (ctx.strike != null ? " " : ""));
  if (ctx.strike != null) parts.push(`strike ${ctx.strike}`);
  return parts.filter(Boolean).join(" · ");
}