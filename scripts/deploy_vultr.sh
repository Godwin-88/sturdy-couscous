#!/usr/bin/env bash
# Deploy GraphAlpha to Vultr VM.
# Run from local machine: ./scripts/deploy_vultr.sh <vultr-ip>
set -euo pipefail

VULTR_IP="${1:?Usage: deploy_vultr.sh <vultr-ip>}"
REMOTE_DIR="/opt/graphalpha"
SSH="ssh root@$VULTR_IP"

echo "=== Deploying GraphAlpha to $VULTR_IP ==="

# 1. Ensure Docker + Compose are installed
$SSH "which docker || (curl -fsSL https://get.docker.com | sh)"
$SSH "which docker-compose || apt-get install -y docker-compose-plugin"

# 2. Sync project files (exclude dev-only stuff)
rsync -avz --exclude='node_modules' --exclude='__pycache__' \
    --exclude='.git' --exclude='*.pyc' \
    . "root@$VULTR_IP:$REMOTE_DIR"

# 3. Ensure .env exists
$SSH "test -f $REMOTE_DIR/.env || cp $REMOTE_DIR/.env.example $REMOTE_DIR/.env"
echo "IMPORTANT: Edit $REMOTE_DIR/.env on Vultr and set all secrets before continuing."

# 4. Pull images and restart
$SSH "cd $REMOTE_DIR && docker compose -f docker-compose.yml -f docker-compose.prod.yml pull"
$SSH "cd $REMOTE_DIR && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans"

# 5. Load graph
$SSH "cd $REMOTE_DIR && docker compose exec graph-loader true || \
      docker compose run --rm graph-loader"

echo ""
echo "=== Deployment complete ==="
echo "API: http://$VULTR_IP:8000"
echo "Memgraph Lab: http://$VULTR_IP:3000"
echo "Prometheus: http://$VULTR_IP:9090  (if monitoring profile active)"
