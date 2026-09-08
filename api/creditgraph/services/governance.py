"""Governance service (E11).

Provides in-memory model registry, policy audit trail and entity audit log.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


_MODELS: dict[str, dict[str, Any]] = {}
_POLICIES: dict[str, dict[str, Any]] = {}
_AUDIT_LOG: list[dict[str, Any]] = []


def _append_audit(entity_type: str, entity_id: str, action: str, actor: str, details: dict[str, Any]) -> None:
    _AUDIT_LOG.append({
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "actor": actor,
        "timestamp": utcnow().isoformat(),
        "details": details,
    })


def register_model(
    model_id: str,
    name: str,
    version: str,
    owner: str,
    description: str | None,
    parameters: dict[str, Any],
    effective_date: datetime | None,
    status: str,
) -> dict[str, Any]:
    effective = effective_date or utcnow()
    record = {
        "model_id": model_id,
        "name": name,
        "version": version,
        "owner": owner,
        "description": description,
        "parameters": parameters,
        "effective_date": effective.isoformat(),
        "status": status,
        "registered_at": utcnow().isoformat(),
    }
    _MODELS[model_id] = record
    _append_audit("model", model_id, "register", owner, {"version": version, "status": status})
    return record


def update_policy(
    policy_id: str,
    previous_value: Any,
    new_value: Any,
    user: str,
    reason: str,
    effective_date: datetime | None,
) -> dict[str, Any]:
    effective = effective_date or utcnow()
    record = {
        "policy_id": policy_id,
        "previous_value": previous_value,
        "new_value": new_value,
        "user": user,
        "reason": reason,
        "effective_date": effective.isoformat(),
        "updated_at": utcnow().isoformat(),
    }
    _POLICIES[policy_id] = record
    _append_audit("policy", policy_id, "update", user, {
        "previous_value": previous_value,
        "new_value": new_value,
    })
    return record


def get_model_governance(model_id: str) -> dict[str, Any]:
    model = _MODELS.get(model_id)
    if model is None:
        return {}
    return model


def list_models() -> list[dict[str, Any]]:
    return list(_MODELS.values())


def get_audit_log(entity_type: str, entity_id: str) -> list[dict[str, Any]]:
    entries = [
        entry for entry in _AUDIT_LOG
        if entry["entity_type"] == entity_type and entry["entity_id"] == entity_id
    ]
    entries.sort(key=lambda x: x["timestamp"])
    return entries
