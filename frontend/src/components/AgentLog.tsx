import { useEffect, useRef } from "react";
import { Radio, AlertCircle, CheckCircle, Clock } from "lucide-react";
import { useWebSocket, WsStatus } from "@/hooks/useWebSocket";
import { WS_BASE } from "@/lib/api";
import clsx from "clsx";

interface AgentEvent {
  event?:     string;
  timestamp?: string;
  count?:     number;
  [key: string]: unknown;
}

const STATUS_DOT: Record<WsStatus, string> = {
  open:       "bg-emerald-400",
  connecting: "bg-yellow-400 animate-pulse",
  closed:     "bg-slate-500",
  error:      "bg-red-500",
};

export default function AgentLog() {
  const { messages, status } = useWebSocket<AgentEvent>(`${WS_BASE}/ws/events`);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Don't auto-scroll — user may be reading; scroll only when at bottom
  useEffect(() => {
    const el = bottomRef.current?.parentElement;
    if (!el) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700 shrink-0">
        <div className="flex items-center gap-2">
          <Radio size={13} className="text-indigo-400" />
          <span className="text-xs font-mono uppercase tracking-wider text-slate-300">
            Live Agent Stream
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={clsx("w-2 h-2 rounded-full", STATUS_DOT[status])} />
          <span className="text-xs text-slate-500 font-mono">{status}</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1 min-h-0">
        {messages.length === 0 && (
          <div className="flex items-center gap-2 text-slate-500 text-xs p-2">
            <Clock size={12} />
            Waiting for agent cycle...
          </div>
        )}
        {[...messages].reverse().map((msg, i) => (
          <EventRow key={i} msg={msg} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function EventRow({ msg }: { msg: AgentEvent }) {
  const text = typeof msg === "string" ? msg : null;
  const isHalt  = (text ?? JSON.stringify(msg)).includes("HALT");
  const isError = (text ?? msg.event ?? "").toString().toLowerCase().includes("error");
  const isSignal = msg.event === "signals_updated";

  const time = msg.timestamp
    ? new Date(msg.timestamp).toLocaleTimeString()
    : new Date().toLocaleTimeString();

  return (
    <div className={clsx(
      "flex gap-2 items-start rounded px-2 py-1 text-xs font-mono",
      isHalt  ? "bg-red-950 border border-red-700" :
      isError ? "bg-red-950/40" : "hover:bg-slate-800/50"
    )}>
      <span className="text-slate-500 shrink-0 pt-0.5">{time}</span>
      {isHalt  ? <AlertCircle size={11} className="text-red-400 mt-0.5 shrink-0" /> :
       isSignal ? <CheckCircle size={11} className="text-emerald-400 mt-0.5 shrink-0" /> :
                  <span className="w-3 shrink-0" />}
      <span className={clsx(
        "break-all",
        isHalt   ? "text-red-300 font-bold" :
        isSignal ? "text-emerald-300" : "text-slate-300"
      )}>
        {text ?? formatEvent(msg)}
      </span>
    </div>
  );
}

function formatEvent(msg: AgentEvent): string {
  if (msg.event === "signals_updated") {
    return `${msg.count ?? "?"} signals generated`;
  }
  try {
    return JSON.stringify(msg);
  } catch {
    return String(msg);
  }
}
