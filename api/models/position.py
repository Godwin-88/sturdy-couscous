from pydantic import BaseModel
from typing import Optional


class Position(BaseModel):
    ticker:           str
    direction:        str
    quantity:         float
    avg_entry_price:  float
    current_price:    float
    notional:         float
    unrealised_pnl:   Optional[float] = None
    status:           str


class PortfolioState(BaseModel):
    nav:               float
    cash:              float
    unrealised_pnl_usd: float
    positions:         list[Position]
    drawdown_pct:      float
    halted:            bool
