"""
fund_attestation.py — H1–3 NAV-attestation loop (BUIDL CTC / RWA track).

Each cycle:
  1. snapshot()          read the Alpaca portfolio (NAV/equity, cash, buying power,
                         positions, unrealized PnL)
  2. canonical_digest()  canonical JSON -> sha256 digest (reuses evidence_chain's
                         deterministic canonicalization — stable floats, sorted keys)
  3. anchor()            best-effort ON-CHAIN anchor (Sepolia / chainKey 1):
                           LIVE   -> NAVAnchor.setNAV(nav_usd, digest, block_ref)
                                    via web3.py (CE-I: build -> sign -> send -> wait)
                           RELAY  -> POST {WEB3_RELAY_URL}/anchor {root, cycleId}
                           OFFLINE-> skipped, status="offline"
  4. attest()            if a source-chain tx_hash exists -> POST the API gateway's
                         /api/v1/risk/evidence/verify (which calls the attestation
                         service and persists the Evidence/Attestation lineage) —
                         works from any container, no heavy imports needed
  5. ledger()            EvidenceChain.append + persisted Redis status report

Hermetic by design: every network producer is injectable or env-gated; the module
self-disables to "/offline" without keys, and NEVER raises on a failed anchor/attest
(a Financial-Engineer tenet: a paper book must not go dark because Sepolia hiccupped).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from agent.evidence_chain import EvidenceChain, canonicalize  # cwd = /app (api)
except ImportError:  # cwd = agent/ (agent-worker)
    from evidence_chain import EvidenceChain, canonicalize  # type: ignore

logger = logging.getLogger(__name__)

FUND_BORROWER_ID = os.getenv("FUND_BORROWER_ID", "fund_graphalpha")


# ── Redis-backed dict-like store for EvidenceChain ─────────────────────────────
class RedisChainStore:
    """Presents the dict-like interface EvidenceChain expects, backed by Redis.

    evidence_chain uses store.get(key, default) and item assignment. Redis needs
    JSON encoding/decoding — this wrapper keeps the chain persistent across cycles.
    """

    def __init__(self, client: Any, prefix: str = "fund_chain"):
        self._r = client
        self._p = prefix

    def _k(self, key: str) -> str:
        # key already contains the prefix namespace (e.g. "fund_chain:entries")
        return key if key.startswith(self._p) else f"{self._p}:{key}"

    def get(self, key: str, default: Any = None) -> Any:
        raw = self._r.get(self._k(key))
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    def __setitem__(self, key: str, value: Any) -> None:
        self._r.set(self._k(key), json.dumps(value))


# ── Redis urls / gates ─────────────────────────────────────────────────────────
def _redis() -> Any:
    import redis

    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


def fund_chain(store: Any = None) -> EvidenceChain:
    """Return the fund EvidenceChain (namespace fund_chain)."""
    return EvidenceChain(store=store if store is not None else RedisChainStore(_redis()))


# ── Step 1: portfolio snapshot ─────────────────────────────────────────────────
async def snapshot(alpaca: Any = None) -> dict:
    """Read the Alpaca paper portfolio into a canonical snapshot dict."""
    if alpaca is None:
        try:
            from agent.alpaca_client import AlpacaClient  # cwd = /app (api)
        except ImportError:
            from alpaca_client import AlpacaClient  # type: ignore  (cwd = agent/)

        alpaca = AlpacaClient()

    account = await alpaca.get_account() if hasattr(alpaca, "get_account") else {}
    positions = await alpaca.get_positions() if hasattr(alpaca, "get_positions") else []

    equity = float(account.get("equity") or 0.0)
    cash = float(account.get("cash") or 0.0)
    bp = float(account.get("buying_power") or 0.0)

    long_mv = 0.0
    short_mv = 0.0
    pos_rows = []
    for p in positions or []:
        mv = float(p.get("market_value") or p.get("current_price") or 0.0)
        upl = float(p.get("unrealized_pl") or 0.0)
        qty = float(p.get("qty") or p.get("quantity") or 0.0)
        if qty == 0.0:
            continue  # closed/dust rows never enter the attested NAV digest
        if qty > 0:
            long_mv += mv
        else:
            short_mv += abs(mv)
        pos_rows.append({
            "symbol": p.get("symbol", "?"),
            "qty": qty,
            "market_value": round(mv, 4),
            "unrealized_pl": round(upl, 4),
        })

    return {
        "venue": "alpaca",
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "equity": round(equity, 4),
        "cash": round(cash, 4),
        "buying_power": round(bp, 4),
        "long_market_value": round(long_mv, 4),
        "short_market_value": round(short_mv, 4),
        "positions": pos_rows,
    }


# ── Step 2: canonical digest ───────────────────────────────────────────────────
def canonical_digest(snap: dict) -> str:
    """Deterministic sha256 digest of the snapshot (stable across float repr)."""
    try:
        from agent.evidence_chain import hash_canonical
    except ImportError:
        from evidence_chain import hash_canonical  # type: ignore

    return hash_canonical(canonicalize(snap))
# ── Step 3: best-effort on-chain anchor ────────────────────────────────────────
NAV_ANCHOR_ABI = [
    {
        "type": "function",
        "name": "setNAV",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "navUsd", "type": "uint256"},
            {"name": "navHash", "type": "bytes32"},
            {"name": "blockRef", "type": "uint64"},
        ],
        "outputs": [],
    },
]


async def anchor_nav(
    web3_client: Any,
    account: Any,
    nav_anchor_address: str,
    nav_usd: float,
    digest: str,
    block_ref: int = 0,
    decimals: int = 6,
    gas_limit: int = 300_000,
    confirmations: int = 1,
) -> str:
    """Send NAVAnchor.setNAV(navUsd, digest, blockRef) on chain.

    CE-I discipline (U2/U31): build -> sign -> broadcast -> wait for receipt,
    asserting status==1 before returning the tx hash. Raises only on a hard
    revert or unrecoverable broadcast error (caller wraps in run()).
    """
    from web3 import Web3  # lazy import — not needed unless anchoring

    if not nav_anchor_address:
        raise ValueError("nav_anchor_address is empty — cannot anchor")

    nav_scaled = int(round(nav_usd * (10 ** decimals)))
    hex_digest = digest[len("sha256:"):]
    as_bytes32 = Web3.to_bytes(hexstr=hex_digest)[:32]

    contract = web3_client.eth.contract(
        address=Web3.to_checksum_address(nav_anchor_address), abi=NAV_ANCHOR_ABI
    )
    nonce = web3_client.eth.get_transaction_count(account.address)

    tx = contract.functions.setNAV(nav_scaled, as_bytes32, block_ref).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": gas_limit,
        "gasPrice": web3_client.eth.gas_price,
    })
    signed = web3_client.eth.account.sign_transaction(tx, private_key=account.key)
    tx_hash = web3_client.eth.send_raw_transaction(signed.rawTransaction)
    receipt = web3_client.eth.wait_for_transaction_receipt(
        tx_hash, timeout=120, poll_latency=2
    )
    if not receipt or receipt.get("status") != 1:
        raise RuntimeError(f"NAVAnchor.setNAV reverted: {getattr(tx_hash, 'hex', lambda: '?')()}")
    for _ in range(max(0, confirmations - 1)):
        time.sleep(1)
    return tx_hash.hex()


async def anchor_via_relay(digest: str, cycle_id: str, relay_url: str) -> dict:
    """Fallback anchor: publish the digest as the evidence-chain root via web3-relay."""
    import httpx

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{relay_url.rstrip('/')}/anchor",
            json={"root": digest, "cycleId": cycle_id},
        )
        resp.raise_for_status()
        return resp.json()


# ── Step 4: attest on the gateway (verify + persist lineage) ───────────────────
async def attest(
    gateway_url: str, tx_hash: str, chain_key: int = 1,
    borrower_id: str = FUND_BORROWER_ID,
) -> dict:
    """POST the gateway's evidence-verify endpoint (verifies via Attestcoin + persists)."""
    import httpx

    url = f"{gateway_url.rstrip('/')}/api/v1/risk/evidence/verify"
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(url, json={
                "tx_hash": tx_hash,
                "chain_key": chain_key,
                "borrower_id": borrower_id,
            })
        except httpx.HTTPError as exc:
            return {"status": "error", "reason": f"httpx: {exc}"}
        if resp.status_code < 500:
            try:
                return resp.json()
            except Exception:
                return {"status": "ok", "raw": resp.text}
        return {"status": "http_error", "reason": f"http_{resp.status_code}"}


# ── Step 4b: mark the fund-as-borrower collateral to market (H3 RWA loop) ─────
async def mark_fund_borrower_to_market(
    gateway_url: str,
    nav_usd: float,
    digest: str,
    borrower_id: str = FUND_BORROWER_ID,
) -> dict:
    """POST the latest NAV into the Borrower node's collateral (additive, gated).

    Gates: the caller must set FUND_MARK_TO_MARKET=1 AND the creditgraph gateway
    must be reachable. Never raises — this is a KG convenience, not the anchor.
    """
    import httpx

    url = f"{gateway_url.rstrip('/')}/api/v1/risk/borrowers/fund/mark-to-market"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json={
                "nav_usd": round(float(nav_usd), 4),
                "digest": digest,
                "borrower_id": borrower_id,
            })
        if resp.status_code < 500:
            try:
                return resp.json()
            except Exception:
                return {"status": "ok", "raw": resp.text}
        return {"status": "http_error", "reason": f"http_{resp.status_code}"}
    except httpx.HTTPError as exc:
        return {"status": "error", "reason": f"httpx: {exc}"}


# ── Step 5: ledger + report ────────────────────────────────────────────────────
def publish_report(r: Any, report: dict) -> None:
    key = "fund:attestation_report"
    try:
        r.set(key, json.dumps(report))
        r.expire(key, 12 * 3600)
    except Exception as e:
        logger.warning(f"[FundAttestation] publish_report failed: {e}")
async def run_fund_attestation(
    cycle_id: str | None = None,
    regime: str = "?",
    alpaca: Any = None,
    store: Any = None,
    web3_factory: Any = None,
    gateway_url: str | None = None,
) -> dict:
    """Run one full cycle of the NAV-attestation loop (H1–3). Never raises."""
    report: dict = {"status": "ok", "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    cycle_id = cycle_id or f"cycle_{uuid.uuid4().hex[:12]}"
    report["cycle_id"] = cycle_id

    # 1) snapshot
    try:
        snap = await snapshot(alpaca)
    except Exception as e:
        snap = {"error": str(e)}
        report["status"] = "snapshot_error"
    report["snapshot"] = snap

    # 2) digest
    digest = canonical_digest(snap)
    report["digest"] = digest

    # 3) anchor
    nav_anchor = os.getenv("NAV_ANCHOR_CONTRACT", "").strip()
    key = os.getenv("CLAIM_TOKEN_PRIVATE_KEY", "") or os.getenv("WEB3_ORACLE_AUTHORITY_PRIVATE_KEY", "")
    relay_url = os.getenv("WEB3_RELAY_URL", "").strip()
    tx_hash: str | None = None

    try:
        if nav_anchor and key and web3_factory is not None:
            w3 = web3_factory()
            account = w3.eth.account.from_key(key)
            tx_hash = await anchor_nav(
                w3, account, nav_anchor,
                float(snap.get("equity") or 0.0), digest,
            )
            report["anchor"] = {"mode": "contract", "tx_hash": tx_hash}
            logger.info(f"[FundAttestation] NAV anchored on-chain: {tx_hash}")
        elif relay_url and (key or os.getenv("DRY_RUN", "1") == "0"):
            res = await anchor_via_relay(digest, cycle_id, relay_url)
            tx_hash = str(res.get("txHash") or "")
            report["anchor"] = {"mode": "relay", "tx_hash": tx_hash or None}
        else:
            report["anchor"] = {"mode": "offline",
                                "reason": "NAV_ANCHOR_CONTRACT+private key or WEB3_RELAY_URL not set"}
    except Exception as e:
        report["anchor"] = {"mode": "error", "reason": str(e)}
        logger.warning(f"[FundAttestation] anchor failed (non-fatal): {e}")

    # 4) attest (only when we have a real source-chain tx)
    if tx_hash and not tx_hash.startswith("stub_"):
        try:
            gw = gateway_url or os.getenv("GATEWAY_URL", "http://localhost:8000")
            result = await attest(gw, tx_hash)
            report["attestation"] = result
        except Exception as e:
            report["attestation"] = {"status": "error", "reason": str(e)}
    else:
        report["attestation"] = {"status": "skipped", "reason": "no source-chain tx"}

    # 4b) mark the fund-as-borrower collateral to market (gated: FUND_MARK_TO_MARKET=1)
    if os.getenv("FUND_MARK_TO_MARKET", "0").strip() == "1" and float(snap.get("equity") or 0.0) > 0:
        try:
            gw = gateway_url or os.getenv("GATEWAY_URL", "http://localhost:8000")
            report["mark_to_market"] = await mark_fund_borrower_to_market(
                gw, float(snap["equity"]), digest,
            )
        except Exception as e:
            report["mark_to_market"] = {"status": "error", "reason": str(e)}
            logger.warning(f"[FundAttestation] mark-to-market failed (non-fatal): {e}")
    else:
        report["mark_to_market"] = {"status": "skipped",
                                    "reason": "FUND_MARK_TO_MARKET != 1 or equity <= 0"}

    # 5) ledger — persist into the fund EvidenceChain (tamper-evident trail)
    try:
        chain = fund_chain(store=store)
        entry = chain.append(cycle_id, regime, [{
            "nav": round(float(snap.get("equity") or 0.0), 4),
            "digest": digest,
            "anchor": report.get("anchor", {}),
            "attestation": report.get("attestation", {}),
        }])
        report["chain"] = {"root": entry["root"], "prev_root": entry["prev_root"],
                           "verify_ok": chain.verify_chain()}
    except Exception as e:
        report["chain"] = {"error": str(e)}
        logger.warning(f"[FundAttestation] chain append failed: {e}")

    return report


async def main() -> None:
    # Auto-build a live web3 factory from env so a production run anchors on-chain
    # when SEPOLIA_RPC_URL + a private key are present (additive; absent -> offline).
    def _web3_factory():
        from web3 import Web3
        from web3.providers.rpc import HTTPProvider
        rpc = os.getenv("SEPOLIA_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com").strip()
        return Web3(HTTPProvider(rpc))

    use_live = bool(
        os.getenv("NAV_ANCHOR_CONTRACT", "").strip()
        and (os.getenv("CLAIM_TOKEN_PRIVATE_KEY", "").strip()
             or os.getenv("WEB3_ORACLE_AUTHORITY_PRIVATE_KEY", "").strip())
    )
    report = await run_fund_attestation(
        regime=os.getenv("CURRENT_REGIME", "?"),
        web3_factory=_web3_factory if use_live else None,
    )

    try:
        publish_report(_redis(), report)
    except Exception:
        pass
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())