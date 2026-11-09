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

# 3. Check Environment File (Single Centralized .env)
echo "[3/5] Checking .env configuration..."
ROOT_ENV="${SCRIPT_DIR}/../.env"
if [[ ! -f "${ROOT_ENV}" ]]; then
    if [[ -f "${SCRIPT_DIR}/../.env.example" ]]; then
        echo "Creating root .env from .env.example..."
        cp "${SCRIPT_DIR}/../.env.example" "${ROOT_ENV}"
    fi
fi
ln -sf ../../.env "${CORE_DIR}/.env"
echo "  -> Linked ${CORE_DIR}/.env to central root .env"

# 4. Check TLS Certificates
echo "[4/5] Checking TLS certificates..."
if [[ ! -f "${CORE_DIR}/emqx/certs/server.crt" ]]; then
    if [[ -f "${SCRIPT_DIR}/generate_certs.sh" ]]; then
        echo "Generating TLS certificates via generate_certs.sh..."
        bash "${SCRIPT_DIR}/generate_certs.sh" || true
    fi
fi

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
    echo "  -> TLS certificates are verified."
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

