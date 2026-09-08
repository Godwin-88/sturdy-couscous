"""Portfolio intelligence — cross-borrower exposure, contagion & systemic risk (E12).

Implements spec §12 EPIC E12 portfolio-intelligence features:
  - get_portfolio_exposure:        aggregate every borrower's collateral,
                                   liabilities and protocol exposures into a
                                   portfolio-level graph
  - get_counterparty_exposure:     total exposure to a single protocol (e.g. Aave)
                                   summed across all borrowers + per-borrower split
  - run_contagion_analysis:        simulate a collateral shock to one borrower and
                                   propagate defaults through shared protocols
  - compute_portfolio_var:         parametric (variance-covariance) VaR for the whole
                                   credit portfolio at a given confidence
  - get_systemic_stress_impact:    apply a portfolio-wide systemic shock and report
                                   aggregate loss / insolvency

All outputs are fully deterministic and carry model metadata + provenance
(NFR-002 / E5-US1): the LLM may explain these numbers but never alters them.
The engine reads borrower state from the Neo4j CreditGraph via the graph
repository; every function is a thin, deterministic aggregation over that state.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable

from creditgraph.graph.credit_graph import get_borrower_state, list_borrowers
from creditgraph.models import CurrentBorrowerState, Exposure, Liability, RiskRegime

# ---------------------------------------------------------------------------
# Model catalogue (metadata only, deterministic + versioned)
# ---------------------------------------------------------------------------

MODEL_CATALOG: dict[str, dict[str, str]] = {
    "m_portfolio_exposure": {"name": "Portfolio Exposure Graph", "version": "1.0.0"},
    "m_counterparty_exposure": {"name": "Counterparty Exposure", "version": "1.0.0"},
    "m_contagion": {"name": "Contagion Analysis", "version": "1.0.0"},
    "m_portfolio_var": {"name": "Portfolio Value-at-Risk", "version": "1.0.0"},
    "m_systemic_stress": {"name": "Systemic Stress Impact", "version": "1.0.0"},
    "m_scenario_generate": {"name": "Scenario P&L Generator", "version": "1.0.0"},
    "m_scenario_custom": {"name": "Custom P&L Input", "version": "1.0.0"},
    "m_scenario_analyze": {"name": "Full Scenario Analysis", "version": "1.0.0"},
}

#: Default collateral shock applied in contagion analysis (spec default -30%).
DEFAULT_CONTAGION_SHOCK = -0.30

#: Transmission factor per contagion hop; each ring absorbs this fraction of
#: the prior ring's effective shock (deterministic decay, no randomness).
CONTAGION_TRANSMISSION = 0.5

#: Maximum number of contagion rings simulated before the cascade is truncated.
MAX_CONTAGION_RINGS = 6

#: Default systemic shock used by the systemic-stress scenario (=-55%).
SYSTEMIC_SHOCK = -0.55

#: Default VaR holding period in calendar days (parametric scaling).
VAR_HORIZON_DAYS = 10

#: Inter-borrower (systemic) correlation assumed for the variance-covariance VaR.
#: Borrowers are not independent: a shared market factor links them.
DEFAULT_SYSTEMIC_CORRELATION = 0.45

#: Annualized collateral volatility per market regime (deterministic baseline).
REGIME_VOLATILITY: dict[RiskRegime, float] = {
    RiskRegime.NEUTRAL: 0.25,
    RiskRegime.TRENDING: 0.30,
    RiskRegime.MEAN_REVERTING: 0.25,
    RiskRegime.LOW_VOLATILITY: 0.18,
    RiskRegime.RECOVERY: 0.30,
    RiskRegime.HIGH_VOLATILITY: 0.50,
    RiskRegime.CRISIS: 0.70,
    RiskRegime.SYSTEMIC_STRESS: 0.85,
}

#: Systemic correlation uplift by the most stressed regime present in the book;
#: a single crisis borrower raises the assumed co-movement of the whole book.
REGIME_CORRELATION_UPLIFT: dict[RiskRegime, float] = {
    RiskRegime.NEUTRAL: 0.0,
    RiskRegime.TRENDING: 0.0,
    RiskRegime.MEAN_REVERTING: 0.0,
    RiskRegime.LOW_VOLATILITY: -0.05,
    RiskRegime.RECOVERY: 0.0,
    RiskRegime.HIGH_VOLATILITY: 0.10,
    RiskRegime.CRISIS: 0.25,
    RiskRegime.SYSTEMIC_STRESS: 0.40,
}


class BorrowerNotFoundError(LookupError):
    """Raised when a portfolio analysis targets an unknown borrower."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _model_result(model_id: str, parameters: dict, inputs: dict, outputs: dict) -> dict:
    """Wrap a deterministic model output with metadata + provenance (NFR-002)."""
    meta = MODEL_CATALOG[model_id]
    return {
        "model_id": model_id,
        "model_name": meta["name"],
        "model_version": meta["version"],
        "parameters": parameters,
        "inputs": inputs,
        "outputs": outputs,
        "provenance": {
            "basis": "creditgraph_portfolio_aggregation",
            "data_source": "neo4j_creditgraph",
            "deterministic": True,
            "llm_influenced": False,
            "spec_reference": "E12",
        },
        "timestamp": utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _collect_borrower_states() -> list[tuple[str, CurrentBorrowerState]]:
    """Return (borrower_id, state) for every borrower, skipping unreadable nodes.

    A borrower whose graph state fails to validate (e.g. missing requested
    amount) is excluded from the portfolio aggregate rather than aborting the
    whole portfolio view.
    """
    borrower_ids = await list_borrowers()
    states: list[tuple[str, CurrentBorrowerState]] = []
    for borrower_id in borrower_ids:
        try:
            state = await get_borrower_state(borrower_id)
        except Exception:
            continue
        if state is None:
            continue
        states.append((borrower_id, state))
    return states


def _borrower_protocols(state: CurrentBorrowerState) -> set[str]:
    """All protocol labels a borrower is exposed to (exposures + liabilities)."""
    protocols: set[str] = set()
    for exp in state.exposures:
        if exp.protocol:
            protocols.add(exp.protocol)
    for liab in state.liabilities:
        if liab.protocol:
            protocols.add(liab.protocol)
    return protocols


def _borrower_exposure(state: CurrentBorrowerState) -> float:
    """Total amount the lender has at risk to this borrower.

    Prefers the explicit protocol ``Exposure`` amounts; falls back to collateral
    value when no exposures are recorded.
    """
    exposure_total = sum(e.exposure_amount for e in state.exposures)
    if exposure_total > 0:
        return exposure_total
    return state.total_collateral_value


def _collateral_concentration(state: CurrentBorrowerState) -> float:
    """Dominant correlated-group share of collateral value (0..1)."""
    if not state.collateral:
        return 0.0
    groups: dict[str, float] = {}
    for c in state.collateral:
        groups[c.correlated_group] = groups.get(c.correlated_group, 0.0) + c.valuation
    total = sum(groups.values())
    if total <= 0:
        return 0.0
    return max(groups.values()) / total


def _borrower_volatility(state: CurrentBorrowerState) -> float:
    """Annualized volatility proxy for a borrower's position.

    Regime baseline, widened by collateral concentration (concentrated books
    behave more like a single risky asset).
    """
    regime_vol = REGIME_VOLATILITY.get(state.market_regime, 0.5)
    concentration = _collateral_concentration(state)
    return regime_vol * (1.0 + 0.4 * concentration)


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation).

    Deterministic; used to convert a confidence level into the VaR z-score.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")

    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]

    plow = 0.02425
    phigh = 1.0 - plow

    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
        )
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    )


# ---------------------------------------------------------------------------
# E12 — Portfolio exposure graph
# ---------------------------------------------------------------------------


async def get_portfolio_exposure() -> dict:
    """Aggregate every borrower into a portfolio-level exposure graph.

    Produces per-borrower nodes (collateral, liabilities, exposure, net worth)
    and a protocol-level rollup of total exposure across borrowers, plus
    portfolio concentration and the largest single points of failure.
    """
    states = await _collect_borrower_states()

    borrower_nodes: list[dict] = []
    protocol_exposure: dict[str, float] = {}
    protocol_borrowers: dict[str, int] = {}
    total_collateral = 0.0
    total_liabilities = 0.0
    total_exposure = 0.0

    for borrower_id, state in states:
        exposure = _borrower_exposure(state)
        net_worth = state.total_collateral_value - state.total_liabilities
        protocols = sorted(_borrower_protocols(state))

        borrower_nodes.append(
            {
                "borrower_id": borrower_id,
                "market_regime": state.market_regime.value,
                "total_collateral_value": round(state.total_collateral_value, 2),
                "total_liabilities": round(state.total_liabilities, 2),
                "total_exposure": round(exposure, 2),
                "net_worth": round(net_worth, 2),
                "protocols": protocols,
            }
        )

        total_collateral += state.total_collateral_value
        total_liabilities += state.total_liabilities
        total_exposure += exposure

        for protocol in protocols:
            protocol_exposure[protocol] = protocol_exposure.get(protocol, 0.0) + exposure
            protocol_borrowers[protocol] = protocol_borrowers.get(protocol, 0) + 1

    # Protocol rollup sorted by descending exposure.
    protocol_rollup = [
        {
            "protocol": protocol,
            "total_exposure": round(amount, 2),
            "borrower_count": protocol_borrowers[protocol],
            "share_of_portfolio": (
                round(amount / total_exposure, 6) if total_exposure > 0 else 0.0
            ),
        }
        for protocol, amount in sorted(
            protocol_exposure.items(), key=lambda kv: kv[1], reverse=True
        )
    ]

    # Concentration: largest single borrower share and largest protocol share.
    largest_borrower = (
        max(borrower_nodes, key=lambda b: b["total_exposure"]) if borrower_nodes else None
    )
    largest_protocol = protocol_rollup[0] if protocol_rollup else None

    return _model_result(
        "m_portfolio_exposure",
        parameters={
            "method": "neo4j_aggregated_portfolio_graph",
            "exposure_basis": "protocol_exposure_fallback_collateral",
        },
        inputs={
            "borrower_count": len(borrower_nodes),
            "protocol_count": len(protocol_rollup),
        },
        outputs={
            "borrowers": borrower_nodes,
            "protocols": protocol_rollup,
            "totals": {
                "total_collateral_value": round(total_collateral, 2),
                "total_liabilities": round(total_liabilities, 2),
                "total_exposure": round(total_exposure, 2),
                "net_exposure": round(total_collateral - total_liabilities, 2),
            },
            "concentration": {
                "largest_borrower": (
                    {
                        "borrower_id": largest_borrower["borrower_id"],
                        "exposure": largest_borrower["total_exposure"],
                        "share": (
                            round(largest_borrower["total_exposure"] / total_exposure, 6)
                            if total_exposure > 0
                            else 0.0
                        ),
                    }
                    if largest_borrower
                    else None
                ),
                "largest_protocol": (
                    {
                        "protocol": largest_protocol["protocol"],
                        "exposure": largest_protocol["total_exposure"],
                        "share": largest_protocol["share_of_portfolio"],
                    }
                    if largest_protocol
                    else None
                ),
            },
        },
    )


# ---------------------------------------------------------------------------
# E12 — Counterparty (protocol) exposure
# ---------------------------------------------------------------------------


async def get_counterparty_exposure(protocol: str) -> dict:
    """Total exposure to one protocol (counterparty) across all borrowers.

    Sums the protocol's exposure over every borrower that lists it (via
    Exposure or Liability edges) and reports the per-borrower breakdown and the
    share of the whole portfolio that this single counterparty represents.
    """
    if not protocol or not protocol.strip():
        raise ValueError("protocol must be a non-empty string")

    target = protocol.strip()
    states = await _collect_borrower_states()

    # Need the portfolio total to express the counterparty's share.
    portfolio_exposure = 0.0
    counterparty_borrowers: list[dict] = []
    counterparty_total = 0.0

    for borrower_id, state in states:
        borrower_exposure = _borrower_exposure(state)
        portfolio_exposure += borrower_exposure

        # Exposure attributable to this specific protocol for the borrower.
        protocol_exposure_here = 0.0
        matched = False
        for exp in state.exposures:
            if exp.protocol and exp.protocol.lower() == target.lower():
                protocol_exposure_here += exp.exposure_amount
                matched = True
        for liab in state.liabilities:
            if liab.protocol and liab.protocol.lower() == target.lower():
                protocol_exposure_here += liab.outstanding
                matched = True

        if matched:
            counterparty_total += protocol_exposure_here
            counterparty_borrowers.append(
                {
                    "borrower_id": borrower_id,
                    "market_regime": state.market_regime.value,
                    "protocol_exposure": round(protocol_exposure_here, 2),
                    "borrower_total_exposure": round(borrower_exposure, 2),
                    "exposure_share": (
                        round(protocol_exposure_here / borrower_exposure, 6)
                        if borrower_exposure > 0
                        else 0.0
                    ),
                }
            )

    counterparty_borrowers.sort(key=lambda b: b["protocol_exposure"], reverse=True)

    share_of_portfolio = (
        round(counterparty_total / portfolio_exposure, 6) if portfolio_exposure > 0 else 0.0
    )

    return _model_result(
        "m_counterparty_exposure",
        parameters={"method": "neo4j_protocol_rollup", "protocol": target},
        inputs={
            "requested_protocol": target,
            "portfolio_exposure": round(portfolio_exposure, 2),
        },
        outputs={
            "protocol": target,
            "total_exposure": round(counterparty_total, 2),
            "borrower_count": len(counterparty_borrowers),
            "share_of_portfolio": share_of_portfolio,
            "borrowers": counterparty_borrowers,
            "risk_level": (
                "high"
                if share_of_portfolio >= 0.40
                else "elevated"
                if share_of_portfolio >= 0.25
                else "moderate"
                if share_of_portfolio >= 0.10
                else "low"
            ),
        },
    )


# ---------------------------------------------------------------------------
# E12 — Contagion analysis
# ---------------------------------------------------------------------------


def _stressed_collateral(state: CurrentBorrowerState, shock_pct: float) -> float:
    """Collateral value after applying a (negative) price shock."""
    return state.total_collateral_value * (1.0 + shock_pct)


def _is_insolvent(state: CurrentBorrowerState, shock_pct: float) -> bool:
    """True when the shocked collateral no longer covers outstanding debt."""
    if state.total_liabilities <= 0:
        return False
    return _stressed_collateral(state, shock_pct) < state.total_liabilities


async def run_contagion_analysis(
    borrower_id: str, shock_pct: float = DEFAULT_CONTAGION_SHOCK
) -> dict:
    """Simulate a collateral shock to one borrower and propagate contagion.

    The primary borrower suffers ``shock_pct`` on its collateral. Borrowers that
    share a protocol (Exposure/Liability edge) with an infected borrower become
    infected in the next ring, absorbing ``shock_pct * transmission^ring`` of the
    shock. Each ring's loss is the infected borrowers' collateral times their
    effective shock. The cascade stops when no new borrowers are reached or
    ``MAX_CONTAGION_RINGS`` is reached.

    Deterministic: identical inputs always yield the same cascade.
    """
    if not 0.0 >= shock_pct >= -0.95:
        raise ValueError("shock_pct must be between -0.95 and 0.0")

    primary = await get_borrower_state(borrower_id)
    if primary is None:
        raise BorrowerNotFoundError(f"Borrower {borrower_id} not found")

    states = await _collect_borrower_states()
    states_by_id = {bid: st for bid, st in states}

    # Protocol index: protocol -> set of borrower ids (excluding the primary
    # so we can find neighbours).
    protocol_to_borrowers: dict[str, set[str]] = {}
    for bid, st in states:
        for protocol in _borrower_protocols(st):
            protocol_to_borrowers.setdefault(protocol, set()).add(bid)

    primary_protocols = _borrower_protocols(primary)
    primary_loss = abs(primary.total_collateral_value * shock_pct)

    rings: list[dict] = []
    infected: set[str] = set()
    defaulted: set[str] = set()

    # Primary ring (ring 0) is the shocked borrower itself.
    if _is_insolvent(primary, shock_pct):
        defaulted.add(borrower_id)
    rings.append(
        {
            "ring": 0,
            "borrowers": [borrower_id],
            "effective_shock": shock_pct,
            "collateral_loss": round(primary_loss, 2),
        }
    )

    # Frontier starts with borrowers sharing a protocol with the primary.
    frontier: set[str] = set()
    for protocol in primary_protocols:
        frontier |= protocol_to_borrowers.get(protocol, set())
    frontier.discard(borrower_id)
    frontier -= infected

    cumulative_loss = primary_loss
    for ring_index in range(1, MAX_CONTAGION_RINGS + 1):
        if not frontier:
            break
        effective_shock = shock_pct * (CONTAGION_TRANSMISSION**ring_index)
        ring_loss = 0.0
        ring_borrowers: list[str] = []
        next_frontier: set[str] = set()

        for bid in sorted(frontier):
            st = states_by_id.get(bid)
            if st is None:
                continue
            loss = abs(st.total_collateral_value * effective_shock)
            ring_loss += loss
            ring_borrowers.append(bid)
            infected.add(bid)
            if _is_insolvent(st, effective_shock):
                defaulted.add(bid)
            # Spread to this borrower's protocol neighbours.
            for protocol in _borrower_protocols(st):
                next_frontier |= protocol_to_borrowers.get(protocol, set())

        cumulative_loss += ring_loss
        rings.append(
            {
                "ring": ring_index,
                "borrowers": ring_borrowers,
                "effective_shock": round(effective_shock, 6),
                "collateral_loss": round(ring_loss, 2),
            }
        )

        # Prepare next frontier: neighbours not yet infected.
        next_frontier.discard(borrower_id)
        next_frontier -= infected
        frontier = next_frontier

    total_collateral_in_portfolio = sum(st.total_collateral_value for _, st in states)
    contagion_only_loss = cumulative_loss - primary_loss

    return _model_result(
        "m_contagion",
        parameters={
            "method": "protocol_linked_ring_cascade",
            "initial_shock_pct": shock_pct,
            "transmission_factor": CONTAGION_TRANSMISSION,
            "max_rings": MAX_CONTAGION_RINGS,
        },
        inputs={
            "source_borrower_id": borrower_id,
            "source_protocols": sorted(primary_protocols),
            "portfolio_borrower_count": len(states_by_id),
        },
        outputs={
            "source_borrower_id": borrower_id,
            "primary_collateral_loss": round(primary_loss, 2),
            "contagion_collateral_loss": round(contagion_only_loss, 2),
            "total_collateral_loss": round(cumulative_loss, 2),
            "loss_as_share_of_portfolio": (
                round(cumulative_loss / total_collateral_in_portfolio, 6)
                if total_collateral_in_portfolio > 0
                else 0.0
            ),
            "infected_borrower_count": len(infected),
            "defaulted_borrower_count": len(defaulted),
            "defaulted_borrowers": sorted(defaulted),
            "cascade_depth": len(rings) - 1,
            "rings": rings,
            "severity": (
                "severe"
                if len(defaulted) >= 3 or contagion_only_loss >= 0.25 * cumulative_loss
                else "moderate"
                if len(defaulted) >= 1
                else "localized"
            ),
        },
    )


# ---------------------------------------------------------------------------
# E12 — Portfolio Value-at-Risk
# ---------------------------------------------------------------------------


async def compute_portfolio_var(confidence: float = 0.95) -> dict:
    """Parametric (variance-covariance) VaR for the whole credit portfolio.

    Treats each borrower as a position of size ``w_i`` (its total exposure) with
    annualized volatility ``σ_i`` (regime + concentration driven). Portfolio
    variance assumes a single systemic factor linking every pair of borrowers:

        σ_p² = Σ w_i² σ_i² + 2 Σ_{i<j} w_i w_j σ_i σ_j ρ

    VaR (over ``VAR_HORIZON_DAYS``) = z · σ_p · √horizon · PortfolioValue,
    with ``z`` the standard-normal quantile at ``confidence``.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")

    states = await _collect_borrower_states()
    if not states:
        return _model_result(
            "m_portfolio_var",
            parameters={
                "method": "parametric_variance_covariance",
                "confidence": confidence,
                "horizon_days": VAR_HORIZON_DAYS,
            },
            inputs={"borrower_count": 0},
            outputs={
                "portfolio_value": 0.0,
                "portfolio_volatility_annual": 0.0,
                "portfolio_volatility_horizon": 0.0,
                "z_score": round(_norm_ppf(confidence), 6),
                "var": 0.0,
                "var_pct_of_portfolio": 0.0,
                "positions": [],
            },
        )

    # Most-stressed regime present drives the assumed systemic correlation.
    worst_regime = max(
        states, key=lambda kv: REGIME_CORRELATION_UPLIFT.get(kv[1].market_regime, 0.0)
    )[1].market_regime
    systemic_corr = min(
        0.95,
        max(0.0, DEFAULT_SYSTEMIC_CORRELATION + REGIME_CORRELATION_UPLIFT.get(worst_regime, 0.0)),
    )

    weights: list[float] = []
    vols: list[float] = []
    positions: list[dict] = []
    portfolio_value = 0.0
    for borrower_id, state in states:
        exposure = _borrower_exposure(state)
        vol = _borrower_volatility(state)
        weights.append(exposure)
        vols.append(vol)
        portfolio_value += exposure
        positions.append(
            {
                "borrower_id": borrower_id,
                "market_regime": state.market_regime.value,
                "exposure": round(exposure, 2),
                "annual_volatility": round(vol, 6),
            }
        )

    if portfolio_value <= 0:
        sigma_p = 0.0
    else:
        # Variance contribution (deterministic, O(n^2) over borrowers).
        variance = 0.0
        for i in range(len(weights)):
            wi, vi = weights[i] / portfolio_value, vols[i]
            variance += wi * wi * vi * vi
            for j in range(i + 1, len(weights)):
                wj, vj = weights[j] / portfolio_value, vols[j]
                variance += 2.0 * wi * wj * vi * vj * systemic_corr
        variance = max(0.0, variance)
        sigma_p = math.sqrt(variance)

    sigma_horizon = sigma_p * math.sqrt(VAR_HORIZON_DAYS / 365.0)
    z = _norm_ppf(confidence)
    var_value = z * sigma_horizon * portfolio_value

    return _model_result(
        "m_portfolio_var",
        parameters={
            "method": "parametric_variance_covariance",
            "confidence": confidence,
            "horizon_days": VAR_HORIZON_DAYS,
            "systemic_correlation": round(systemic_corr, 6),
            "worst_regime": worst_regime.value,
        },
        inputs={
            "borrower_count": len(positions),
            "portfolio_value": round(portfolio_value, 2),
        },
        outputs={
            "portfolio_value": round(portfolio_value, 2),
            "portfolio_volatility_annual": round(sigma_p, 6),
            "portfolio_volatility_horizon": round(sigma_horizon, 6),
            "z_score": round(z, 6),
            "var": round(var_value, 2),
            "var_pct_of_portfolio": (
                round(var_value / portfolio_value, 6) if portfolio_value > 0 else 0.0
            ),
            "positions": positions,
        },
    )


# ---------------------------------------------------------------------------
# E12 — Systemic stress impact
# ---------------------------------------------------------------------------


async def get_systemic_stress_impact(shock_pct: float = SYSTEMIC_SHOCK) -> dict:
    """Apply a portfolio-wide systemic shock and report aggregate impact.

    Every borrower's collateral is marked down by ``shock_pct``; the aggregate
    collateral loss, loss percentage and the count of borrowers tipped into
    insolvency (shocked collateral < outstanding liabilities) are reported,
    together with the stressed net worth of the book.
    """
    if not 0.0 >= shock_pct >= -0.95:
        raise ValueError("shock_pct must be between -0.95 and 0.0")

    states = await _collect_borrower_states()

    base_collateral = 0.0
    base_liabilities = 0.0
    stressed_collateral = 0.0
    total_loss = 0.0
    insolvent: list[dict] = []
    stressed_borrowers: list[dict] = []

    for borrower_id, state in states:
        base_collateral += state.total_collateral_value
        base_liabilities += state.total_liabilities
        loss = abs(state.total_collateral_value * shock_pct)
        total_loss += loss
        stressed_value = _stressed_collateral(state, shock_pct)
        stressed_collateral += stressed_value

        is_insolvent = (
            state.total_liabilities > 0 and stressed_value < state.total_liabilities
        )
        if is_insolvent:
            insolvent.append(
                {
                    "borrower_id": borrower_id,
                    "stressed_collateral": round(stressed_value, 2),
                    "total_liabilities": round(state.total_liabilities, 2),
                    "shortfall": round(state.total_liabilities - stressed_value, 2),
                }
            )

        stressed_borrowers.append(
            {
                "borrower_id": borrower_id,
                "market_regime": state.market_regime.value,
                "base_collateral": round(state.total_collateral_value, 2),
                "stressed_collateral": round(stressed_value, 2),
                "loss": round(loss, 2),
                "insolvent": is_insolvent,
            }
        )

    loss_pct = (total_loss / base_collateral) if base_collateral > 0 else 0.0
    stressed_net_worth = stressed_collateral - base_liabilities
    base_net_worth = base_collateral - base_liabilities

    return _model_result(
        "m_systemic_stress",
        parameters={
            "method": "uniform_portfolio_shock",
            "shock_pct": shock_pct,
            "basis": "collateral_markdown",
        },
        inputs={
            "borrower_count": len(stressed_borrowers),
            "base_collateral": round(base_collateral, 2),
        },
        outputs={
            "shock_pct": shock_pct,
            "total_collateral_loss": round(total_loss, 2),
            "loss_pct_of_collateral": round(loss_pct, 6),
            "base_collateral": round(base_collateral, 2),
            "stressed_collateral": round(stressed_collateral, 2),
            "base_liabilities": round(base_liabilities, 2),
            "base_net_worth": round(base_net_worth, 2),
            "stressed_net_worth": round(stressed_net_worth, 2),
            "net_worth_impairment": round(base_net_worth - stressed_net_worth, 2),
            "insolvent_borrower_count": len(insolvent),
            "insolvent_borrowers": insolvent,
            "severity": (
                "critical"
                if loss_pct >= 0.40
                else "severe"
                if loss_pct >= 0.25
                else "elevated"
                if loss_pct >= 0.10
                else "moderate"
            ),
            "borrowers": stressed_borrowers,
        },
    )


__all__ = [
    "MODEL_CATALOG",
    "BorrowerNotFoundError",
    "get_portfolio_exposure",
    "get_counterparty_exposure",
    "run_contagion_analysis",
    "compute_portfolio_var",
    "get_systemic_stress_impact",
]
