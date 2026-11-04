#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Core Setup Script (RPi 2)
# ==============================================================================
# Verifies system prerequisites, creates directories, checks environment files,
# and verifies TLS certificates for RPi 2 (Core).
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../raspberry_pi/core" && pwd)"

echo "=== EnviroMesh RPi 2 (Core) Environment Setup ==="

# 1. Check Docker & Compose
echo "[1/5] Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed."
    exit 1
fi
if ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose plugin is not installed."
    exit 1
fi
echo "  -> Docker and Docker Compose are available."

# 2. Create required directory tree
echo "[2/5] Creating directories..."
mkdir -p "${CORE_DIR}/emqx/certs"
mkdir -p "${CORE_DIR}/database/migrations"
mkdir -p "${CORE_DIR}/database/seeds"
echo "  -> Directories verified."

# 3. Check Environment File
echo "[3/5] Checking .env configuration..."
if [[ ! -f "${CORE_DIR}/.env" ]]; then
    if [[ -f "${CORE_DIR}/.env.example" ]]; then
        echo "Copying .env.example to .env..."
        cp "${CORE_DIR}/.env.example" "${CORE_DIR}/.env"
        echo "IMPORTANT: Generated ${CORE_DIR}/.env. Please edit it with strong passwords!"
    else
        echo "ERROR: .env.example not found in ${CORE_DIR}"
        exit 1
    fi
else
    echo "  -> ${CORE_DIR}/.env exists."
fi

# 4. Check TLS Certificates
echo "[4/5] Checking TLS certificates..."
MISSING_CERTS=0
for cert in ca.crt server.crt server.key; do
    if [[ ! -f "${CORE_DIR}/emqx/certs/${cert}" ]]; then
        echo "WARNING: Missing certificate ${CORE_DIR}/emqx/certs/${cert}"
        MISSING_CERTS=1
    fi
done

if [[ ${MISSING_CERTS} -eq 1 ]]; then
    echo ""
    echo "TLS certificates are missing. Refer to docs/certificate-setup.md to generate them."
else
    echo "  -> TLS certificates are present."
fi

# 5. Check migration scripts
echo "[5/5] Verifying database migration files..."
for mig in 001_create_registry.sql 001_create_telemetry.sql 003_add_gateway_metadata.sql; do
    if [[ -f "${CORE_DIR}/database/migrations/${mig}" ]]; then
        echo "  -> Found ${mig}"
    else
        echo "WARNING: Missing migration ${mig} in ${CORE_DIR}/database/migrations/"
    fi
done

echo ""
echo "=== Core Setup Complete ==="
echo "Next steps:"
echo "1. Edit ${CORE_DIR}/.env with production credentials."
echo "2. Generate TLS certificates (docs/certificate-setup.md)."
echo "3. Run ${SCRIPT_DIR}/deploy_core.sh to deploy the stack."

