"""
Monte Carlo Portfolio Simulation — M1 L2: multivariate paths, VaR/CVaR
"""

import numpy as np
from typing import Optional
from dataclasses import dataclass


@dataclass
class MCSimulationResult:
    terminal_wealth_mean: float
    terminal_wealth_std: float
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    percentiles: dict


def monte_carlo_portfolio(
    returns: np.ndarray,
    weights: np.ndarray,
    portfolio_value: float = 1.0,
    horizon_days: int = 1,
    n_paths: int = 100_000,
    use_t_dist: bool = False,
    df: float = 5.0,
) -> MCSimulationResult:
    """
    Simulate portfolio P&L over horizon. Returns distribution of terminal wealth.
    """
    mu = np.mean(returns, axis=0)
    cov = np.cov(returns.T, ddof=1)
    w = np.asarray(weights).flatten()
    port_mu = float(mu @ w)
    port_vol = float(np.sqrt(w @ cov @ w))

    if use_t_dist:
        from scipy.stats import t
        daily_ret = t.rvs(df, loc=port_mu, scale=port_vol, size=(n_paths, horizon_days))
    else:
        daily_ret = np.random.normal(port_mu, port_vol, (n_paths, horizon_days))

    terminal = portfolio_value * np.prod(1 + daily_ret, axis=1)
    losses = portfolio_value - terminal

    var_95 = float(np.percentile(losses, 95))
    var_99 = float(np.percentile(losses, 99))
    tail_95 = losses[losses >= var_95]
    tail_99 = losses[losses >= var_99]
    cvar_95 = float(np.mean(tail_95)) if len(tail_95) > 0 else var_95
    cvar_99 = float(np.mean(tail_99)) if len(tail_99) > 0 else var_99

    return MCSimulationResult(
        terminal_wealth_mean=float(np.mean(terminal)),
        terminal_wealth_std=float(np.std(terminal)),
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        percentiles={5: float(np.percentile(terminal, 5)), 25: float(np.percentile(terminal, 25)), 50: float(np.percentile(terminal, 50)), 75: float(np.percentile(terminal, 75)), 95: float(np.percentile(terminal, 95))},
    )
