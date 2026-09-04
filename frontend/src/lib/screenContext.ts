import type { OrderDraft, OptionSuggestion } from "@/lib/api";

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
  /** Optional: user-selected regime override (UI scenario playback) */
  regime?: string;
  /** Optional: crypto pair displayed (e.g. "BTC/USD") */
  pair?: string;
  /** Optional: a pre-filled order draft from the Financial Engineer chat */
  prefillDraft?: OrderDraft;
  /** Optional: free-form extra context (spot, dte, liquidity notes …) */
  extra?: Record<string, unknown>;
}

const store = new Map<string, ScreenContextData>();

export function setScreenContext(screen: string, data: Partial<ScreenContextData>): void {
  const merged = { screen, ...data };
  store.set(screen, merged);
  // Notify listeners (OptionsPanel consumes order drafts even when already mounted)
  window.dispatchEvent(new CustomEvent("ga-screen-context", { detail: { screen, data: merged } }));
}

export function getScreenContext(screen: string): ScreenContextData | undefined {
  return store.get(screen);
}

// ── One-shot order-draft handoff (survives store overwrites / navigation remounts) ──
let pendingOrderDraft: { screen: string; draft: OptionSuggestion; underlying?: string } | null = null;
export function queueOrderDraft(screen: string, draft: OptionSuggestion, underlying?: string): void {
  pendingOrderDraft = { screen, draft, underlying };
}
export function takeOrderDraft(screen: string): { draft: OptionSuggestion; underlying?: string } | null {
  if (!pendingOrderDraft || pendingOrderDraft.screen !== screen) return null;
  const out = pendingOrderDraft;
  pendingOrderDraft = null;
  return out;
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