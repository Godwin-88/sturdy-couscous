"""
evidence_chain.py
──────────────────
Cryptographic assurance layer for GraphAlpha P11 (docs/p11_web3_defi_expansion.md §4).

Applies the tenets of *Cryptographic Primitives in Blockchain Technology*:

  U25  digital signatures — every decision root is signed; tampering inverts
       the signature (Ch. 3.3.2.4: authentication + integrity + non-repudiation).
  U26  Merkle trees — period roots are batched into a Merkle root that can be
       anchored on-chain; membership proofs are O(log n) (Ch. 3.5).
  C7/C8+C9  hash security (256-bit) + Byzantine "quorum with authentication".

Pure-Python and deterministic: hashlib only for the chain; the optional
eth_account ECDSA signing degrades gracefully to HMAC when the dependency is
absent (paper/lab mode). No network, no Docker deps, no testnet key —
fully hermetic and stub-testable.

Design (identical to P9 U4/U15 but chain-agnostic):
  append(cycle_id, regime, decisions)
    -> hashes each decision (sha256 of canonical JSON)
    -> links them under a hash of (prev_root, cycle_id, regime, hashes)
  .root()       current chain root (sha256 hexdigest, "sha256:" prefix)
  .verify_chain()  walk every stored entry; True iff no discontinuity
  .merkle_root(entries) / .merkle_proof / .verify_merkle_proof
                 stable O(log n) batch root with directional L/R proofs
  .sign_root / .verify_root   ECDSA (eth_account) or HMAC fallback
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import time
import uuid
from typing import Any, Optional

try:
    from eth_account import Account  # type: ignore  (optional, paper mode)
except Exception:  # pragma: no cover
    Account = None  # type: ignore

_NAMESPACE = os.getenv("EVIDENCE_CHAIN_NAMESPACE", "evidence_chain")
_DIGEST = "sha256"


# ── Canonicalization (deterministic decision preimage) ──────────────────────

class _NormalizeNegativeZero:
    """json encoder hook: keep numbers, but force -0.0 → 0.0 deterministically."""
    def __init__(self, inner: Any):
        self.inner = inner

    def __float__(self) -> float:
        return 0.0 if self.inner == 0.0 else float(self.inner)


def _normalize(obj: Any) -> Any:
    """Recursively force -0.0 to 0.0 (Python emits -0.0; we want canonical 0.0)."""
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    if isinstance(obj, set):
        return [_normalize(v) for v in sorted(obj, key=repr)]
    if isinstance(obj, float):
        return float(_NormalizeNegativeZero(obj))
    return obj


def _stable_float(f: float) -> float:
    """Round floats to canonical bytes via normalization (keeps repr stable)."""
    return float(_NormalizeNegativeZero(f))


def canonicalize(obj: Any) -> str:
    """
    Recursively build a deterministic JSON string from arbitrary data:
    sorted keys, -0.0→0.0, sorted sets, isoformat datetimes, hex bytes.
    The output is the signature preimage (U25).

    Standard-library json is deliberately used for float encoding: Python's
    json emits the bare JSON tokens NaN / Infinity / -Infinity and repr for
    finite floats, all of which are deterministic across platforms for the
    same IEEE-754 value.
    """
    return json.dumps(
        _normalize(obj),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=True,
        default=lambda o: o.isoformat() if hasattr(o, "isoformat") else repr(o),
    )

# ── Hashing ──────────────────────────────────────────────────────────────────

def _sha256(b: bytes) -> str:
    return _DIGEST + ":" + hashlib.sha256(b).hexdigest()


def hash_canonical(s: str) -> str:
    return _sha256(s.encode("utf-8"))


def hash_decision(decision: dict) -> str:
    """Hash a single decision/event dict (U25 preimage -> leaf)."""
    return hash_canonical(canonicalize(decision))


def compute_cycle_id(
    prev_root: str,
    round_ts: float,
    regime: str,
    cycle_sec: int = 300,
) -> str:
    """
    Replay-protection nonce (Ch. 6.7 nonce semantics + U17):
    two cycles with the same (prev_root, round_bucket, regime) collide -> the
    bot dedupes instead of double-submitting. `round_bucket` quantizes time so
    retries within a cycle produce the SAME id (idempotency), the next cycle
    produces a DIFFERENT id.
    """
    bucket = int(round_ts) // max(1, int(cycle_sec))
    return hash_canonical(f"{prev_root}|{bucket}|{regime}")


# ── Merkle tree (U26) ───────────────────────────────────────────────────────

def _pair_hash(a: str, b: str) -> str:
    """Deterministic sister-node combine (Bolfing Ch. 3.5 Merkle combine)."""
    return _sha256(f"{a}|{b}".encode("utf-8"))


def merkle_root(leaves: list[str]) -> str:
    """
    Stable Merkle root for an ordered list of leaf hashes.
    Odd level: final node promoted unchanged (standard practice), so roots
    are deterministic regardless of chunk grouping.
    """
    if not leaves:
        return _sha256(b"")
    level = list(leaves)
    while len(level) > 1:
        nxt: list[str] = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(_pair_hash(level[i], level[i + 1]))
            else:
                nxt.append(level[i])
        level = nxt
    return level[0]


def merkle_proof(leaves: list[str], index: int) -> list[tuple[str, str]]:
    """
    Sibling path for membership of `index`, O(log n), as directional
    ("L"|"R", hash) pairs so a standalone verifier can fold left/right
    deterministically without the original list.
    """
    if not leaves or not (0 <= index < len(leaves)):
        raise ValueError("index out of range")
    level = list(leaves)
    proof: list[tuple[str, str]] = []
    idx = index
    while len(level) > 1:
        if idx % 2 == 0:
            if idx + 1 < len(level):
                proof.append(("R", level[idx + 1]))   # sibling to the RIGHT
        else:
            proof.append(("L", level[idx - 1]))       # sibling to the LEFT
        nxt: list[str] = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(_pair_hash(level[i], level[i + 1]))
            else:
                nxt.append(level[i])
        level = nxt
        idx //= 2
    return proof


def verify_merkle_proof(leaf: str, proof: list[tuple[str, str]], root: str) -> bool:
    """Fold leaf + L/R siblings, compare to root. O(log n), no original list."""
    cur = leaf
    for side, sib in proof:
        cur = _pair_hash(sib, cur) if side == "L" else _pair_hash(cur, sib)
    return cur == root
_HEX_CHARS = set("0123456789abcdefABCDEF")


def _is_evm_private_key(key: str) -> bool:
    """True if `key` is a 32-byte EVM private key (64 hex chars, optional 0x)."""
    k = key[2:] if key.startswith("0x") else key
    return len(k) == 64 and all(c in _HEX_CHARS for c in k)


def _is_evm_signature(sig: str) -> bool:
    """True if `sig` is an eth-account ECDSA signature (0x + 130 hex chars)."""
    return sig.startswith("0x") and len(sig) == 132 and all(
        c in _HEX_CHARS for c in sig[2:]
    )


class EvidenceChain:
    """
    Hash-chained decision ledger. Backed by any dict-like store (Redis, in-mem,
    or a testing fake). Entries:

        {
          ...
        }

    .verify_chain() walks from the head backward, recomputing each root and
    asserting the child's prev_root == parent's root — the tamper-evidence
    property (U25). Nothing here touches the network.
    """

    def __init__(self, store: Any, namespace: str = _NAMESPACE):
        self.store = store
        self.key_entries = f"{namespace}:entries"
        self.key_head = f"{namespace}:head"

    # ── store helpers (dict-like) ─────────────────────────────────────────
    def _get_entries(self) -> list[dict]:
        raw = self.store.get(self.key_entries, [])
        return list(raw) if isinstance(raw, list) else []

    def _put_entries(self, entries: list[dict]) -> None:
        self.store[self.key_entries] = entries

    # ── head ──────────────────────────────────────────────────────────────
    @property
    def head(self) -> Optional[dict]:
        entries = self._get_entries()
        return entries[-1] if entries else None

    def root(self) -> str:
        h = self.head
        return h["root"] if h else _sha256(b"genesis")

    # ── append a cycle ────────────────────────────────────────────────────
    def append(self, cycle_id: str, regime: str, decisions: list[dict]) -> dict:
        leaves = [hash_decision(d) for d in decisions]
        prev = self.root()
        payload = f"{prev}|{cycle_id}|{regime}|" + "|".join(leaves)
        entry = {
            "cycle_id": cycle_id,
            "regime": regime,
            "prev_root": prev,
            "root": _sha256(payload.encode("utf-8")),
            "decision_hashes": leaves,
            "ts": time.time(),
        }
        entries = self._get_entries() + [entry]
        self._put_entries(entries)
        return entry

    # ── tamper-evidence (U25) ─────────────────────────────────────────────
    def verify_chain(self) -> bool:
        entries = self._get_entries()
        if not entries:
            return True                       # empty chain trivially consistent
        if entries[0]["prev_root"] != _sha256(b"genesis"):
            return False
        for i, entry in enumerate(entries):
            if i == 0:
                continue
            if entry["prev_root"] != entries[i - 1]["root"]:
                return False
            leaves = entry["decision_hashes"]
            payload = (
                f"{entry['prev_root']}|{entry['cycle_id']}|{entry['regime']}|"
                + "|".join(leaves)
            )
            if entry["root"] != _sha256(payload.encode("utf-8")):
                return False
        # head integrity: recompute from its stored fields
        head = entries[-1]
        leaves = head["decision_hashes"]
        payload = (
            f"{head['prev_root']}|{head['cycle_id']}|{head['regime']}|"
            + "|".join(leaves)
        )
        return head["root"] == _sha256(payload.encode("utf-8"))

    # ── batch attestation root over all stored entries (U26) ──────────────
    def merkle_root(self) -> str:
        return merkle_root([e["root"] for e in self._get_entries()])

    # ── signing (U25): ECDSA when eth_account is present AND the key is a
    #    valid 32-byte EVM private key; HMAC otherwise (paper/lab — the
    #    documented graceful-degradation contract).
    @staticmethod
    def sign_root(root: str, private_key: str) -> str:
        if Account is not None and _is_evm_private_key(private_key):
            from eth_account.messages import encode_defunct  # type: ignore
            msg = encode_defunct(text=root)
            sig = Account.sign_message(msg, private_key=private_key)  # type: ignore
            return sig.signature.hex()
        return hmac.new(
            private_key.encode(), root.encode(), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def verify_root(public_key: str, root: str, signature: str) -> bool:
        if Account is not None and _is_evm_signature(signature):
            from eth_account.messages import encode_defunct  # type: ignore
            from eth_utils import to_checksum_address  # type: ignore
            msg = encode_defunct(text=root)
            recovered = Account.recover_message(msg, signature=signature)  # type: ignore
            return to_checksum_address(recovered) == to_checksum_address(public_key)
        expected = hmac.new(
            public_key.encode(), root.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


def verify_candidate(decision: dict, recompute_fn: Callable[[dict], Any]) -> bool:
    """
    Recompute-verify a stored decision (the "PoW cheap-to-verify" analog,
    Ch. 6.7): strategy modules ship a deterministic recompute path; this
    confirms the recorded decision is reproducible from the same inputs.
    """
    try:
        return bool(recompute_fn(decision))  # type: ignore
    except Exception:
        return False


def make_cycle_id(regime: str, now: Optional[float] = None) -> str:
    """Convenience: fresh random cycle id for a live orchestrator run."""
    return str(uuid.uuid4()) + "::" + regime


__all__ = [
    "canonicalize",
    "hash_canonical",
    "hash_decision",
    "compute_cycle_id",
    "merkle_root",
    "merkle_proof",
    "verify_merkle_proof",
    "EvidenceChain",
    "verify_candidate",
    "make_cycle_id",
]