#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — MQTT Security Mode Controller (Auth & TLS Toggle Switch)
#
# Allows turning MQTT authentication and TLS encryption ON or OFF effortlessly
# via CLI arguments or an interactive menu ("button turn/off").
#
# Usage:
#   ./scripts/toggle_security.sh [options]
#
# Options:
#   --auth on|off     Enable or disable MQTT password-based authentication & ACL
#   --tls on|off      Enable or disable inter-Pi MQTT TLS encryption (port 8883 vs 1883)
#   --status          Display current security settings across all environments
#   --apply           Immediately restart EMQX / Gateway to apply changes
#   --help            Show this help message
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

cd "${PROJECT_ROOT}"

# Helper to update key=val in an env file
set_env_val() {
    local file="$1"
    local key="$2"
    local val="$3"
    
    if [ ! -f "${file}" ]; then
        return 0
    fi
    
    if grep -q "^${key}=" "${file}"; then
        local escaped_val
        escaped_val=$(printf '%s\n' "$val" | sed -e 's/[\/&]/\\&/g')
        sed -i.bak "s/^${key}=.*/${key}=${escaped_val}/" "${file}" && rm -f "${file}.bak"
    else
        echo "${key}=${val}" >> "${file}"
    fi
}

get_env_val() {
    local file="$1"
    local key="$2"
    local default_val="$3"
    if [ -f "${file}" ] && grep -q "^${key}=" "${file}"; then
        grep "^${key}=" "${file}" | cut -d '=' -f2- | tr -d '"' | tr -d "'"
    else
        echo "${default_val}"
    fi
}

# Single central root environment file
get_env_files() {
    local files=()
    if [ ! -f "${PROJECT_ROOT}/.env" ]; then
        cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
    fi
    files+=("${PROJECT_ROOT}/.env")
    echo "${files[@]}"
}

show_status() {
    local ref_file="${PROJECT_ROOT}/.env"
    if [ ! -f "${ref_file}" ]; then
        ref_file="${PROJECT_ROOT}/.env.example"
    fi
    
    local auth_status
    local tls_status
    local current_auth
    local current_tls
    
    current_auth=$(get_env_val "${ref_file}" "MQTT_AUTH_ENABLED" "true")
    current_tls=$(get_env_val "${ref_file}" "MQTT_CORE_USE_TLS" "false")
    
    if [ "${current_auth}" = "true" ] || [ "${current_auth}" = "1" ]; then
        auth_status="${GREEN}${BOLD}[ON]${NC} (Password auth & ACL enforced)"
    else
        auth_status="${YELLOW}${BOLD}[OFF]${NC} (Anonymous connection allowed, ACL bypass)"
    fi
    
    if [ "${current_tls}" = "true" ] || [ "${current_tls}" = "1" ]; then
        tls_status="${GREEN}${BOLD}[ON]${NC} (Port 8883, TLS Certificate encrypted)"
    else
        tls_status="${YELLOW}${BOLD}[OFF]${NC} (Port 1883/1884, Plain TCP)"
    fi
    
    echo -e "\n${BLUE}${BOLD}=== EnviroMesh MQTT Security Configuration ===${NC}"
    echo -e "  • MQTT Authentication: ${auth_status}"
    echo -e "  • MQTT TLS Encryption: ${tls_status}"
    echo -e "  • Environment source:   ${ref_file}\n"
}

set_auth() {
    local state="$1"
    local env_files
    # shellcheck disable=SC2207
    env_files=($(get_env_files))
    
    if [ "${state}" = "on" ] || [ "${state}" = "true" ] || [ "${state}" = "1" ]; then
        echo -e "${GREEN}Enabling MQTT Authentication...${NC}"
        for f in "${env_files[@]}"; do
            set_env_val "${f}" "MQTT_AUTH_ENABLED" "true"
            set_env_val "${f}" "EMQX_AUTH_ENABLED" "true"
            set_env_val "${f}" "EMQX_ACL_NO_MATCH" "deny"
            set_env_val "${f}" "EMQX_ALLOW_ANONYMOUS" "false"
        done
        echo -e "  ✔ Authentication enabled (credentials required, ACL active)."
    else
        echo -e "${YELLOW}Disabling MQTT Authentication (Anonymous mode)...${NC}"
        for f in "${env_files[@]}"; do
            set_env_val "${f}" "MQTT_AUTH_ENABLED" "false"
            set_env_val "${f}" "EMQX_AUTH_ENABLED" "false"
            set_env_val "${f}" "EMQX_ACL_NO_MATCH" "allow"
            set_env_val "${f}" "EMQX_ALLOW_ANONYMOUS" "true"
        done
        echo -e "  ✔ Authentication disabled (any client may connect and publish/subscribe)."
    fi
}

set_tls() {
    local state="$1"
    local env_files
    # shellcheck disable=SC2207
    env_files=($(get_env_files))
    
    if [ "${state}" = "on" ] || [ "${state}" = "true" ] || [ "${state}" = "1" ]; then
        echo -e "${GREEN}Enabling MQTT TLS Encryption...${NC}"
        # Ensure certs exist
        bash "${SCRIPT_DIR}/generate_certs.sh" >/dev/null 2>&1 || true
        for f in "${env_files[@]}"; do
            set_env_val "${f}" "MQTT_CORE_USE_TLS" "true"
            set_env_val "${f}" "MQTT_TLS_ENABLED" "true"
            set_env_val "${f}" "MQTT_CORE_PORT" "8883"
        done
        echo -e "  ✔ TLS enabled on port 8883 (using certificates in certs/ and gateway/certs/)."
    else
        echo -e "${YELLOW}Disabling MQTT TLS Encryption (Plain TCP)...${NC}"
        for f in "${env_files[@]}"; do
            set_env_val "${f}" "MQTT_CORE_USE_TLS" "false"
            set_env_val "${f}" "MQTT_TLS_ENABLED" "false"
            set_env_val "${f}" "MQTT_CORE_PORT" "1883"
        done
        echo -e "  ✔ TLS disabled. Inter-Pi communication uses plain MQTT port 1883."
    fi
}

apply_changes() {
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        echo -e "${BLUE}Restarting running MQTT broker services to apply new configuration...${NC}"
        docker compose restart emqx-local emqx-core gateway 2>/dev/null || true
        echo -e "${GREEN}✔ Services updated.${NC}"
    else
        echo -e "${YELLOW}Notice: Docker is not running. Changes will apply on next startup.${NC}"
    fi
}

# Parse options
AUTH_ARG=""
TLS_ARG=""
STATUS_ARG=false
APPLY_ARG=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --auth)
            AUTH_ARG="$2"
            shift 2
            ;;
        --tls)
            TLS_ARG="$2"
            shift 2
            ;;
        --status)
            STATUS_ARG=true
            shift
            ;;
        --apply)
            APPLY_ARG=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./scripts/toggle_security.sh [--auth on|off] [--tls on|off] [--status] [--apply]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ "${STATUS_ARG}" = true ]; then
    show_status
    exit 0
fi

if [ -n "${AUTH_ARG}" ]; then
    set_auth "${AUTH_ARG}"
fi

if [ -n "${TLS_ARG}" ]; then
    set_tls "${TLS_ARG}"
fi

# Interactive menu if no arguments were provided
if [ -z "${AUTH_ARG}" ] && [ -z "${TLS_ARG}" ]; then
    show_status
    echo -e "${CYAN}${BOLD}Security Toggle Switch Menu:${NC}"
    echo -e "  [1] Turn Authentication ${GREEN}ON${NC}  (Enforce user accounts and ACL)"
    echo -e "  [2] Turn Authentication ${YELLOW}OFF${NC} (Allow anonymous connection, open topics)"
    echo -e "  [3] Turn TLS Encryption ${GREEN}ON${NC}  (Secure inter-Pi port 8883 with certificates)"
    echo -e "  [4] Turn TLS Encryption ${YELLOW}OFF${NC} (Plain TCP on port 1883)"
    echo -e "  [5] Quick preset: ${GREEN}Full Production Security${NC} (Auth ON + TLS ON)"
    echo -e "  [6] Quick preset: ${YELLOW}Development / Simplicity${NC} (Auth OFF + TLS OFF)"
    echo -e "  [q] Quit without changes"
    
    read -r -p "Select option [1-6/q]: " choice
    case "${choice}" in
        1) set_auth "on" ;;
        2) set_auth "off" ;;
        3) set_tls "on" ;;
        4) set_tls "off" ;;
        5) set_auth "on"; set_tls "on" ;;
        6) set_auth "off"; set_tls "off" ;;
        q|Q) exit 0 ;;
        *) echo "Invalid option"; exit 1 ;;
    esac
    
    read -r -p "Restart running containers to apply now? [y/N]: " apply_choice
    if [[ "${apply_choice}" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        apply_changes
    fi
    show_status
    exit 0
fi

if [ "${APPLY_ARG}" = true ]; then
    apply_changes
fi

show_status

