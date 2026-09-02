/**
 * AgentCoPilot — the "agent + human" dual-mode surface.
 *
 * This is the WebMCP counterpart to ScreenChat: it shows the human what an
 * LLM agent is doing via /ws/events (`tool_invocation` events) and lets them
 * approve a two-phase proposed order with a single click. It reuses the
 * existing useWebSocket hook + api.ts surfaces; no new service code.
 */
import { useMemo, useState } from "react";
import clsx from "clsx";
import { Bot, ShieldCheck, X, Loader2, CheckCircle2 } from "lucide-react";

import { WS_BASE, webmcpApi } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";

interface ToolInvocation {
  type?: string;
  tool?: string;
  name?: string;
  input?: Record<string, unknown>;
  output?: unknown;
  at?: string;
  proposal_token?: string;
}

interface AgentEvent {
  type: string;
  [k: string]: unknown;
}

function eventText(ev: ToolInvocation): string {
  const tool = String(ev.tool ?? ev.name ?? "unknown_tool");
  const input = ev.input ? `\n  input: ${JSON.stringify(ev.input)}` : "";
  const out = ev.output ? `\n  output: ${JSON.stringify(ev.output).slice(0, 600)}` : "";
  return `tool_invocation · ${tool}${input}${out}`;
}

export default function AgentCoPilot({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { messages } = useWebSocket<AgentEvent>(`${WS_BASE}/ws/events`);

  // Filter to tool_invocation events
  const invocations = useMemo(
    () =>
      messages
        .filter((m) => (m.type ?? "").toString().toLowerCase().includes("tool"))
        .slice(0, 40) as ToolInvocation[],
    [messages]
  );

  const [approving, setApproving] = useState(false);
  const [approveMsg, setApproveMsg] = useState<string | null>(null);
  const [approveErr, setApproveErr] = useState<string | null>(null);

  if (!open) return null;

  async function approve(ev: ToolInvocation) {
    const input = ev.input as Record<string, unknown> | undefined;
    if (!ev.proposal_token && !(ev.output as Record<string, unknown>)?.proposal_token) {
      setApproveErr("No proposal_token on this event — can't approve directly.");
      return;
    }
    const token = ev.proposal_token ?? (ev.output as Record<string, unknown>)?.proposal_token;
    const ticker = String(input?.ticker ?? "");
    const direction = (input?.direction ?? "buy") as "buy" | "sell";
    const quantity = Number(input?.quantity ?? 1);
    setApproving(true);
    setApproveMsg(null);
    setApproveErr(null);
    try {
      const res = await webmcpApi.submitOrder({
        ticker,
        direction,
        quantity,
        proposal_token: String(token),
        venue: (input?.venue as string) ?? "alpaca",
      });
      setApproveMsg(`Order ${res.order_id} ${res.status} @ ${res.venue}.`);
    } catch (e) {
      setApproveErr(String(e));
    } finally {
      setApproving(false);
    }
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-[360px] border-l border-slate-700 bg-slate-900 shadow-2xl flex flex-col">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-950">
        <Bot size={14} className="text-emerald-400" />
        <span className="text-xs font-semibold uppercase tracking-widest text-slate-200">Agent CoPilot</span>
        <span className="ml-auto flex items-center gap-1 text-[10px] font-mono text-slate-400">
          <ShieldCheck size={10} className="text-amber-400" /> WebMCP
        </span>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
          <X size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {invocations.length === 0 && (
          <div className="text-xs text-slate-500 font-mono">
            No WebMCP tool invocations yet. When an LLM agent drives GraphAlpha
            through <span className="text-emerald-400">/ws/events</span>, its
            tool calls + proposed orders appear here for human approval.
          </div>
        )}

        {approveMsg && (
          <div className="flex items-center gap-1.5 text-[10px] text-emerald-300 bg-emerald-950/40 border border-emerald-800 rounded px-2 py-1.5">
            <CheckCircle2 size={10} /> {approveMsg}
          </div>
        )}
        {approveErr && (
          <div className="text-[10px] text-red-300 bg-red-950/40 border border-red-800 rounded px-2 py-1.5 font-mono">
            {approveErr}
          </div>
        )}

        {invocations.map((ev, i) => {
          const out = ev.output as Record<string, unknown> | undefined;
          const hasToken = Boolean(ev.proposal_token ?? out?.proposal_token);
          return (
            <div key={i} className={clsx("rounded border border-slate-700 bg-slate-800/60 p-2",
              hasToken ? "border-amber-700/60" : "")}>
              <div className="whitespace-pre-wrap text-[10px] font-mono text-slate-300 leading-relaxed">
                {eventText(ev)}
              </div>
              {hasToken && (
                <button
                  onClick={() => approve(ev)}
                  disabled={approving}
                  className="mt-2 flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-600/30 border border-amber-500/40 text-[10px] font-bold text-amber-300 hover:bg-amber-600/50 disabled:opacity-50"
                >
                  {approving ? <Loader2 size={10} className="animate-spin" /> : <ShieldCheck size={10} />}
                  Approve &amp; execute (paper)
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}