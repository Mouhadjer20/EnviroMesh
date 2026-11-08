#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Core Deployment Script (RPi 2)
# ==============================================================================
# Validates environment and TLS certificates, builds and starts the RPi 2
# Core stack, waits for TimescaleDB, and executes database migrations safely.
#
# NOTE: Never uses 'docker compose down -v' so database volume is preserved.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../raspberry_pi/core" && pwd)"

echo "=== Deploying EnviroMesh Core (RPi 2) ==="

cd "${CORE_DIR}"

# 1. Environment check
if [[ ! -f ".env" ]]; then
    echo "ERROR: .env file missing in ${CORE_DIR}. Run setup_core.sh first."
    exit 1
fi

# Export .env variables for migration script
set -a
# shellcheck disable=SC1091
source .env
set +a

# 2. Check TLS certificates
for cert in ca.crt server.crt server.key; do
    if [[ ! -f "emqx/certs/${cert}" ]]; then
        echo "ERROR: emqx/certs/${cert} is missing. Follow docs/certificate-setup.md."
        exit 1
    fi
done

# 3. Build & Pull
echo "[1/4] Building and pulling containers..."
docker compose build
docker compose pull emqx-core timescaledb nginx

# 4. Start containers
echo "[2/4] Starting Core services..."
docker compose up -d

# 5. Wait for TimescaleDB to become healthy
echo "[3/4] Waiting for TimescaleDB..."
MAX_ATTEMPTS=30
ATTEMPT=0
while [[ $ATTEMPT -lt $MAX_ATTEMPTS ]]; do
    if docker compose exec timescaledb pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" &>/dev/null; then
        echo "  -> TimescaleDB is ready."
        break
    fi
    echo "  Waiting for database (attempt $((ATTEMPT + 1))/${MAX_ATTEMPTS})..."
    sleep 2
    ATTEMPT=$((ATTEMPT + 1))
done

if [[ $ATTEMPT -ge $MAX_ATTEMPTS ]]; then
    echo "ERROR: TimescaleDB failed to start within timeout."
    exit 1
fi

# 6. Run database migrations safely
echo "[4/4] Executing database migrations..."

MIGRATIONS=(
    "001_create_registry.sql"
    "001_create_telemetry.sql"
    "003_add_gateway_metadata.sql"
    "004_add_active_user.sql"
    "005_require_password_rotation.sql"
)

for mig in "${MIGRATIONS[@]}"; do
    if [[ -f "database/migrations/${mig}" ]]; then
        echo "  Applying ${mig}..."
        docker compose exec -T timescaledb psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" < "database/migrations/${mig}"
    else
        echo "WARNING: Migration file ${mig} not found in database/migrations/"
    fi
done

echo ""
echo "=== Core Deployment Complete ==="
docker compose ps
echo ""
echo "Dashboard is available at: http://${CORE_LAN_IP:-localhost}:${WEB_PORT:-8080}"
echo "To monitor backend logs: docker compose logs -f backend"
echo "To check health: python3 ${SCRIPT_DIR}/check_core_health.py"

