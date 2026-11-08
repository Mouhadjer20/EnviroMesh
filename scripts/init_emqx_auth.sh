#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Initialize EMQX Authentication Users via REST API
#
# Ensures all MQTT clients (gateway, backend subscriber, simulated nodes) are
# registered in the EMQX built-in database even if persistent volumes exist.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load .env if present
if [ -f "${PROJECT_ROOT}/.env" ]; then
    # shellcheck disable=SC2046
    export $(grep -v '^#' "${PROJECT_ROOT}/.env" | xargs -0) 2>/dev/null || true
fi

LOCAL_API="http://127.0.0.1:${EMQX_LOCAL_DASHBOARD_PORT:-18083}/api/v5"
CORE_API="http://127.0.0.1:${EMQX_CORE_DASHBOARD_PORT:-18084}/api/v5"

LOCAL_AUTH="${EMQX_LOCAL_DASHBOARD_USERNAME:-admin}:${EMQX_LOCAL_DASHBOARD_PASSWORD:-admin123}"
CORE_AUTH="${EMQX_CORE_DASHBOARD_USERNAME:-admin}:${EMQX_CORE_DASHBOARD_PASSWORD:-admin123}"

add_emqx_user() {
    local api_base="$1"
    local auth="$2"
    local username="$3"
    local password="$4"
    local label="$5"

    local endpoint="${api_base}/authentication/password_based%3Abuilt_in_database/users"
    
    # Try adding user; if user already exists (409/already_exists), update password
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -u "${auth}" \
        -X POST "${endpoint}" \
        -H "Content-Type: application/json" \
        -d "{\"user_id\":\"${username}\",\"password\":\"${password}\",\"is_superuser\":false}" 2>/dev/null || echo "000")

    if [ "${http_code}" = "201" ] || [ "${http_code}" = "200" ]; then
        echo "  ✔ [${label}] Created user: ${username}"
    elif [ "${http_code}" = "400" ] || [ "${http_code}" = "409" ]; then
        # Already exists, update password to ensure sync
        curl -s -o /dev/null -u "${auth}" \
            -X PUT "${endpoint}/${username}" \
            -H "Content-Type: application/json" \
            -d "{\"password\":\"${password}\"}" 2>/dev/null || true
        echo "  ✔ [${label}] Synchronized existing user: ${username}"
    else
        echo "  ⚠ [${label}] Notice: HTTP ${http_code} for user ${username} (broker may still be booting)"
    fi
}

echo "=== Initializing EMQX Authentication ==="

echo "Configuring Gateway Local EMQX (localhost:${EMQX_LOCAL_DASHBOARD_PORT:-18083})..."
add_emqx_user "${LOCAL_API}" "${LOCAL_AUTH}" "${MQTT_LOCAL_USERNAME:-gw_ingestion}" "${MQTT_LOCAL_PASSWORD:-gw_ingest_secret}" "emqx-local"

# Node accounts for local EMQX
for node in g11 g31 g41 g51 g61 g42 g43; do
    add_emqx_user "${LOCAL_API}" "${LOCAL_AUTH}" "${node}" "node_secret_${node}" "emqx-local"
done

echo "Configuring Core Central EMQX (localhost:${EMQX_CORE_DASHBOARD_PORT:-18084})..."
add_emqx_user "${CORE_API}" "${CORE_AUTH}" "${MQTT_CORE_USERNAME:-gw_forwarder}" "${MQTT_CORE_PASSWORD:-gw_forward_secret}" "emqx-core"
add_emqx_user "${CORE_API}" "${CORE_AUTH}" "${MQTT_APP_USERNAME:-enviromesh_backend}" "${MQTT_APP_PASSWORD:-backend_secret_pass}" "emqx-core"

echo "✔ EMQX credentials initialization finished."

