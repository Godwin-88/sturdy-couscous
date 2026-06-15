from pydantic import BaseModel
from typing import List, Optional


class Signal(BaseModel):
    schema_version: int
    cycle_id: str
    timestamp: str
    regime: str
    strategy: str
    ticker: str
    venue: str
    venue_symbol: str
    asset_class: str
    direction: str
    score: float
    quant_score: float
    sentiment_score: float
    news_overlay: float
    macro_overlay: float
    kg_formula_contribution: float
    graph_path: List[str]
    contradiction_blocked: bool


class Order(BaseModel):
    schema_version: int
    order_id: str
    cycle_id: str
    ticker: str
    venue: str
    venue_symbol: str
    direction: str
    quantity: float
    notional_usd: float
    kelly_fraction: float
    var_contribution_pct: float
    mode: str
    risk_checks: dict

