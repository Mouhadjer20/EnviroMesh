#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Root Installation & Setup Entrypoint
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure certs/ and security directories exist and TLS certs are provisioned
mkdir -p "${SCRIPT_DIR}/certs" "${SCRIPT_DIR}/raspberry_pi/gateway/certs" "${SCRIPT_DIR}/raspberry_pi/core/emqx/certs"
if [ -f "${SCRIPT_DIR}/scripts/generate_certs.sh" ]; then
    bash "${SCRIPT_DIR}/scripts/generate_certs.sh" >/dev/null 2>&1 || true
fi

# Ensure single root .env is linked to partition directories for docker-compose
mkdir -p "${SCRIPT_DIR}/raspberry_pi/core" "${SCRIPT_DIR}/raspberry_pi/gateway"
ln -sf ../../.env "${SCRIPT_DIR}/raspberry_pi/core/.env"
ln -sf ../../.env "${SCRIPT_DIR}/raspberry_pi/gateway/.env"

exec bash "${SCRIPT_DIR}/scripts/setup_env.sh" "$@"

