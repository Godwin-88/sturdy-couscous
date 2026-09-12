#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy-claim.sh — deploy the ClaimToken + NAVAnchor (RWA claim layer, P11)
#
# Pattern-matched to the existing web3/scripts/deploy.sh (foundry forge create).
# CHAIN default = sepolia (chainKey 1 — the chain Attestcoin attests).
#
# Usage:
#   CLAIM_NAME="GraphAlpha Strategy Fund" CLAIM_SYMBOL="GASF" \
#   CLAIM_TOKEN_PRIVATE_KEY=0x... NAVANCHOR_PRIVATE_KEY=0x... \
#   ./scripts/deploy-claim.sh [chain]
#
# Notes:
#   - Token + anchor are deployed from the SAME funded key (operator = deployer).
#   - Requires Sepolia test ETH in the deployer key (faucet).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

CHAIN=${1:-sepolia}
NAME=${CLAIM_NAME:-"GraphAlpha Strategy Fund"}
SYMBOL=${CLAIM_SYMBOL:-"GASF"}
TOKEN_KEY=${CLAIM_TOKEN_PRIVATE_KEY:-${PRIVATE_KEY:-}}
ANCHOR_KEY=${NAVANCHOR_PRIVATE_KEY:-${TOKEN_KEY}}

echo "Deploying ClaimToken + NAVAnchor to $CHAIN ..."
# Build ONLY the RWA-claim artifacts (targeted): a full-tree `forge build` fails
# because the stellcasp-ported contracts (ZKPassport/UltraHonkVerifier) import
# @openzeppelin/contracts which is not vendored in web3/ (they are inert here:
# WEB3_PASSPORT_CONTRACT / WEB3_VERIFIER_CONTRACT are hardcoded 0x0). The claim
# contracts are self-contained (no external imports) so targeted paths compile.
forge build contracts/ClaimToken.sol contracts/NAVAnchor.sol contracts/test/ClaimNava.t.sol

TOKEN_OUT=$(forge create \
  --rpc-url "$CHAIN" \
  --private-key "$TOKEN_KEY" \
  --etherscan-api-key "${ETHERSCAN_API_KEY:-}" \
  --broadcast \
  --verify \
  contracts/ClaimToken.sol:ClaimToken \
  --constructor-args "$NAME" "$SYMBOL" 18 2>&1)
TOKEN_ADDR=$(echo "$TOKEN_OUT" | grep -oE 'Deployed to: 0x[0-9a-fA-F]{40}' | awk '{print $3}')
echo "CLAIM_TOKEN_CONTRACT=$TOKEN_ADDR"

ANCHOR_OUT=$(forge create \
  --rpc-url "$CHAIN" \
  --private-key "$ANCHOR_KEY" \
  --etherscan-api-key "${ETHERSCAN_API_KEY:-}" \
  --broadcast \
  --verify \
  contracts/NAVAnchor.sol:NAVAnchor 2>&1)
ANCHOR_ADDR=$(echo "$ANCHOR_OUT" | grep -oE 'Deployed to: 0x[0-9a-fA-F]{40}' | awk '{print $3}')
echo "NAV_ANCHOR_CONTRACT=$ANCHOR_ADDR"

echo "--- Deployment complete ---"
echo "CLAIM_TOKEN_CONTRACT=$TOKEN_ADDR"
echo "NAV_ANCHOR_CONTRACT=$ANCHOR_ADDR"