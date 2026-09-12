/**
 * EvidenceTab.tsx
 * ───────────────────
 * Credit → Evidence — the Attestcoin / NAVAnchor proof trail for the strategy
 * fund (fund_graphalpha). GraphAlpha design system; no credit.css.
 *
 * Two surfaces:
 *  1. Verify a source-chain tx (Sepolia NAVAnchor anchor) → persisted Evidence.
 *  2. History: every attested evidence row with its verification status.
 */
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, Loader2, XCircle } from "lucide-react";
import { api } from "../../lib/creditApi";
import type { Evidence } from "../../types/credit";

const short = (s: string | null | undefined, n = 16) =>
  !s ? "—" : s.length <= n ? s : `${s.slice(0, 6)}…${s.slice(-(n - 6))}`;

function StatusChip({ s }: { s: Evidence["status"] }) {
  return s === "verified" ? (
    <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-emerald-400/10 text-emerald-400">
      <CheckCircle2 size={10} /> VERIFIED
    </span>
  ) : s === "invalid" ? (
    <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-red-400/10 text-red-400">
      <XCircle size={10} /> INVALID
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-400">
      UNVERIFIED
    </span>
  );
}

export default function EvidenceTab({ borrowerId = "fund_graphalpha" }: { borrowerId?: string }) {
  const [txHash, setTxHash] = useState("");
  const [chainKey, setChainKey] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState("");
  const [history, setHistory] = useState<Evidence[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const data = await api.listEvidence(borrowerId);
      setHistory(Array.isArray(data) ? data : []);
    } catch {
      // history is best-effort
    } finally {
      setLoadingHistory(false);
    }
  }, [borrowerId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const verify = async () => {
    if (!txHash.trim() || verifying) return;
    setVerifying(true);
    setVerifyError("");
    try {
      await api.verifyEvidence(txHash.trim(), chainKey ? Number(chainKey) : undefined, borrowerId);
      setTxHash("");
      setChainKey("");
      await loadHistory();
    } catch (e) {
      setVerifyError(e instanceof Error ? e.message : "Verification failed");
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="p-4 space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <CheckCircle2 size={15} className="text-brand-300" /> Attestcoin Evidence
        </h2>
        <p className="text-[11px] text-gray-500">
          Proof trail for borrower <span className="font-mono">{borrowerId}</span> — NAVAnchor anchors on
          Sepolia, attested through the Attestcoin protocol.
        </p>
      </div>

      {/* Verify card */}
      <div className="border border-slate-700 rounded-lg p-4 space-y-3 bg-slate-900/40">
        <span className="text-[11px] font-medium uppercase tracking-wider text-gray-400">Verify a source-chain tx</span>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
          <div className="sm:col-span-2">
            <label className="block text-[10px] text-gray-500">Transaction hash</label>
            <input
              value={txHash}
              onChange={(e) => setTxHash(e.target.value)}
              placeholder="0x…"
              className="w-full mt-1 text-xs bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-white placeholder-slate-600 font-mono focus:border-brand-400 outline-none"
            />
          </div>
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <label className="block text-[10px] text-gray-500">Chain key</label>
              <input
                value={chainKey}
                onChange={(e) => setChainKey(e.target.value)}
                type="number" placeholder="auto"
                className="w-full mt-1 text-xs bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-white placeholder-slate-600 focus:border-brand-400 outline-none"
              />
            </div>
            <button
              onClick={verify}
              disabled={verifying || !txHash.trim()}
              className="text-xs px-3 py-1.5 rounded bg-brand-500/20 text-brand-200 hover:bg-brand-500/35 disabled:opacity-40"
            >
              {verifying ? <Loader2 size={12} className="animate-spin" /> : "Verify"}
            </button>
          </div>
        </div>
        {verifyError && <p className="text-[11px] text-red-400">{verifyError}</p>}
      </div>

      {/* History */}
      <div className="border border-slate-700 rounded-lg bg-slate-900/40">
        <div className="flex items-center justify-between px-4 py-2 border-b border-slate-700">
          <span className="text-[11px] font-medium uppercase tracking-wider text-gray-400">Attestation history</span>
          {loadingHistory && <Loader2 size={12} className="animate-spin text-gray-500" />}
        </div>
        {history.length === 0 && (
          <p className="text-xs text-gray-500 px-4 py-6">No evidence yet — verify the latest NAVAnchor anchor tx.</p>
        )}
        {history.map((ev) => (
          <div key={ev.evidence_id} className="border-b border-slate-700/60 last:border-0 px-4 py-3 space-y-1">
            <div className="flex flex-wrap items-center gap-2 justify-between">
              <div className="flex items-center gap-2 text-xs">
                <span className="font-mono text-brand-300 text-[11px]" title={ev.tx_id}>
                  {short(ev.tx_id, 22)}
                </span>
                <StatusChip s={ev.status} />
              </div>
              {ev.source_chain && <span className="text-[10px] text-gray-500">{ev.source_chain}</span>}
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-gray-500">
              <span>attestation <span className="font-mono text-gray-400">{short(ev.attestation_id, 12)}</span></span>
              {ev.header_number != null && <span>block {ev.header_number}</span>}
              {ev.chain_key != null && <span>chainKey {ev.chain_key}</span>}
              {ev.verified_at && <span>verified {new Date(ev.verified_at).toLocaleString()}</span>}
              {ev.tx_id.startsWith("0x") && (
                <a
                  href={`https://sepolia.etherscan.io/tx/${ev.tx_id}`}
                  target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1 text-brand-300 hover:underline"
                >
                  explorer <ExternalLink size={9} />
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}