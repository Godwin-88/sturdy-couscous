"""Bayesian inference for CreditGraph default risk (E5-US2).

Implements Beta-binomial conjugate updating for probability of default,
with evidence-driven posterior revision and feature-conditional blending.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

MODEL_ID = "m_bayesian_pd"
MODEL_NAME = "Bayesian Probability of Default"
MODEL_VERSION = "1.0.0"

PRIOR_ALPHA = 2.0
PRIOR_BETA = 18.0
PRIOR_STRENGTH = PRIOR_ALPHA + PRIOR_BETA

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


def _provenance(parameters: dict, inputs: dict, outputs: dict) -> dict:
    return {
        "model_id": MODEL_ID,
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "parameters": parameters,
        "inputs": inputs,
        "outputs": outputs,
        "timestamp": utcnow().isoformat(),
    }


def _pd_to_beta(pd: float, n: float = PRIOR_STRENGTH) -> tuple[float, float]:
    alpha = n * pd
    beta = n * (1.0 - pd)
    return max(alpha, 1e-9), max(beta, 1e-9)


def _beta_ppf_approx(alpha: float, beta: float, p: float) -> float:
    """Approximate the Beta quantile function (inverse CDF) via normal."""
    mean = alpha / (alpha + beta)
    variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return mean
    z = _inv_cdf_std_normal(p)
    return max(0.0, min(1.0, mean + z * std))


def _inv_cdf_std_normal(p: float) -> float:
    """Approximate the inverse CDF of the standard normal distribution."""
    if p <= 0:
        return -1e9
    if p >= 1:
        return 1e9
    if p < 0.5:
        sign = -1.0
        q = p
    else:
        sign = 1.0
        q = 1.0 - p
    t = math.sqrt(-2.0 * math.log(q))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    x = t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)
    return sign * x


def update_with_evidence(prior_pd: float, evidence: list[dict]) -> dict:
    """Update posterior PD given new evidence items using Beta-binomial conjugacy.

    Args:
        prior_pd: Prior probability of default (0.0-1.0).
        evidence: List of evidence dicts with keys:
            - type: one of {attestation, liability, exposure, collateral}
            - strength: float in [0.0, 1.0]

    Returns:
        Provenance dict with prior/posterior Beta parameters and PD.
    """
    prior_pd = max(0.001, min(0.999, prior_pd))

    alpha, beta = _pd_to_beta(prior_pd)
    positive_strength = 0.0
    negative_strength = 0.0

    for item in evidence:
        etype = item.get("type", "").lower()
        strength = float(item.get("strength", 0.0))
        strength = max(0.0, min(1.0, strength))

        if etype in ("attestation", "collateral"):
            alpha += strength
            positive_strength += strength
        elif etype in ("liability", "exposure"):
            beta += strength
            negative_strength += strength

    posterior_pd = alpha / (alpha + beta)

    return _provenance(
        parameters={
            "prior_alpha": round(alpha - positive_strength - negative_strength, 6),
            "prior_beta": round(beta - positive_strength - negative_strength, 6),
            "prior_pd": round(prior_pd, 6),
            "evidence_total_strength": round(positive_strength + negative_strength, 6),
            "positive_evidence_strength": round(positive_strength, 6),
            "negative_evidence_strength": round(negative_strength, 6),
        },
        inputs={
            "prior_pd": round(prior_pd, 6),
            "evidence_count": len(evidence),
            "evidence": evidence,
        },
        outputs={
            "posterior_pd": round(posterior_pd, 6),
            "posterior_alpha": round(alpha, 6),
            "posterior_beta": round(beta, 6),
            "confidence_interval_95": {
                "lower": round(_beta_ppf_approx(alpha, beta, 0.025), 6),
                "upper": round(_beta_ppf_approx(alpha, beta, 0.975), 6),
            },
        },
    )


def _compute_base_pd(fico_score: float, leverage: float, regime: str) -> float:
    """Compute base PD from FICO, leverage, and regime using logistic mapping."""
    log_odds = (690.0 - fico_score) / 60.0
    log_odds += 0.35 * leverage
    log_odds += REGIME_LOGODDS_ADJ.get(regime, 0.0)
    pd = 1.0 / (1.0 + math.exp(-log_odds))
    return max(0.001, min(0.999, pd))


def compute_posterior_pd(
    fico_score: float,
    leverage: float,
    regime: str,
    evidence_posterior: float,
) -> dict:
    """Full posterior PD combining FICO, leverage, regime, and evidence updates.

    Args:
        fico_score: Borrower FICO score (300-850).
        leverage: Debt-to-collateral ratio (0.0+).
        regime: Market regime string.
        evidence_posterior: Posterior PD from evidence update (0.0-1.0).

    Returns:
        Provenance dict with combined posterior PD and component breakdown.
    """
    evidence_posterior = max(0.001, min(0.999, evidence_posterior))
    base_pd = _compute_base_pd(fico_score, leverage, regime)

    base_log_odds = math.log(base_pd / (1.0 - base_pd))
    evidence_log_odds = math.log(evidence_posterior / (1.0 - evidence_posterior))

    combined_log_odds = 0.4 * base_log_odds + 0.6 * evidence_log_odds
    posterior_pd = 1.0 / (1.0 + math.exp(-combined_log_odds))

    return _provenance(
        parameters={
            "fico_scaling": 60.0,
            "leverage_weight": 0.35,
            "evidence_weight": 0.6,
            "base_weight": 0.4,
            "regime_adjustments": REGIME_LOGODDS_ADJ,
        },
        inputs={
            "fico_score": fico_score,
            "leverage": round(leverage, 6),
            "regime": regime,
            "evidence_posterior": round(evidence_posterior, 6),
        },
        outputs={
            "base_pd": round(base_pd, 6),
            "posterior_pd": round(posterior_pd, 6),
        },
    )
