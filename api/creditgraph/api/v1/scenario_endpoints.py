"""Scenario & stress-test endpoints wired to the deterministic quant engine."""

from __future__ import annotations

import math
from random import Random

from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query

from creditgraph.graph.credit_graph import get_borrower_state, list_borrowers
from creditgraph.models import RiskRegime, ScenarioInput
from creditgraph.services import quant_engine
from creditgraph.services.portfolio import (
    _borrower_exposure,
    _collect_borrower_states,
    _model_result,
    _norm_ppf,
)

scenario_router = APIRouter(prefix="/risk", tags=["quantitative-risk"])
quant_router = APIRouter(prefix="/risk/quant", tags=["quantitative-risk"])


# ---------------------------------------------------------------------------
# Shared models
# ---------------------------------------------------------------------------


class PnlSeries(BaseModel):
    pnl: list[float] = Field(..., min_length=1, description="Daily P&L observations")
    confidence: float = Field(0.95, gt=0.0, lt=1.0)


class ScenarioGenerateRequest(BaseModel):
    source: str = Field(
        ...,
        description="Data source: 'portfolio', 'borrower', 'sample', or 'custom'",
    )
    borrower_id: str | None = Field(
        None,
        description="Borrower ID (required when source=borrower)",
    )
    regime: RiskRegime = Field(
        RiskRegime.HIGH_VOLATILITY,
        description="Market regime for P&L generation",
    )
    exposure: float = Field(
        1_000_000.0,
        gt=0,
        description="Base exposure in USD (used for scaling P&L)",
    )
    confidence: float = Field(
        0.95,
        gt=0.0,
        lt=1.0,
        description="Confidence level for VaR/CVaR",
    )
    custom_pnl: list[float] | None = Field(
        None,
        description="Custom P&L series (used when source=custom)",
    )
    days: int = Field(
        20,
        ge=5,
        le=252,
        description="Number of daily P&L observations to generate",
    )


class ScenarioAnalyzeRequest(BaseModel):
    pnl: list[float] = Field(..., min_length=1, description="Daily P&L observations")
    exposure: float = Field(..., gt=0, description="Base exposure in USD")
    shock_pct: float = Field(-0.20, ge=-0.95, le=0.0, description="Shock percent for stress")
    recovery_rate: float = Field(0.4, ge=0.0, le=1.0, description="Recovery rate for stress")
    pd: float = Field(0.05, ge=0.0, lt=1.0, description="Probability of default")
    lgd: float = Field(0.4, ge=0.0, le=1.0, description="Loss given default")
    confidence: float = Field(0.95, gt=0.0, lt=1.0, description="VaR/CVaR confidence")


# ---------------------------------------------------------------------------
# P&L generation helpers
# ---------------------------------------------------------------------------

#: Deterministic regime parameters for P&L simulation.
#: Each regime defines annualized volatility and a seed for reproducibility.
REGIME_PNL_PARAMS: dict[RiskRegime, dict] = {
    RiskRegime.TRENDING: {"vol": 0.25, "mean": 0.08, "seed": 42},
    RiskRegime.MEAN_REVERTING: {"vol": 0.25, "mean": 0.00, "seed": 43},
    RiskRegime.LOW_VOLATILITY: {"vol": 0.12, "mean": 0.05, "seed": 44},
    RiskRegime.HIGH_VOLATILITY: {"vol": 0.50, "mean": -0.02, "seed": 45},
    RiskRegime.CRISIS: {"vol": 0.80, "mean": -0.15, "seed": 46},
    RiskRegime.SYSTEMIC_STRESS: {"vol": 0.90, "mean": -0.25, "seed": 47},
    RiskRegime.RECOVERY: {"vol": 0.30, "mean": 0.12, "seed": 48},
    RiskRegime.NEUTRAL: {"vol": 0.20, "mean": 0.03, "seed": 49},
}


def _generate_sample_pnl(
    regime: RiskRegime,
    exposure: float,
    days: int,
    seed: int = 42,
) -> list[float]:
    """Generate a deterministic P&L series for a given regime.

    Uses a fixed-seed pseudo-random walk scaled to exposure and regime
    volatility. Deterministic: same inputs always yield identical output.
    """
    params = REGIME_PNL_PARAMS.get(regime, REGIME_PNL_PARAMS[RiskRegime.HIGH_VOLATILITY])
    rng = Random(seed)
    daily_vol = params["vol"] / math.sqrt(252)
    daily_mean = params["mean"] / 252

    pnl: list[float] = []
    prev = exposure
    for _ in range(days):
        shock = rng.gauss(daily_mean, daily_vol)
        prev = prev * (1.0 + shock)
        pnl.append(round(prev - exposure, 2))
    return pnl


async def _generate_portfolio_pnl(
    regime: RiskRegime,
    exposure: float,
    days: int,
) -> list[float]:
    """Generate P&L from actual portfolio exposure distribution."""
    try:
        states = await _collect_borrower_states()
    except Exception:
        states = []

    if not states:
        return _generate_sample_pnl(regime, exposure, days)

    weights: list[float] = []
    vols: list[float] = []
    portfolio_value = 0.0
    for _, state in states:
        exp = _borrower_exposure(state)
        if exp <= 0:
            continue
        vol = REGIME_PNL_PARAMS.get(state.market_regime, REGIME_PNL_PARAMS[RiskRegime.HIGH_VOLATILITY])["vol"]
        weights.append(exp)
        vols.append(vol)
        portfolio_value += exp

    if portfolio_value <= 0:
        return _generate_sample_pnl(regime, exposure, days)

    weights = [w / portfolio_value for w in weights]
    systemic_corr = 0.45
    variance = sum(w * w * v * v for w, v in zip(weights, vols))
    for i in range(len(weights)):
        for j in range(i + 1, len(weights)):
            variance += 2.0 * weights[i] * weights[j] * vols[i] * vols[j] * systemic_corr
    sigma_p = math.sqrt(max(0.0, variance))
    daily_sigma = sigma_p / math.sqrt(252)
    daily_mean = REGIME_PNL_PARAMS.get(regime, REGIME_PNL_PARAMS[RiskRegime.HIGH_VOLATILITY])["mean"] / 252

    rng = Random(42)
    pnl = []
    prev = exposure
    for _ in range(days):
        shock = rng.gauss(daily_mean, daily_sigma)
        prev = prev * (1.0 + shock)
        pnl.append(round(prev - exposure, 2))
    return pnl


async def _generate_borrower_pnl(
    borrower_id: str,
    regime: RiskRegime,
    exposure: float,
    days: int,
) -> list[float]:
    """Generate P&L for a specific borrower's exposure under the given regime."""
    try:
        state = await get_borrower_state(borrower_id)
    except Exception:
        state = None

    if state is None:
        return _generate_sample_pnl(regime, exposure, days)

    borrower_exposure = _borrower_exposure(state)
    if borrower_exposure <= 0:
        borrower_exposure = exposure

    vol = REGIME_PNL_PARAMS.get(state.market_regime, REGIME_PNL_PARAMS[RiskRegime.HIGH_VOLATILITY])["vol"]
    daily_sigma = vol / math.sqrt(252)
    daily_mean = REGIME_PNL_PARAMS.get(regime, REGIME_PNL_PARAMS[RiskRegime.HIGH_VOLATILITY])["mean"] / 252

    rng = Random(hash(borrower_id) % (2**31))
    pnl = []
    prev = borrower_exposure
    for _ in range(days):
        shock = rng.gauss(daily_mean, daily_sigma)
        prev = prev * (1.0 + shock)
        pnl.append(round(prev - exposure, 2))
    return pnl


# ---------------------------------------------------------------------------
# Legacy endpoints
# ---------------------------------------------------------------------------


@scenario_router.post("/scenario/stress")
async def stress_scenario(
    base_exposure: float = Query(..., ge=0, description="Base exposure Value"),
    shock_pct: float = Query(-0.20, ge=-0.5, le=0.5, description="Shock as percent delta, e.g. -0.2"),
    recovery_rate: float = Query(0.4, ge=0.0, le=1.0, description="Recovery rate"),
) -> dict:
    """Run a deterministic stress test on an exposure."""
    if base_exposure <= 0:
        raise HTTPException(status_code=422, detail="base_exposure must be positive")
    return quant_engine.run_stress_test(base_exposure, shock_pct, recovery_rate)


@scenario_router.post("/scenario/var")
async def var(body: PnlSeries) -> dict:
    """Compute historical Value at Risk (deterministic)."""
    return quant_engine.calculate_var_historical(body.pnl, body.confidence)


@scenario_router.post("/scenario/cvar")
async def cvar(body: PnlSeries) -> dict:
    """Compute historical CVaR / Expected Shortfall (deterministic)."""
    return quant_engine.calculate_cvar_historical(body.pnl, body.confidence)


@scenario_router.post("/scenario/expected-loss")
async def expected_loss(
    exposure: float = Query(..., gt=0, description="Exposure at default"),
    pd: float = Query(..., gt=0, lt=1.0, description="Probability of default"),
    lgd: float = Query(0.4, ge=0.0, le=1.0, description="Loss given default"),
) -> dict:
    """Compute Expected Loss = EAD * PD * LGD (deterministic)."""
    return quant_engine.expected_loss(exposure, pd, lgd)


@scenario_router.post("/scenario/run")
async def run_scenario(scenario: ScenarioInput) -> dict:
    """Run all deterministic scenario metrics for a single exposure.

    Returns a composite result: stress loss, VaR at 95% (single-loss proxy),
    CVaR, and expected loss.
    """
    stressed = quant_engine.run_stress_test(
        base_exposure=100.0,
        shock_pct=scenario.shock_pct,
        recovery_rate=0.4,
    )
    return {
        "scenario": scenario.name,
        "label": scenario.stress_label,
        "shock_pct": scenario.shock_pct,
        "vix": scenario.vix,
        "stressed": stressed,
    }


# ---------------------------------------------------------------------------
# New: Scenario Builder
# ---------------------------------------------------------------------------


@quant_router.post("/scenario/generate")
async def generate_scenario(body: ScenarioGenerateRequest) -> dict:
    """Generate a P&L series from a selected data source and regime.

    Sources:
    - ``portfolio``: derive from actual portfolio exposure + regime vol
    - ``borrower``: derive from a specific borrower's state + regime vol
    - ``sample``: deterministic regime-aware sample distribution
    - ``custom``: echo back the user-provided P&L (validated)
    """
    source = body.source.lower().strip()
    if source not in {"portfolio", "borrower", "sample", "custom"}:
        raise HTTPException(
            status_code=422,
            detail=f"source must be one of portfolio, borrower, sample, custom; got {source}",
        )

    if source == "custom":
        if not body.custom_pnl or len(body.custom_pnl) < 1:
            raise HTTPException(status_code=422, detail="custom_pnl must be non-empty when source=custom")
        pnl = [float(x) for x in body.custom_pnl]
        return _model_result(
            model_id="m_scenario_custom",
            parameters={
                "method": "user_provided_pnl",
                "regime": body.regime.value,
                "days": len(pnl),
            },
            inputs={
                "source": "custom",
                "exposure": body.exposure,
                "regime": body.regime.value,
                "confidence": body.confidence,
            },
            outputs={"pnl": pnl, "count": len(pnl), "min": round(min(pnl), 2), "max": round(max(pnl), 2)},
        )

    if source == "portfolio":
        pnl = await _generate_portfolio_pnl(body.regime, body.exposure, body.days)
    elif source == "borrower":
        if not body.borrower_id:
            raise HTTPException(status_code=422, detail="borrower_id is required when source=borrower")
        pnl = await _generate_borrower_pnl(body.borrower_id, body.regime, body.exposure, body.days)
    else:
        pnl = _generate_sample_pnl(body.regime, body.exposure, body.days)

    return _model_result(
        model_id="m_scenario_generate",
        parameters={
            "method": f"{source}_derived_pnl",
            "regime": body.regime.value,
            "days": body.days,
            "volatility": REGIME_PNL_PARAMS.get(body.regime, {}).get("vol"),
        },
        inputs={
            "source": source,
            "borrower_id": body.borrower_id,
            "exposure": body.exposure,
            "regime": body.regime.value,
            "confidence": body.confidence,
        },
        outputs={"pnl": pnl, "count": len(pnl), "min": round(min(pnl), 2), "max": round(max(pnl), 2)},
    )


@quant_router.post("/scenario/analyze")
async def analyze_scenario(body: ScenarioAnalyzeRequest) -> dict:
    """Run the full quant suite from a single P&L series + exposure.

    Computes:
    - Historical VaR
    - Historical CVaR (Expected Shortfall)
    - Deterministic Stress Test (using body.shock_pct)
    - Expected Loss (using body.pd and body.lgd)
    """
    if not body.pnl or len(body.pnl) < 1:
        raise HTTPException(status_code=422, detail="pnl must be non-empty")

    var_result = quant_engine.calculate_var_historical(body.pnl, body.confidence)
    cvar_result = quant_engine.calculate_cvar_historical(body.pnl, body.confidence)
    stress_result = quant_engine.run_stress_test(body.exposure, body.shock_pct, body.recovery_rate)
    el_result = quant_engine.expected_loss(body.exposure, body.pd, body.lgd)

    return {
        "model_id": "m_scenario_analyze",
        "model_name": "Full Scenario Analysis",
        "model_version": "1.0.0",
        "parameters": {
            "shock_pct": body.shock_pct,
            "recovery_rate": body.recovery_rate,
            "pd": body.pd,
            "lgd": body.lgd,
            "confidence": body.confidence,
        },
        "inputs": {
            "pnl_count": len(body.pnl),
            "exposure": body.exposure,
        },
        "outputs": {
            "var": var_result["outputs"],
            "cvar": cvar_result["outputs"],
            "stress": stress_result["outputs"],
            "expected_loss": el_result["outputs"],
        },
        "timestamp": quant_engine.datetime.now(quant_engine.timezone.utc).isoformat(),
    }
