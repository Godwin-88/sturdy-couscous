"""
EVM / L2 Passport Adapter — ported into GraphAlpha from
stellcasp/zkkyc/adapters/ethereum (EP-08 F-08.2 — US-08.2.1/2/3).

Spec reference: EP-08 (F-08.2 — US-08.2.1, US-08.2.2, US-08.2.3), EP-02 (F-02.1)

Implements the PassportAdapterBase interface for EVM-compatible chains
(Ethereum, Base, Arbitrum, Optimism, etc.) using:

  1. Noir's native Solidity UltraHonk verifier output (Verifier.sol)
  2. ERC-721 soulbound Compliance Passport implementing EIP-5192

One implementation covers all EVM chains — only the RPC URL and contract
addresses change per deployment.

Environment variables consumed:
  WEB3_RPC_URL, WEB3_VERIFIER_CONTRACT_ADDRESS,
  WEB3_PASSPORT_CONTRACT_ADDRESS, WEB3_CHAIN_ID,
  WEB3_ORACLE_AUTHORITY_PRIVATE_KEY
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .config import Settings, get_settings
from .base import (
    AdapterDeploymentError,
    DeploymentInfo,
    PassportAdapterBase,
)

logger = logging.getLogger(__name__)


class EVMAdapter(PassportAdapterBase):
    """EVM/L2 Compliance Passport Adapter.

    Spec reference: US-08.2.1, US-08.2.2, US-08.2.3
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def verify_proof(self, proof_hex: str, public_inputs: list[int]) -> bool:
        """Verify a Noir UltraHonk proof on an EVM chain.

        Calls `verify(proof, publicInputs)` on the deployed Verifier.sol contract
        and returns True if the call succeeds.

        Args:
            proof_hex: hex-encoded UltraHonk proof bytes.
            public_inputs: public input integers from the Noir circuit.

        Returns:
            True if the verifier contract returns `true`.
        """
        verifier_address = getattr(self.settings, "web3_verifier_contract_address", None)
        if not verifier_address:
            raise AdapterDeploymentError(
                "sepolia-evm", "WEB3_VERIFIER_CONTRACT_ADDRESS is not configured"
            )

        try:
            from web3 import Web3
        except ImportError as exc:
            raise AdapterDeploymentError(
                "sepolia-evm", "web3.py not installed; run: pip install web3", cause=exc
            ) from exc

        rpc_url = getattr(self.settings, "web3_rpc_url", "https://sepolia.infura.io/v3/YOUR_KEY")
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            raise AdapterDeploymentError("sepolia-evm", f"Cannot connect to RPC {rpc_url}")

        try:
            proof_bytes = bytes.fromhex(proof_hex)
        except ValueError as exc:
            raise AdapterDeploymentError("sepolia-evm", f"proof_hex is not valid hex: {exc}", cause=exc) from exc

        verifier_abi = [
            {
                "inputs": [
                    {"name": "proof", "type": "bytes"},
                    {"name": "publicInputs", "type": "uint256[]"},
                ],
                "name": "verify",
                "outputs": [{"name": "", "type": "bool"}],
                "stateMutability": "view",
                "type": "function",
            }
        ]
        contract = w3.eth.contract(address=verifier_address, abi=verifier_abi)
        private_key = getattr(self.settings, "web3_oracle_authority_private_key", None)
        if not private_key:
            raise AdapterDeploymentError("sepolia-evm", "WEB3_ORACLE_AUTHORITY_PRIVATE_KEY is not configured")

        account = w3.eth.account.from_key(private_key)
        try:
            is_valid = contract.functions.verify(proof_bytes, public_inputs).call({"from": account.address})
            logger.info("ethereum proof verified", extra={"valid": is_valid, "verifier": verifier_address})
            return bool(is_valid)
        except Exception as exc:
            raise AdapterDeploymentError("sepolia-evm", f"verifier contract call failed: {exc}", cause=exc) from exc

    async def mint_passport(
        self,
        wallet: str,
        policy_id: str,
        expires_at: int,
        proof_hash: str,
    ) -> str:
        """Mint a soulbound ERC-721 Compliance Passport.

        Calls `mintPassport(address, string, uint256, bytes32)` on the
        CompliancePassport contract, which internally verifies the proof
        against the UltraHonk verifier before minting.

        Args:
            wallet: destination EVM address (0x...).
            policy_id: policy identifier string.
            expires_at: UNIX timestamp.
            proof_hash: 32-byte proof hash hex string.

        Returns:
            Ethereum transaction hash (0x...).
        """
        passport_address = getattr(self.settings, "web3_passport_contract_address", None)
        if not passport_address:
            raise AdapterDeploymentError(
                "sepolia-evm", "WEB3_PASSPORT_CONTRACT_ADDRESS is not configured"
            )

        try:
            from web3 import Web3
        except ImportError as exc:
            raise AdapterDeploymentError("sepolia-evm", "web3.py not installed", cause=exc) from exc

        rpc_url = getattr(self.settings, "web3_rpc_url", "https://sepolia.infura.io/v3/YOUR_KEY")
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            raise AdapterDeploymentError("sepolia-evm", f"Cannot connect to RPC {rpc_url}")

        private_key = getattr(self.settings, "web3_oracle_authority_private_key", None)
        if not private_key:
            raise AdapterDeploymentError("sepolia-evm", "WEB3_ORACLE_AUTHORITY_PRIVATE_KEY is not configured")
        account = w3.eth.account.from_key(private_key)

        passport_abi = [
            {
                "inputs": [
                    {"name": "wallet", "type": "address"},
                    {"name": "policyId", "type": "string"},
                    {"name": "expiresAt", "type": "uint256"},
                    {"name": "proofHash", "type": "bytes32"},
                ],
                "name": "mintPassport",
                "outputs": [{"name": "tokenId", "type": "uint256"}],
                "stateMutability": "nonpayable",
                "type": "function",
            }
        ]
        contract = w3.eth.contract(address=passport_address, abi=passport_abi)
        proof_hash_bytes = bytes.fromhex(proof_hash)

        try:
            tx = contract.functions.mintPassport(
                Web3.to_checksum_address(wallet),
                policy_id,
                expires_at,
                proof_hash_bytes,
            ).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 300_000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status != 1:
                raise AdapterDeploymentError("sepolia-evm", f"mint tx reverted: {receipt.transactionHash.hex()}")

            logger.info(
                "ethereum passport minted",
                extra={"tx_hash": tx_hash.hex(), "wallet": wallet, "policy_id": policy_id},
            )
            return tx_hash.hex()
        except AdapterDeploymentError:
            raise
        except Exception as exc:
            raise AdapterDeploymentError("sepolia-evm", f"mintPassport failed: {exc}", cause=exc) from exc

    async def revoke_passport(self, wallet: str, policy_id: str, reason: str) -> str:
        """Revoke a Compliance Passport on EVM.

        Calls `revokePassport(address, string, string)` on the CompliancePassport
        contract.

        Args:
            wallet: EVM address to revoke.
            policy_id: policy identifier.
            reason: revocation reason.

        Returns:
            Ethereum transaction hash.
        """
        passport_address = getattr(self.settings, "web3_passport_contract_address", None)
        if not passport_address:
            raise AdapterDeploymentError("sepolia-evm", "WEB3_PASSPORT_CONTRACT_ADDRESS is not configured")

        try:
            from web3 import Web3
        except ImportError as exc:
            raise AdapterDeploymentError("sepolia-evm", "web3.py not installed", cause=exc) from exc

        rpc_url = getattr(self.settings, "web3_rpc_url", "https://sepolia.infura.io/v3/YOUR_KEY")
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            raise AdapterDeploymentError("sepolia-evm", f"Cannot connect to RPC {rpc_url}")

        private_key = getattr(self.settings, "web3_oracle_authority_private_key", None)
        if not private_key:
            raise AdapterDeploymentError("sepolia-evm", "WEB3_ORACLE_AUTHORITY_PRIVATE_KEY is not configured")
        account = w3.eth.account.from_key(private_key)

        passport_abi = [
            {
                "inputs": [
                    {"name": "wallet", "type": "address"},
                    {"name": "policyId", "type": "string"},
                    {"name": "reason", "type": "string"},
                ],
                "name": "revokePassport",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            }
        ]
        contract = w3.eth.contract(address=passport_address, abi=passport_abi)

        try:
            tx = contract.functions.revokePassport(
                Web3.to_checksum_address(wallet),
                policy_id,
                reason,
            ).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 200_000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status != 1:
                raise AdapterDeploymentError("sepolia-evm", f"revoke tx reverted: {receipt.transactionHash.hex()}")

            logger.info("ethereum passport revoked", extra={"tx_hash": tx_hash.hex(), "wallet": wallet, "reason": reason})
            return tx_hash.hex()
        except AdapterDeploymentError:
            raise
        except Exception as exc:
            raise AdapterDeploymentError("sepolia-evm", f"revokePassport failed: {exc}", cause=exc) from exc

    async def verify_credential(self, wallet: str, policy_id: str) -> dict[str, Any]:
        """Check if `wallet` holds a valid Compliance Passport on EVM.

        Queries the ERC-721 `verifyCredential(address, string)` view function
        which returns `(bool valid, uint256 expiresAt)`.

        Args:
            wallet: EVM address to check.
            policy_id: policy identifier.

        Returns:
            Dict with `valid` (bool), `expires_at` (int), `policy_id` (str).
        """
        passport_address = getattr(self.settings, "web3_passport_contract_address", None)
        if not passport_address:
            return {"valid": False, "expires_at": 0, "policy_id": policy_id}

        try:
            from web3 import Web3
        except ImportError:
            return {"valid": False, "expires_at": 0, "policy_id": policy_id}

        rpc_url = getattr(self.settings, "web3_rpc_url", "https://sepolia.infura.io/v3/YOUR_KEY")
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            return {"valid": False, "expires_at": 0, "policy_id": policy_id}

        passport_abi = [
            {"inputs": [{"name": "owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"name": "tokenId", "type": "uint256"}], "name": "locked", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"name": "wallet", "type": "address"}, {"name": "policyId", "type": "string"}], "name": "verifyCredential", "outputs": [{"name": "valid", "type": "bool"}, {"name": "expiresAt", "type": "uint256"}], "stateMutability": "view", "type": "function"},
        ]
        contract = w3.eth.contract(address=passport_address, abi=passport_abi)

        try:
            result = contract.functions.verifyCredential(
                Web3.to_checksum_address(wallet), policy_id
            ).call()
            valid = bool(result[0])
            expires_at = int(result[1])
            return {"valid": valid, "expires_at": expires_at, "policy_id": policy_id}
        except Exception as exc:
            logger.warning("ethereum verifyCredential failed", extra={"error": str(exc)})
            return {"valid": False, "expires_at": 0, "policy_id": policy_id}

    async def get_deployment_info(self) -> DeploymentInfo:
        """Return EVM deployment metadata."""
        verifier = getattr(self.settings, "web3_verifier_contract_address", "")
        passport = getattr(self.settings, "web3_passport_contract_address", "")
        chain_id = int(getattr(self.settings, "web3_chain_id", "11155111"))
        rpc_url = getattr(self.settings, "web3_rpc_url", "")
        network = "testnet" if "sepolia" in rpc_url.lower() or "goerli" in rpc_url.lower() else "mainnet"

        return DeploymentInfo(
            chain_id=f"sepolia-evm:{chain_id}",
            contract_address=passport or verifier,
            deployed_at=datetime.now(timezone.utc),
            network=network,
            extra={
                "verifier_contract_address": verifier,
                "passport_contract_address": passport,
                "chain_id": chain_id,
                "rpc_url": rpc_url,
            },
        )
