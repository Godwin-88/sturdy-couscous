"""
Double-entry accounting models — accounts, journal_entries, journal_lines.
Ref: TRANSACT_APP_SPEC.md § 3.8; plan: sum(debits) = sum(credits) per entry.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

Base = declarative_base()


def get_engine():
    url = os.getenv("DATABASE_URL", "postgresql://pricing_engine:pricing_engine_kb@localhost:5432/blotter")
    return create_engine(url, pool_pre_ping=True, echo=False)


def get_session_factory():
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


_session_factory: Optional[sessionmaker] = None


def get_session() -> Session:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _session_factory()


def init_db():
    """Create all tables. Safe to call on startup."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _seed_accounts_if_empty()


def _seed_accounts_if_empty():
    session = get_session()
    try:
        if session.query(Account).count() > 0:
            return
        defaults = [
            ("1000", "Cash", "asset"),
            ("2000", "Securities", "asset"),
            ("3000", "Realized P&L", "income"),
            ("4000", "Unrealized P&L", "income"),
            ("5000", "Commission / Expense", "expense"),
        ]
        for code, name, acct_type in defaults:
            session.add(Account(code=code, name=name, type=acct_type))
        session.commit()
    finally:
        session.close()


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(32), nullable=False)  # asset | liability | equity | income | expense
    created_at = Column(DateTime, default=datetime.utcnow)

    lines = relationship("JournalLine", back_populates="account")

    def __repr__(self):
        return f"<Account {self.code} {self.name}>"


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    date = Column(Date, nullable=False, index=True)
    description = Column(Text, nullable=True)
    reference_type = Column(String(64), nullable=True)  # trade | adjustment | close
    reference_id = Column(String(255), nullable=True)  # e.g. trade id
    created_at = Column(DateTime, default=datetime.utcnow)

    lines = relationship("JournalLine", back_populates="journal", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<JournalEntry {self.id} {self.date}>"


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    journal_id = Column(String(36), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String(36), ForeignKey("accounts.id"), nullable=False, index=True)
    debit_amount = Column(Numeric(20, 4), nullable=False, default=Decimal("0"))
    credit_amount = Column(Numeric(20, 4), nullable=False, default=Decimal("0"))
    currency = Column(String(8), nullable=False, default="USD")

    journal = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", back_populates="lines")

    __table_args__ = (
        CheckConstraint("debit_amount >= 0", name="chk_debit_nonneg"),
        CheckConstraint("credit_amount >= 0", name="chk_credit_nonneg"),
    )

    def __repr__(self):
        return f"<JournalLine {self.account_id} Dr {self.debit_amount} Cr {self.credit_amount}>"


class Trade(Base):
    """Denormalized trade record for positions/history API; journal entry holds double-entry."""
    __tablename__ = "trades"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset = Column(String(64), nullable=False, index=True)
    direction = Column(String(8), nullable=False)  # long | short
    quantity = Column(Numeric(20, 4), nullable=False)
    entry_price = Column(Numeric(20, 4), nullable=False)
    entry_date = Column(Date, nullable=False, index=True)
    model_used = Column(String(64), nullable=True)
    theoretical_price_at_entry = Column(Numeric(20, 4), nullable=True)
    strategy_tag = Column(String(128), nullable=True)
    asset_class = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
