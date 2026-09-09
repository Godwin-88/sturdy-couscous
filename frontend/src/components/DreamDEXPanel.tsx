import { useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import clsx from "clsx";
import { setScreenContext } from "../lib/screenContext";
import { usePolling } from "../hooks/usePolling";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface Market {
  marketId?: string;
  market_id?: string;
  symbol?: string;
  title?: string;
  asset?: string;
  category?: string;
  status?: number;
  closes_at?: string;
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
  gates?: { freeze?: boolean; audit_chain_ok?: boolean; determinism_ok?: boolean };
}

interface TypedData {
  markets?: { markets?: Market[]; cached?: boolean };
  candidates?: { candidates?: Candidate[]; cached?: boolean };
  status?: Status;
  positions?: { positions?: unknown[]; drift_items?: unknown[] };
  fills?: { fills?: unknown[] };
}

const fmtPct = (x?: number) => x === undefined ? "—" : `${(x * 100).toFixed(1)}%`;

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

  const [tab, setTab] = useState<"markets" | "candidates" | "positions" | "fills">("candidates");

  useMemo(() => {
    setScreenContext("dreamdex", { screen: "dreamdex", extra: { ...status } });
  }, [status]);

  return (
    <div className="p-4 space-y-4">
      {/* Status bar */}
      <div className="flex items-center gap-3 text-xs text-gray-400 border border-gray-700 rounded px-3 py-2">
        <span className={clsx("w-2 h-2 rounded-full", !status?.enabled ? "bg-gray-500" : status?.relay_reachable ? "bg-green-400" : "bg-yellow-500")} />
        <span>
          {!status?.enabled
            ? "DreamDEX disabled — set DREAMDEX_ENABLED=1"
            : status?.relay_reachable
              ? (status?.dry_run ? "DreamDEX connected (DRY-RUN)" : "DreamDEX connected (LIVE)")
              : "Relay unreachable — candidates stale"}
        </span>
        {status?.mode && <span className="ml-auto font-mono">{status.mode.toUpperCase()}</span>}
        {status?.wallet_short && <span className="font-mono">{status.wallet_short}</span>}
        {loading && <RefreshCw size={12} className="animate-spin" />}
      </div>

      {/* Three-lamp safety gates (U24) */}
      {status?.gates && (
        <div className="flex items-center gap-2 text-[10px] text-gray-500 font-mono">
          <span className={clsx("w-1.5 h-1.5 rounded-full", status.gates.freeze ? "bg-red-500" : "bg-green-400")} />freeze
          <span className={clsx("w-1.5 h-1.5 rounded-full", status.gates.audit_chain_ok ? "bg-green-400" : "bg-yellow-500")} />audit
          <span className={clsx("w-1.5 h-1.5 rounded-full", status.gates.determinism_ok ? "bg-green-400" : "bg-red-500")} />determinism
          {error && <span className="text-red-400 ml-auto">{error.slice(0, 60)}</span>}
        </div>
      )}

      {/* Tab nav */}
      <div className="flex gap-2 border-b border-gray-700 pb-2">
        {(["markets", "candidates", "positions", "fills"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              "text-xs px-3 py-1 rounded capitalize transition-colors",
              tab === t ? "bg-brand-600 text-white" : "text-gray-400 hover:text-white"
            )}
          >
            {t}
            {t === "candidates" && candidates.length > 0 && (
              <span className="ml-1 bg-yellow-500 text-black text-[10px] rounded-full px-1">{candidates.length}</span>
            )}
          </button>
        ))}
        <button onClick={refresh} className="text-xs px-2 py-1 text-gray-400 hover:text-white" title="Refresh">
          <RefreshCw size={12} />
        </button>
      </div>
      {/* Markets tab */}
      {tab === "markets" && (
        <div className="space-y-2">
          {markets.length === 0 && <p className="text-xs text-gray-500">No markets loaded — is the relay reachable?</p>}
          {markets.map((m) => {
            const marketId = m.marketId ?? m.market_id ?? "?";
            return (
              <div key={marketId} className="border border-gray-700 rounded p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white font-mono">{m.symbol ?? marketId}</span>
                  <span className={clsx("text-[10px]", m.status === 0 ? "text-green-400" : "text-yellow-500")}>
                    {["Trading", "Locked", "Resolved", "Voided", "Rolled"][m.status ?? 0] ?? `st${m.status}`}
                  </span>
                </div>
                <div className="flex gap-2 text-xs text-gray-400">
                  <span className="capitalize">{m.category ?? m.asset ?? "crypto"}</span>
                  <span>·</span>
                  <span>Up {fmtPct(m.up?.ask)} / Down {fmtPct(m.down?.ask)}</span>
                  {m.closes_at && <span>· closes {new Date(m.closes_at).toLocaleString()}</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Candidates tab — edge + Kelly sizing (the financial story) */}
      {tab === "candidates" && (
        <div className="space-y-2">
          {candidates.length === 0 && (
            <p className="text-xs text-gray-500">
              No candidates this cycle — no market cleared the multiplicity-corrected edge gate.
            </p>
          )}
          {candidates.map((c, i) => {
            const okay = (c.net_edge_pct ?? 0) > 0;
            return (
              <div key={i} className={clsx("border rounded p-3 space-y-1", okay ? "border-brand-500/40" : "border-gray-700")}>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white font-mono">{c.symbol ?? c.market_id ?? "ec"}</span>
                  <span className={clsx("text-xs font-bold", c.side === "up" ? "text-green-400" : "text-red-400")}>
                    BUY {c.side?.toUpperCase()}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-gray-400">
                  <span>Est <span className="text-white">{fmtPct(c.estimate)}</span></span>
                  <span>@ ask <span className="text-white">{fmtPct(c.ask)}</span></span>
                  <span className={okay ? "text-green-400" : "text-yellow-500"}>
                    edge {c.edge_pct}% / net {c.net_edge_pct}%
                  </span>
                  <span>kelly <span className="text-white">{(c.binary_kelly ?? 0).toFixed(3)}</span></span>
                  <span>size <span className="text-white">${c.size_usd?.toFixed(0)}</span></span>
                  <span>qty <span className="text-white">{c.qty_contracts}</span></span>
                  <span>regime <span className="text-white">{c.regime}</span></span>
                  <span className="text-gray-600">n={c.n_tested}</span>
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
            <p className="text-xs text-gray-500">No open positions — connect the relay and place a candidate.</p>
          )}
          {(data?.positions?.drift_items ?? []).length > 0 && (
            <p className="text-xs text-yellow-500">Reconciliation drift: {data?.positions?.drift_items!.length} item(s) — check /dreamdex/positions.</p>
          )}
        </div>
      )}

      {/* Fills tab (U14: confirmations / reorg) */}
      {tab === "fills" && (
        <div className="space-y-1">
          {fills.length === 0 && <p className="text-xs text-gray-500">No fills yet.</p>}
          {fills.map((f: any, i: number) => (
            <div key={i} className="border border-gray-700 rounded px-3 py-1 text-xs font-mono text-gray-400">
              {f.marketId ?? f.market_id ?? "ec"} · {f.side} · qty {f.qty} · {f.confirmations ?? 0} conf
              {f.reorg_detected ? <span className="text-red-400"> ⚠ reorg</span> : <span className="text-green-400"> ✓</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
