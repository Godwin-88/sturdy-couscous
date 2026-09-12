/**
 * FundConsole.tsx
 * ───────────────────
 * The Credit → Fund screen's human-in-the-loop console (P11 / BUIDL-CTC RWA).
 *
 * Shows the strategy fund (fund_graphalpha) end-to-end:
 *   Attested NAV  →  CC3 executor  →  credit decision  →  APPROVE  →  EXECUTE
 *                       (NAVAnchor + (transferKeepAlive,
 *                        Attestcoin digest)   human-gated)
 * The decision gate is RIGID: a "pending" decision needs an operator Approve
 * before the disbursement Execute button unlocks (U6/U21 discipline — the
 * chat recommends, this console is the only place a human acts).
 *
 * Style: GraphAlpha design system — midnight slate + brand ramp. No credit.css.
 */
import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import {
  Activity,
  CheckCircle2,
  ExternalLink,
  Landmark,
  Loader2,
  Shield,
  Wallet,
  XCircle,
} from "lucide-react";
import { api, fundApi } from "../../lib/creditApi";
import type { CreditExecution, FundStatus } from "../../types/credit";

const fmt = (n: number | null | undefined, d = 2) =>
  n == null ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

const short = (s: string | null | undefined, n = 12) =>
  !s ? "—" : s.length <= n ? s : `${s.slice(0, 4)}…${s.slice(-(n - 4))}`;

function DirtyChip({ ok, good, bad }: { ok: boolean | null | undefined; good: string; bad: string }) {
  return ok ? (
    <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-emerald-400/10 text-emerald-400">
      <CheckCircle2 size={10} /> {good}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-red-400/10 text-red-400">
      <XCircle size={10} /> {bad}
    </span>
  );
}

export default function FundConsole() {
  const [status, setStatus] = useState<FundStatus | null>(null);
  const [busy, setBusy] = useState(true);
  const [actionMsg, setActionMsg] = useState("");
  const [actionErr, setActionErr] = useState("");
  const [approving, setApproving] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [monitoring, setMonitoring] = useState(false);
  const [execution, setExecution] = useState<CreditExecution | null>(null);
  const [toAddr, setToAddr] = useState("");
  const [amount, setAmount] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = async () => {
    try {
      const s = await fundApi.status();
      setStatus(s);
      if (s?.latest_decision?.recommended_amount && !amount) {
        setAmount(String(Number(s.latest_decision.recommended_amount).toFixed(2)));
      }
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "fund status fetch failed");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    load();
    timer.current = setInterval(load, 30_000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const decision = status?.latest_decision;
  const approved = decision?.approval_status === "approved";
  const executed = decision?.approval_status === "executed" || !!execution?.tx_hash;

  const approve = async () => {
    if (!decision) return;
    setApproving(true);
    setActionErr("");
    setActionMsg("");
    try {
      const r = await api.approveDecision(decision.decision_id);
      setActionMsg(`Decision ${decision.decision_id} → ${r.status}`);
      await load();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "approve failed");
    } finally {
      setApproving(false);
    }
  };

  const execute = async () => {
    if (!decision || !toAddr.trim()) return;
    setExecuting(true);
    setActionErr("");
    setActionMsg("");
    try {
      const amt = amount ? Number(amount) : undefined;
      const r = await api.execute({
        decision_id: decision.decision_id,
        to: toAddr.trim(),
        amount: amt,
      });
      setExecution(r);
      setActionMsg(`Execution ${r.execution_id} → ${r.status}${r.tx_hash ? ` tx ${short(r.tx_hash, 16)}` : ""}`);
      await load();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "execute failed");
    } finally {
      setExecuting(false);
    }
  };

  const monitor = async () => {
    const tx = execution?.tx_hash ?? decision?.execution_transaction;
    if (!tx) return;
    setMonitoring(true);
    setActionErr("");
    try {
      const r = await api.monitor(tx);
      setActionMsg(`Monitor: ${r.status}${r.block ? ` · block ${r.block}` : ""}`);
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "monitor failed");
    } finally {
      setMonitoring(false);
    }
  };

  const report = status?.latest_report;
  const cc3 = status?.cc3_execution;

  return (
    <div className="p-4 space-y-4">
      {/* Title strip */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Landmark size={15} className="text-brand-300" /> Strategy Fund — Attested-NAV Financing
          </h2>
          <p className="text-[11px] text-gray-500 font-mono">
            borrower {status?.borrower_id ?? "fund_graphalpha"} · anchor {status?.nav_anchor_contract ?? "—"}
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-gray-400">
          <span className={clsx("w-2 h-2 rounded-full", status ? "bg-emerald-400" : "bg-red-400")} />
          {busy ? "loading…" : status ? "LIVE" : "unreachable"}
          <DirtyChip ok={status?.attestation_reachable} good="attestation ✓" bad="attestation down" />
        </div>
      </div>

      {/* Row 1 — two cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Attested NAV */}
        <div className="border border-brand-500/25 rounded-lg p-4 space-y-3 bg-slate-900/40">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium uppercase tracking-wider text-gray-400">Attested NAV</span>
            {report?.offline ? (
              <DirtyChip ok={false} good="" bad="offline snapshot" />
            ) : (
              <DirtyChip ok={report?.chain_linked} good="anchored on-chain" bad="not anchored" />
            )}
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <p className="text-gray-500">NAV</p>
              <p className={(report?.nav ?? 0) >= 0 ? "text-emerald-400 text-lg font-semibold" : "text-red-400 text-lg font-semibold"}>
                ${fmt(report?.nav)}
              </p>
            </div>
            <div>
              <p className="text-gray-500">Cash</p>
              <p className="text-white text-lg font-semibold">${fmt(report?.cash)}</p>
            </div>
            <div className="col-span-2">
              <p className="text-gray-500">Collateral digest</p>
              <p className="text-white font-mono text-[11px] truncate" title={report?.digest}>
                {short(report?.digest, 34)}
              </p>
            </div>
            <div className="col-span-2">
              <p className="text-gray-500 mb-1">Anchor tx</p>
              {report?.anchor_tx ? (
                <a
                  href={`https://sepolia.etherscan.io/tx/${report.anchor_tx}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-brand-300 font-mono text-[11px] hover:underline"
                >
                  {short(report.anchor_tx, 20)} <ExternalLink size={10} />
                </a>
              ) : (
                <p className="text-gray-500 text-[11px]">none yet — next loop will anchor</p>
              )}
            </div>
          </div>
          <p className="text-[10px] text-gray-500">
            {report?.positions?.length ?? 0} positions · {report?.currency ?? ""} ·{" "}
            {report?.generated_at ? new Date(report.generated_at).toLocaleTimeString() : ""}
          </p>
        </div>

        {/* CC3 executor */}
        <div className="border border-slate-700 rounded-lg p-4 space-y-3 bg-slate-900/40">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium uppercase tracking-wider text-gray-400">
              <Wallet size={11} className="inline mr-1" /> Creditcoin (CC3) Executor
            </span>
            <DirtyChip ok={cc3?.reachable} good="reachable" bad="unreachable" />
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="col-span-2">
              <p className="text-gray-500">Lender account (SS58 · {cc3?.ss58_format ?? 42})</p>
              <p className="text-white font-mono text-[11px] truncate" title={cc3?.account ?? undefined}>
                {short(cc3?.account, 24)}
              </p>
            </div>
            <div>
              <p className="text-gray-500">Free CTC</p>
              <p className="text-emerald-400 text-lg font-semibold">{fmt(cc3?.free_ctc)}</p>
            </div>
            <div>
              <p className="text-gray-500">Lendable pool</p>
              <p className="text-white text-lg font-semibold">${fmt(cc3?.free_ctc)}</p>
            </div>
          </div>
          <p className="text-[10px] text-gray-500">
            Disbursements are real CC3 testnet <span className="font-mono">transferKeepAlive</span> txs.
          </p>
        </div>
      </div>

      {/* Row 2 — credit decision + human action */}
      <div className="border border-slate-700 rounded-lg p-4 space-y-4 bg-slate-900/40">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Shield size={14} className="text-brand-300" />
            <span className="text-[11px] font-medium uppercase tracking-wider text-gray-400">
              Credit Decision — Human Gate
            </span>
          </div>
          <div className="flex gap-2 text-[10px]">
            <span
              className={clsx(
                "px-1.5 py-0.5 rounded",
                decision
                  ? approved
                    ? "bg-emerald-400/10 text-emerald-400"
                    : "bg-amber-400/10 text-amber-400"
                  : "bg-slate-700 text-slate-400"
              )}
            >
              {decision ? `decision ${short(decision.decision_id, 8)}` : "no decision"}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">
              {decision?.decision_status ?? "—"} · {(decision?.approval_status ?? "—").toUpperCase()}
            </span>
          </div>
        </div>

        {!decision && (
          <p className="text-xs text-gray-500">
            No CreditGraph decision yet — run an assessment to generate the financing terms against the attested NAV.
          </p>
        )}

        {decision && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div>
              <p className="text-gray-500">Recommended</p>
              <p className="text-white font-semibold">${fmt(decision.recommended_amount)}</p>
            </div>
            <div>
              <p className="text-gray-500">Collateral (NAV)</p>
              <p className="text-white font-semibold">${fmt(decision.collateral_value)}</p>
            </div>
            <div>
              <p className="text-gray-500">Credit score</p>
              <p className="text-emerald-400 font-semibold">{fmt(decision.credit_score)}</p>
            </div>
            <div>
              <p className="text-gray-500">PD</p>
              <p className="text-red-400 font-semibold">{(decision.probability_of_default ?? 0).toFixed(1)}%</p>
            </div>
          </div>
        )}

        {/* Execution form (Execute unlocks only after Approve) */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
          <div>
            <label className="block text-[10px] text-gray-500">Borrower CC3 address (to)</label>
            <input
              value={toAddr}
              onChange={(e) => setToAddr(e.target.value)}
              placeholder="5F..."
              className="w-full mt-1 text-xs bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-white placeholder-slate-600 focus:border-brand-400 outline-none"
            />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500">Amount (CTC)</label>
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              type="number" inputMode="decimal" min="0" step="0.01"
              className="w-full mt-1 text-xs bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-white focus:border-brand-400 outline-none"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={approve}
              disabled={approving || !decision || approved || executed}
              className={clsx(
                "text-xs px-3 py-1.5 rounded transition-colors",
                approved || executed
                  ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                  : "bg-brand-500/20 text-brand-200 hover:bg-brand-500/35"
              )}
            >
              {approving ? <Loader2 size={12} className="animate-spin" /> : "Approve"}
            </button>
            <button
              onClick={execute}
              disabled={executing || !approved || executed || !toAddr.trim()}
              className={clsx(
                "text-xs px-3 py-1.5 rounded transition-colors",
                approved && !executed && toAddr.trim()
                  ? "bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/35"
                  : "bg-slate-700 text-slate-400 cursor-not-allowed"
              )}
            >
              {executing ? <Loader2 size={12} className="animate-spin" /> : "Execute"}
            </button>
            <button
              onClick={monitor}
              disabled={monitoring || !(execution?.tx_hash ?? decision?.execution_transaction)}
              className="text-xs px-3 py-1.5 rounded bg-slate-700 text-slate-200 hover:bg-slate-600 disabled:opacity-40"
            >
              {monitoring ? <Loader2 size={12} className="animate-spin" /> : "Monitor"}
            </button>
          </div>
        </div>

        {(execution || decision?.execution_transaction) && (
          <p className="text-[11px] text-gray-500">
            tx <span className="font-mono text-brand-300">{short(execution?.tx_hash ?? decision?.execution_transaction, 20)}</span> · {execution?.status ?? "broadcast"}
          </p>
        )}

        {actionMsg && (
          <p className="text-[11px] text-emerald-400 flex items-center gap-1">
            <CheckCircle2 size={12} /> {actionMsg}
          </p>
        )}
        {actionErr && (
          <p className="text-[11px] text-red-400 flex items-center gap-1">
            <XCircle size={12} /> {actionErr}
          </p>
        )}
      </div>

      {/* Row 3 — attestation report */}
      <div className="border border-slate-700 rounded-lg p-4 bg-slate-900/40">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-medium uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
            <Activity size={13} className="text-brand-300" /> Last attestation cycle
          </span>
          <span className="text-[10px] text-gray-500">
            {report?.generated_at ? new Date(report.generated_at).toLocaleString() : ""}
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs text-gray-300">
          <span>equity <b className="text-white">${fmt(report?.equity)}</b></span>
          <span>buying power <b className="text-white">${fmt(report?.buying_power)}</b></span>
          <span>mode <b className="text-white font-mono">{report?.mode ?? "—"}</b></span>
          <span>verified <b className="text-white">{report?.verified ? "✓" : "—"}</b></span>
        </div>
      </div>
    </div>
  );
}