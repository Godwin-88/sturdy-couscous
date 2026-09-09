/**
 * DefiWorkspace.tsx
 * ─────────────────
 * P11 Stage-5 panel — the Web3 DeFi agent surface.
 *
 * Read-only dashboard of the DeFiAgent's D1–D8 candidate stream, the D6
 * oracle-integrity governor, EVM/EC positions, and the tamper-evident
 * EvidenceChain (U25/U26). All data flows from the /defi/* Redis-backed
 * endpoints; no execution is performed from the UI (two-phase human gate).
 * Uses the app-wide GitHub-blue brand ramp.
 */
import { useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import clsx from "clsx";
import { setScreenContext } from "../lib/screenContext";
import { usePolling } from "../hooks/usePolling";
import { fetchDefi, type DefiApiData, type DeFiCandidate } from "../lib/defiApi";

const fmtPct = (x?: number) => (x === undefined ? "—" : `${(x * 100).toFixed(1)}%`);
const fmtUsd = (x?: number) => (x === undefined ? "—" : `$${x.toFixed(0)}`);

type TabId = "candidates" | "sectors" | "governor" | "evidence";

const SECTOR_LABEL: Record<string, string> = {
  D1: "AMM LP",
  D2: "Lending",
  D3: "Yield",
  D4: "Perps",
  D5: "EC Hedge",
  D7: "EC Tail",
};

export default function DefiWorkspace() {
  const { data, error, loading, refresh } = usePolling<DefiApiData>(fetchDefi, 30_000, []);
  const [tab, setTab] = useState<TabId>("candidates");

  const candidates = data?.candidates?.candidates ?? [];
  const governor = data?.governor?.governor ?? {};
  const sectors = data?.sectors?.sectors ?? {};
  const status = data?.status;
  const ev = data?.evidence;

  useMemo(() => {
    setScreenContext("defi", { screen: "defi", extra: { ...status } });
  }, [status]);

  const paused = Boolean(governor.paused_evm || governor.paused_ec);

  return (
    <div className="p-4 space-y-4">
      {/* Status bar */}
      <div className="flex items-center gap-3 text-xs text-gray-400 border border-gray-700 rounded px-3 py-2">
        <span
          className={clsx(
            "w-2 h-2 rounded-full",
            !status?.enabled ? "bg-gray-500" : paused ? "bg-yellow-500" : status?.relay_reachable ? "bg-green-400" : "bg-yellow-500"
          )}
        />
        <span>
          {!status?.enabled
            ? "DeFi disabled — set DEFI_ENABLED=1"
            : paused
              ? "Oracle governor PAUSED (D6 breaker active)"
              : status?.dry_run
                ? "DeFi connected (DRY-RUN)"
                : "DeFi connected (LIVE)"}
        </span>
        <span className="ml-auto font-mono hidden sm:inline">{status?.venue ?? "sepolia-evm + somnia-relay"}</span>
        {status?.mode && <span className="font-mono">{status.mode.toUpperCase()}</span>}
        {loading && <RefreshCw size={12} className="animate-spin" />}
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}

      {/* Tab nav */}
      <div className="flex gap-2 border-b border-gray-700 pb-2">
        {(["candidates", "sectors", "governor", "evidence"] as const).map((t) => (
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
              <span className="ml-1 bg-brand-500 text-black text-[10px] rounded-full px-1">{candidates.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Candidates — edge/Kelly/size story */}
      {tab === "candidates" && (
        <div className="space-y-2">
          {candidates.length === 0 && (
            <p className="text-xs text-gray-500">No candidates this cycle — no sector cleared its edge gate.</p>
          )}
          {candidates.map((c: DeFiCandidate, i: number) => {
            const okay = (c.net_edge_pct ?? 0) > 0;
            return (
              <div key={`${c.market_id ?? c.kind}-${i}`} className={clsx("border rounded p-3 space-y-1", okay ? "border-brand-500/40" : "border-gray-700")}>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white font-mono truncate">{c.symbol ?? c.market_id ?? c.kind ?? "defi"}</span>
                  <span className="text-xs font-bold text-brand-400">{SECTOR_LABEL[c.sector ?? ""] ?? c.sector ?? "?"}</span>
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-gray-400">
                  <span className="font-mono">{c.venue}</span>
                  <span>Est <span className="text-white">{fmtPct(c.estimate)}</span></span>
                  <span>@ ask <span className="text-white">{fmtPct(c.ask)}</span></span>
                  <span className={okay ? "text-green-400" : "text-yellow-500"}>edge {c.edge_pct}% / net {c.net_edge_pct}%</span>
                  <span>kelly <span className="text-white">{(c.binary_kelly ?? 0).toFixed(3)}</span></span>
                  <span>size <span className="text-white">{fmtUsd(c.size_usd)}</span></span>
                  {c.qty_contracts !== undefined && <span>qty <span className="text-white">{c.qty_contracts}</span></span>}
                  <span>regime <span className="text-white">{c.regime}</span></span>
                  <span className="text-gray-600">{c.status ?? c.kind}</span>
                </div>
              </div>
            );
          })}
        </div>
)}

      {/* Sectors tab — per-sector aggregation */}
      {tab === "sectors" && (
        <div className="space-y-2">
          {Object.keys(sectors).length === 0 && <p className="text-xs text-gray-500">No sector data cached yet.</p>}
          {Object.entries(sectors).map(([s, a]) => (
            <div key={s} className="border border-gray-700 rounded p-3 flex items-center justify-between text-xs">
              <span className="text-white font-mono">{SECTOR_LABEL[s] ?? s}</span>
              <span className="text-gray-400">x{a.count} · {fmtUsd(a.size_usd)}</span>
              <span className="text-gray-500 font-mono">{a.venue}</span>
            </div>
          ))}
          {data?.sectors?.total_size_usd !== undefined && data?.sectors?.total_size_usd > 0 && (
            <p className="text-xs text-gray-400">
              Total candidate notional: <span className="text-white font-mono">{fmtUsd(data.sectors.total_size_usd)}</span>
            </p>
          )}
        </div>
      )}

      {/* Governor tab — D6 oracle integrity breaker */}
      {tab === "governor" && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-3 text-xs">
            <span className={clsx("px-2 py-1 rounded", governor.paused_evm ? "bg-yellow-500/20 text-yellow-400" : "bg-green-500/10 text-green-400")}>
              EVM venue: {governor.paused_evm ? "PAUSED" : "ok"}
            </span>
            <span className={clsx("px-2 py-1 rounded", governor.paused_ec ? "bg-yellow-500/20 text-yellow-400" : "bg-green-500/10 text-green-400")}>
              EC venue: {governor.paused_ec ? "PAUSED" : "ok"}
            </span>
          </div>
          {(governor.feeds ?? []).length === 0 && <p className="text-xs text-gray-500">No feed telemetry cached this cycle.</p>}
          {(governor.feeds ?? []).map((f, i) => (
            <div key={i} className="border border-gray-700 rounded px-3 py-1 text-xs font-mono text-gray-400 flex justify-between">
              <span>{f.feed_id}</span>
              <span>{f.venue}</span>
              <span className={f.status === "ok" ? "text-green-400" : "text-yellow-500"}>{f.status ?? "unknown"}</span>
              {f.stale_ms !== undefined && <span>{f.stale_ms}ms</span>}
            </div>
          ))}
        </div>
      )}

      {/* EvidenceChain tab — the auditable decision trail (U25/U26) */}
      {tab === "evidence" && (
        <div className="space-y-2">
          <div className="flex items-center gap-3 text-xs">
            <span className={clsx("w-2 h-2 rounded-full", ev?.verify_ok ? "bg-green-400" : "bg-red-400")} />
            <span className="text-gray-400">
              {ev?.cached ? (ev.verify_ok ? "Chain verified — tamper-evident ledger" : "Chain BROKEN — tampering detected!") : "No chain entries yet"}
            </span>
          </div>
          <div className="border border-gray-700 rounded p-3 space-y-1 text-xs font-mono text-gray-400 break-all">
            <p>root: <span className="text-white">{ev?.root?.slice(0, 48) || "—"}</span></p>
            <p>merkle: <span className="text-white">{ev?.merkle_root?.slice(0, 48) || "—"}</span></p>
          </div>
          {ev?.head && (
            <div className="border border-brand-500/30 rounded p-3 space-y-1 text-xs text-gray-400">
              <p><span className="text-white">{ev.head.cycle_id}</span> · {ev.head.regime}</p>
              <p className="font-mono break-all">hash: {ev.head.hash}</p>
              <p className="font-mono break-all">prev: {ev.head.prev?.slice(0, 48)}</p>
              {(ev.head.ts ?? 0) > 0 && <p>{new Date(ev.head.ts! * 1000).toLocaleString()}</p>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}