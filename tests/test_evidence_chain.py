"""EvidenceChain unit tests — P11 §4 cryptographic assurance layer (U25/U26).

Hermetic: pure-Python stdlib (hashlib/hmac/uuid); in-memory dict store; no
network, no Docker deps, no testnet key.

Covers, per *Cryptographic Primitives in Blockchain Technology*:
  U25  digital-signature semantics — signatures bind the root; tampering
       with a stored decision inverts chain verification.
  U26  Merkle-tree batch attestation — stable roots, O(log n) L/R proof
       verification, deterministic regardless of chunk grouping.
  C7   canonical preimages are deterministic (sorted keys, stable floats).
  C8/C9  hash chaining + nonce idempotency via compute_cycle_id.
"""
import pytest

import agent.evidence_chain as ec
from agent.evidence_chain import EvidenceChain
from agent.evidence_chain import (
    canonicalize,
    compute_cycle_id,
    hash_decision,
    merkle_proof,
    merkle_root,
    verify_merkle_proof,
)


def _mk_store() -> dict:
    return {}


# ── canonicalization / hashing (C7) ────────────────────────────────────────

def test_canonicalize_sorted_and_stable():
    a = canonicalize({"b": 2, "a": [1, 2.0, {"z": 3, "y": 1}], "flag": True})
    b = canonicalize({"a": [1, 2.0, {"y": 1, "z": 3}], "flag": True, "b": 2})
    assert a == b
    assert "2.0" in a            # stable float rendering (bare token)
    assert "true" in a


def test_canonicalize_float_edge_cases():
    assert canonicalize({"x": -0.0}) == canonicalize({"x": 0.0})
    assert "NaN" in canonicalize({"x": float("nan")})
    assert "Infinity" in canonicalize({"x": float("inf")})
    assert "-Infinity" in canonicalize({"x": float("-inf")})


def test_hash_decision_deterministic():
    d1 = {"market": "BTC-1HR", "side": "buy", "score": 0.62}
    d2 = {"score": 0.6200, "side": "buy", "market": "BTC-1HR"}
    assert hash_decision(d1) == hash_decision(d2)
    assert hash_decision(d1).startswith("sha256:")


# ── Merkle tree (U26) ──────────────────────────────────────────────────────

def _leaves(k=5):
    return [hash_decision({"i": i, "v": float(i)}) for i in range(k)]


def test_merkle_root_deterministic_and_odd():
    assert merkle_root(_leaves(4)) == merkle_root(_leaves(4))
    assert merkle_root(_leaves(5)) == merkle_root(_leaves(5))  # odd promoted


def test_merkle_proof_verifies_every_index():
    for n in (1, 2, 3, 4, 5, 8, 32):
        leaves = _leaves(n)
        root = merkle_root(leaves)
        for i in range(n):
            proof = merkle_proof(leaves, i)
            assert verify_merkle_proof(leaves[i], proof, root)
        imposter = hash_decision({"i": 999, "v": 999.0})
        assert not verify_merkle_proof(imposter, merkle_proof(leaves, 0), root)


def test_merkle_proof_length_is_log():
    leaves = _leaves(32)
    assert len(merkle_proof(leaves, 0)) == 5   # ceil(log2(32))


def test_merkle_proof_out_of_range_raises():
    with pytest.raises(ValueError):
        merkle_proof(_leaves(4), 99)


# ── cycle_id nonce (C9/C8) ─────────────────────────────────────────────────

def test_cycle_id_idempotent_within_bucket_different_across():
    a1 = compute_cycle_id("root0", 1000, "Bull Trend", 300)
    a2 = compute_cycle_id("root0", 1199, "Bull Trend", 300)   # same bucket
    b  = compute_cycle_id("root0", 1300, "Bull Trend", 300)   # next bucket
    c  = compute_cycle_id("root1", 1000, "Bull Trend", 300)   # different prev
    assert a1 == a2
    assert a1 != b
    assert a1 != c


def test_cycle_id_deterministic():
    assert compute_cycle_id("r", 5, "X", 1) == compute_cycle_id("r", 5, "X", 1)


# ── EvidenceChain (U25 tamper-evidence) ────────────────────────────────────

def _chain() -> EvidenceChain:
    return EvidenceChain(_mk_store(), "test:e")


def test_empty_chain_verifies_and_root_is_genesis():
    chain = _chain()
    assert chain.verify_chain() is True
    assert chain.root() == ec._sha256(b"genesis")


def test_append_links_and_root_changes():
    chain = _chain()
    e1 = chain.append("c1", "Bear Trend", [{"a": 1}])
    e2 = chain.append("c2", "Bear Trend", [{"a": 2}])
    assert e2["prev_root"] == e1["root"]
    assert chain.verify_chain() is True
    assert len(chain._get_entries()) == 2


def test_tamper_with_decision_inverts_chain():
    chain = _chain()
    chain.append("c1", "Regime", [{"market": "M", "action": "hold"}])
    entries = chain._get_entries()
    entries[-1]["decision_hashes"] = [hash_decision({"market": "M", "action": "buy"})]
    chain._put_entries(entries)
    assert chain.verify_chain() is False


def test_tamper_with_prev_link_inverts_chain():
    chain = _chain()
    chain.append("c1", "R", [{"x": 1}])
    chain.append("c2", "R", [{"x": 2}])
    entries = chain._get_entries()
    entries[1]["prev_root"] = "sha256:deadbeef"
    chain._put_entries(entries)
    assert chain.verify_chain() is False


def test_merkle_of_entries_stable():
    chain = _chain()
    chain.append("c1", "R", [{"x": 1}])
    chain.append("c2", "R", [{"x": 2}])
    assert chain.merkle_root() == chain.merkle_root()


# ── signing (U25) — HMAC fallback path (eth_account optional) ──────────────

def test_sign_verify_hmac_roundtrip():
    key = "test-secret-key"
    root = _chain().append("c1", "R", [{"x": 1}])["root"]
    sig = EvidenceChain.sign_root(root, key)
    assert EvidenceChain.verify_root(key, root, sig) is True
    assert EvidenceChain.verify_root(key, root + "x", sig) is False


# ── verify_candidate (PoW-style recompute) ─────────────────────────────────

def test_verify_candidate_recompute():
    def recompute(d):
        return d.get("a") == 1 and d.get("b") == 2
    assert ec.verify_candidate({"a": 1, "b": 2}, recompute) is True
    assert ec.verify_candidate({"a": 1, "b": 3}, recompute) is False
    assert ec.verify_candidate({"bad": True}, lambda d: 1 / 0) is False
    assert compute_cycle_id("r", 5, "X", 1) == compute_cycle_id("r", 5, "X", 1)