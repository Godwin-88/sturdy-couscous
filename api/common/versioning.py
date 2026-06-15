"""
Schema versioning policy enforcement.
Both engines declare a maximum supported version and reject anything higher.
"""
from __future__ import annotations

MAX_SUPPORTED_SCHEMA_VERSION = 1


def validate_schema_version(version: int | None) -> None:
    if version is None:
        raise ValueError("schema_version is required and must be an integer.")
    if not isinstance(version, int):
        raise ValueError(f"schema_version must be an integer, got {type(version).__name__}.")
    if version > MAX_SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported schema_version {version}. "
            f"Max supported is {MAX_SUPPORTED_SCHEMA_VERSION}. "
            "Reject the message rather than guessing field defaults."
        )
