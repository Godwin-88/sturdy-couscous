"""Performance metrics including Jobson-Korkie test for capstone significance testing."""

import numpy as np
from scipy import stats


def sharpe(returns: np.ndarray, rf: float = 0.05) -> float:
    daily_rf = rf / 252
    excess = returns - daily_rf
    return float(np.sqrt(252) * excess.mean() / excess.std()) if excess.std() > 0 else 0.0


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
    """
    Jobson-Korkie (1981) test: H0: Sharpe(r1) == Sharpe(r2).
    Returns (z-statistic, p-value). Two-tailed.
    """
    n = len(r1)
    sr1 = sharpe(r1)
    sr2 = sharpe(r2)

    mu1, mu2 = r1.mean(), r2.mean()
    s1, s2   = r1.std(), r2.std()
    s12      = np.cov(r1, r2)[0, 1]

    # Variance of (SR1 - SR2) per Jobson & Korkie
    theta = (
        (1/n) * (
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


def summary(returns: np.ndarray, benchmark: np.ndarray = None) -> dict:
    result = {
        "total_return":  round(total_return(returns), 4),
        "sharpe_ratio":  round(sharpe(returns), 3),
        "calmar_ratio":  round(calmar(returns), 3),
        "max_drawdown":  round(max_drawdown(returns), 4),
        "ann_volatility": round(returns.std() * np.sqrt(252), 4),
        "n_days":        len(returns),
    }
    if benchmark is not None:
        z, p = jobson_korkie(returns, benchmark)
        result["jk_z_stat"]  = round(z, 3)
        result["jk_p_value"] = round(p, 4)
        result["jk_significant"] = p < 0.05
    return result
