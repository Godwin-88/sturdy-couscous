"""Deterministic correlation & hidden-concentration analysis (E6 / F6.4).

Implements spec §14 EPIC E6 feature F6.4 and user story E6-US2:
  - compute_correlation_matrix: pairwise correlation matrix for a symbol set
  - compute_portfolio_correlation_exposure: concentration + hidden correlation
    exposure for a borrower's collateral portfolio
  - identify_correlated_groups: asset clusters whose correlation exceeds a
    configurable threshold

For the MVP the correlation source is a *synthetic* group model rather than an
estimated return covariance: assets are classified into groups and each group
carries a fixed intra-group correlation (crypto 0.7, stablecoin 0.3, l2 0.6,
defi 0.5, default 0.2). Cross-group correlations come from a small symmetric
table. This keeps the engine fully deterministic and free of LLM influence
(spec §7 / NFR-002): the LLM may explain these numbers but can never alter
them. Every function returns its result wrapped with model metadata +
provenance so the values can be attributed to a versioned model.

Replacing the synthetic layer later only requires changing `pair_correlation`;
`parameters.basis` in the provenance block records which basis produced a
result.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from creditgraph.graph.credit_graph import get_borrower_state
from creditgraph.models import CurrentBorrowerState

# ---------------------------------------------------------------------------
# Model catalogue (metadata only, deterministic + versioned)
# ---------------------------------------------------------------------------

MODEL_CATALOG: dict[str, dict[str, str]] = {
    "m_correlation_matrix": {"name": "Asset Correlation Matrix", "version": "1.0.0"},
    "m_portfolio_correlation": {
        "name": "Portfolio Correlation Exposure",
        "version": "1.0.0",
    },
    "m_correlated_groups": {"name": "Correlated Asset Groups", "version": "1.0.0"},
}

#: Correlation basis label recorded in provenance for every result.
CORRELATION_BASIS = "synthetic_group_correlation"

#: Default (configurable) correlation threshold — E6-US2.
DEFAULT_CORRELATION_THRESHOLD = 0.5

#: Fallback group for unrecognised symbols.
DEFAULT_GROUP = "default"

#: Intra-group correlation per spec E6 MVP.
GROUP_BASE_CORRELATION: dict[str, float] = {
    "crypto": 0.7,
    "stablecoin": 0.3,
    "l2": 0.6,
    "defi": 0.5,
    DEFAULT_GROUP: 0.2,
}

#: Known asset universe per group (drives classification + group discovery).
GROUP_MEMBERS: dict[str, tuple[str, ...]] = {
    "crypto": (
        "BTC", "WBTC", "ETH", "WETH", "STETH", "SOL", "AVAX",
        "DOT", "ADA", "XRP", "LTC", "BNB", "ATOM", "NEAR", "CTC",
    ),
    "stablecoin": ("USDC", "USDT", "DAI", "TUSD", "FRAX", "LUSD", "PYUSD", "USDE"),
    "l2": ("ARB", "OP", "MATIC", "POL", "STRK", "ZK", "MNT", "METIS", "IMX", "BASE"),
    "defi": (
        "AAVE", "UNI", "COMP", "MKR", "CRV", "SNX",
        "LDO", "SUSHI", "BAL", "RPL", "GMX",
    ),
}

#: Reverse index: symbol -> group.
SYMBOL_TO_GROUP: dict[str, str] = {
    symbol: group for group, symbols in GROUP_MEMBERS.items() for symbol in symbols
}

#: Explicit symmetric cross-group correlations, keyed by sorted group pair.
CROSS_GROUP_CORRELATION: dict[tuple[str, str], float] = {
    ("crypto", "l2"): 0.65,          # L2 tokens carry ETH beta
    ("crypto", "defi"): 0.60,
    ("defi", "l2"): 0.55,
    ("crypto", "stablecoin"): 0.05,
    ("l2", "stablecoin"): 0.05,
    ("defi", "stablecoin"): 0.05,
    ("crypto", DEFAULT_GROUP): 0.15,
    ("l2", DEFAULT_GROUP): 0.15,
    ("defi", DEFAULT_GROUP): 0.15,
    (DEFAULT_GROUP, "stablecoin"): 0.05,
}

#: Damping applied to `min(base_a, base_b)` when no explicit pair is defined.
CROSS_GROUP_DAMPING = 0.5

#: Guard rail on matrix size (n^2 growth, and keeps API payloads bounded).
MAX_MATRIX_SYMBOLS = 64

_TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+")


class BorrowerNotFoundError(LookupError):
    """Raised when correlation analysis is requested for an unknown borrower."""


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
            "basis": CORRELATION_BASIS,
            "data_source": "static_group_catalog",
            "deterministic": True,
            "llm_influenced": False,
            "spec_reference": "E6/F6.4",
        },
        "timestamp": utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _candidate_groups(text: str) -> set[str]:
    """Groups implied by a symbol or correlated-group label.

    Tokenises on non-alphanumeric separators so composite collateral symbols
    (``ETH+USDC``, ``ETH/USDC LP``) and graph group labels (``eth_l2``) both
    resolve. A token matches either a known asset symbol or a group name.
    """
    groups: set[str] = set()
    for token in _TOKEN_SPLIT.split(text or ""):
        if not token:
            continue
        upper = token.upper()
        lower = token.lower()
        if upper in SYMBOL_TO_GROUP:
            groups.add(SYMBOL_TO_GROUP[upper])
        elif lower in GROUP_BASE_CORRELATION:
            groups.add(lower)
    return groups


def classify_asset(symbol: str, correlated_group: str | None = None) -> str:
    """Resolve an asset to a correlation group.

    Considers both the explicit graph ``correlated_group`` label and the symbol
    itself. When several groups are implied (e.g. ``ETH+USDC`` implies crypto
    and stablecoin) the highest-correlation group wins, so a composite position
    is never treated as less correlated than its riskiest leg.
    """
    candidates: set[str] = set()
    if correlated_group and correlated_group.strip().lower() not in {"", "none"}:
        candidates |= _candidate_groups(correlated_group)
    candidates |= _candidate_groups(symbol)
    if not candidates:
        return DEFAULT_GROUP
    return max(candidates, key=lambda g: (GROUP_BASE_CORRELATION.get(g, 0.0), g))


def pair_correlation(
    symbol_a: str,
    symbol_b: str,
    group_a: str | None = None,
    group_b: str | None = None,
) -> float:
    """Synthetic pairwise correlation for two assets (symmetric, in [0, 1])."""
    if _normalize_symbol(symbol_a) == _normalize_symbol(symbol_b):
        return 1.0

    ga = group_a or classify_asset(symbol_a)
    gb = group_b or classify_asset(symbol_b)
    default_base = GROUP_BASE_CORRELATION[DEFAULT_GROUP]

    if ga == gb:
        return GROUP_BASE_CORRELATION.get(ga, default_base)

    key = (ga, gb) if ga <= gb else (gb, ga)
    if key in CROSS_GROUP_CORRELATION:
        return CROSS_GROUP_CORRELATION[key]

    base_a = GROUP_BASE_CORRELATION.get(ga, default_base)
    base_b = GROUP_BASE_CORRELATION.get(gb, default_base)
    return round(min(base_a, base_b) * CROSS_GROUP_DAMPING, 4)


# ---------------------------------------------------------------------------
# F6.4 — Correlation matrix
# ---------------------------------------------------------------------------


def compute_correlation_matrix(
    asset_symbols: list[str],
    threshold: float = DEFAULT_CORRELATION_THRESHOLD,
) -> dict:
    """Pairwise correlation matrix for `asset_symbols`.

    The matrix is symmetric with a unit diagonal. Duplicate symbols are
    de-duplicated while preserving input order. Returns the matrix plus the
    pairs at or above `threshold`, wrapped with model provenance.
    """
    if not asset_symbols:
        raise ValueError("asset_symbols must contain at least one symbol")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")

    symbols: list[str] = []
    for raw in asset_symbols:
        symbol = _normalize_symbol(raw)
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    if not symbols:
        raise ValueError("asset_symbols must contain at least one non-empty symbol")
    if len(symbols) > MAX_MATRIX_SYMBOLS:
        raise ValueError(f"at most {MAX_MATRIX_SYMBOLS} symbols may be correlated at once")

    groups = {symbol: classify_asset(symbol) for symbol in symbols}

    matrix: dict[str, dict[str, float]] = {}
    pairs: list[dict] = []
    for i, a in enumerate(symbols):
        row: dict[str, float] = {}
        for j, b in enumerate(symbols):
            rho = 1.0 if i == j else pair_correlation(a, b, groups[a], groups[b])
            row[b] = round(rho, 6)
            if j > i:
                pairs.append(
                    {
                        "asset_a": a,
                        "asset_b": b,
                        "group_a": groups[a],
                        "group_b": groups[b],
                        "correlation": round(rho, 6),
                        "same_group": groups[a] == groups[b],
                        "above_threshold": rho >= threshold,
                    }
                )
        matrix[a] = row

    off_diagonal = [p["correlation"] for p in pairs]
    average = sum(off_diagonal) / len(off_diagonal) if off_diagonal else 0.0
    flagged = [p for p in pairs if p["above_threshold"]]
    unclassified = [s for s, g in groups.items() if g == DEFAULT_GROUP]

    return _model_result(
        "m_correlation_matrix",
        parameters={
            "method": "group_lookup",
            "basis": CORRELATION_BASIS,
            "threshold": threshold,
            "group_base_correlation": dict(GROUP_BASE_CORRELATION),
            "cross_group_damping": CROSS_GROUP_DAMPING,
        },
        inputs={
            "requested_symbols": list(asset_symbols),
            "resolved_symbols": symbols,
            "symbol_count": len(symbols),
        },
        outputs={
            "symbols": symbols,
            "groups": groups,
            "matrix": matrix,
            "pairs": pairs,
            "highly_correlated_pairs": flagged,
            "average_correlation": round(average, 6),
            "max_pair_correlation": round(max(off_diagonal), 6) if off_diagonal else 0.0,
            "unclassified_symbols": unclassified,
        },
    )


# ---------------------------------------------------------------------------
# F6.3 / F6.4 — Portfolio concentration + hidden correlation exposure
# ---------------------------------------------------------------------------


def _aggregate_positions(state: CurrentBorrowerState) -> list[dict]:
    """Collapse collateral into value-weighted positions keyed by symbol."""
    by_symbol: dict[str, dict] = {}
    for item in state.collateral:
        symbol = _normalize_symbol(item.symbol) or _normalize_symbol(item.asset_id)
        if not symbol:
            continue
        entry = by_symbol.get(symbol)
        if entry is None:
            entry = {
                "symbol": symbol,
                "group": classify_asset(symbol, item.correlated_group),
                "valuation": 0.0,
                "adjusted_valuation": 0.0,
                "declared_groups": [],
            }
            by_symbol[symbol] = entry
        entry["valuation"] += item.valuation
        entry["adjusted_valuation"] += item.valuation * (1.0 - item.haircut)
        if item.correlated_group and item.correlated_group not in entry["declared_groups"]:
            entry["declared_groups"].append(item.correlated_group)
    return list(by_symbol.values())


def _risk_level(
    average_pair_correlation: float, concentration: float, hidden: float
) -> str:
    """Classify correlation risk from pair correlation, concentration and hidden risk.

    Uses fixed bands rather than the caller's flagging `threshold` so that risk
    levels stay comparable across borrowers even when a caller tunes the
    pair-flagging threshold.
    """
    if average_pair_correlation >= 0.70 or concentration >= 0.80 or hidden >= 0.40:
        return "high"
    if average_pair_correlation >= 0.50 or concentration >= 0.60 or hidden >= 0.25:
        return "elevated"
    if average_pair_correlation >= 0.30 or hidden >= 0.10:
        return "moderate"
    return "low"


async def compute_portfolio_correlation_exposure(
    borrower_id: str,
    threshold: float = DEFAULT_CORRELATION_THRESHOLD,
    state: CurrentBorrowerState | None = None,
) -> dict:
    """Concentration risk + hidden correlation exposure for a borrower.

    Definitions (all deterministic, weights `w` are collateral value shares):

      portfolio_correlation = ΣΣ w_i·w_j·ρ_ij            (ρ_ii = 1)
      independence_baseline = Σ w_i²                     (correlation-blind view)
      hidden_correlation_exposure = portfolio_correlation − independence_baseline
                                  = Σ_{i≠j} w_i·w_j·ρ_ij
      weighted_average_pair_correlation
                            = Σ_{i≠j} w_i·w_j·ρ_ij / Σ_{i≠j} w_i·w_j
      effective_positions   = 1 / portfolio_correlation

    `portfolio_correlation` is a *variance ratio*, so its floor is
    `independence_baseline` (a perfectly uncorrelated 2-asset book scores 0.5);
    it drives the diversification metrics. `weighted_average_pair_correlation`
    is the threshold-comparable number — it is the exposure-weighted mean
    correlation *between distinct* positions and is 0 for an uncorrelated book
    regardless of position count, so it is what `threshold` is applied to.

    `hidden_correlation_exposure` is the concentration a naive "count the
    distinct assets" view misses: zero only when every position is mutually
    uncorrelated, growing toward 1 as the portfolio behaves like a single
    asset (E6-US2).

    Pass `state` to analyse a borrower state directly and skip the graph read.
    Raises `BorrowerNotFoundError` when the borrower does not exist.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")

    if state is None:
        state = await get_borrower_state(borrower_id)
    if state is None:
        raise BorrowerNotFoundError(f"Borrower {borrower_id} not found")

    positions = _aggregate_positions(state)
    total_value = sum(p["valuation"] for p in positions)
    adjusted_value = sum(p["adjusted_valuation"] for p in positions)

    if not positions or total_value <= 0:
        return _model_result(
            "m_portfolio_correlation",
            parameters={
                "method": "weighted_pairwise_correlation",
                "basis": CORRELATION_BASIS,
                "threshold": threshold,
            },
            inputs={"borrower_id": state.borrower_id, "position_count": len(positions)},
            outputs={
                "borrower_id": state.borrower_id,
                "market_regime": state.market_regime.value,
                "positions": [],
                "group_exposure": {},
                "total_collateral_value": 0.0,
                "haircut_adjusted_value": 0.0,
                "portfolio_correlation": 0.0,
                "weighted_average_pair_correlation": 0.0,
                "independence_baseline": 0.0,
                "hidden_correlation_exposure": 0.0,
                "hidden_exposure_value": 0.0,
                "effective_positions": 0.0,
                "naive_effective_positions": 0.0,
                "diversification_shortfall": 0.0,
                "concentration_factor": 0.0,
                "dominant_group": None,
                "position_hhi": 0.0,
                "group_hhi": 0.0,
                "correlated_pairs": [],
                "highly_correlated_pairs": [],
                "risk_level": "unknown",
                "risk_factors": ["No valued collateral available for correlation analysis"],
            },
        )

    for position in positions:
        position["weight"] = position["valuation"] / total_value

    # Group-level exposure (F6.3 concentration).
    group_exposure: dict[str, dict[str, float]] = {}
    for position in positions:
        entry = group_exposure.setdefault(position["group"], {"value": 0.0, "weight": 0.0})
        entry["value"] += position["valuation"]
        entry["weight"] += position["weight"]

    dominant_group = max(group_exposure, key=lambda g: (group_exposure[g]["value"], g))
    concentration = group_exposure[dominant_group]["value"] / total_value

    # Weighted pairwise correlation aggregation.
    portfolio_correlation = 0.0
    correlated_pairs: list[dict] = []
    for i, p in enumerate(positions):
        for j, q in enumerate(positions):
            rho = (
                1.0
                if i == j
                else pair_correlation(p["symbol"], q["symbol"], p["group"], q["group"])
            )
            portfolio_correlation += p["weight"] * q["weight"] * rho
            if j > i:
                correlated_pairs.append(
                    {
                        "asset_a": p["symbol"],
                        "asset_b": q["symbol"],
                        "group_a": p["group"],
                        "group_b": q["group"],
                        "correlation": round(rho, 6),
                        "combined_weight": round(p["weight"] + q["weight"], 6),
                        "correlated_value": round(
                            (p["valuation"] + q["valuation"]) * rho, 2
                        ),
                        "above_threshold": rho >= threshold,
                    }
                )

    portfolio_correlation = min(1.0, max(0.0, portfolio_correlation))
    independence_baseline = sum(p["weight"] ** 2 for p in positions)
    hidden = max(0.0, portfolio_correlation - independence_baseline)
    # Exposure-weighted mean correlation between *distinct* positions. The
    # cross-weight mass is (1 - Σw²); zero for a single position.
    cross_weight = max(0.0, 1.0 - independence_baseline)
    average_pair_correlation = (hidden / cross_weight) if cross_weight > 1e-12 else 0.0
    effective_positions = 1.0 / portfolio_correlation if portfolio_correlation > 0 else 0.0
    naive_effective = 1.0 / independence_baseline if independence_baseline > 0 else 0.0
    group_hhi = sum(e["weight"] ** 2 for e in group_exposure.values())

    flagged_pairs = [p for p in correlated_pairs if p["above_threshold"]]

    risk_factors: list[str] = []
    if concentration > 0.50:
        risk_factors.append(
            f"{concentration*100:.0f}% of collateral in the '{dominant_group}' correlation group"
        )
    if average_pair_correlation >= threshold:
        risk_factors.append(
            f"Average correlation between collateral positions "
            f"{average_pair_correlation:.2f} at or above threshold {threshold:.2f}"
        )
    if hidden > 0.10:
        risk_factors.append(
            f"Hidden correlation exposure of {hidden*100:.0f}% not visible in naive diversification"
        )
    if flagged_pairs:
        risk_factors.append(
            f"{len(flagged_pairs)} collateral pair(s) correlated at or above {threshold:.2f}"
        )
    if len(positions) == 1:
        risk_factors.append("Single-asset collateral portfolio: no diversification benefit")
    if not risk_factors:
        risk_factors.append("Collateral shows no material correlation concentration")

    return _model_result(
        "m_portfolio_correlation",
        parameters={
            "method": "weighted_pairwise_correlation",
            "basis": CORRELATION_BASIS,
            "threshold": threshold,
            "group_base_correlation": dict(GROUP_BASE_CORRELATION),
        },
        inputs={
            "borrower_id": state.borrower_id,
            "market_regime": state.market_regime.value,
            "position_count": len(positions),
            "total_collateral_value": round(total_value, 4),
        },
        outputs={
            "borrower_id": state.borrower_id,
            "market_regime": state.market_regime.value,
            "positions": [
                {
                    "symbol": p["symbol"],
                    "group": p["group"],
                    "declared_groups": p["declared_groups"],
                    "valuation": round(p["valuation"], 2),
                    "adjusted_valuation": round(p["adjusted_valuation"], 2),
                    "weight": round(p["weight"], 6),
                }
                for p in positions
            ],
            "group_exposure": {
                group: {
                    "value": round(entry["value"], 2),
                    "weight": round(entry["weight"], 6),
                    "intra_group_correlation": GROUP_BASE_CORRELATION.get(
                        group, GROUP_BASE_CORRELATION[DEFAULT_GROUP]
                    ),
                }
                for group, entry in group_exposure.items()
            },
            "total_collateral_value": round(total_value, 2),
            "haircut_adjusted_value": round(adjusted_value, 2),
            "portfolio_correlation": round(portfolio_correlation, 6),
            "weighted_average_pair_correlation": round(average_pair_correlation, 6),
            "independence_baseline": round(independence_baseline, 6),
            "hidden_correlation_exposure": round(hidden, 6),
            "hidden_exposure_value": round(total_value * hidden, 2),
            "effective_positions": round(effective_positions, 4),
            "naive_effective_positions": round(naive_effective, 4),
            "diversification_shortfall": round(max(0.0, naive_effective - effective_positions), 4),
            "concentration_factor": round(concentration, 6),
            "dominant_group": dominant_group,
            "position_hhi": round(independence_baseline, 6),
            "group_hhi": round(group_hhi, 6),
            "correlated_pairs": correlated_pairs,
            "highly_correlated_pairs": flagged_pairs,
            "risk_level": _risk_level(average_pair_correlation, concentration, hidden),
            "risk_factors": risk_factors,
        },
    )


# ---------------------------------------------------------------------------
# E6-US2 — Correlated group discovery
# ---------------------------------------------------------------------------


def identify_correlated_groups(threshold: float = DEFAULT_CORRELATION_THRESHOLD) -> dict:
    """Asset groups whose correlation is at or above `threshold`.

    Reports both intra-group clusters (assets that move together) and
    cross-group links above the threshold, so that collateral spread across
    two separately-named groups is still flagged as correlated. The threshold
    is configurable per call (E6-US2).
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")

    groups: list[dict] = []
    excluded: list[dict] = []
    for group, symbols in sorted(GROUP_MEMBERS.items()):
        correlation = GROUP_BASE_CORRELATION.get(
            group, GROUP_BASE_CORRELATION[DEFAULT_GROUP]
        )
        record = {
            "group": group,
            "correlation": correlation,
            "asset_count": len(symbols),
            "assets": list(symbols),
        }
        if correlation >= threshold:
            groups.append(record)
        else:
            excluded.append({"group": group, "correlation": correlation})

    cross_links: list[dict] = []
    for (group_a, group_b), correlation in sorted(CROSS_GROUP_CORRELATION.items()):
        if correlation >= threshold and group_a in GROUP_MEMBERS and group_b in GROUP_MEMBERS:
            cross_links.append(
                {
                    "group_a": group_a,
                    "group_b": group_b,
                    "correlation": correlation,
                }
            )

    covered = sorted({s for g in groups for s in g["assets"]})

    return _model_result(
        "m_correlated_groups",
        parameters={
            "threshold": threshold,
            "basis": CORRELATION_BASIS,
            "group_base_correlation": dict(GROUP_BASE_CORRELATION),
        },
        inputs={
            "universe_size": len(SYMBOL_TO_GROUP),
            "group_count": len(GROUP_MEMBERS),
        },
        outputs={
            "threshold": threshold,
            "groups": groups,
            "group_count": len(groups),
            "cross_group_links": cross_links,
            "assets_covered": covered,
            "assets_covered_count": len(covered),
            "excluded_groups": excluded,
        },
    )
