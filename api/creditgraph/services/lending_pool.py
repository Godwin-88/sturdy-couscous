"""Lending pool on the attested fund claim (H6-9 / DeFi track).

Implements a deterministic, Redis-backed pool where external "lenders" deposit
CTC (held by the CC3 executor) and the strategy fund (borrower fund_graphalpha)
borrows against its ATTESTED NAV collateral. The money leg forwards disbursement
to the Creditcoin execution-service (`balances.transferKeepAlive`) when reachable;
when offline the pool still marks-to-model so the UI and chat stay honest.

Financial-engineering rules encoded (How-to-DeFi Ch.5 + WQU credit engine):
  - utilization pricing: u = active_loan / total_deposits
        borrow_rate_pct = BASE + SLOPE * u**2        (quadratic; rises with utilisation)
        lend_rate_pct    = borrow_rate_pct * u * (1 - reserve_factor)
  - borrow capacity     = min(collateral_ltv_cap, liquidity_cap, approved_recommendation)
        collateral_ltv_cap = attested_NAV * MAX_LTV_PCT
        liquidity_cap      = total_deposits - active_loan
  - liquidation monitor: ltv_pct = active_loan / attested_NAV
        >= WARN_PCT  -> amber warning, freeze new borrows
        >= LIQ_PCT   -> liquidatable (status = liquidatable), pool frozen
  - human gate (U6/U21): borrow requires the H3-6 CreditDecision to be
        approval_status == "approved" AND amount <= recommended_amount.
        No LLM/agent can originate a loan without that explicit approval.

All pure functions are deterministic; state is time-stamped and event-logged.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import redis

# ── Pool constants (deterministic, env-tunable) ─────────────────────────────
POOL_KEY = "creditgraph:lending_pool"
BORROWER_ID = os.getenv("FUND_BORROWER_ID", "fund_graphalpha")

BASE_BORROW_RATE_PCT = float(os.getenv("LENDING_BASE_RATE_PCT", "3.0"))
SLOPE_PCT = float(os.getenv("LENDING_RATE_SLOPE_PCT", "18.0"))
RESERVE_FACTOR = float(os.getenv("LENDING_RESERVE_FACTOR", "0.2"))
MAX_LTV_PCT = float(os.getenv("LENDING_MAX_LTV_PCT", "60.0"))
LIQUIDATION_WARN_PCT = float(os.getenv("LENDING_WARN_LTV_PCT", "70.0"))
LIQUIDATION_LTV_PCT = float(os.getenv("LENDING_LIQ_LTV_PCT", "80.0"))

QUOTE_DECIMALS = 6  # planck units of display precision in the API


def _r() -> redis.Redis:
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


def _default_pool() -> dict[str, Any]:
    return {
        "pool_id": "fund_graphalpha_lending_pool",
        "borrower_id": BORROWER_ID,
        "status": "open",                     # open | frozen | liquidatable
        "warning": None,                      # None | "ltv_warning" | "ltv_breach"
        "total_deposits": float(os.getenv("LENDING_INITIAL_DEPOSITS", "0.0")),
        "active_loan": 0.0,
        "reserve_factor": RESERVE_FACTOR,
        "max_ltv_pct": MAX_LTV_PCT,
        "borrow_rate_pct": BASE_BORROW_RATE_PCT,
        "lend_rate_pct": 0.0,
        "utilization": 0.0,
        "collateral_value": 0.0,
        "ltv_pct": 0.0,
        "borrowable": 0.0,
        "disbursement_tx": None,
        "last_borrow_decision": None,
        "events": [],
        "updated_at": time.time(),
    }


def load_pool() -> dict[str, Any]:
    raw = _r().get(POOL_KEY)
    if not raw:
        pool = _default_pool()
        _r().set(POOL_KEY, json.dumps(pool))
        return pool
    pool = json.loads(raw)
    # forward-compat fill of defaults
    base = _default_pool()
    for k, v in base.items():
        pool.setdefault(k, v)
    return pool


def save_pool(pool: dict[str, Any]) -> None:
    pool["updated_at"] = time.time()
    _r().set(POOL_KEY, json.dumps(pool), ex=7 * 24 * 3600)


def _push_event(pool: dict[str, Any], kind: str, detail: dict[str, Any], max_len: int = 60) -> None:
    pool["events"].insert(0, {"kind": kind, "at": time.time(), **detail})
    pool["events"] = pool["events"][:max_len]
def _attested_collateral() -> float:
    """Best-effort: read the fund's latest attested NAV from Redis.

    Falls back to the pool's stored collateral so the pool never zeroes out on
    a Redis-key miss (monitor-first, model-second financial posture).
    """
    try:
        raw = _r().get("fund:attestation_report")
        if raw:
            report = json.loads(raw)
            nav = report.get("nav") or report.get("equity") or 0.0
            if nav > 0:
                return float(nav)
    except Exception:
        pass
    return load_pool().get("collateral_value", 0.0)


def compute_rates(pool: dict[str, Any]) -> dict[str, float]:
    """Deterministic utilization-based pricing (HTD Ch.5)."""
    u = 0.0
    if pool.get("total_deposits", 0.0) > 0:
        u = min(1.0, pool.get("active_loan", 0.0) / pool["total_deposits"])
    borrow = BASE_BORROW_RATE_PCT + SLOPE_PCT * (u * u)
    lend = borrow * u * (1.0 - RESERVE_FACTOR)
    return {"utilization": round(u, 6), "borrow_rate_pct": round(borrow, 4), "lend_rate_pct": round(lend, 4)}


def _recompute(pool: dict[str, Any]) -> dict[str, Any]:
    """Re-price + re-assess LTV/liquidation from current balances."""
    rates = compute_rates(pool)
    pool.update(rates)

    collateral = _attested_collateral()
    if collateral:
        pool["collateral_value"] = round(collateral, 2)

    ltv = 0.0
    ltv_cap = pool.get("collateral_value", 0.0) * pool.get("max_ltv_pct", MAX_LTV_PCT) / 100.0
    liquidity = max(0.0, pool.get("total_deposits", 0.0) - pool.get("active_loan", 0.0))
    if pool.get("collateral_value", 0.0) > 0:
        ltv = pool.get("active_loan", 0.0) / pool["collateral_value"] * 100.0
    pool["ltv_pct"] = round(ltv, 4)
    pool["borrowable"] = round(min(ltv_cap, liquidity), 6)

    # Liquidation posture (financial-engineer priorities)
    if pool["status"] != "liquidatable":
        if ltv >= LIQUIDATION_LTV_PCT:
            pool["status"] = "liquidatable"
            pool["warning"] = "ltv_breach"
        elif ltv >= LIQUIDATION_WARN_PCT:
            pool["status"] = "frozen"
            pool["warning"] = "ltv_warning"
        else:
            pool["status"] = "open"
            pool["warning"] = None

    save_pool(pool)
    return pool


def public_pool_snapshot(pool: dict[str, Any] | None = None) -> dict[str, Any]:
    p = _recompute(load_pool() if pool is None else pool)
    return {
        "pool_id": p["pool_id"],
        "borrower_id": p["borrower_id"],
        "status": p["status"],
        "warning": p["warning"],
        "total_deposits": round(p.get("total_deposits", 0.0), QUOTE_DECIMALS),
        "active_loan": round(p.get("active_loan", 0.0), QUOTE_DECIMALS),
        "utilization": p.get("utilization"),
        "borrow_rate_pct": p.get("borrow_rate_pct"),
        "lend_rate_pct": p.get("lend_rate_pct"),
        "reserve_factor": p.get("reserve_factor"),
        "max_ltv_pct": p.get("max_ltv_pct"),
        "collateral_value": p.get("collateral_value"),
        "ltv_pct": p.get("ltv_pct"),
        "borrowable": p.get("borrowable"),
        "liquidation_warn_pct": LIQUIDATION_WARN_PCT,
        "liquidation_ltv_pct": LIQUIDATION_LTV_PCT,
        "disbursement_tx": p.get("disbursement_tx"),
        "last_borrow_decision": p.get("last_borrow_decision"),
        "events": p.get("events", [])[:15],
        "updated_at": p.get("updated_at"),
    }


def deposit(amount: float, lender_id: str = "cc3_lender") -> dict[str, Any]:
    if amount <= 0:
        return {"ok": False, "error": "amount must be > 0"}
    pool = load_pool()
    if pool["status"] == "liquidatable":
        return {"ok": False, "error": "pool liquidatable — deposits frozen"}
    pool["total_deposits"] = round(pool.get("total_deposits", 0.0) + amount, QUOTE_DECIMALS)
    _push_event(pool, "deposit", {"lender": lender_id, "amount": amount})
    _recompute(pool)
    return {"ok": True, "pool": public_pool_snapshot(pool)}


def withdraw(amount: float, lender_id: str = "cc3_lender") -> dict[str, Any]:
    if amount <= 0:
        return {"ok": False, "error": "amount must be > 0"}
    pool = load_pool()
    available = pool.get("total_deposits", 0.0) - pool.get("active_loan", 0.0)
    if amount > available:
        return {
            "ok": False,
            "error": f"insufficient un-lent liquidity — {available:.4f} CTC available",
        }
    pool["total_deposits"] = round(pool.get("total_deposits", 0.0) - amount, QUOTE_DECIMALS)
    _push_event(pool, "withdraw", {"lender": lender_id, "amount": amount})
    _recompute(pool)
    return {"ok": True, "pool": public_pool_snapshot(pool)}


def _approved_decision_cap() -> dict[str, float | None]:
    """The latest HUMAN-APPROVED H3-6 decision for the fund (best-effort, from KG)."""
    try:
        import asyncio

        from creditgraph.graph.credit_graph import list_credit_decisions

        async def _latest_approved() -> dict[str, float | None]:
            rows = await list_credit_decisions(BORROWER_ID)
            for d in rows:
                if getattr(d, "approval_status", None) == "approved":
                    return {
                        "decision_id": getattr(d, "decision_id", None),
                        "recommended_amount": getattr(d, "recommended_amount", None),
                    }
            return {}

        return asyncio.run(_latest_approved())
    except Exception:
        return {}


def borrow(amount: float) -> dict[str, Any]:
    """Borrow CTC against the attested NAV — requires a human-approved decision.

    Returns an error (409-class) if: pool is frozen/liquidatable, amount <= 0,
    no approved CreditDecision, or amount exceeds the recommendation or capacity.
    """
    if amount <= 0:
        return {"ok": False, "error": "amount must be > 0"}
    pool = load_pool()
    if pool["status"] in ("frozen", "liquidatable"):
        return {"ok": False, "error": f"pool {pool['status']} — borrows frozen"}
    if pool["warning"]:
        return {"ok": False, "error": f"liquidation {pool['warning']} — borrows frozen"}

    approved = _approved_decision_cap()
    if not approved.get("decision_id"):
        return {
            "ok": False,
            "error": "no human-approved CreditDecision — borrow requires approval (U6/U21)",
        }
    rec = float(approved.get("recommended_amount") or 0.0)
    if amount > rec:
        return {"ok": False, "error": f"amount {amount} exceeds decision recommendation {rec:.2f}"}

    _recompute(pool)
    if amount > pool.get("borrowable", 0.0):
        return {"ok": False, "error": f"amount {amount} exceeds borrowable {pool['borrowable']:.4f}"}

    pool["active_loan"] = round(pool.get("active_loan", 0.0) + amount, QUOTE_DECIMALS)
    pool["last_borrow_decision"] = approved["decision_id"]
    _push_event(pool, "borrow", {"amount": amount, "decision_id": approved["decision_id"]})
    _recompute(pool)

    # Money leg: forward to Creditcoin execution-service (best-effort, non-fatal).
    tx = None
    try:
        import httpx

        exc_url = os.getenv("EXECUTION_SERVICE_URL", "http://execution-service:8081")
        r = httpx.post(
            f"{exc_url}/execute",
            json={"to": BORROWER_ID, "amount": amount},
            timeout=8,
        )
        if r.status_code == 200:
            tx = r.json().get("txHash") or r.json().get("hash")
    except Exception:
        tx = None
    pool["disbursement_tx"] = tx
    save_pool(pool)

    return {"ok": True, "disbursement_tx": tx, "pool": public_pool_snapshot(pool)}


def repay(amount: float) -> dict[str, Any]:
    if amount <= 0:
        return {"ok": False, "error": "amount must be > 0"}
    pool = load_pool()
    if amount > pool.get("active_loan", 0.0):
        return {"ok": False, "error": "repay exceeds active_loan"}
    pool["active_loan"] = round(pool.get("active_loan", 0.0) - amount, QUOTE_DECIMALS)
    _push_event(pool, "repay", {"amount": amount})
    _recompute(pool)
    return {"ok": True, "pool": public_pool_snapshot(pool)}


def liquidation_monitor() -> dict[str, Any]:
    snapshot = public_pool_snapshot()
    ltv = snapshot.get("ltv_pct", 0.0)
    health = "liquidatable" if ltv >= LIQUIDATION_LTV_PCT else (
        "warning" if ltv >= LIQUIDATION_WARN_PCT else "healthy"
    )
    return {
        "health": health,
        "ltv_pct": snapshot["ltv_pct"],
        "collateral_value": snapshot["collateral_value"],
        "active_loan": snapshot["active_loan"],
        "warn_threshold_pct": LIQUIDATION_WARN_PCT,
        "liquidate_threshold_pct": LIQUIDATION_LTV_PCT,
        "closing_liquidation_price": round(
            snapshot["active_loan"] / (LIQUIDATION_LTV_PCT / 100.0), 2
        )
        if snapshot["active_loan"] > 0 and snapshot.get("collateral_value")
        else None,
    }