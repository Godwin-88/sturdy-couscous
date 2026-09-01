from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats


def sharpe(returns: np.ndarray, rf: float = 0.05) -> float:
    daily_rf = rf / 252
    excess = returns - daily_rf
    return float(np.sqrt(252) * excess.mean() / excess.std()) if excess.std() > 0 else 0.0

def sortino(returns: np.ndarray, rf: float = 0.05) -> float:
    daily_rf = rf / 252
    excess = returns - daily_rf
    downside = excess[excess < 0]
    downside_std = np.sqrt(np.mean(downside**2)) if len(downside) > 0 else 0
    return float(np.sqrt(252) * excess.mean() / downside_std) if downside_std > 0 else 0.0


def calmar(returns: np.ndarray) -> float:
    total = (1 + returns).prod() - 1
    dd = max_drawdown(returns)
    return float(total / abs(dd)) if dd != 0 else 0.0


def max_drawdown(returns: np.ndarray) -> float:
    cum = (1 + returns).cumprod()
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    return float(dd.min())


def total_return(returns: np.ndarray) -> float:
    return float((1 + returns).prod() - 1)


def jobson_korkie(r1: np.ndarray, r2: np.ndarray) -> tuple[float, float]:
    n = len(r1)
    sr1 = sharpe(r1)
    sr2 = sharpe(r2)

    mu1, mu2 = r1.mean(), r2.mean()
    s1, s2   = r1.std(), r2.std()
    s12      = np.cov(r1, r2)[0, 1]

    theta = (
        (1 / n) * (
            2 * s1**2 * s2**2
            - 2 * s1 * s2 * s12
            + 0.5 * mu1**2 * s2**2
            + 0.5 * mu2**2 * s1**2
            - (mu1 * mu2 * s12**2) / (s1 * s2)
        )
    ) / (s1**2 * s2**2)

    z = (sr1 - sr2) / np.sqrt(max(theta, 1e-12))
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return float(z), float(p)


# Update the `summary` function signature and body
def summary(returns: np.ndarray, benchmark: np.ndarray = None, rf: float = 0.05) -> dict:
    result = {
        "total_return":    round(total_return(returns), 4),
        "sharpe_ratio":    round(sharpe(returns, rf=rf), 3),
        "sortino_ratio":   round(sortino(returns, rf=rf), 3), # NEW
        "calmar_ratio":    round(calmar(returns), 3),
        "max_drawdown":    round(max_drawdown(returns), 4),
        "ann_volatility":  round(returns.std() * np.sqrt(252), 4),
        "n_days":          len(returns),
    }
    if benchmark is not None and len(benchmark) > 0:
        z, p = jobson_korkie(returns, benchmark)
        result["jk_z_stat"]       = round(z, 3)
        result["jk_p_value"]      = round(p, 4)
        result["jk_significant"]  = bool(p < 0.05)
    return result



def profit_factor(trade_pnls: np.ndarray) -> Optional[float]:
    if len(trade_pnls) == 0:
        return None
    gross_profit = float(trade_pnls[trade_pnls > 0].sum())
    gross_loss   = float(abs(trade_pnls[trade_pnls < 0].sum()))
    if gross_loss == 0.0:
        return None
    return gross_profit / gross_loss


def win_rate(trade_pnls: np.ndarray) -> float:
    if len(trade_pnls) == 0:
        return 0.0
    return float((trade_pnls > 0).sum() / len(trade_pnls))


def avg_hold_days(
    entry_dates: list[pd.Timestamp],
    exit_dates:  list[pd.Timestamp],
) -> Optional[float]:
    if not entry_dates or not exit_dates or len(entry_dates) != len(exit_dates):
        return None
    holds = [
        (ex - en).total_seconds() / 86400.0
        for en, ex in zip(entry_dates, exit_dates)
    ]
    if not holds:
        return None
    return float(np.mean(holds))


def trade_summary(
    trade_pnls: np.ndarray,
    entry_dates: Optional[list[pd.Timestamp]] = None,
    exit_dates:  Optional[list[pd.Timestamp]] = None,
) -> dict:
    result = {
        "total_return":        round(total_return(trade_pnls), 4) if len(trade_pnls) else 0.0,
        "sharpe_ratio":        round(sharpe(trade_pnls), 3) if len(trade_pnls) else 0.0,
        "calmar_ratio":        round(calmar(trade_pnls), 3) if len(trade_pnls) else 0.0,
        "max_drawdown":        round(max_drawdown(trade_pnls), 4) if len(trade_pnls) else 0.0,
        "ann_volatility":      round(trade_pnls.std() * np.sqrt(252), 4) if len(trade_pnls) else 0.0,
        "n_days":              len(trade_pnls),
        "profit_factor":       profit_factor(trade_pnls),
        "win_rate":            round(win_rate(trade_pnls), 4),
        "avg_hold_days":       round(avg_hold_days(entry_dates or [], exit_dates or []), 2)
                               if (entry_dates and exit_dates and len(entry_dates) == len(exit_dates))
                               else None,
        "open_positions_at_end": 0,
    }
    return result
