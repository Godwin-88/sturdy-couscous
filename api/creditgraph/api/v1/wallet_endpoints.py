"""Wallet discovery endpoints (E1-US1 / FR-001).

POST /risk/wallet/resolve              -> resolve a wallet address to chain identity
GET  /risk/borrowers/{borrower_id}/wallets -> list borrower wallets with exposure
POST /risk/wallet/aggregate            -> aggregate exposure for a single wallet
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from creditgraph.services import wallet_discovery

logger = logging.getLogger(__name__)

wallet_router = APIRouter(prefix="/risk", tags=["wallet-discovery"])


class WalletResolveRequest(BaseModel):
    wallet_address: str = Field(..., min_length=1, description="Blockchain wallet address")
    chain: str | None = Field(
        None, description="Optional chain hint to disambiguate EVM chains (ethereum/polygon)"
    )


class WalletAggregateRequest(BaseModel):
    wallet_address: str = Field(..., min_length=1, description="Blockchain wallet address")
    chain: str | None = Field(
        None, description="Optional chain hint to disambiguate EVM chains (ethereum/polygon)"
    )


@wallet_router.post("/wallet/resolve", response_model=dict)
async def resolve_wallet_endpoint(req: WalletResolveRequest) -> dict:
    """Resolve a wallet address into its chain identity and discovered data."""
    try:
        return await wallet_discovery.resolve_wallet(req.wallet_address, req.chain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@wallet_router.get("/borrowers/{borrower_id}/wallets", response_model=dict)
async def borrower_wallets_endpoint(borrower_id: str) -> dict:
    """List all wallets linked to a borrower, each enriched with exposure."""
    try:
        wallets = await wallet_discovery.discover_borrower_wallets(borrower_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    enriched: list[dict] = []
    for wallet in wallets:
        address = wallet.get("address")
        exposure: dict = {}
        if address:
            try:
                exposure = await wallet_discovery.aggregate_wallet_exposure(address)
            except Exception as exc:
                logger.warning("Exposure aggregation failed for %s: %s", address, exc)
        entry = dict(wallet)
        entry["exposure"] = exposure
        enriched.append(entry)

    return {
        "borrower_id": borrower_id,
        "wallets": enriched,
        "wallet_count": len(enriched),
    }


@wallet_router.post("/wallet/aggregate", response_model=dict)
async def aggregate_wallet_endpoint(req: WalletAggregateRequest) -> dict:
    """Aggregate a single wallet's assets, liabilities, and protocol exposures."""
    try:
        return await wallet_discovery.aggregate_wallet_exposure(req.wallet_address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
