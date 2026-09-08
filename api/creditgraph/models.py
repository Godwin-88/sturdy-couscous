"""Pydantic domain models for CreditGraph."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DecisionStatus(str, Enum):
    RECOMMENDED = "recommended"
    APPROVED = "approved"
    REJECTED = "rejected"
    OVERRIDDEN = "overridden"
    EXECUTED = "executed"


class RiskRegime(str, Enum):
    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CRISIS = "crisis"
    SYSTEMIC_STRESS = "systemic_stress"
    RECOVERY = "recovery"
    NEUTRAL = "neutral"


class AttestationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    INVALID = "invalid"


# ---------------------------------------------------------------------------
# Core domain entities
# ---------------------------------------------------------------------------


class Wallet(BaseModel):
    address: str
    chain: str


class Asset(BaseModel):
    asset_id: str
    symbol: str
    chain: str
    price_usd: float = Field(0.0, ge=0.0)
    volatility_annualized: float = Field(0.0, ge=0.0)
    quantity: float = Field(0.0, ge=0.0)


class Transaction(BaseModel):
    tx_id: str
    chain: str
    timestamp: datetime
    tx_type: str  # deposit/withdrawal/borrow/repay/collateralize
    amount: float = Field(0.0, ge=0.0)
    asset_symbol: str
    counterparty: str | None = None


class Attestation(BaseModel):
    attestation_id: str
    tx_id: str
    source_chain: str
    status: AttestationStatus = AttestationStatus.VERIFIED
    verifier: str | None = None
    verified_at: datetime | None = None


class Evidence(BaseModel):
    """Verified cross-chain evidence (spec §25 / E1-US3 lineage).

    A risk observation can be traversed to its supporting evidence; evidence
    identifies source chain, transaction/event identifier, timestamp and
    attestation. Verified and unverified evidence are never conflated.
    """

    evidence_id: str
    source_chain: str
    tx_id: str
    timestamp: datetime = Field(default_factory=utcnow)
    attestation_id: str
    status: AttestationStatus = AttestationStatus.UNVERIFIED
    verifier: str | None = None
    verified_at: datetime | None = None
    header_number: int | None = None
    chain_key: int | None = None
    proof: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class Collateral(BaseModel):
    asset_id: str
    symbol: str
    valuation: float = Field(0.0, ge=0.0)
    quantity: float = Field(0.0, ge=0.0)
    haircut: float = Field(0.0, ge=0.0, le=1.0)
    correlated_group: str = "none"


class Liability(BaseModel):
    protocol: str
    outstanding: float = Field(0.0, ge=0.0)
    asset_symbol: str


class Exposure(BaseModel):
    protocol: str
    asset: str
    exposure_amount: float = Field(0.0, ge=0.0)


class CurrentBorrowerState(BaseModel):
    """Aggregated borrower state used by the deterministic risk engine.

    Mirrors spec §10 / §25 borrower representation (assets, liabilities,
    collateral, protocol exposure, concentration).
    """

    borrower_id: str
    requested_amount: float = Field(..., gt=0, description="Requested loan (CTC units)")
    fico_score: float = Field(680.0, ge=300.0, le=850.0)
    total_collateral_value: float = Field(0.0, ge=0.0)
    total_liabilities: float = Field(0.0, ge=0.0)
    assets: list[Asset] = Field(default_factory=list)
    collateral: list[Collateral] = Field(default_factory=list)
    liabilities: list[Liability] = Field(default_factory=list)
    exposures: list[Exposure] = Field(default_factory=list)
    market_regime: RiskRegime = RiskRegime.HIGH_VOLATILITY
    # Attested evidence references (persisted want lineage)
    attestation_refs: list[str] = Field(default_factory=list)


class BorrowerProfile(BaseModel):
    """Legacy borrower profile used by the /risk/credit-score endpoint."""

    fico_score: float = Field(680.0, ge=300.0, le=850.0)
    dti_ratio: float = Field(0.0, ge=0.0, le=1.0)
    loan_to_value: float = Field(0.0, ge=0.0, le=1.0)


class ScenarioInput(BaseModel):
    name: str = Field("", description="Scenario label")
    stress_label: str = Field("", description="Human-readable scenario label")
    shock_pct: float = Field(-0.20, ge=-0.90, le=0.0, description="Market shock as a negative delta (e.g. -0.2)")
    vix: float = Field(25.0, ge=0.0)


# ---------------------------------------------------------------------------
# Risk / Decision outputs
# ---------------------------------------------------------------------------


class RiskObservation(BaseModel):
    observation_id: str
    model_id: str
    model_name: str
    model_version: str
    value: float
    unit: str
    note: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class CreditAssessment(BaseModel):
    """Deterministic risk assessment result (E5/E6)."""

    borrower_id: str
    credit_score: float = Field(ge=0.0, le=100.0)
    probability_of_default: float = Field(ge=0.0, le=1.0)
    expected_loss: float = Field(ge=0.0)
    loan_to_value: float = Field(ge=0.0)
    required_collateral_ratio: float = Field(ge=0.0)
    stress_ltv: float = Field(ge=0.0)
    market_regime: RiskRegime
    principal_risk_factors: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    IN_BLOCK = "in_block"
    FINALIZED = "finalized"
    FAILED = "failed"
    TIMEOUT = "timeout"


class CreditExecution(BaseModel):
    """A Creditcoin execution request/record (E10).

    Captures the full lender→borrower transfer lifecycle: scheduled against an
    approved CreditDecision, submitted as a `balances.transferKeepAlive`
    extrinsic on Creditcoin (testnet/mainnet), and monitored to finalization.
    """

    execution_id: str
    decision_id: str
    borrower_id: str
    to: str
    amount: float = Field(gt=0.0, description="Amount in CTC (decimal)")
    amount_planck: str | None = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    tx_hash: str | None = None
    block: str | None = None
    block_hash: str | None = None
    extrinsic_index: int | None = None
    failure: str | None = None
    source: str = "creditcoin"
    created_at: datetime = Field(default_factory=utcnow)
    confirmed_at: datetime | None = None


class CreditDecision(BaseModel):
    """Final credit recommendation (spec §27)."""

    decision_id: str
    borrower_id: str
    requested_amount: float = Field(ge=0.0)
    recommended_amount: float = Field(ge=0.0)
    collateral_value: float = Field(ge=0.0)
    required_collateral_ratio: float = Field(ge=0.0)
    credit_score: float = Field(ge=0.0, le=100.0)
    probability_of_default: float = Field(ge=0.0, le=1.0)
    expected_loss: float = Field(ge=0.0)
    risk_regime: RiskRegime
    stress_result: float = Field(ge=0.0)
    principal_risk_factors: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    attestation_references: list[str] = Field(default_factory=list)
    model_versions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None
    decision_status: DecisionStatus = DecisionStatus.RECOMMENDED
    approval_status: str = "pending"
    execution_transaction: str | None = None


class ExecuteCreditRequest(BaseModel):
    """Client request to execute an approved CreditDecision on Creditcoin (E10).

    Refuses execution unless the referenced decision has been human-approved
    (approval_status == "approved"). The amount defaults to the decision's
    recommended_amount; safe for the lender to override.
    """

    decision_id: str = Field(..., description="Approved CreditDecision to execute")
    to: str = Field(..., description="Recipient Substrate SS58 or EVM 0x address")
    amount: float | None = Field(None, gt=0.0, description="Optional amount override (CTC)")
    amount_planck: str | None = Field(None, description="Exact planck amount (overrides amount)")


class AssessmentRequest(BaseModel):
    """Client request to run a credit assessment / decision for a borrower."""

    requested_amount: float = Field(..., gt=0, description="Requested loan in CTC")
    regime: RiskRegime = RiskRegime.HIGH_VOLATILITY

    # Allowed override weights (optional; defaults applied when omitted)
    risk_free_rate: float = Field(0.02, ge=0.0, le=0.20)
    confidence: float = Field(0.95, gt=0.0, lt=1.0)