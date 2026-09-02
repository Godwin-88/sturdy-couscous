import { useState, useRef, useEffect, useCallback } from "react";
import clsx from "clsx";
import { X, Brain, Send, Loader2, BookOpen, FileText, ChevronDown, Trash2 } from "lucide-react";
import { chatApi, type ChatMessage, type ChatContext } from "@/lib/api";
import Markdown from "@/components/Markdown";
import { getScreenContext, screenContextLabel } from "@/lib/screenContext";

/**
 * Financial Engineer chat — a right slide-over available on every screen.
 * On open, calls GET /chat/context/{screen} (live screen data + Hybrid GraphRAG
 * context) and auto-generates the "break down this screen" answer. One component
 * mounted globally with zero edits to the 20+ screen pages.
 */
export default function ScreenChat({ screen }: { screen: string }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [context, setContext] = useState<ChatContext | null>(null);
  const [err, setErr] = useState<string>("");
  const [showSources, setShowSources] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const loadContext = useCallback(async (screenId: string) => {
    try {
      const pg = getScreenContext(screenId) ?? {};
      const ctx = await chatApi.context(screenId, pg);
      setContext(ctx);
      return ctx;
    } catch (e) {
      setErr(`Context unavailable: ${e instanceof Error ? e.message : String(e)}`);
      return null;
    }
  }, []);

  useEffect(() => {
    if (!open || messages.length > 0) return;
    let cancelled = false;
    setBusy(true);
    setErr("");
    (async () => {
      const ctx = await loadContext(screen);
      if (cancelled) return;
      if (ctx) {
        try {
          const pg = getScreenContext(screen) ?? {};
          const resp = await chatApi.ask(screen, "", [], pg);
          if (!cancelled) {
            setMessages([
              { role: "user", content: `(auto) Break down the ${screen} screen as a financial engineer` },
              { role: "assistant", content: resp.answer, sources: resp.sources, suggestions: resp.suggestions },
            ]);
          }
        } catch (e) {
          setErr(`Auto breakdown failed: ${e instanceof Error ? e.message : String(e)}`);
        }
      }
      if (!cancelled) setBusy(false);
    })();
    return () => { cancelled = true; };
  }, [open, screen, loadContext, messages.length]);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setErr("");
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    try {
      const pg = getScreenContext(screen) ?? {};
      const resp = await chatApi.ask(screen, q, history, pg);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: resp.answer, sources: resp.sources, suggestions: resp.suggestions },
      ]);
    } catch (e) {
      setErr(`Ask failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const clearHistory = async () => {
    try { await chatApi.clearHistory(screen); } catch { /* ignore */ }
    setMessages([]);
    setContext(null);
  };

  const sourceCount = messages.reduce((acc, m) => acc + (m.sources?.length ?? 0), 0);

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        title="Financial Engineer (screen-aware chat)"
        className={clsx(
          "fixed bottom-4 right-4 z-[60] flex items-center gap-2 px-3.5 py-2.5 rounded-full shadow-lg border transition-colors",
          open ? "bg-slate-800 border-slate-600 text-slate-200" : "bg-indigo-600 hover:bg-indigo-500 border-indigo-400/40 text-white",
        )}
      >
        {open ? <X size={16} /> : <Brain size={16} />}
        <span className="text-xs font-semibold">{open ? "Close" : "Financial Engineer"}</span>
        {sourceCount > 0 && !open && <span className="text-[10px] font-mono text-indigo-200">{sourceCount}</span>}
      </button>

      {open && (
        <div className="fixed inset-y-0 right-0 z-[55] flex w-[400px] max-w-[92vw] flex-col border-l border-slate-700 bg-slate-900 shadow-2xl">
          <div className="flex items-center gap-2 px-3 py-2.5 border-b border-slate-700 bg-slate-950/50">
            <Brain size={15} className="text-indigo-400" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold text-slate-200 uppercase tracking-wider">Financial Engineer</div>
              <div className="text-[10px] font-mono text-slate-500">screen: {screen}</div>
              {screenContextLabel(getScreenContext(screen)) && (
                <div className="text-[10px] font-mono text-indigo-300 truncate mt-0.5">
                  Analyzing: {screenContextLabel(getScreenContext(screen))}
                </div>
              )}
            </div>
            <button onClick={clearHistory} title="Clear history" className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200">
              <Trash2 size={13} />
            </button>
            <button onClick={() => setOpen(false)} className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200">
              <X size={14} />
            </button>
          </div>

          {messages.length > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 border-b border-slate-700/70 bg-slate-900">
              <button
                onClick={() => setShowSources((s) => !s)}
                className={clsx(
                  "flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded border",
                  showSources ? "bg-indigo-600/20 border-indigo-500/40 text-indigo-300" : "bg-slate-800 border-slate-600 text-slate-400",
                )}
              >
                <BookOpen size={11} /> Sources ({sourceCount})
                <ChevronDown size={10} />
              </button>
              {err && <span className="text-[10px] text-amber-400 font-mono">{err}</span>}
            </div>
          )}

          <div ref={listRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
            {messages.length === 0 && busy && (
              <div className="flex items-center gap-2 text-xs text-slate-400 font-mono justify-center py-8">
                <Loader2 size={14} className="animate-spin" /> Assembling graph context…
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={clsx("space-y-1", m.role === "user" ? "text-right" : "text-left")}>
                <div className={clsx(
                  "inline-block max-w-[90%] rounded-lg px-3 py-2 text-xs",
                  m.role === "user" ? "bg-indigo-600/30 border border-indigo-500/30 text-slate-100 whitespace-pre-wrap" : "bg-slate-800 border border-slate-700 text-slate-200",
                )}>
                  {m.role === "user" ? m.content : <Markdown text={m.content} />}
                </div>

                {m.role === "assistant" && m.sources && m.sources.length > 0 && showSources && (
                  <div className="text-left text-[10px] font-mono text-slate-500 space-y-0.5 mt-1">
                    {m.sources.map((s, j) => (
                      <div key={j} className="flex items-start gap-1">
                        <FileText size={10} className="mt-0.5 shrink-0" />
                        <span className="truncate">
                          {s.book ? `[${s.book} · ${s.section ?? ""}]` : s.concept ? `concept: ${s.concept}` : s.formula ? `formula: ${s.formula}` : s.strategy ? `strategy: ${s.strategy}` : JSON.stringify(s)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {m.role === "assistant" && m.suggestions && m.suggestions.length > 0 && !showSources && (
                  <div className="flex flex-wrap gap-1.5 mt-1.5 text-left">
                    {m.suggestions.slice(0, 3).map((sg, k) => (
                      <button
                        key={k}
                        onClick={() => send(sg)}
                        disabled={busy}
                        className="text-[10px] font-mono px-2 py-1 rounded bg-slate-800 border border-slate-600 text-slate-300 hover:bg-slate-700 hover:border-slate-500"
                      >
                        {sg}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {messages.length > 0 && busy && (
              <div className="flex items-center gap-2 text-[10px] text-slate-500 font-mono justify-center">
                <Loader2 size={12} className="animate-spin" /> thinking…
              </div>
            )}
          </div>

          <div className="border-t border-slate-700 p-2.5 flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") send(input); }}
              placeholder="Ask as a financial engineer…"
              disabled={busy}
              className="flex-1 min-w-0 rounded-lg bg-slate-800 border border-slate-600 px-3 py-2 text-xs font-mono text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500"
            />
            <button
              onClick={() => send(input)}
              disabled={busy || !input.trim()}
              className="px-3 py-2 rounded-lg bg-indigo-600 text-white disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
