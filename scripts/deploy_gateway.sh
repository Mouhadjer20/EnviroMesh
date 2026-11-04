#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Gateway Deployment Script (RPi 1)
# ==============================================================================
# Validates environment and certificates, builds containers, and starts
# the RPi 1 Gateway stack.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_DIR="$(cd "${SCRIPT_DIR}/../raspberry_pi/gateway" && pwd)"

echo "=== Deploying EnviroMesh Gateway (RPi 1) ==="

cd "${GATEWAY_DIR}"

# 1. Environment check
if [[ ! -f ".env" ]]; then
    echo "ERROR: .env file missing in ${GATEWAY_DIR}. Run setup_gateway.sh first."
    exit 1
fi

# 2. Check TLS certificate
if [[ ! -f "certs/core-ca.crt" ]]; then
    echo "ERROR: certs/core-ca.crt is missing. Copy ca.crt from RPi 2 before deploying."
    exit 1
fi

# 3. Pull / Build images
echo "[1/3] Building and pulling container images..."
docker compose build
docker compose pull emqx-local

# 4. Start containers
echo "[2/3] Starting Gateway services..."
docker compose up -d

# 5. Health verification
echo "[3/3] Waiting for Gateway services to become healthy..."
MAX_ATTEMPTS=30
ATTEMPT=0

while [[ $ATTEMPT -lt $MAX_ATTEMPTS ]]; do
    STATUS=$(docker compose ps emqx-local --format json 2>/dev/null | grep -o '"Health":"[^"]*"' | cut -d'"' -f4 || echo "starting")
    if [[ "$STATUS" == "healthy" ]]; then
        echo "  -> emqx-local is healthy."
        break
    fi
    echo "  Waiting for emqx-local (current: ${STATUS:-starting})..."
    sleep 2
    ATTEMPT=$((ATTEMPT + 1))
done

if [[ $ATTEMPT -ge $MAX_ATTEMPTS ]]; then
    echo "WARNING: emqx-local took longer than expected to become healthy."
fi

echo ""
echo "=== Gateway Deployment Complete ==="
docker compose ps
echo ""
echo "To monitor logs: docker compose logs -f gateway"
echo "To check health: python3 ${SCRIPT_DIR}/check_gateway_health.py"

