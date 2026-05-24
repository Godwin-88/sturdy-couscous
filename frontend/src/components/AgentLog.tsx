import { useEffect, useRef, useState } from "react";
import { Radio, AlertCircle, CheckCircle, Clock, TrendingUp, Zap, RefreshCw } from "lucide-react";
import { useWebSocket, WsStatus } from "@/hooks/useWebSocket";
import { WS_BASE } from "@/lib/api";
import clsx from "clsx";

interface AgentEvent {
  event?:     string;
  timestamp?: string;
  count?:     number;
  [key: string]: unknown;
}

type FilterType = "ALL" | "SIGNAL" | "TRADE" | "ERROR" | "REGIME";

const STATUS_DOT: Record<WsStatus, string> = {
  open:       "bg-emerald-400",
  connecting: "bg-yellow-400 animate-pulse",
  closed:     "bg-slate-500",
  error:      "bg-red-500",
};

function classifyEvent(msg: AgentEvent): FilterType {
  const text = JSON.stringify(msg).toLowerCase();
  const evt  = (msg.event ?? "").toString().toLowerCase();
  if (text.includes("error") || text.includes("halt") || text.includes("fail")) return "ERROR";
  if (evt === "signals_updated" || text.includes("signal")) return "SIGNAL";
  if (evt.includes("order") || evt.includes("trade") || evt.includes("fill")) return "TRADE";
  if (evt.includes("regime") || text.includes("regime")) return "REGIME";
  return "SIGNAL";
}

const FILTER_COLORS: Record<FilterType, string> = {
  ALL:    "bg-slate-700 text-slate-300 border-slate-600",
  SIGNAL: "bg-indigo-900/60 text-indigo-300 border-indigo-700",
  TRADE:  "bg-emerald-900/60 text-emerald-300 border-emerald-700",
  ERROR:  "bg-red-900/60 text-red-300 border-red-700",
  REGIME: "bg-purple-900/60 text-purple-300 border-purple-700",
};

const FILTER_ACTIVE: Record<FilterType, string> = {
  ALL:    "bg-slate-600 text-white border-slate-400",
  SIGNAL: "bg-indigo-700 text-white border-indigo-500",
  TRADE:  "bg-emerald-700 text-white border-emerald-500",
  ERROR:  "bg-red-700 text-white border-red-500",
  REGIME: "bg-purple-700 text-white border-purple-500",
};

export default function AgentLog() {
  const { messages, status } = useWebSocket<AgentEvent>(`${WS_BASE}/ws/events`);
  const [filter, setFilter] = useState<FilterType>("ALL");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = bottomRef.current?.parentElement;
    if (!el) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const counts = (["SIGNAL", "TRADE", "ERROR", "REGIME"] as FilterType[]).reduce(
    (acc, f) => ({ ...acc, [f]: messages.filter(m => classifyEvent(m) === f).length }),
    {} as Record<FilterType, number>
  );

  const visible = filter === "ALL"
    ? messages
    : messages.filter(m => classifyEvent(m) === filter);

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

      {/* Filter bar */}
      <div className="flex items-center gap-1 px-2 py-1.5 border-b border-slate-700 shrink-0 overflow-x-auto">
        {(["ALL", "SIGNAL", "TRADE", "REGIME", "ERROR"] as FilterType[]).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={clsx(
              "flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono border transition-colors shrink-0",
              filter === f ? FILTER_ACTIVE[f] : FILTER_COLORS[f]
            )}
          >
            {f === "SIGNAL" && <Zap size={9} />}
            {f === "TRADE"  && <TrendingUp size={9} />}
            {f === "ERROR"  && <AlertCircle size={9} />}
            {f === "REGIME" && <RefreshCw size={9} />}
            {f}
            {f !== "ALL" && (
              <span className="ml-0.5 opacity-70">{counts[f] ?? 0}</span>
            )}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1 min-h-0">
        {visible.length === 0 && (
          <div className="flex items-center gap-2 text-slate-500 text-xs p-2">
            <Clock size={12} />
            {filter === "ALL" ? "Waiting for agent cycle..." : `No ${filter.toLowerCase()} events yet`}
          </div>
        )}
        {[...visible].reverse().map((msg, i) => (
          <EventRow key={i} msg={msg} type={classifyEvent(msg)} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function EventRow({ msg, type }: { msg: AgentEvent; type: FilterType }) {
  const text = typeof msg === "string" ? msg : null;
  const time = msg.timestamp
    ? new Date(msg.timestamp).toLocaleTimeString()
    : new Date().toLocaleTimeString();

  const rowClass = {
    ERROR:  "bg-red-950/50 border-l-2 border-red-600",
    SIGNAL: "border-l-2 border-indigo-600/50",
    TRADE:  "border-l-2 border-emerald-600/50",
    REGIME: "border-l-2 border-purple-600/50",
    ALL:    "",
  }[type];

  const textClass = {
    ERROR:  "text-red-300 font-bold",
    SIGNAL: "text-indigo-200",
    TRADE:  "text-emerald-200",
    REGIME: "text-purple-200",
    ALL:    "text-slate-300",
  }[type];

  const icon = {
    ERROR:  <AlertCircle size={11} className="text-red-400 mt-0.5 shrink-0" />,
    SIGNAL: <Zap size={11} className="text-indigo-400 mt-0.5 shrink-0" />,
    TRADE:  <TrendingUp size={11} className="text-emerald-400 mt-0.5 shrink-0" />,
    REGIME: <RefreshCw size={11} className="text-purple-400 mt-0.5 shrink-0" />,
    ALL:    <span className="w-3 shrink-0" />,
  }[type];

  return (
    <div className={clsx(
      "flex gap-2 items-start rounded px-2 py-1 text-xs font-mono hover:bg-slate-800/50",
      rowClass
    )}>
      <span className="text-slate-500 shrink-0 pt-0.5">{time}</span>
      {icon}
      <span className={clsx("break-all", textClass)}>
        {text ?? formatEvent(msg)}
      </span>
    </div>
  );
}

function formatEvent(msg: AgentEvent): string {
  if (msg.event === "signals_updated") return `${msg.count ?? "?"} signals generated`;
  if (msg.event === "regime_change")   return `Regime → ${msg.regime ?? "unknown"}`;
  if (msg.event === "order_filled")    return `Order filled: ${msg.ticker ?? ""} ${msg.direction ?? ""} ${msg.quantity ?? ""}`;
  try { return JSON.stringify(msg); } catch { return String(msg); }
}
