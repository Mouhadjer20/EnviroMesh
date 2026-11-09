#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Automated TLS Certificate Generator
#
# Generates self-signed PKI certificates for securing MQTT communication
# between Gateway 1 (192.168.1.20), Gateway 2 (192.168.1.30), and Core (192.168.1.5).
#
# Creates:
#   - Root CA: ca.crt, ca.key
#   - Core Server Cert: server.crt, server.key (with SANs for Core & Gateways)
#   - Gateway CA copy: core-ca.crt in raspberry_pi/gateway/certs/
#   - Unified copies in root certs/ directory
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

FORCE=false
if [ "${1:-}" = "--force" ] || [ "${1:-}" = "-f" ]; then
    FORCE=true
fi

echo -e "${BLUE}=== EnviroMesh TLS Certificate Provisioning ===${NC}"

# Target directories
ROOT_CERTS_DIR="${PROJECT_ROOT}/certs"
CORE_CERTS_DIR="${PROJECT_ROOT}/raspberry_pi/core/emqx/certs"
GATEWAY_CERTS_DIR="${PROJECT_ROOT}/raspberry_pi/gateway/certs"

mkdir -p "${ROOT_CERTS_DIR}" "${CORE_CERTS_DIR}" "${GATEWAY_CERTS_DIR}"

if ! command -v openssl >/dev/null 2>&1; then
    echo -e "${RED}Error: OpenSSL command not found. Cannot generate TLS certificates.${NC}"
    echo -e "Please install openssl or generate certificates manually using docs/certificate-setup.md."
    exit 1
fi

CA_KEY="${CORE_CERTS_DIR}/ca.key"
CA_CRT="${CORE_CERTS_DIR}/ca.crt"
SERVER_KEY="${CORE_CERTS_DIR}/server.key"
SERVER_CSR="${CORE_CERTS_DIR}/server.csr"
SERVER_CRT="${CORE_CERTS_DIR}/server.crt"
SERVER_EXT="${CORE_CERTS_DIR}/server_ext.cnf"
GW_CA_CRT="${GATEWAY_CERTS_DIR}/core-ca.crt"

if [ -f "${CA_CRT}" ] && [ -f "${SERVER_CRT}" ] && [ -f "${GW_CA_CRT}" ] && [ "${FORCE}" = false ]; then
    echo -e "${GREEN}✔ Valid TLS certificates already exist in:${NC}"
    echo -e "  • Core EMQX:    ${CORE_CERTS_DIR}"
    echo -e "  • Gateway CA:   ${GW_CA_CRT}"
    
    # Sync to root certs/ if missing
    cp -n "${CA_CRT}" "${SERVER_CRT}" "${SERVER_KEY}" "${ROOT_CERTS_DIR}/" 2>/dev/null || true
    echo -e "  • Root certs/:  ${ROOT_CERTS_DIR}"
    echo -e "Use ${YELLOW}--force${NC} to regenerate."
    exit 0
fi

echo -e "Generating Certificate Authority (CA) and Server Certificates..."

# 1. Generate CA private key and self-signed certificate
openssl genrsa -out "${CA_KEY}" 4096 2>/dev/null
openssl req -x509 -new -nodes -key "${CA_KEY}" -sha256 -days 3650 -out "${CA_CRT}" \
    -subj "/C=FR/ST=IDF/L=Paris/O=EnviroMesh/CN=EnviroMesh-Root-CA" 2>/dev/null

# 2. Generate Server private key and CSR
openssl genrsa -out "${SERVER_KEY}" 2048 2>/dev/null
openssl req -new -key "${SERVER_KEY}" -out "${SERVER_CSR}" \
    -subj "/C=FR/ST=IDF/L=Paris/O=EnviroMesh/CN=192.168.1.5" 2>/dev/null

# 3. Create SAN extension file covering Core (192.168.1.5), GW1 (.20), GW2 (.30), and local hosts
cat > "${SERVER_EXT}" << 'EOF'
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
IP.1 = 127.0.0.1
IP.2 = 192.168.1.5
IP.3 = 192.168.1.20
IP.4 = 192.168.1.30
DNS.1 = localhost
DNS.2 = emqx-core
DNS.3 = emqx-local
DNS.4 = rpi2-core.local
DNS.5 = enviromesh.local
EOF

# 4. Sign Server certificate with CA
openssl x509 -req -in "${SERVER_CSR}" -CA "${CA_CRT}" -CAkey "${CA_KEY}" -CAcreateserial \
    -out "${SERVER_CRT}" -days 3650 -sha256 -extfile "${SERVER_EXT}" 2>/dev/null

# 5. Distribute CA certificate to Gateway and root certs/ directory
cp "${CA_CRT}" "${GW_CA_CRT}"
cp "${CA_CRT}" "${ROOT_CERTS_DIR}/ca.crt"
cp "${SERVER_CRT}" "${ROOT_CERTS_DIR}/server.crt"
cp "${SERVER_KEY}" "${ROOT_CERTS_DIR}/server.key"
cp "${GW_CA_CRT}" "${ROOT_CERTS_DIR}/core-ca.crt"

# 6. Apply strict file permissions
chmod 600 "${CA_KEY}" "${SERVER_KEY}" "${ROOT_CERTS_DIR}/server.key" 2>/dev/null || true
chmod 644 "${CA_CRT}" "${SERVER_CRT}" "${GW_CA_CRT}" "${ROOT_CERTS_DIR}/ca.crt" "${ROOT_CERTS_DIR}/server.crt" 2>/dev/null || true

echo -e "${GREEN}✔ TLS certificates generated successfully!${NC}"
echo -e "  • Core Certs:    ${CORE_CERTS_DIR}/ (ca.crt, server.crt, server.key)"
echo -e "  • Gateway CA:    ${GW_CA_CRT}"
echo -e "  • Root Bundle:   ${ROOT_CERTS_DIR}/"

