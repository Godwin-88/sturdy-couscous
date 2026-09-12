"""Hermetic tests for the /fund/* read-only endpoints (RWA H1–3).

Mirrors the /defi route-test pattern: FastAPI TestClient with the router's Redis
access monkeypatched to an in-memory fake. No network, no live Redis.
"""
import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routes.fund as fund_routes


class FakeCache:
    def __init__(self, data: dict | None = None):
        self.data = data or {}

    def get(self, key: str):
        return self.data.get(key)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(fund_routes, "_r", lambda: FakeCache())
    app = FastAPI()
    app.include_router(fund_routes.router)
    return TestClient(app)


def test_report_empty(client):
    r = client.get("/fund/attestation-report")
    assert r.status_code == 200
    assert r.json()["report"] is None
    assert r.json()["cached"] is False


def test_report_cached(client, monkeypatch):
    report = {"cycle_id": "cycle_x", "digest": "sha256:abc",
              "chain": {"root": "sha256:r", "verify_ok": True}}
    monkeypatch.setattr(fund_routes, "_r", lambda: FakeCache(
        {"fund:attestation_report": json.dumps(report)}))
    r = client.get("/fund/attestation-report")
    body = r.json()
    assert body["cached"] is True
    assert body["report"]["cycle_id"] == "cycle_x"
    assert body["report"]["chain"]["verify_ok"] is True


def test_status_shape(client, monkeypatch):
    monkeypatch.setenv("FUND_BORROWER_ID", "fund_alice")
    r = client.get("/fund/status")
    body = r.json()
    assert body["borrower_id"] == "fund_alice"
    assert body["offline_ok"] is True
    assert "nav_anchor_contract" in body