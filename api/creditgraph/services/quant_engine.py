"""Deterministic quantitative risk engine.

All financial calculations are executable, deterministic and free of LLM
influence. Future phases will pull parameters from the Neo4j financial
knowledge graph (master.cypher) concepts/formulas.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _wrap_result(
    model_id: str,
    model_name: str,
    model_version: str,
    parameters: dict,
    inputs: dict,
    outputs: dict,
) -> dict:
    """Build a uniform model-result dict with execution metadata."""
    return {
        "model_id": model_id,
        "model_name": model_name,
        "model_version": model_version,
        "parameters": parameters,
        "inputs": inputs,
        "outputs": outputs,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def calculate_var_historical(
    pnl_array: list[float], confidence: float = 0.95
) -> dict:
    """Historical Value at Risk at given confidence.

    VaR = -(1-confidence) quantile of P&L. Deterministic: uses sorted
    observation quantiles, no sampling.
    """
    if not pnl_array or confidence <= 0 or confidence >= 1:
        raise ValueError("pnl_array must be non-empty and 0<confidence<1")

    sorted_pnl = sorted(pnl_array)
    q = 1 - confidence
    idx = min(len(sorted_pnl) - 1, max(0, round(q * len(sorted_pnl))))
    var = -sorted_pnl[idx]

    return _wrap_result(
        model_id="m_historical_var",
        model_name="Historical VaR",
        model_version="1.0.0",
        parameters={"confidence": confidence, "method": "historical_quantile"},
        inputs={"pnl_count": len(pnl_array)},
        outputs={"var": round(var, 6), "quantile": idx},
    )


def calculate_cvar_historical(
    pnl_array: list, confidence: float = 0.95
) -> dict:
    """CVaR / Expected Shortfall at given confidence using historical tail mean."""
    if not pnl_array or confidence <= 0 or confidence >= 1:
        raise ValueError("pnl_array must be non-empty and 0<confidence<1")

    q = 1 - confidence
    sorted_pnl = sorted(pnl_array)
    idx = round(q * len(sorted_pnl))
    tail = sorted_pnl[:max(1, idx)]  # worst `idx` losses
    cvar = -(sum(tail) / max(1, len(tail)))

    return _wrap_result(
        model_id="m_historical_cvar",
        model_name="Historical CVaR (Expected Shortfall)",
        model_version="1.0.0",
        parameters={"confidence": confidence, "method": "tail_mean"},
        inputs={"pnl_count": len(pnl_array), "tail_count": len(tail)},
        outputs={"cvar": round(cvar, 2)},
    )


def run_stress_test(
    base_exposure: float, shock_pct: float, recovery_rate: float = 0.4
) -> dict:
    """Apply a deterministic shock to exposure and return stressed loss.

    stressed_loss = -(base_exposure * shock_pct) * (1 - recovery_rate).
    shock_pct is negative for a drawdown.
    """
    stressed_loss = -(base_exposure * shock_pct) * (1.0 - recovery_rate)
    return _wrap_result(
        model_id="m_stress_test",
        model_name="Deterministic Stress Test",
        model_version="1.0.0",
        parameters={"shock_pct": shock_pct, "recovery_rate": recovery_rate},
        inputs={"base_exposure": base_exposure},
        outputs={
            "stressed_exposure": round(base_exposure * (1.0 + shock_pct), 2),
            "stressed_loss": round(stressed_loss, 2),
        },
    )


def expected_loss(
    exposure_at_default: float, pd: float, lgd: float
) -> dict:
    """EL = EAD * PD * LGD. Deterministic."""
    el = exposure_at_default * pd * lgd
    return _wrap_result(
        model_id="m_expected_loss",
        model_name="Expected Loss",
        model_version="1.0.0",
        parameters={"pd": pd, "lgd": lgd, "ead": exposure_at_default},
        inputs={"exposure_at_default": exposure_at_default},
        outputs={"expected_loss": round(el, 2)},
    )
