#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Gateway Setup Script (RPi 1)
# ==============================================================================
# Verifies system prerequisites, enables hardware interfaces, creates required
# directories, and prepares environment files for RPi 1 (Gateway).
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_DIR="$(cd "${SCRIPT_DIR}/../raspberry_pi/gateway" && pwd)"

echo "=== EnviroMesh RPi 1 (Gateway) Environment Setup ==="

# 1. Check Docker & Docker Compose
echo "[1/6] Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed. Please install Docker first."
    exit 1
fi
if ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose plugin is not installed."
    exit 1
fi
echo "  -> Docker and Docker Compose are available."

# 2. Check and Enable SPI
echo "[2/6] Checking SPI hardware interface..."
if [[ -e /dev/spidev0.0 ]]; then
    echo "  -> /dev/spidev0.0 is present."
else
    echo "WARNING: /dev/spidev0.0 not found!"
    if command -v raspi-config &> /dev/null; then
        echo "Attempting to enable SPI via raspi-config..."
        sudo raspi-config nonint do_spi 0
        echo "SPI enabled. You may need to reboot if /dev/spidev0.0 does not appear."
    else
        echo "  -> Not running on Raspberry Pi OS or raspi-config missing. Hardware LoRa will run in emulation/fallback."
    fi
fi

# 3. Create required directory tree
echo "[3/6] Creating directories..."
mkdir -p "${GATEWAY_DIR}/certs"
mkdir -p "${GATEWAY_DIR}/data"
mkdir -p "${GATEWAY_DIR}/emqx"
echo "  -> Directories verified."

# 4. Check Environment File (Single Centralized .env)
echo "[4/6] Checking .env configuration..."
ROOT_ENV="${SCRIPT_DIR}/../.env"
if [[ ! -f "${ROOT_ENV}" ]]; then
    if [[ -f "${SCRIPT_DIR}/../.env.example" ]]; then
        echo "Creating root .env from .env.example..."
        cp "${SCRIPT_DIR}/../.env.example" "${ROOT_ENV}"
    fi
fi
ln -sf ../../.env "${GATEWAY_DIR}/.env"
echo "  -> Linked ${GATEWAY_DIR}/.env to central root .env"

# 5. Check CA Certificate for TLS connection to RPi 2
echo "[5/6] Checking TLS CA certificate..."
if [[ ! -f "${GATEWAY_DIR}/certs/core-ca.crt" ]]; then
    if [[ -f "${SCRIPT_DIR}/../certs/ca.crt" ]]; then
        cp "${SCRIPT_DIR}/../certs/ca.crt" "${GATEWAY_DIR}/certs/core-ca.crt"
        echo "  -> Copied CA certificate from certs/ca.crt to ${GATEWAY_DIR}/certs/core-ca.crt"
    elif [[ -f "${SCRIPT_DIR}/generate_certs.sh" ]]; then
        bash "${SCRIPT_DIR}/generate_certs.sh" >/dev/null 2>&1 || true
    fi
fi
if [[ -f "${GATEWAY_DIR}/certs/core-ca.crt" ]]; then
    echo "  -> core-ca.crt certificate verified."
else
    echo "WARNING: ${GATEWAY_DIR}/certs/core-ca.crt is missing!"
    echo "  Copy the CA certificate generated on RPi 2 to:"
    echo "  ${GATEWAY_DIR}/certs/core-ca.crt"
fi

# 6. Check EMQX ACL file
echo "[6/6] Verifying EMQX ACL configuration..."
if [[ -f "${GATEWAY_DIR}/emqx/acl.conf" ]]; then
    echo "  -> emqx/acl.conf is present."
else
    echo "ERROR: emqx/acl.conf is missing."
    exit 1
fi

echo ""
echo "=== Gateway Setup Complete ==="
echo "Next steps:"
echo "1. Edit ${GATEWAY_DIR}/.env to configure real passwords and RPi 2 IP."
echo "2. Place ca.crt from RPi 2 into ${GATEWAY_DIR}/certs/core-ca.crt."
echo "3. Run ${SCRIPT_DIR}/deploy_gateway.sh to start services."

