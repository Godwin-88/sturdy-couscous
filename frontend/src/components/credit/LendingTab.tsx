/**
 * LendingTab.tsx
 * Credit → Lending: H6-9 DeFi vertical — lending pool ON the attested fund claim.
 * Deterministic utilization pricing (HTD Ch.5), LTV/liquidation monitor,
 * strict human-gated borrow (U6/U21). GraphAlpha design system.
 */
import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDollarSign,
  History,
  Loader2,
  Shield,
  XCircle,
} from "lucide-react";
import { api } from "../../lib/creditApi";
import type { LendingLiquidation, LendingPoolState } from "../../types/credit";

const fmt = (n: number | null | undefined, d = 2) =>
  n == null ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

const pct = (n: number | null | undefined, d = 1) =>
  n == null ? "—" : `${(n * 100).toFixed(d)}%`;

function utilPct(u: number | null | undefined) {
  return u == null ? "—" : `${(u * 100).toFixed(1)}%`;
}

function Chip({ good, bad, ok }: { ok: boolean | null | undefined; good: string; bad: string }) {
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


export default function LendingTab() {
  const [pool, setPool] = useState<LendingPoolState | null>(null);
  const [health, setHealth] = useState<LendingLiquidation | null>(null);
  const [busy, setBusy] = useState(true);
  const [actionMsg, setActionMsg] = useState("");
  const [actionErr, setActionErr] = useState("");
  const [pumping, setPumping] = useState(false);
  const [amount, setAmount] = useState("5000");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = async () => {
    try {
      const [p, h] = await Promise.all([api.lendingPool(), api.lendingLiquidation()]);
      setPool(p);
      setHealth(h);
    } catch {
      /* keep last known state */
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
  }, []);

  const run = async (kind: string) => {
    const a = parseFloat(amount || "0");
    if (!(a > 0) || !pool) return;
    setPumping(true);
    setActionErr("");
    setActionMsg("");
    try {
      let r: { ok: boolean; pool?: LendingPoolState; disbursement_tx?: string | null };
      if (kind === "deposit") r = await api.lendingDeposit(a);
      else if (kind === "withdraw") r = await api.lendingWithdraw(a);
      else if (kind === "repay") r = await api.lendingRepay(a);
      else r = await api.lendingBorrow(a);
      if (!r.ok) throw new Error("pool op refused");
      if (r.pool) setPool(r.pool);
      setHealth(await api.lendingLiquidation());
      setActionMsg(
        kind === "borrow" && r.disbursement_tx
          ? `borrowed ${fmt(a)} CTC · CC3 leg ${String(r.disbursement_tx).slice(0, 12)}…`
          : `${kind} ${fmt(a)} CTC · marked-to-model (chain leg pending operator)`,
      );
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : `${kind} failed`);
    } finally {
      setPumping(false);
    }
  };

  const status = pool?.status ?? "open";
  const liq = health?.health ?? "healthy";
  const frozen = status !== "open" || liq !== "healthy";

  return (
    <div className="h-full overflow-y-auto px-4 py-3 space-y-4">
      {busy && pool == null ? (
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <Loader2 size={12} className="animate-spin" /> loading pool…
        </div>
      ) : (
        <>
          {/* Row 0 — liquidation banner */}
          <div
            className={clsx(
              "border rounded-lg px-4 py-2 flex items-center gap-3 text-xs",
              liq === "healthy"
                ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-300"
                : liq === "warning"
                  ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
                  : "border-red-500/50 bg-red-500/10 text-red-400",
            )}
          >
            {liq === "healthy" ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
            <span className="font-medium uppercase tracking-wider">
              {liq === "healthy" ? "Pool healthy" : liq === "warning" ? "LTV WARNING — borrows frozen" : "LIQUIDATABLE"}
            </span>
            <span className="ml-auto font-mono">
              LTV {fmt(health?.ltv_pct, 2)}% · warn ≥ {fmt(health?.warn_threshold_pct, 0)}% · liq ≥ {fmt(health?.liquidate_threshold_pct, 0)}%
            </span>
          </div>

          {/* Row 1 — pool economics */}
          <div className="border border-slate-700 rounded-lg p-4 bg-slate-900/40">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-medium uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
                <CircleDollarSign size={13} className="text-brand-300" /> Pool economics · utilization pricing (HTD Ch.5)
              </span>
              <span className={clsx("text-[10px] px-2 py-0.5 rounded font-mono", status === "open" ? "bg-emerald-400/10 text-emerald-400" : "bg-red-400/10 text-red-400")}>
                {status}
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs text-gray-300">
              <span>Utilization <b className="text-white">{utilPct(pool?.utilization)}</b></span>
              <span>Borrow APR <b className="text-white">{fmt(pool?.borrow_rate_pct, 2)}%</b></span>
              <span>Lend APR <b className="text-white">{fmt(pool?.lend_rate_pct, 2)}%</b></span>
              <span>Reserve <b className="text-white">{pct(pool?.reserve_factor, 0)}</b></span>
            </div>
            <div className="mt-2 flex items-center gap-2 text-[10px] text-gray-500">
              <span className="font-mono">{pool?.pool_id}</span>
              <span>·</span>
              <span>min(LTV cap, liquidity, approved decision) caps the borrowable</span>
            </div>
          </div>

          {/* Row 2 — collateral LTV */}
          <div className="border border-slate-700 rounded-lg p-4 bg-slate-900/40">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-medium uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
                <Shield size={13} className="text-brand-300" /> Collateral — attested strategy NAV
              </span>
              <Chip ok={!frozen} good="borrowable" bad={status === "liquidatable" ? "liquidatable" : "frozen"} />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs text-gray-300">
              <span>Attested NAV <b className="text-white">${fmt(pool?.collateral_value, 2)}</b></span>
              <span>Active loan <b className="text-white">{fmt(pool?.active_loan)} CTC</b></span>
              <span>Deposits <b className="text-white">{fmt(pool?.total_deposits)} CTC</b></span>
              <span>Borrowable <b className="text-white">{fmt(pool?.borrowable)} CTC</b></span>
            </div>
          </div>

          {/* Row 3 — actions (human-gated) */}
          <div className="border border-slate-700 rounded-lg p-4 bg-slate-900/40">
            <div className="text-[11px] font-medium uppercase tracking-wider text-gray-400 mb-2 flex items-center gap-1.5">
              <History size={13} className="text-brand-300" /> Pool actions
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Amount (CTC)</label>
                <input
                  type="number"
                  min="0"
                  step="100"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-36 text-xs bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-white focus:border-brand-400 outline-none"
                />
              </div>
              <button onClick={() => run("deposit")} disabled={pumping || !(parseFloat(amount) > 0)}
                className="text-xs px-3 py-1.5 rounded bg-brand-500/15 text-brand-200 hover:bg-brand-500/30 disabled:opacity-40">Deposit</button>
              <button onClick={() => run("withdraw")} disabled={pumping || !(parseFloat(amount) > 0)}
                className="text-xs px-3 py-1.5 rounded bg-slate-700 text-slate-200 hover:bg-slate-600 disabled:opacity-40">Withdraw</button>
              <button onClick={() => run("borrow")} disabled={pumping || frozen || !(parseFloat(amount) > 0)}
                className={clsx("text-xs px-3 py-1.5 rounded transition-colors",
                  !frozen && !pumping ? "bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/35" : "bg-slate-700 text-slate-400 cursor-not-allowed")}>Borrow</button>
              <button onClick={() => run("repay")} disabled={pumping || !(parseFloat(amount) > 0) || (pool?.active_loan ?? 0) <= 0}
                className="text-xs px-3 py-1.5 rounded bg-slate-700 text-slate-200 hover:bg-slate-600 disabled:opacity-40">Repay</button>
            </div>
            <div className="mt-1.5 text-[10px] text-gray-500">
              Borrow requires a human-approved CreditDecision in the Fund tab (U6/U21) — the chat never executes.
            </div>
            {pool?.disbursement_tx && (
              <p className="mt-2 text-[11px] text-brand-300 font-mono">CC3 disbursement tx {String(pool.disbursement_tx).slice(0, 24)}…</p>
            )}
            {actionMsg && <p className="text-[11px] text-emerald-400 flex items-center gap-1"><CheckCircle2 size={12} /> {actionMsg}</p>}
            {actionErr && <p className="text-[11px] text-red-400 flex items-center gap-1"><XCircle size={12} /> {actionErr}</p>}
          </div>

          {/* Row 4 — event log */}
          {(pool?.events?.length ?? 0) > 0 && (
            <div className="border border-slate-700 rounded-lg p-3 bg-slate-900/30">
              <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1.5">Event log</div>
              <div className="space-y-1 font-mono text-[11px]">
                {pool && pool.events.slice(0, 8).map((ev) => (
                  <div key={`${ev.kind}-${ev.at}`} className="text-gray-400">
                    <span className="text-brand-300">{ev.kind}</span>
                    <span> · {fmt(ev.amount)} CTC</span>
                    {ev.lender && <span> · {ev.lender}</span>}
                    <span className="text-gray-600"> · {new Date((ev.at as number) * 1000).toLocaleTimeString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
