import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import { X, Brain, Send, Loader2, BookOpen, FileText, ChevronDown, Trash2, CheckCircle2, XCircle, ClipboardList, ShieldAlert, ExternalLink } from "lucide-react";
import { chatApi, optionsApi, type ChatMessage, type ChatContext, type OrderDraft, type FeStep, type FeNews } from "@/lib/api";
import Markdown from "@/components/Markdown";
import { getScreenContext, screenContextLabel, setScreenContext } from "@/lib/screenContext";

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
  const navigate = useNavigate();
  const [proposals, setProposals] = useState<Record<number, { token?: string; risk?: string; done?: string; err?: string; busy?: boolean }>>({});

  const makePlaceRequest = (d: OrderDraft) => {
    const legs = (d.legs ?? []).slice(0, 4).filter((l) => l.symbol);
    const primary = legs[0];
    if (!primary?.symbol) return null;
    const toIntent = (side?: string) =>
      side === "sell" ? "sell_to_open" as const : "buy_to_open" as const;
    return {
      contract_symbol: primary.symbol!,
      qty: primary.contracts ?? 1,
      side: primary.side === "sell" ? "sell" as const : "buy" as const,
      position_intent: toIntent(primary.side),
      order_type: "limit" as const,
      limit_price: null as number | null,
      order_class: (legs.length > 1 ? "vertical" : "simple") as "vertical" | "simple",
      label: d.strategy ?? "financial_engineer",
      legs: legs.slice(1).map((l) => ({
        symbol: l.symbol!,
        side: (l.side === "sell" ? "sell" : "buy") as "buy" | "sell",
        qty: l.contracts ?? 1,
        position_intent: toIntent(l.side),
      })),
    };
  };

  const reviewInOptions = (d: OrderDraft) => {
    const ct = d.contract_type === "put" || d.contract_type === "call" ? d.contract_type : undefined;
    setScreenContext("options", {
      underlying: d.underlying,
      expiration: d.expiration ?? undefined,
      contract_type: ct,
      prefillDraft: d,
    });
    navigate("/options");
  };

  const runProposal = async (msgIndex: number, d: OrderDraft) => {
    const req = makePlaceRequest(d);
    if (!req) { updateProposal(msgIndex, { err: "No contract leg available for this draft." }); return; }
    setProposals((p) => ({ ...p, [msgIndex]: { ...(p[msgIndex] ?? {}), busy: true } }));
    try {
      const preview = await optionsApi.place({ ...req, preview: true });
      const pv = preview as unknown as Record<string, unknown>;
      const risk = "risk_preview" in pv
        ? JSON.stringify(pv.risk_preview as Record<string, unknown>, null, 0)
        : "";
      updateProposal(msgIndex, { token: pv.proposal_token as string, risk });
    } catch (e) {
      updateProposal(msgIndex, { err: e instanceof Error ? e.message : String(e) });
    }
  };

  const executeProposal = async (msgIndex: number, d: OrderDraft, token: string) => {
    const req = makePlaceRequest(d);
    if (!req) { updateProposal(msgIndex, { err: "No contract leg available" }); return; }
    setProposals((p) => ({ ...p, [msgIndex]: { ...(p[msgIndex] ?? {}), busy: true } }));
    try {
      const res = await optionsApi.place({ ...req, proposal_token: token });
      updateProposal(msgIndex, {
        done: `Order ${res.status} · ${res.contract_symbol} · qty ${res.quantity} · ${res.alpaca_order_id ? `alpaca:${res.alpaca_order_id}` : `id:${res.order_id}`}`,
        token: undefined,
      });
    } catch (e) {
      updateProposal(msgIndex, { err: e instanceof Error ? e.message : String(e) });
    }
  };

  const updateProposal = (msgIndex: number, patch: Record<string, string | undefined>) => {
    setProposals((p) => ({ ...p, [msgIndex]: { ...(p[msgIndex] ?? {}), ...patch, busy: false } }));
  };

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
              { role: "assistant", content: resp.answer, sources: resp.sources, suggestions: resp.suggestions, steps: resp.steps, news: resp.news, order_drafts: resp.order_drafts },
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
        { role: "assistant", content: resp.answer, sources: resp.sources, suggestions: resp.suggestions, steps: resp.steps, news: resp.news, order_drafts: resp.order_drafts },
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

                {m.role === "assistant" && m.steps && m.steps.length > 0 && (
                  <div className="text-left mt-2">
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-400 uppercase tracking-widest mb-1">
                      <ClipboardList size={11} /> Agent tool steps
                    </div>
                    <div className="space-y-0.5">
                      {m.steps.map((s, sj) => (
                        <div key={sj} className={clsx("flex items-center gap-1.5 text-[10px] font-mono",
                          s.ok ? "text-slate-400" : "text-amber-400/90")}>
                          {s.ok ? <CheckCircle2 size={10} className="text-emerald-400/80" /> : <XCircle size={10} className="text-amber-400" />}
                          <span className="truncate">{s.summary}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {m.role === "assistant" && m.news && m.news.length > 0 && (
                  <div className="text-left mt-2">
                    <div className="flex flex-wrap gap-1.5">
                      {m.news.slice(0, 6).map((n, nj) => (
                        <span key={nj} className={clsx(
                          "text-[10px] font-mono px-1.5 py-0.5 rounded border",
                          (n.sentiment ?? 0) > 0 ? "bg-emerald-950/40 border-emerald-800 text-emerald-300"
                            : (n.sentiment ?? 0) < 0 ? "bg-rose-950/40 border-rose-800 text-rose-300"
                            : "bg-slate-800 border-slate-700 text-slate-400")}>
                          {n.headline.length > 70 ? `${n.headline.slice(0, 70)}…` : n.headline}
                          {n.sentiment != null && <> ({n.sentiment > 0 ? "+" : ""}{n.sentiment})</>}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {m.role === "assistant" && m.order_drafts && m.order_drafts.length > 0 && m.order_drafts.map((d, di) => {
                  const p = proposals[di] ?? {};
                  return (
                    <div key={di} className="text-left mt-2 rounded-lg border border-violet-800/70 bg-slate-900 overflow-hidden">
                      <div className="flex items-center gap-1.5 px-2 py-1.5 bg-violet-950/40 border-b border-violet-800/60">
                        <ShieldAlert size={11} className="text-violet-400" />
                        <span className="text-[10px] font-mono text-violet-300 uppercase tracking-widest">Proposed trade — human approval required</span>
                      </div>
                      <div className="p-2 space-y-1 text-[10px] font-mono text-slate-300">
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-400">strategy</span><b className="text-slate-100">{d.strategy ?? "—"}</b>
                          <span className="text-slate-500">·</span><span>{d.regime ?? ""}</span>
                        </div>
                        {d.legs?.map((l, li) => (
                          <div key={li} className="text-slate-400">
                            <span className={l.side === "sell" ? "text-rose-300" : "text-emerald-300"}>{l.side ?? "buy"}</span>{" "}
                            <span className="text-slate-200">{l.symbol ?? ""}</span>{" "}
                            {l.strike != null && <> · {l.strike}</>} · {l.contracts ?? 1} contracts
                          </div>
                        ))}
                        <div className="flex flex-wrap gap-x-3 gap-y-0.5 pt-0.5 text-slate-400">
                          {d.est_premium != null && <span>premium <b className="text-slate-100">{d.est_premium}</b></span>}
                          {d.max_profit != null && <span>maxP <b className="text-emerald-300">{d.max_profit}</b></span>}
                          {d.max_loss != null && <span>maxL <b className="text-rose-300">{d.max_loss}</b></span>}
                          {d.max_losspct_nav != null && <span>maxL%NAV <b className="text-rose-300">{d.max_losspct_nav.toFixed(2)}%</b></span>}
                          {d.score != null && <span>score <b className="text-slate-100">{d.score}</b></span>}
                        </div>
                        {p.risk && <div className="text-[9px] text-slate-500">{p.risk}</div>}
                        {p.done && <div className="text-[10px] text-emerald-300">{p.done}</div>}
                        {p.err && <div className="text-[10px] text-amber-300">{p.err}</div>}
                      </div>
                      <div className="flex gap-1.5 px-2 pb-2">
                        <button
                          onClick={() => reviewInOptions(d)}
                          className="flex items-center gap-1 px-2 py-1 rounded bg-slate-800 border border-slate-600 text-[10px] text-slate-200 hover:bg-slate-700">
                          <ExternalLink size={10} /> Open in ticket
                        </button>
                        {!p.token && !p.done && (
                          <button
                            onClick={() => runProposal(di, d)}
                            disabled={p.busy}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-violet-600/30 border border-violet-500/40 text-[10px] text-violet-200 hover:bg-violet-600/50 disabled:opacity-50">
                            {p.busy ? <Loader2 size={10} className="animate-spin" /> : <ClipboardList size={10} />} Propose
                          </button>
                        )}
                        {p.token && (
                          <button
                            onClick={() => executeProposal(di, d, p.token!)}
                            disabled={p.busy}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-rose-600/30 border border-rose-500/40 text-[10px] text-rose-200 hover:bg-rose-600/50 disabled:opacity-50">
                            <ShieldAlert size={10} /> Execute on paper
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}

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
