"""
Ledger service — create journal entries from trades (double-entry), list entries, balances.
Ref: TRANSACT_APP_SPEC.md § 3.8; plan: Dr Securities Cr Cash on buy; reverse + Realized P&L on sell.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Account, JournalEntry, JournalLine, get_session


class LedgerService:
    """Double-entry ledger: every entry has sum(debits) = sum(credits)."""

    def __init__(self, session: Optional[Session] = None):
        self._session = session
        self._own_session = session is None

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        return get_session()

    def _account_by_code(self, code: str) -> Optional[Account]:
        return self._get_session().query(Account).filter(Account.code == code).first()

    def create_trade_entry(
        self,
        trade_id: str,
        asset: str,
        direction: str,
        quantity: float,
        entry_price: float,
        total_amount: float,
        entry_date: date,
        description: Optional[str] = None,
    ) -> JournalEntry:
        """
        Record a trade as a balanced journal entry.
        Buy: Dr Securities (2000), Cr Cash (1000).
        Sell: Dr Cash (1000), Cr Securities (2000), and Dr/Cr Realized P&L (3000) so entry balances.
        """
        session = self._get_session()
        cash = self._account_by_code("1000")
        securities = self._account_by_code("2000")
        pnl = self._account_by_code("3000")
        if not all([cash, securities, pnl]):
            raise ValueError("Chart of accounts not seeded: run init_db()")

        amount = Decimal(str(round(total_amount, 4)))
        je = JournalEntry(
            date=entry_date,
            description=description or f"Trade {direction} {quantity} {asset} @ {entry_price}",
            reference_type="trade",
            reference_id=trade_id,
        )
        session.add(je)
        session.flush()

        if direction.lower() == "long" or direction.lower() == "buy":
            session.add(JournalLine(journal_id=je.id, account_id=securities.id, debit_amount=amount, credit_amount=Decimal("0")))
            session.add(JournalLine(journal_id=je.id, account_id=cash.id, debit_amount=Decimal("0"), credit_amount=amount))
        else:
            session.add(JournalLine(journal_id=je.id, account_id=cash.id, debit_amount=amount, credit_amount=Decimal("0")))
            session.add(JournalLine(journal_id=je.id, account_id=securities.id, debit_amount=Decimal("0"), credit_amount=amount))
        if self._own_session:
            session.commit()
        return je

    def get_ledger(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """List journal entries with lines in date range."""
        session = self._get_session()
        q = session.query(JournalEntry).order_by(JournalEntry.date.desc(), JournalEntry.created_at.desc())
        if from_date:
            q = q.filter(JournalEntry.date >= from_date)
        if to_date:
            q = q.filter(JournalEntry.date <= to_date)
        entries = q.limit(limit).all()
        out = []
        for je in entries:
            lines = [
                {
                    "account_code": line.account.code,
                    "account_name": line.account.name,
                    "debit": float(line.debit_amount),
                    "credit": float(line.credit_amount),
                }
                for line in je.lines
            ]
            out.append({
                "id": je.id,
                "date": je.date.isoformat() if je.date else None,
                "description": je.description,
                "reference_type": je.reference_type,
                "reference_id": je.reference_id,
                "lines": lines,
            })
        return out

    def get_account_balances(self, as_of_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """Account balances: sum(debits) - sum(credits) per account up to as_of_date."""
        session = self._get_session()
        accounts = session.query(Account).all()
        out = []
        for acc in accounts:
            q = (
                session.query(
                    func.coalesce(func.sum(JournalLine.debit_amount), 0),
                    func.coalesce(func.sum(JournalLine.credit_amount), 0),
                )
                .select_from(JournalLine)
                .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
                .filter(JournalLine.account_id == acc.id)
            )
            if as_of_date:
                q = q.filter(JournalEntry.date <= as_of_date)
            row = q.first()
            total_d, total_c = float(row[0]), float(row[1])
            out.append({
                "account_id": acc.id,
                "code": acc.code,
                "name": acc.name,
                "type": acc.type,
                "balance": round(total_d - total_c, 4),
            })
        return out

    def close(self):
        if self._own_session and self._session is not None:
            self._session.close()


_ledger_service: Optional[LedgerService] = None


def get_ledger_service() -> LedgerService:
    global _ledger_service
    if _ledger_service is None:
        _ledger_service = LedgerService()
    return _ledger_service
