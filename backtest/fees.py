from __future__ import annotations

from typing import Tuple

from .config import cfg


def fee_slippage_for(ticker: str, asset_class: str, venue: str) -> Tuple[float, float]:
    if asset_class == "crypto" and venue == "kraken":
        return cfg.crypto_fee_pct, cfg.crypto_slip_pct
    if asset_class in {"equity_xstock", "macro_proxy"} and venue == "ibkr":
        return cfg.equity_fee_pct, cfg.equity_slip_pct
    raise ValueError(f"No fee schedule for (asset_class={asset_class!r}, venue={venue!r})")
