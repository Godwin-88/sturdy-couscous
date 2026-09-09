#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

source "$ROOT_DIR/.env"

CHAIN=${1:-sepolia}

echo "Deploying ZK-KYC contracts to $CHAIN..."

forge build

# Deploy UltraVerifier first (pre-deployed or deploy a placeholder)
echo "Deploying UltraHonkVerifier..."
VERIFIER_OUTPUT=$(forge create \
  --rpc-url "$CHAIN" \
  --private-key "$PRIVATE_KEY" \
  --etherscan-api-key "$ETHERSCAN_API_KEY" \
  --verify \
  src/UltraHonkVerifier.sol:UltraHonkVerifier \
  --constructor-args "$VERIFIER_ADDRESS" 2>&1)

# Deploy ZKPassport
echo "Deploying ZKPassport..."
PASSPORT_OUTPUT=$(forge create \
  --rpc-url "$CHAIN" \
  --private-key "$PRIVATE_KEY" \
  --etherscan-api-key "$ETHERSCAN_API_KEY" \
  --verify \
  src/ZKPassport.sol:ZKPassport \
  --constructor-args "ZK Passport" "ZKP" 1000000 "$(cast wallet address "$PRIVATE_KEY")" 2>&1)

echo "Deployment complete!"
echo "VERIFIER_ADDRESS=$VERIFIER_ADDRESS"
echo "PASSPORT_ADDRESS=$PASSPORT_ADDRESS"
