"""
DB-backed blotter: trades and positions from Postgres (double-entry ledger).
When DATABASE_URL is set, use this; else fall back to in-memory TradeStore.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    from app.accounting import get_session, init_db, get_ledger_service
    from app.accounting.models import Trade
    _ACCOUNTING_AVAILABLE = True
except ImportError:
    _ACCOUNTING_AVAILABLE = False
    Trade = None  # type: ignore
    get_session = None  # type: ignore
    init_db = None  # type: ignore
    get_ledger_service = None  # type: ignore


def use_db_blotter() -> bool:
    return bool(_ACCOUNTING_AVAILABLE and os.getenv("DATABASE_URL"))


def ensure_db_init():
    if use_db_blotter() and init_db:
        init_db()


def add_trade(
    asset: str,
    direction: str,
    quantity: float,
    entry_price: float,
    entry_date: Optional[str] = None,
    model_used: Optional[str] = None,
    theoretical_price: Optional[float] = None,
    strategy_tag: Optional[str] = None,
    asset_class: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist trade to DB and ledger. Returns trade dict with id."""
    if not use_db_blotter() or not get_ledger_service:
        return {}
    ensure_db_init()
    session = get_session()
    try:
        dt = datetime.strptime(entry_date, "%Y-%m-%d").date() if entry_date else date.today()
        total = quantity * entry_price
        trade = Trade(
            asset=asset,
            direction=direction.lower(),
            quantity=Decimal(str(quantity)),
            entry_price=Decimal(str(entry_price)),
            entry_date=dt,
            model_used=model_used,
            theoretical_price_at_entry=Decimal(str(theoretical_price)) if theoretical_price is not None else None,
            strategy_tag=strategy_tag,
            asset_class=asset_class,
        )
        session.add(trade)
        session.commit()
        session.refresh(trade)
        ledger = get_ledger_service()
        ledger.create_trade_entry(
            trade_id=str(trade.id),
            asset=asset,
            direction=direction,
            quantity=quantity,
            entry_price=entry_price,
            total_amount=total,
            entry_date=dt,
        )
        return {
            "id": trade.id,
            "asset": trade.asset,
            "direction": trade.direction,
            "quantity": float(trade.quantity),
            "entry_price": float(trade.entry_price),
            "entry_date": trade.entry_date.isoformat(),
        }
    finally:
        session.close()


def get_trades_from_db(
    asset: Optional[str] = None,
    strategy_tag: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return list of trades from DB."""
    if not use_db_blotter() or get_session is None:
        return []
    ensure_db_init()
    session = get_session()
    try:
        q = session.query(Trade).order_by(Trade.entry_date.desc(), Trade.created_at.desc())
        if asset:
            q = q.filter(Trade.asset == asset)
        if strategy_tag:
            q = q.filter(Trade.strategy_tag == strategy_tag)
        if from_date:
            q = q.filter(Trade.entry_date >= datetime.strptime(from_date, "%Y-%m-%d").date())
        if to_date:
            q = q.filter(Trade.entry_date <= datetime.strptime(to_date, "%Y-%m-%d").date())
        rows = q.all()
        return [
            {
                "id": t.id,
                "asset": t.asset,
                "direction": t.direction,
                "quantity": float(t.quantity),
                "entry_price": float(t.entry_price),
                "entry_date": t.entry_date.isoformat(),
                "model_used": t.model_used,
                "theoretical_price_at_entry": float(t.theoretical_price_at_entry) if t.theoretical_price_at_entry else None,
                "strategy_tag": t.strategy_tag,
            }
            for t in rows
        ]
    finally:
        session.close()


def get_journal(from_date: Optional[str] = None, to_date: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
    """Journal entries with lines for ledger view."""
    if not use_db_blotter() or not get_ledger_service:
        return []
    ensure_db_init()
    from datetime import datetime as dt
    fd = dt.strptime(from_date, "%Y-%m-%d").date() if from_date else None
    td = dt.strptime(to_date, "%Y-%m-%d").date() if to_date else None
    return get_ledger_service().get_ledger(from_date=fd, to_date=td, limit=limit)


def get_accounts_balances(as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Account list with balances for trial balance / ledger view."""
    if not use_db_blotter() or not get_ledger_service:
        return []
    ensure_db_init()
    from datetime import datetime as dt
    ad = dt.strptime(as_of_date, "%Y-%m-%d").date() if as_of_date else None
    return get_ledger_service().get_account_balances(as_of_date=ad)


def get_positions_from_db(current_prices: Dict[str, float]) -> List[Dict[str, Any]]:
    """Aggregate trades into positions with P&L (from DB)."""
    trades = get_trades_from_db()
    by_key: Dict[tuple, Dict[str, Any]] = {}
    for t in trades:
        key = (t["asset"], t["direction"])
        mult = 1 if t["direction"] == "long" else -1
        qty = t["quantity"] * mult
        if key not in by_key:
            by_key[key] = {"qty": 0, "cost": 0.0, "entry_date": t["entry_date"]}
        by_key[key]["qty"] += qty
        by_key[key]["cost"] += qty * t["entry_price"]
    out = []
    for (asset, direction), data in by_key.items():
        qty = data["qty"]
        if qty == 0:
            continue
        avg = data["cost"] / qty
        cur = current_prices.get(asset, avg)
        pnl = (cur - avg) * qty
        pnl_pct = (pnl / (avg * abs(qty)) * 100) if avg * qty != 0 else 0
        out.append({
            "asset": asset,
            "quantity": abs(qty),
            "direction": "long" if qty > 0 else "short",
            "entry_price": avg,
            "entry_date": data["entry_date"],
            "current_price": cur,
            "unrealized_pnl": pnl,
            "unrealized_pnl_pct": pnl_pct,
        })
    return out
