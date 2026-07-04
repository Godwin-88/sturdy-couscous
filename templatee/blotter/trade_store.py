"""
Trade Store — basic trade entry and P&L tracking.
In-memory store; can be extended to SQLite.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import uuid


@dataclass
class Trade:
    """Single trade record."""
    id: str
    asset: str
    direction: str  # "long" | "short"
    quantity: float
    entry_price: float
    entry_date: str
    model_used: Optional[str] = None
    theoretical_price_at_entry: Optional[float] = None
    strategy_tag: Optional[str] = None
    asset_class: Optional[str] = None


@dataclass
class Position:
    """Aggregated position with live P&L."""
    asset: str
    quantity: float
    direction: str
    entry_price: float
    entry_date: str
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class TradeStore:
    """In-memory trade ledger."""

    def __init__(self):
        self._trades: List[Trade] = []

    def add_trade(
        self,
        asset: str,
        direction: str,
        quantity: float,
        entry_price: float,
        entry_date: Optional[str] = None,
        model_used: Optional[str] = None,
        theoretical_price: Optional[float] = None,
        strategy_tag: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> Trade:
        """Add a new trade."""
        trade = Trade(
            id=str(uuid.uuid4()),
            asset=asset,
            direction=direction.lower(),
            quantity=abs(quantity),
            entry_price=entry_price,
            entry_date=entry_date or datetime.utcnow().strftime("%Y-%m-%d"),
            model_used=model_used,
            theoretical_price_at_entry=theoretical_price,
            strategy_tag=strategy_tag,
            asset_class=asset_class,
        )
        self._trades.append(trade)
        return trade

    def get_trades(
        self,
        asset: Optional[str] = None,
        strategy_tag: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Trade]:
        """Filter trades."""
        out = self._trades
        if asset:
            out = [t for t in out if t.asset == asset]
        if strategy_tag:
            out = [t for t in out if t.strategy_tag == strategy_tag]
        if from_date:
            out = [t for t in out if t.entry_date >= from_date]
        if to_date:
            out = [t for t in out if t.entry_date <= to_date]
        return out

    def get_positions(
        self,
        current_prices: dict,
        as_of_date: Optional[str] = None,
    ) -> List[Position]:
        """Aggregate trades into positions with P&L. If as_of_date given, only include trades on/before that date."""
        positions: dict = {}
        trades = self._trades
        if as_of_date:
            trades = [t for t in trades if t.entry_date <= as_of_date]
        for t in trades:
            key = (t.asset, t.direction)
            if key not in positions:
                positions[key] = {"qty": 0, "cost": 0.0, "entry_date": t.entry_date}
            mult = 1 if t.direction == "long" else -1
            positions[key]["qty"] += mult * t.quantity
            positions[key]["cost"] += mult * t.quantity * t.entry_price

        result = []
        for (asset, direction), data in positions.items():
            qty = data["qty"]
            if qty == 0:
                continue
            avg_price = data["cost"] / qty if qty != 0 else 0
            current = current_prices.get(asset, avg_price)
            pnl = (current - avg_price) * qty
            pnl_pct = (pnl / (avg_price * abs(qty)) * 100) if avg_price * qty != 0 else 0
            result.append(
                Position(
                    asset=asset,
                    quantity=abs(qty),
                    direction="long" if qty > 0 else "short",
                    entry_price=avg_price,
                    entry_date=data["entry_date"],
                    current_price=current,
                    unrealized_pnl=pnl,
                    unrealized_pnl_pct=pnl_pct,
                )
            )
        return result

    def get_cumulative_pnl(
        self,
        current_prices: dict,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> float:
        """Total unrealized P&L across all positions."""
        positions = self.get_positions(current_prices)
        return sum(p.unrealized_pnl for p in positions)

    def get_history(self) -> List[dict]:
        """Full transaction history as dicts."""
        return [
            {
                "id": t.id,
                "asset": t.asset,
                "direction": t.direction,
                "quantity": t.quantity,
                "entry_price": t.entry_price,
                "entry_date": t.entry_date,
                "model_used": t.model_used,
                "theoretical_price_at_entry": t.theoretical_price_at_entry,
                "strategy_tag": t.strategy_tag,
            }
            for t in self._trades
        ]

    def get_pnl_timeseries(
        self,
        price_history: List[dict],
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[dict]:
        """
        Build cumulative P&L time series from price history.
        price_history: [{"date": "2024-01-01", "prices": {"AAPL": 150, "GOOG": 140}}, ...]
        Returns: [{"date": str, "cumulative_pnl": float, "positions_value": float}, ...]
        """
        out = []
        sorted_ph = sorted(price_history, key=lambda x: x.get("date", ""))
        for ph in sorted_ph:
            date = ph.get("date", "")
            prices = ph.get("prices", {})
            if from_date and date < from_date:
                continue
            if to_date and date > to_date:
                continue
            positions = self.get_positions(prices, as_of_date=date)
            total_cost = sum(
                p.entry_price * p.quantity * (1 if p.direction == "long" else -1)
                for p in positions
            )
            total_value = sum(
                prices.get(p.asset, p.entry_price) * p.quantity * (1 if p.direction == "long" else -1)
                for p in positions
            )
            cum_pnl = total_value - total_cost if total_cost != 0 else 0
            out.append({
                "date": date,
                "cumulative_pnl": cum_pnl,
                "positions_value": total_value,
            })
        return out


# Singleton for API use
_store: Optional[TradeStore] = None


def get_trade_store() -> TradeStore:
    global _store
    if _store is None:
        _store = TradeStore()
    return _store
