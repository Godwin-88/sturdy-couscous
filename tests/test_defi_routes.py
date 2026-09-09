"""Hermetic tests for the /defi/* read-only endpoints (P11 Stage-5).

Runs in the api container (cwd=/app). Uses a FastAPI TestClient with the
router's Redis access monkeypatched to an in-memory fake — no network, no
live Redis needed. The /defi/positions relay call and /defi/status relay
probe are stubbed likewise for determinism.
"""
import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routes.defi as defi_routes
import agent.dreamdex_adapter as dreamdex_adapter  # noqa: E402


class FakeCache:
    """Minimal stand-in for redis.Redis.get (decode_responses=True)."""

    def __init__(self, data: dict | None = None):
        self.data = data or {}

    def get(self, key: str):
        return self.data.get(key)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(defi_routes, "_r", lambda: FakeCache())
    # Stub outbound relay/probe calls so tests stay hermetic.
    monkeypatch.setattr(dreamdex_adapter, "get_positions", lambda: ([], []))
    monkeypatch.setattr(dreamdex_adapter, "relay_status", lambda: {"reachable": False, "dry_run": True})
    app = FastAPI()
    app.include_router(defi_routes.router)
    return TestClient(app)


def test_candidates_empty(client):
    r = client.get("/defi/candidates")
    assert r.status_code == 200
    assert r.json()["candidates"] == []
    assert r.json()["cached"] is False


def test_candidates_cached(client, monkeypatch):
    cands = [{"market_id": "m1", "sector": "D1", "venue": "sepolia-evm",
              "size_usd": 120.5, "net_edge_pct": 0.04}]
    monkeypatch.setattr(defi_routes, "_r", lambda: FakeCache(
        {"defi:candidates": json.dumps(cands)}))
    r = client.get("/defi/candidates")
    assert r.status_code == 200
    assert r.json()["cached"] is True
    assert r.json()["candidates"] == cands


def test_governor(client, monkeypatch):
    gov = {"paused_evm": True, "paused_ec": False,
           "feeds": [{"feed_id": "evm-price-sepolia", "venue": "sepolia", "status": "ok"}]}
    monkeypatch.setattr(defi_routes, "_r", lambda: FakeCache(
        {"defi:governor": json.dumps(gov)}))
    r = client.get("/defi/governor")
    assert r.status_code == 200
    assert r.json()["governor"]["paused_evm"] is True


def test_sectors_groups_by_sector(client, monkeypatch):
    cands = [
        {"market_id": "a", "sector": "D1", "venue": "sepolia-evm", "size_usd": 50.0},
        {"market_id": "b", "sector": "D1", "venue": "sepolia-evm", "size_usd": 30.0},
        {"market_id": "c", "sector": "D5", "venue": "somnia-relay", "size_usd": 20.0},
    ]
    monkeypatch.setattr(defi_routes, "_r", lambda: FakeCache(
        {"defi:candidates": json.dumps(cands)}))
    r = client.get("/defi/sectors")
    body = r.json()
    assert r.status_code == 200
    assert body["sectors"]["D1"]["count"] == 2
    assert body["sectors"]["D1"]["size_usd"] == pytest.approx(80.0)
    assert body["sectors"]["D5"]["venue"] == "somnia-relay"
    assert body["total_size_usd"] == pytest.approx(100.0)


def test_status_shape(client):
    r = client.get("/defi/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["venue"] == "sepolia-evm + somnia-relay"
    assert "min_lp_edge_pct" in body["gates"]
    assert "freeze" in body["gates"]


def test_status_enabled_true(client, monkeypatch):
    monkeypatch.setenv("DEFI_ENABLED", "1")
    r = client.get("/defi/status")
    assert r.status_code == 200
    assert r.json()["enabled"] is True


def test_evidence_returns_readonly_shape(client):
    r = client.get("/defi/evidence")
    assert r.status_code == 200
    body = r.json()
    for key in ("head", "root", "merkle_root", "verify_ok", "cached"):
        assert key in body


def test_positions_with_stub(client):
    r = client.get("/defi/positions")
    assert r.status_code == 200
    body = r.json()
    assert body["positions"] == []
    assert body["evm_positions"] == []


def test_health(client):
    r = client.get("/defi/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"