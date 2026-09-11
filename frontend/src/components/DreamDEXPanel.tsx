import { useMemo, useState } from "react";
import { RefreshCw, Shield, AlertTriangle, ExternalLink } from "lucide-react";
import clsx from "clsx";
import { setScreenContext } from "../lib/screenContext";
import { usePolling } from "../hooks/usePolling";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const EXPLORER = "https://shannon-explorer.somnia.network";

interface Market {
  marketId?: string;
  market_id?: string;
  symbol?: string;
  title?: string;
  asset?: string;
  category?: string;
  status?: number;
  closes_at?: string;
  closesAt?: string;
  up?: { ask?: number; bid?: number; last?: number };
  down?: { ask?: number; bid?: number; last?: number };
}

interface Candidate {
  market_id?: string;
  symbol?: string;
  asset?: string;
  side?: string;
  estimate?: number;
  ask?: number;
  edge_pct?: number;
  net_edge_pct?: number;
  binary_kelly?: number;
  size_usd?: number;
  qty_contracts?: number;
  regime?: string;
  belief_source?: string;
  closes_at?: string;
  n_tested?: number;
}

interface Status {
  mode?: string;
  network?: string;
  enabled?: boolean;
  relay_reachable?: boolean;
  dry_run?: boolean;
  wallet_short?: string;
  claimable?: number;
  balances?: { somi?: number | null; tusdc?: number | null };
  gates?: { freeze?: boolean; audit_chain_ok?: boolean; determinism_ok?: boolean };
}

interface Fill {
  marketId?: string;
  market_id?: string;
  symbol?: string;
  side?: string;
  qty?: number;
  txHash?: string;
  tx_hash?: string;
  confirmations?: number;
  reorg_detected?: boolean;
  mode?: string;
  state?: string;
  timestamp?: string | number;
}

interface TypedData {
  markets?: { markets?: Market[]; cached?: boolean; live?: boolean };
  candidates?: { candidates?: Candidate[]; cached?: boolean };
  status?: Status;
  positions?: { positions?: unknown[]; drift_items?: unknown[] };
  fills?: { fills?: Fill[] };
}

const fmtPct = (x?: number) => (x === undefined ? "—" : `${(x * 100).toFixed(1)}%`);
const fmtNum = (x?: number | null) => (x === undefined || x === null ? "—" : x.toLocaleString(undefined, { maximumFractionDigits: 2 }));
const isStub = (h?: string) => !!h && h.startsWith("stub_");
const shortTx = (h?: string) => (h && !isStub(h) ? h.slice(0, 10) + "…" : (h ?? ""));

export default function DreamDEXPanel() {
  const { data, error, loading, refresh } = usePolling<TypedData>(async () => {
    const [m, c, s, p, f] = await Promise.all([
      fetch(`${API}/dreamdex/markets`).then((r) => r.json()),
      fetch(`${API}/dreamdex/candidates`).then((r) => r.json()),
      fetch(`${API}/dreamdex/status`).then((r) => r.json()),
      fetch(`${API}/dreamdex/positions`).then((r) => r.json()),
      fetch(`${API}/dreamdex/fills`).then((r) => r.json()),
    ]);
    return { markets: m, candidates: c, status: s, positions: p, fills: f };
  }, 30_000, []);

  const markets = data?.markets?.markets ?? [];
  const candidates = data?.candidates?.candidates ?? [];
  const status = data?.status;
  const fills = data?.fills?.fills ?? [];
  const liveSource = (data?.markets as { live?: boolean } | undefined)?.live === true;

  const [tab, setTab] = useState<"markets" | "candidates" | "positions" | "fills">("markets");

  // ── Two-phase trade ticket (human-in-the-loop, U6/U21) ────────────────────
  const [ticket, setTicket] = useState<Market | null>(null);
  const [side, setSide] = useState<"up" | "down">("up");
  const [qty, setQty] = useState("1");
  const [confirming, setConfirming] = useState(false);
  const [placed, setPlaced] = useState<{ ok: boolean; reason?: string; txHash?: string; state?: string } | null>(null);

  const openTicket = (m: Market) => {
    setTicket(m);
    setSide("up");
    setQty("1");
    setConfirming(false);
    setPlaced(null);
  };
  const place = async () => {
    if (!ticket) return;
    const n = Number(qty);
    if (!Number.isFinite(n) || n < 1) return;
    if (!confirming) {
      setConfirming(true);
      return;
    }
    try {
      const r = await fetch(`${API}/dreamdex/order`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          marketId: ticket.marketId ?? ticket.market_id ?? "",
          side,
          qty: n,
        }),
      });
      const j = await r.json();
      setPlaced(j);
      if (j.ok) {
        setConfirming(false);
        setTicket(null);
        refresh();
      }
    } catch (e) {
      setPlaced({ ok: false, reason: String(e) });
    }
  };

  // ── Claim / Redeem (human-gated settlement sweep, U6/U21) ─────────────────
  const [claiming, setClaiming] = useState(false);
  const [claimResponse, setClaimResponse] = useState<{ ok?: boolean; results?: unknown[]; error?: string } | null>(null);

  const runClaim = async () => {
    if (claiming) return;
    setClaiming(true);
    setClaimResponse(null);
    try {
      const r = await fetch(`${API}/dreamdex/claim`, { method: "POST" });
      const j = await r.json();
      setClaimResponse(j);
      refresh();
    } catch (e) {
      setClaimResponse({ ok: false, error: String(e) });
    } finally {
      setClaiming(false);
    }
  };

  useMemo(() => {
    setScreenContext("dreamdex", { screen: "dreamdex", extra: { ...status } });
  }, [status]);

  const best = ticket ? (side === "up" ? ticket.up?.ask : ticket.down?.ask) : undefined;
  const cost = (best ?? 0) * (Number(qty) || 0);

  return (
    <div className="p-4 space-y-4">
      {/* Status bar + live wallet strip */}
      <div className="flex items-center gap-3 text-xs text-slate-400 border border-slate-700 rounded px-3 py-2 flex-wrap">
        <span className={clsx("w-2 h-2 rounded-full", !status?.enabled ? "bg-slate-500" : status?.relay_reachable ? "bg-emerald-400" : "bg-brand-500")} />
        <span>
          {!status?.enabled
            ? "DreamDEX disabled — set DREAMDEX_ENABLED=1"
            : status?.relay_reachable
              ? (status?.dry_run ? "DreamDEX connected (DRY-RUN — nothing broadcasts)" : "DreamDEX connected (LIVE)")
              : "Relay unreachable — candidates stale"}
        </span>
        {status?.mode && <span className="ml-auto font-mono">{status.mode.toUpperCase()}</span>}
        {status?.wallet_short && (
          <a className="font-mono text-brand-400 underline decoration-dotted" href={`${EXPLORER}/address/${status.wallet_short}`} target="_blank" rel="noreferrer">
            {status.wallet_short}
          </a>
        )}
        {/* Live wallet balances (read-only) */}
        {status?.balances && (
          <span className="font-mono text-emerald-400" title="Live Somnia balances">
            Ⓢ {fmtNum(status.balances.somi)} SOMI · {fmtNum(status.balances.tusdc)} tUSDC
          </span>
        )}
        {!status?.dry_run && <span className="text-brand-400 text-[10px]">● LIVE ARM</span>}
        {status?.gates?.freeze && (
          <span className="text-red-400 text-[10px] font-bold border border-red-500/60 rounded px-1.5 bg-red-500/10" title="U6 kill-switch active — orders/claims rejected with 423">
            🔒 FROZEN — ALL ORDER & CLAIM ACTIONS BLOCKED
          </span>
        )}
        {loading && <RefreshCw size={12} className="animate-spin" />}
      </div>

      {error && <div className="text-xs text-red-400">Poll error: {error}</div>}

      {/* Tab nav */}
      <div className="flex gap-2 border-b border-slate-700 pb-2">
        {(["markets", "candidates", "positions", "fills"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs px-3 py-1 rounded capitalize transition-colors
              ${tab === t ? "bg-brand-500 text-white" : "text-slate-400 hover:text-white"}`}
          >
            {t}
            {t === "markets" && markets.length > 0 && (
              <span className="ml-1 bg-brand-400 text-white text-[10px] rounded-full px-1">{markets.length}</span>
            )}
            {t === "fills" && fills.length > 0 && (
              <span className="ml-1 bg-brand-500 text-black text-[10px] rounded-full px-1">{fills.length}</span>
            )}
          </button>
        ))}
        {liveSource && (
          <span className="text-[10px] text-brand-400 ml-2" title="Agent cache cold — showing the fresh live relay snapshot">● live</span>
        )}
      </div>

      {/* Markets tab — live books + trade ticket */}
      {tab === "markets" && (
        <div className="space-y-2">
          {markets.length === 0 && (
            <p className="text-xs text-slate-500">No markets loaded — relay offline or venue has no open windows.</p>
          )}
          {([...markets].sort((a: Market, b: Market) =>
            (a.closes_at ?? a.closesAt ?? "").localeCompare(b.closes_at ?? b.closesAt ?? "")))
            .map((m: Market, i: number) => {
              const tradable = m.status === 1 && (m.up?.ask ?? 0) > 0;
              return (
                <div key={m.marketId ?? m.market_id ?? i} className={clsx("border rounded p-3 space-y-1", tradable ? "border-brand-500/40" : "border-slate-700 opacity-60")}>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-100 font-mono">{m.symbol ?? m.title ?? m.market_id ?? "ec"}</span>
                    <span className={clsx("text-[10px] px-1.5 rounded", tradable ? "bg-emerald-400/10 text-emerald-400" : "bg-slate-600 text-slate-400")}>
                      {m.status === 1 ? "TRADING" : `status ${m.status}`}
                    </span>
                  </div>
                  <div className="flex gap-2 text-xs text-slate-400">
                    <span className={(m.asset ?? "crypto").toLowerCase() === "btc" ? "text-brand-400" : "text-brand-300"}>{(m.asset ?? "crypto").toUpperCase()}</span>
                    <span>·</span>
                    <span>Up {fmtPct(m.up?.ask)} / Down {fmtPct(m.down?.ask)}</span>
                    {(m.closes_at || m.closesAt) && <span>· closes {new Date(m.closes_at ?? m.closesAt ?? "").toLocaleTimeString()}</span>}
                    {tradable && (
                      <button onClick={() => openTicket(m)}
                        className="ml-auto text-[10px] px-2 py-0.5 rounded bg-brand-500/15 text-brand-300 hover:bg-brand-500/30">
                        <Shield size={10} className="inline mr-1" />Trade
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
        </div>
      )}

      {/* Trade ticket (two-phase: quote → confirm) — fixed modal, above chat drawer (z-100) */}
      {ticket && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto">
          <div className="absolute inset-0 bg-slate-950/75" onClick={() => setTicket(null)} />
          <div className="relative w-[460px] max-w-[94vw] mx-auto my-6 rounded-lg border border-brand-500 bg-slate-900 shadow-2xl p-3.5 max-h-[86vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-slate-100 font-mono">Trade — {ticket.symbol ?? ticket.market_id}</p>
              <button onClick={() => setTicket(null)} aria-label="Close trade ticket"
                className="text-[10px] text-slate-500 hover:text-slate-200 px-1.5 rounded border border-slate-700">
                ✕ close
              </button>
            </div>
            <div className="flex gap-2 items-center flex-wrap">
              {(["up", "down"] as const).map((s) => (
                <button key={s} onClick={() => { setSide(s); setConfirming(false); }}
                  className={clsx("px-2 py-1 rounded text-xs", side === s ? "bg-brand-500 text-white" : "bg-slate-800 text-slate-400")}>
                  {s === "up" ? `UP ${fmtPct(ticket.up?.ask)}` : `DOWN ${fmtPct(ticket.down?.ask)}`}
                </button>
              ))}
              <input value={qty} onChange={(e) => { setQty(e.target.value); setConfirming(false); }}
                className="w-20 bg-slate-800 text-slate-100 text-xs rounded px-2 py-1" inputMode="numeric" placeholder="qty" />
              <span className="text-xs text-slate-400">≈ <span className="text-slate-100">{cost.toFixed(2)}</span> tUSDC</span>
            </div>
            {!confirming ? (
              <button onClick={place} className="mt-2.5 text-[11px] px-3 py-1 rounded bg-brand-500 text-white">Place {side.toUpperCase()} order</button>
            ) : (
              <button onClick={place} className={clsx("mt-2.5 text-[11px] px-3 py-1 rounded", "bg-brand-500 text-black")}>
                <AlertTriangle size={11} className="inline mr-1" />Confirm {side.toUpperCase()} × {qty} at {fmtPct(best)}?
              </button>
            )}
            {placed && (
              <div className={clsx("text-[11px] mt-1 font-mono", placed.ok ? "text-emerald-400" : "text-red-400")}>
                {placed.ok ? `✓ filled ${placed.state} ${shortTx(placed.txHash)}` : `✗ ${placed.reason}`}
                {placed.txHash && !isStub(placed.txHash) && (
                  <a className="text-brand-400 underline ml-2" href={`${EXPLORER}/tx/${placed.txHash}`} target="_blank" rel="noreferrer">view on explorer</a>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Candidates tab — edge + Kelly sizing (the financial story) */}
      {tab === "candidates" && (
        <div className="space-y-2">
          {candidates.length === 0 && (
            <p className="text-xs text-slate-500">No candidates this cycle — no market cleared the multiplicity-corrected edge gate.</p>
          )}
          {candidates.map((c, i) => {
            const okay = (c.net_edge_pct ?? 0) > 0;
            return (
              <div key={i} className={clsx("border rounded p-3 space-y-1", okay ? "border-brand-500/40" : "border-slate-700")}>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-100 font-mono">{c.symbol ?? c.market_id ?? "ec"}</span>
                  <span className={clsx("text-xs font-bold", c.side === "up" ? "text-emerald-400" : "text-red-400")}>
                    BUY {c.side?.toUpperCase()}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-slate-400">
                  <span>Est <span className="text-slate-100">{fmtPct(c.estimate)}</span></span>
                  <span>@ ask <span className="text-slate-100">{fmtPct(c.ask)}</span></span>
                  <span className={okay ? "text-emerald-400" : "text-brand-500"}>edge {c.edge_pct}% / net {c.net_edge_pct}%</span>
                  <span>kelly <span className="text-slate-100">{(c.binary_kelly ?? 0).toFixed(3)}</span></span>
                  <span>size <span className="text-slate-100">${c.size_usd?.toFixed(0)}</span></span>
                  <span>qty <span className="text-slate-100">{c.qty_contracts}</span></span>
                  <span>regime <span className="text-slate-100">{c.regime}</span></span>
                  <span className="text-slate-600">n={c.n_tested}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Positions tab */}
      {tab === "positions" && (
        <div className="space-y-2">
          {(data?.positions?.positions ?? []).length === 0 && (
            <p className="text-xs text-slate-500">No open positions — connect the relay and place a candidate.</p>
          )}
          {(data?.positions?.drift_items ?? []).length > 0 && (
            <p className="text-xs text-brand-500">Reconciliation drift: {data?.positions?.drift_items!.length} item(s) — check /dreamdex/positions.</p>
          )}
          {/* Human-gated settlement sweep (U6/U21) — claim settled winnings */}
          <div className="flex items-center gap-2">
            <button
              onClick={runClaim}
              disabled={claiming}
              className="text-[10px] px-2.5 py-1 rounded bg-brand-500/15 text-brand-300 hover:bg-brand-500/30 disabled:opacity-40 flex items-center gap-1"
            >
              <Shield size={10} className="inline" />
              {claiming ? "Claiming…" : "Claim settled winnings (REDEEM)"}
            </button>
            {claimResponse && (
              <span className="text-[10px] font-mono text-slate-500 truncate flex-1">
                {JSON.stringify(claimResponse).slice(0, 160)}
              </span>
            )}
            {/* Claim action hint — surfaced only when settled winnings exist (claimable) */}
            {!claiming && !claimResponse && (status?.claimable ?? 0) > 0 && (
              <span className="text-[10px] text-brand-400 flex-1">
                {status!.claimable} settled contract(s) awaiting claim — market resolved, run REDEEM to sweep winnings.
              </span>
            )}
          </div>
        </div>
      )}

      {/* Fills tab (U14: confirmations / reorg + explorer links) */}
      {tab === "fills" && (
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <button
              onClick={runClaim}
              disabled={claiming}
              className="text-[10px] px-2.5 py-1 rounded bg-brand-500/15 text-brand-300 hover:bg-brand-500/30 disabled:opacity-40 flex items-center gap-1"
            >
              <Shield size={10} className="inline" />
              {claiming ? "Claiming…" : "Redeem settled (claim sweep)"}
            </button>
            {claimResponse && (
              <span className="text-[10px] font-mono text-slate-500 truncate flex-1">
                {JSON.stringify(claimResponse).slice(0, 160)}
              </span>
            )}
          </div>
          {fills.length === 0 && <p className="text-xs text-slate-500">No fills yet.</p>}
          {fills.map((f: Fill, i: number) => {
            const h = f.txHash ?? f.tx_hash;
            return (
              <div key={i} className="border border-slate-700 rounded px-3 py-1 text-xs font-mono text-slate-400">
                {f.symbol ?? f.marketId ?? f.market_id ?? "ec"} · {f.side} · qty {f.qty} · {f.confirmations ?? 0} conf
                {f.reorg_detected
                  ? <span className="text-red-400"> ⚠ reorg</span>
                  : <span className="text-emerald-400"> ✓</span>}
                {h && !isStub(h) && (
                  <a className="text-brand-400 underline ml-2" href={`${EXPLORER}/tx/${h}`} target="_blank" rel="noreferrer">
                    <ExternalLink size={10} className="inline" /> {shortTx(h)}
                  </a>
                )}
                {h && isStub(h) && <span className="text-slate-600 ml-2">dry-run</span>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
