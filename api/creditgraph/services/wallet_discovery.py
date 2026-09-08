"""Wallet discovery for CreditGraph (E1-US1 / FR-001).

Resolves a blockchain wallet address into a chain identity, discovers the
wallets linked to a borrower from Neo4j, and aggregates a single wallet's
on-chain exposure (assets, liabilities, protocol exposures).

MVP chain detection supports EVM chains by address prefix. Ethereum and
Polygon share the 0x EVM address format, so detection resolves a valid 0x
address to the configured default EVM chain unless an explicit chain hint is
supplied (e.g. "polygon").

All graph reads are parameterized and go through the shared Neo4j driver in
`creditgraph.db.neo4j`. Discovery failures degrade gracefully: resolution still
returns the chain identity even when graph enrichment is unavailable.
"""

from __future__ import annotations

import logging
import re

from creditgraph.db.neo4j import get_driver
from creditgraph.models import Asset, Exposure, Liability, utcnow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chain detection
# ---------------------------------------------------------------------------

SUPPORTED_CHAINS: set[str] = {"ethereum", "polygon"}
DEFAULT_EVM_CHAIN: str = "ethereum"
EVM_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")


def detect_chain(wallet_address: str, chain_hint: str | None = None) -> str:
    """Resolve a wallet address to a supported chain identity.

    Ethereum and Polygon are both EVM chains (0x-prefixed 40-hex addresses),
    so the chain hint disambiguates when an explicit target is known.
    Returns the chain string; raises ValueError for an unsupported/empty address.
    """
    address = (wallet_address or "").strip()
    if not address:
        raise ValueError("wallet_address must not be empty")

    if chain_hint:
        hint = chain_hint.strip().lower()
        if hint not in SUPPORTED_CHAINS:
            raise ValueError(
                f"Unsupported chain hint '{chain_hint}'. "
                f"Supported: {sorted(SUPPORTED_CHAINS)}"
            )
        return hint

    if EVM_ADDRESS_RE.fullmatch(address):
        return DEFAULT_EVM_CHAIN

    raise ValueError(
        f"Could not detect chain for address '{address}'. "
        f"Supported EVM format: 0x + 40 hex chars, or pass an explicit chain hint."
    )


def _asset_to_dict(node: dict) -> dict:
    asset = Asset(
        asset_id=node.get("asset_id", ""),
        symbol=node.get("symbol", ""),
        chain=node.get("chain", ""),
        price_usd=float(node.get("price_usd", 0.0)),
        volatility_annualized=float(node.get("volatility_annualized", 0.0)),
        quantity=float(node.get("quantity", 0.0)),
    )
    return asset.model_dump()


def _liability_to_dict(node: dict) -> dict:
    liability = Liability(
        protocol=node.get("protocol", ""),
        outstanding=float(node.get("outstanding", 0.0)),
        asset_symbol=node.get("asset_symbol", ""),
    )
    return liability.model_dump()


def _exposure_to_dict(node: dict) -> dict:
    exposure = Exposure(
        protocol=node.get("protocol", ""),
        asset=node.get("asset", ""),
        exposure_amount=float(node.get("exposure_amount", 0.0)),
    )
    return exposure.model_dump()


# ---------------------------------------------------------------------------
# Wallet resolution
# ---------------------------------------------------------------------------


async def resolve_wallet(wallet_address: str, chain: str | None = None) -> dict:
    """Resolve a wallet address to its chain identity and discovered data.

    Returns a structured dict with chain, address, and any assets/transactions
    discovered for the wallet in the graph. Chain detection failures raise
    ValueError; Neo4j enrichment failures are logged and degrade to empty
    discovery so the chain identity is still returned.
    """
    address = (wallet_address or "").strip()
    resolved_chain = detect_chain(address, chain)

    result: dict = {
        "address": address,
        "chain": resolved_chain,
        "supported": resolved_chain in SUPPORTED_CHAINS,
        "assets": [],
        "transactions": [],
        "discovered_at": utcnow().isoformat(),
    }

    try:
        driver = get_driver()
        async with driver.session() as sess:
            cypher = (
                "MATCH (w:Wallet {address: $address}) "
                "OPTIONAL MATCH (w)-[:HOLDS]->(a:Asset) "
                "OPTIONAL MATCH (w)-[:HAS_TRANSACTION]->(t:Transaction) "
                "RETURN collect(DISTINCT a) AS assets, "
                "       collect(DISTINCT t) AS transactions"
            )
            record = await (await sess.run(cypher, {"address": address})).single()
        if record:
            result["assets"] = [
                _asset_to_dict(a) for a in record["assets"] if a is not None
            ]
            result["transactions"] = [
                dict(t) for t in record["transactions"] if t is not None
            ]
        logger.info(
            "Resolved wallet %s on chain %s (%d assets, %d transactions)",
            address,
            resolved_chain,
            len(result["assets"]),
            len(result["transactions"]),
        )
    except Exception as exc:  # pragma: no cover - graph unavailable
        logger.error("Failed to enrich wallet %s from Neo4j: %s", address, exc)

    return result


# ---------------------------------------------------------------------------
# Borrower wallet discovery
# ---------------------------------------------------------------------------


async def discover_borrower_wallets(borrower_id: str) -> list[dict]:
    """Retrieve all wallets linked to a borrower from Neo4j and enrich them.

    Wallets are read via `(b:Borrower)-[:OWNS]->(w:Wallet)` and each is enriched
    with its chain identity and discovered assets/transactions. Returns a list
    of resolved-wallet dicts.
    """
    bid = (borrower_id or "").strip()
    if not bid:
        raise ValueError("borrower_id must not be empty")

    driver = get_driver()
    wallets: list[dict] = []
    try:
        async with driver.session() as sess:
            cypher = (
                "MATCH (b:Borrower {borrower_id: $bid})-[:OWNS]->(w:Wallet) "
                "RETURN w"
            )
            cursor = await sess.run(cypher, {"bid": bid})
            rows = [row async for row in cursor]
    except Exception as exc:
        logger.error("Failed to discover wallets for borrower %s: %s", bid, exc)
        raise

    for row in rows:
        node = row["w"]
        if node is None:
            continue
        address = node.get("address", "")
        chain = node.get("chain") or None
        try:
            enriched = await resolve_wallet(address, chain)
            wallets.append(enriched)
        except Exception as exc:
            logger.warning("Could not enrich wallet %s: %s", address, exc)
            wallets.append(
                {"address": address, "chain": chain, "error": str(exc)}
            )

    logger.info("Discovered %d wallet(s) for borrower %s", len(wallets), bid)
    return wallets


# ---------------------------------------------------------------------------
# Wallet exposure aggregation
# ---------------------------------------------------------------------------


async def aggregate_wallet_exposure(wallet_address: str) -> dict:
    """Aggregate assets, liabilities, and protocol exposures for a single wallet.

    Reads the wallet's held assets plus any linked liabilities and exposures
    from Neo4j and computes totals (asset value, liabilities, exposure, net
    worth). Raises ValueError for an empty address; raises on graph errors.
    """
    address = (wallet_address or "").strip()
    if not address:
        raise ValueError("wallet_address must not be empty")

    driver = get_driver()
    try:
        async with driver.session() as sess:
            cypher = (
                "MATCH (w:Wallet {address: $address}) "
                "OPTIONAL MATCH (w)-[:HOLDS]->(a:Asset) "
                "OPTIONAL MATCH (w)-[:HAS_LIABILITY]->(l:Liability) "
                "OPTIONAL MATCH (w)-[:HAS_EXPOSURE]->(e:Exposure) "
                "RETURN collect(DISTINCT a) AS assets, "
                "       collect(DISTINCT l) AS liabilities, "
                "       collect(DISTINCT e) AS exposures"
            )
            record = await (await sess.run(cypher, {"address": address})).single()
    except Exception as exc:
        logger.error("Failed to aggregate exposure for wallet %s: %s", address, exc)
        raise

    if not record:
        logger.info("No wallet node found for %s; returning empty exposure", address)
        return {
            "address": address,
            "assets": [],
            "liabilities": [],
            "exposures": [],
            "totals": {
                "asset_value": 0.0,
                "liabilities": 0.0,
                "exposure": 0.0,
                "net_worth": 0.0,
            },
        }

    assets = [_asset_to_dict(a) for a in record["assets"] if a is not None]
    liabilities = [
        _liability_to_dict(l) for l in record["liabilities"] if l is not None
    ]
    exposures = [
        _exposure_to_dict(e) for e in record["exposures"] if e is not None
    ]

    total_asset_value = sum(
        float(a["price_usd"]) * float(a["quantity"]) for a in assets
    )
    total_liabilities = sum(float(l["outstanding"]) for l in liabilities)
    total_exposure = sum(float(e["exposure_amount"]) for e in exposures)
    net_worth = total_asset_value - total_liabilities

    logger.info(
        "Aggregated exposure for wallet %s: assets=%.2f liab=%.2f exposure=%.2f",
        address,
        total_asset_value,
        total_liabilities,
        total_exposure,
    )

    return {
        "address": address,
        "assets": assets,
        "liabilities": liabilities,
        "exposures": exposures,
        "totals": {
            "asset_value": round(total_asset_value, 2),
            "liabilities": round(total_liabilities, 2),
            "exposure": round(total_exposure, 2),
            "net_worth": round(net_worth, 2),
        },
    }
