"""
Schema validation utilities for GraphAlpha data contracts.
Loads JSON Schema documents and exposes validate_signal / validate_order helpers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from common.versioning import MAX_SUPPORTED_SCHEMA_VERSION, validate_schema_version

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

_SIGNAL_SCHEMA: dict | None = None
_ORDER_SCHEMA: dict | None = None


def _load_schema(name: str) -> dict:
    path = SCHEMAS_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_signal_schema() -> dict:
    global _SIGNAL_SCHEMA
    if _SIGNAL_SCHEMA is None:
        _SIGNAL_SCHEMA = _load_schema("signal_schema_v1.json")
    return _SIGNAL_SCHEMA


def get_order_schema() -> dict:
    global _ORDER_SCHEMA
    if _ORDER_SCHEMA is None:
        _ORDER_SCHEMA = _load_schema("approved_order_schema_v1.json")
    return _ORDER_SCHEMA


def _get_fusion_threshold() -> float:
    return float(os.getenv("FUSION_THRESHOLD", os.getenv("SELL_THRESHOLD", "0.2")))


def validate_signal(data: dict[str, Any]) -> None:
    validate_schema_version(data.get("schema_version"))
    schema = get_signal_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        msgs = "; ".join(
            f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in errors
        )
        raise ValidationError(f"Signal validation failed: {msgs}")

    direction = data.get("direction")
    score = data.get("score")
    if direction == "hold" and score is not None:
        threshold = _get_fusion_threshold()
        if abs(float(score)) >= threshold:
            raise ValidationError(
                f"Signal direction='hold' requires |score| < {threshold}, got {score}"
            )


def validate_order(data: dict[str, Any]) -> None:
    validate_schema_version(data.get("schema_version"))
    schema = get_order_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        msgs = "; ".join(
            f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in errors
        )
        raise ValidationError(f"ApprovedOrder validation failed: {msgs}")

    risk_checks = data.get("risk_checks", {})
    if not all(risk_checks.get(k) is True for k in ("position_pct_ok", "sector_pct_ok", "var_ok")):
        raise ValidationError(
            "ApprovedOrder invalid: all risk_checks must be true. "
            f"Got: {risk_checks}"
        )
