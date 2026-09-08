"""Deterministic credit risk + decision engine (E5/E6/E8).

Implements, with zero LLM influence:
  - Credit score (0-100) with contributing risk factors
  - Probability of default (PD) via a FICO- and leverage-informed logistic
  - Expected loss = EAD * PD * LGD
  - Loan-to-value and required collateral ratio
  - Stress LTV under a market shock (propagates through regime)
  - Recommended safe exposure from PD, LTV, concentration, stress

All methods are pure and deterministic for identical inputs + model version.
Returned dicts carry model metadata + provenance per NFR-002 / E5-US1.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone

from creditgraph.models import (
    CreditAssessment,
    CreditDecision,
    CurrentBorrowerState,
    DecisionStatus,
    RiskRegime,
)

# Deterministic, versioned model catalogue (metadata only)
MODEL_CATALOG: dict[str, dict[str, str]] = {
    "m_credit_score": {"name": "Credit Score", "version": "1.0.0"},
    "m_probability_default": {"name": "Probability of Default", "version": "2.1.0"},
    "m_expected_loss": {"name": "Expected Loss", "version": "1.0.0"},
    "m_ltv": {"name": "Loan-to-Value", "version": "1.0.0"},
    "m_collateral_ratio": {"name": "Required Collateral Ratio", "version": "1.0.0"},
    "m_stress": {"name": "Stress LTV", "version": "1.0.0"},
    "m_recommended_exposure": {"name": "Recommended Exposure", "version": "1.0.0"},
}

# Deterministic regime stress table (shock is a negative price delta)
REGIME_STRESS: dict[RiskRegime, dict[str, float]] = {
    RiskRegime.NEUTRAL: {"shock": -0.15, "liquidity_factor": 1.0},
    RiskRegime.TRENDING: {"shock": -0.15, "liquidity_factor": 1.0},
    RiskRegime.MEAN_REVERTING: {"shock": -0.15, "liquidity_factor": 1.0},
    RiskRegime.LOW_VOLATILITY: {"shock": -0.10, "liquidity_factor": 0.9},
    RiskRegime.RECOVERY: {"shock": -0.15, "liquidity_factor": 1.0},
    RiskRegime.HIGH_VOLATILITY: {"shock": -0.25, "liquidity_factor": 1.2},
    RiskRegime.CRISIS: {"shock": -0.40, "liquidity_factor": 1.6},
    RiskRegime.SYSTEMIC_STRESS: {"shock": -0.55, "liquidity_factor": 2.2},
}

# Regime penalty on the log-odds scale (deterministic)
REGIME_LOGODDS_ADJ: dict[str, float] = {
    "neutral": 0.0,
    "trending": 0.0,
    "mean_reverting": 0.0,
    "low_volatility": 0.0,
    "recovery": 0.0,
    "high_volatility": 0.20,
    "crisis": 0.45,
    "systemic_stress": 0.65,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _model_result(model_id: str, parameters: dict, inputs: dict, outputs: dict) -> dict:
    """Wrap a deterministic model output with metadata + provenance."""
    meta = MODEL_CATALOG[model_id]
    return {
        "model_id": model_id,
        "model_name": meta["name"],
        "model_version": meta["version"],
        "parameters": parameters,
        "inputs": inputs,
        "outputs": outputs,
        "timestamp": utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Probability of Default
# ---------------------------------------------------------------------------


def probability_of_default(state: CurrentBorrowerState) -> dict:
    """Logistic PD from FICO + leverage (DTI) + regime adjustment."""
    leverage = 0.0
    if state.total_collateral_value > 0:
        leverage = state.total_liabilities / state.total_collateral_value

    # Base log-odds from FICO (690 ~ neutral). Comparable logistic mapping.
    log_odds = (690.0 - state.fico_score) / 60.0
    log_odds += 0.35 * leverage
    log_odds += REGIME_LOGODDS_ADJ.get(state.market_regime.value, 0.0)

    pd = 1.0 / (1.0 + math.exp(-log_odds))
    pd = max(0.001, min(0.50, pd))
    return _model_result(
        "m_probability_default",
        parameters={
            "method": "logistic_fico_leverage_regime",
            "fico_scaling": 60.0,
            "leverage_weight": 0.35,
        },
        inputs={
            "fico_score": state.fico_score,
            "total_collateral_value": state.total_collateral_value,
            "total_liabilities": state.total_liabilities,
            "market_regime": state.market_regime.value,
            "leverage": round(leverage, 6),
        },
        outputs={"probability_of_default": round(pd, 6)},
    )


# ---------------------------------------------------------------------------
# LTV / collateral
# ---------------------------------------------------------------------------


def compute_ltv(state: CurrentBorrowerState, requested: float) -> dict:
    """LTV = requested / haircut-adjusted collateral value."""
    adj_value = sum(c.valuation * (1.0 - c.haircut) for c in state.collateral)
    ltv = (requested / adj_value) if adj_value > 0 else float("inf")
    return _model_result(
        "m_ltv",
        parameters={"adjusted": True},
        inputs={"requested": requested, "adjusted_collateral": round(adj_value, 4)},
        outputs={"loan_to_value": round(ltv, 6), "collateral_value": round(adj_value, 6)},
    )


def compute_required_ratio(state: CurrentBorrowerState, target_ltv: float = 0.6) -> dict:
    """Required collateral ratio = (1 / target LTV) * regime liquidity multiplier."""
    mult = REGIME_STRESS.get(state.market_regime.value, {}).get("liquidity_factor", 1.0)
    ratio = (1.0 / target_ltv) * mult
    return _model_result(
        "m_collateral_ratio",
        parameters={"target_ltv": target_ltv, "regime_multiplier": mult},
        inputs={"market_regime": state.market_regime.value},
        outputs={"required_collateral_ratio": round(ratio, 4)},
    )


# ---------------------------------------------------------------------------
# Concentration
# ---------------------------------------------------------------------------


def concentration_factor(state: CurrentBorrowerState) -> float:
    """Fraction of collateral in the dominant correlation/cluster group."""
    if not state.collateral:
        return 0.0
    groups: dict[str, float] = {}
    for c in state.collateral:
        groups[c.correlated_group] = groups.get(c.correlated_group, 0.0) + c.valuation
    total = sum(groups.values())
    if total <= 0:
        return 0.0
    return max(groups.values()) / total


# ---------------------------------------------------------------------------
# Credit score
# ---------------------------------------------------------------------------


def credit_score(
    state: CurrentBorrowerState,
    pd_result: dict,
    ltv_result: dict,
    concentration: float,
) -> dict:
    """Credit score 0-100: penalized by PD, LTV, concentration, liquidity."""
    pd = pd_result["outputs"]["probability_of_default"]
    ltv = ltv_result["outputs"]["loan_to_value"]

    w_pd, w_ltv, w_conc, w_liq = 0.35, 0.25, 0.25, 0.15
    penalty = (
        w_pd * (pd / 0.25)
        + w_ltv * min(ltv, 1.0)
        + w_conc * concentration
    )
    liq = REGIME_STRESS.get(state.market_regime.value, {}).get("liquidity_factor", 1.0)
    penalty += w_liq * (liq - 1.0)
    score = max(0.0, min(100.0, 100.0 * (1.0 - penalty)))

    factors: list[str] = []
    if pd > 0.10:
        factors.append(f"Estimated default probability {pd*100:.1f}%")
    if ltv > 0.60:
        factors.append(f"High loan-to-value ({ltv*100:.0f}%)")
    if concentration > 0.50:
        factors.append(f"High collateral concentration ({concentration*100:.0f}%)")
    if liq > 1.0:
        factors.append("Elevated liquidity risk under current regime")
    if not factors:
        factors.append("Low observed risk across assessed dimensions")

    return _model_result(
        "m_credit_score",
        parameters={
            "weights": {"pd": w_pd, "ltv": w_ltv, "concentration": w_conc, "liquidity": w_liq},
            "pd_scale": 0.25,
        },
        inputs={
            "pd": pd,
            "ltv": ltv,
            "concentration_factor": concentration,
            "market_regime": state.market_regime.value,
        },
        outputs={"score": round(score, 2), "principal_risk_factors": factors},
    )


# ---------------------------------------------------------------------------
# Stress
# ---------------------------------------------------------------------------


def stress_ltv(
    state: CurrentBorrowerState,
    requested: float,
    collateral_value: float,
    shock_pct: float | None = None,
) -> dict:
    """Stress LTV after applying the regime shock to collateral value."""
    shock = shock_pct if shock_pct is not None else REGIME_STRESS[state.market_regime.value]["shock"]
    stressed_collateral = collateral_value * (1.0 + shock)
    stress_ltv_val = (requested / stressed_collateral) if stressed_collateral > 0 else float("inf")
    stress_loss = -(requested * shock)  # positive loss on drawdown
    return _model_result(
        "m_stress",
        parameters={"shock_pct": shock, "regime": state.market_regime.value},
        inputs={"requested_amount": requested, "base_collateral": round(collateral_value, 4)},
        outputs={
            "stressed_collateral": round(stressed_collateral, 4),
            "stress_ltv": round(stress_ltv_val, 6),
            "stress_loss": round(stress_loss, 2),
        },
    )


# ---------------------------------------------------------------------------
# Recommended exposure (E8)
# ---------------------------------------------------------------------------


def recommended_exposure(
    state: CurrentBorrowerState,
    pd_result: dict,
    ltv_result: dict,
    stress_result: dict,
    concentration: float,
    max_ltv: float = 0.6,
) -> dict:
    """Maximum suggested loan under collateral, concentration, PD and stress.

    capacity = min(
        collateral * max_ltv * (1 - 0.3*concentration),
        collateral * (1 + shock) * max_ltv * (1 - 0.3*concentration)   # stress-bounded
    )
    then scaled by (1 - PD) headroom.
    Recommended = min(capacity, requested).
    """
    pd = pd_result["outputs"]["probability_of_default"]
    collateral = ltv_result["inputs"]["adjusted_collateral"]
    conc_penalty = 1.0 - (0.3 * concentration)

    base_capacity = collateral * max_ltv * conc_penalty
    shock = REGIME_STRESS[state.market_regime.value]["shock"]
    stressed_capacity = collateral * (1.0 + shock) * max_ltv * conc_penalty
    capacity = min(base_capacity, stressed_capacity)
    capacity *= (1.0 - pd)
    recommended = min(capacity, state.requested_amount)

    return _model_result(
        "m_recommended_exposure",
        parameters={"max_ltv": max_ltv, "concentration_penalty": 0.3, "pd_headroom": True},
        inputs={
            "adjusted_collateral": collateral,
            "pd": pd,
            "concentration": round(concentration, 4),
            "stress_loss": stress_result["outputs"]["stress_loss"],
        },
        outputs={"recommended_amount": round(recommended, 2)},
    )


# ---------------------------------------------------------------------------
# Orchestration — the deterministic service API
# ---------------------------------------------------------------------------


def build_assessment_and_decision(
    state: CurrentBorrowerState,
    risk_free_rate: float = 0.02,
) -> tuple[CreditAssessment, CreditDecision, dict[str, dict]]:
    """Run the full deterministic risk chain.

    Returns (assessment, decision, model_results) where model_results maps
    model ids to their metadata-wrapped result (for provenance).
    """
    pd_result = probability_of_default(state)
    ltv_result = compute_ltv(state, state.requested_amount)
    req_ratio_result = compute_required_ratio(state)
    conc = concentration_factor(state)
    score_result = credit_score(state, pd_result, ltv_result, conc)
    stress_result = stress_ltv(
        state, state.requested_amount, ltv_result["inputs"]["adjusted_collateral"]
    )
    rec_result = recommended_exposure(state, pd_result, ltv_result, stress_result, conc)

    pd = pd_result["outputs"]["probability_of_default"]
    lgd = 0.4
    el = state.requested_amount * pd * lgd
    expected_loss_result = {
        "model_id": "m_expected_loss",
        "model_name": MODEL_CATALOG["m_expected_loss"]["name"],
        "model_version": MODEL_CATALOG["m_expected_loss"]["version"],
        "parameters": {"lgd": lgd},
        "inputs": {"ead": state.requested_amount, "pd": pd},
        "outputs": {"expected_loss": round(el, 2)},
        "timestamp": utcnow().isoformat(),
    }

    model_results: dict[str, dict] = {
        "m_probability_default": pd_result,
        "m_ltv": ltv_result,
        "m_collateral_ratio": req_ratio_result,
        "m_credit_score": score_result,
        "m_stress": stress_result,
        "m_recommended_exposure": rec_result,
        "m_expected_loss": expected_loss_result,
    }

    score_val = score_result["outputs"]["score"]
    pd_val = pd_result["outputs"]["probability_of_default"]
    ltv_val = ltv_result["outputs"]["loan_to_value"]
    req_ratio = req_ratio_result["outputs"]["required_collateral_ratio"]
    stress_val = stress_result["outputs"]["stress_ltv"]
    rec_val = rec_result["outputs"]["recommended_amount"]
    factors = score_result["outputs"]["principal_risk_factors"]
    model_ids = list(MODEL_CATALOG.keys())

    assessment = CreditAssessment(
        borrower_id=state.borrower_id,
        credit_score=score_val,
        probability_of_default=pd_val,
        expected_loss=el,
        loan_to_value=ltv_val,
        required_collateral_ratio=req_ratio,
        stress_ltv=stress_val,
        market_regime=state.market_regime,
        principal_risk_factors=factors,
        models=model_ids,
    )

    decision = CreditDecision(
        decision_id=uuid.uuid4().hex[:12],
        borrower_id=state.borrower_id,
        requested_amount=state.requested_amount,
        recommended_amount=rec_val,
        collateral_value=ltv_result["outputs"]["collateral_value"],
        required_collateral_ratio=req_ratio,
        credit_score=score_val,
        probability_of_default=pd_val,
        expected_loss=el,
        risk_regime=state.market_regime,
        stress_result=stress_val,
        principal_risk_factors=factors,
        supporting_evidence=list(state.attestation_refs),
        attestation_references=list(state.attestation_refs),
        model_versions=[f"{k}:{MODEL_CATALOG[k]['version']}" for k in model_ids],
        expires_at=utcnow() + timedelta(days=7),
        decision_status=DecisionStatus.RECOMMENDED,
    )

    return assessment, decision, model_results
