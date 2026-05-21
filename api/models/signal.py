from pydantic import BaseModel
from typing import Optional


class Signal(BaseModel):
    strategy:        str
    strategy_type:   str
    ticker:          str
    kraken_pair:     str
    direction:       str          # buy | sell
    score:           float
    quant_score:     float
    sentiment_score: float
    reasoning:       str
    graph_path:      list[str]
    regime:          str


class Order(BaseModel):
    order_id:         str
    strategy:         Optional[str]
    ticker:           str
    kraken_pair:      str
    direction:        str
    quantity:         float
    notional_usd:     float
    kelly_fraction:   float
    var_contribution: float
    price_estimate:   float
    fill_price:       Optional[float]
    fee_usd:          Optional[float]
    mode:             str
    status:           str
    timestamp:        str
