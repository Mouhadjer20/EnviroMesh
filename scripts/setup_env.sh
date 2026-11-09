#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Interactive Raspberry Pi Installer & Environment Setup
#
# Guides the user through:
# 1. Selecting the target Raspberry Pi deployment (Core, Gateway, or Unified)
# 2. Reviewing/modifying environment variables or keeping defaults
# 3. Performing target-specific first-installation checks (SPI, certs, Docker, Python)
# 4. Optional immediate service startup, database initialization, and health verification
# ==============================================================================

set -euo pipefail

# ANSI color codes for friendly terminal output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

echo -e "${BLUE}${BOLD}======================================================================${NC}"
echo -e "${BLUE}${BOLD}     EnviroMesh — Raspberry Pi Setup & Installation Service           ${NC}"
echo -e "${BLUE}${BOLD}======================================================================${NC}"

# Parse optional command line flags for automated/non-interactive runs
TARGET_ARG=""
DEFAULTS_ARG=false
START_ARG=false

for arg in "$@"; do
    case "$arg" in
        --core|--rpi2) TARGET_ARG="core" ;;
        --gw1|--gateway-1|--rpi1) TARGET_ARG="gw1" ;;
        --gw2|--gateway-2) TARGET_ARG="gw2" ;;
        --gateway) TARGET_ARG="gateway" ;;
        --unified|--single) TARGET_ARG="unified" ;;
        --defaults|-y) DEFAULTS_ARG=true ;;
        --start) START_ARG=true ;;
    esac
done

# ------------------------------------------------------------------------------
# STEP 1: Select Target Device Profile
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}${BOLD}[Step 1/5] Select Deployment Target${NC}"
echo -e "Which device are you configuring right now?"
echo -e "  ${BOLD}[1] RPi 2 — Core Server${NC} (Central Broker, TimescaleDB, FastAPI, Dashboard, Nginx)"
echo -e "  ${BOLD}[2] RPi 1 — Gateway 1${NC}   (GW01 - 192.168.1.20: Field Ingestion Broker, SQLite Queue)"
echo -e "  ${BOLD}[3] RPi 1 — Gateway 2${NC}   (GW02 - 192.168.1.30: Secondary Field Ingestion Broker)"
echo -e "  ${BOLD}[4] Unified / Single-Device${NC} (Runs both Gateway & Core on this machine — demo/dev)"

if [ -n "${TARGET_ARG}" ]; then
    TARGET="${TARGET_ARG}"
    echo -e "  -> Using target flag: ${GREEN}${TARGET}${NC}"
elif [ "${DEFAULTS_ARG}" = true ] || [ ! -t 0 ]; then
    TARGET="unified"
    echo -e "  -> Non-interactive/default mode: using ${GREEN}${TARGET}${NC}"
else
    read -r -p "Select option [1/2/3/4] (Default: 4): " choice_target
    case "${choice_target:-4}" in
        1) TARGET="core" ;;
        2) TARGET="gw1" ;;
        3) TARGET="gw2" ;;
        4) TARGET="unified" ;;
        *) TARGET="unified" ;;
    esac
fi

echo -e "Target configured: ${GREEN}${BOLD}${TARGET}${NC}"

# ------------------------------------------------------------------------------
# STEP 2: Configure Environment Variables (.env) — Single Root Source of Truth
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}${BOLD}[Step 2/5] Environment Variables Configuration${NC}"
echo -e "EnviroMesh uses a single, centralized ${GREEN}${BOLD}.env${NC} file at the project root."

TARGET_ENV_FILE="${PROJECT_ROOT}/.env"
EXAMPLE_ENV_FILE="${PROJECT_ROOT}/.env.example"

if [ ! -f "${TARGET_ENV_FILE}" ]; then
    cp "${EXAMPLE_ENV_FILE}" "${TARGET_ENV_FILE}"
    chmod 600 "${TARGET_ENV_FILE}"
    echo -e "  ✔ Created root ${TARGET_ENV_FILE} from ${EXAMPLE_ENV_FILE}."
else
    echo -e "  ✔ Using existing root ${TARGET_ENV_FILE}."
fi

# Link partition directories to root .env so sub-docker-compose commands always stay synchronized
mkdir -p "${PROJECT_ROOT}/raspberry_pi/core" "${PROJECT_ROOT}/raspberry_pi/gateway"
ln -sf ../../.env "${PROJECT_ROOT}/raspberry_pi/core/.env"
ln -sf ../../.env "${PROJECT_ROOT}/raspberry_pi/gateway/.env"
echo -e "  ✔ Synchronized core and gateway environments (symlinked to root .env)."

set_env_var() {
    local file="$1"
    local key="$2"
    local val="$3"
    if grep -q "^${key}=" "${file}"; then
        local escaped_val
        escaped_val=$(printf '%s\n' "$val" | sed -e 's/[\/&]/\\&/g')
        sed -i.bak "s/^${key}=.*/${key}=${escaped_val}/" "${file}" && rm -f "${file}.bak"
    else
        echo "${key}=${val}" >> "${file}"
    fi
}

# Apply target-specific profile defaults to root .env
if [ "${TARGET}" = "gw1" ]; then
    set_env_var "${TARGET_ENV_FILE}" "GATEWAY_ID" "GW01"
    set_env_var "${TARGET_ENV_FILE}" "GATEWAY_LAN_IP" "192.168.1.20"
    set_env_var "${TARGET_ENV_FILE}" "ENABLE_LORA" "true"
elif [ "${TARGET}" = "gw2" ]; then
    set_env_var "${TARGET_ENV_FILE}" "GATEWAY_ID" "GW02"
    set_env_var "${TARGET_ENV_FILE}" "GATEWAY_LAN_IP" "192.168.1.30"
    set_env_var "${TARGET_ENV_FILE}" "ENABLE_LORA" "false"
fi

# Ask user if they wish to customize environment variables
CUSTOMIZE_ENV=false
if [ "${DEFAULTS_ARG}" = false ] && [ -t 0 ]; then
    echo -e "\nConfiguration options:"
    echo -e "  [1] Keep recommended defaults (Standard ports, preconfigured secrets for testing)"
    echo -e "  [2] Interactively modify environment variables (IPs, custom ports, strong passwords)"
    read -r -p "Select option [1/2] (Default: 1): " choice_env
    if [ "${choice_env:-1}" = "2" ]; then
        CUSTOMIZE_ENV=true
    fi
fi

if [ "${CUSTOMIZE_ENV}" = true ]; then
    echo -e "\n${YELLOW}=== Interactive Configuration for ${TARGET} ===${NC}"

    if [ "${TARGET}" = "core" ]; then
        read -r -p "Enter Web Dashboard Port [8080]: " custom_port
        custom_port="${custom_port:-8080}"
        set_env_var "${TARGET_ENV_FILE}" "WEB_PORT" "${custom_port}"

        read -r -p "Enter PostgreSQL Database Password [enviromesh_secret_db_pass]: " custom_db_pass
        custom_db_pass="${custom_db_pass:-enviromesh_secret_db_pass}"
        set_env_var "${TARGET_ENV_FILE}" "POSTGRES_PASSWORD" "${custom_db_pass}"
        set_env_var "${TARGET_ENV_FILE}" "DB_PASSWORD" "${custom_db_pass}"

        read -r -p "Enter Core EMQX Dashboard Password [admin123]: " custom_emqx_pass
        custom_emqx_pass="${custom_emqx_pass:-admin123}"
        set_env_var "${TARGET_ENV_FILE}" "EMQX_DASHBOARD_PASSWORD" "${custom_emqx_pass}"

    elif [ "${TARGET}" = "gw1" ] || [ "${TARGET}" = "gateway" ]; then
        read -r -p "Enter Gateway ID [GW01]: " custom_gw_id
        custom_gw_id="${custom_gw_id:-GW01}"
        set_env_var "${TARGET_ENV_FILE}" "GATEWAY_ID" "${custom_gw_id}"

        read -r -p "Enter Gateway LAN IP [192.168.1.20]: " custom_gw_ip
        custom_gw_ip="${custom_gw_ip:-192.168.1.20}"
        set_env_var "${TARGET_ENV_FILE}" "GATEWAY_LAN_IP" "${custom_gw_ip}"

        read -r -p "Enter RPi 2 (Core Server) IP address [192.168.1.5]: " custom_core_ip
        custom_core_ip="${custom_core_ip:-192.168.1.5}"
        set_env_var "${TARGET_ENV_FILE}" "MQTT_CORE_HOST" "${custom_core_ip}"

        read -r -p "Enter Local MQTT Port for Field Nodes [1883]: " custom_local_port
        custom_local_port="${custom_local_port:-1883}"
        set_env_var "${TARGET_ENV_FILE}" "MQTT_LOCAL_PORT" "${custom_local_port}"

    elif [ "${TARGET}" = "gw2" ]; then
        read -r -p "Enter Gateway ID [GW02]: " custom_gw_id
        custom_gw_id="${custom_gw_id:-GW02}"
        set_env_var "${TARGET_ENV_FILE}" "GATEWAY_ID" "${custom_gw_id}"

        read -r -p "Enter Gateway LAN IP [192.168.1.30]: " custom_gw_ip
        custom_gw_ip="${custom_gw_ip:-192.168.1.30}"
        set_env_var "${TARGET_ENV_FILE}" "GATEWAY_LAN_IP" "${custom_gw_ip}"

        read -r -p "Enter RPi 2 (Core Server) IP address [192.168.1.5]: " custom_core_ip
        custom_core_ip="${custom_core_ip:-192.168.1.5}"
        set_env_var "${TARGET_ENV_FILE}" "MQTT_CORE_HOST" "${custom_core_ip}"

        read -r -p "Enter Local MQTT Port for Field Nodes [1883]: " custom_local_port
        custom_local_port="${custom_local_port:-1883}"
        set_env_var "${TARGET_ENV_FILE}" "MQTT_LOCAL_PORT" "${custom_local_port}"

    else # unified
        read -r -p "Enter Web Dashboard Port [8080]: " custom_port
        custom_port="${custom_port:-8080}"
        set_env_var "${TARGET_ENV_FILE}" "WEB_PORT" "${custom_port}"

        read -r -p "Enter Gateway ID [GW01]: " custom_gw_id
        custom_gw_id="${custom_gw_id:-GW01}"
        set_env_var "${TARGET_ENV_FILE}" "GATEWAY_ID" "${custom_gw_id}"

        read -r -p "Enter PostgreSQL Database Password [enviromesh_secret_db_pass]: " custom_db_pass
        custom_db_pass="${custom_db_pass:-enviromesh_secret_db_pass}"
        set_env_var "${TARGET_ENV_FILE}" "POSTGRES_PASSWORD" "${custom_db_pass}"
        set_env_var "${TARGET_ENV_FILE}" "DB_PASSWORD" "${custom_db_pass}"
    fi
    echo -e "  ✔ Configuration saved to ${GREEN}${TARGET_ENV_FILE}${NC}."
else
    echo -e "  ✔ Keeping defaults in ${GREEN}${TARGET_ENV_FILE}${NC}."
fi

# ------------------------------------------------------------------------------
# STEP 3: Prerequisites & Target Hardware Checks
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}${BOLD}[Step 3/5] Verifying Prerequisites & Hardware Interfaces${NC}"

# Check Docker & Docker Compose
if command -v docker >/dev/null 2>&1; then
    echo -e "  ✔ Docker is installed: $(command -v docker)"
    if docker compose version >/dev/null 2>&1; then
        echo -e "  ✔ Docker Compose is available: $(docker compose version --short)"
    else
        echo -e "  ✖ ${RED}Docker Compose plugin not detected.${NC}"
    fi
else
    echo -e "  ✖ ${RED}Docker is not installed! Please install Docker Engine first.${NC}"
fi

# Gateway-specific hardware checks (SPI for SX1278 LoRa)
if [ "${TARGET}" = "gw2" ]; then
    echo -e "  ℹ Gateway 2 (${BOLD}GW02${NC}) configured in pure Wi-Fi mode. LoRa receiver is ${YELLOW}disabled${NC} (ENABLE_LORA=false)."
elif [ "${TARGET}" = "gw1" ] || [ "${TARGET}" = "gateway" ] || [ "${TARGET}" = "unified" ]; then
    echo -e "  Checking SPI hardware interface (/dev/spidev0.0)..."
    if [ -e "/dev/spidev0.0" ]; then
        echo -e "  ✔ /dev/spidev0.0 detected (Hardware LoRa active)."
    else
        if command -v raspi-config >/dev/null 2>&1; then
            echo -e "  ℹ Enabling SPI interface via raspi-config..."
            sudo raspi-config nonint do_spi 0 || true
            echo -e "  ✔ SPI interface command executed (reboot may be required if on real Pi)."
        else
            echo -e "  ℹ SPI interface not present. Gateway will operate in Wi-Fi & software emulation mode."
        fi
    fi
fi

# TLS certificates provisioning (certs/ folder & Core/Gateway bundles)
echo -e "  Provisioning TLS certificates..."
if [ -f "${SCRIPT_DIR}/generate_certs.sh" ]; then
    bash "${SCRIPT_DIR}/generate_certs.sh" || true
fi

# ------------------------------------------------------------------------------
# STEP 4: Directory Structure, Permissions & Python Environment
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}${BOLD}[Step 4/5] Preparing Directories, Permissions & Python Dependencies${NC}"

# Ensure directories exist (including root certs/)
mkdir -p certs raspberry_pi/gateway/certs raspberry_pi/gateway/data raspberry_pi/gateway/emqx
mkdir -p raspberry_pi/core/emqx/certs raspberry_pi/core/backend/services raspberry_pi/core/backend/routes
mkdir -p raspberry_pi/core/backend/services raspberry_pi/core/backend/routes
mkdir -p raspberry_pi/core/dashboard raspberry_pi/core/database/migrations raspberry_pi/core/database/seeds
mkdir -p firmware/nodes/node_g11/src firmware/nodes/node_g41/src firmware/nodes/node_g31/src firmware/nodes/node_g51/src firmware/nodes/node_g61_servo/src

# Set executable flags
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x scripts/*.py 2>/dev/null || true
echo -e "  ✔ Executable permissions applied to scripts/ directory."

# Optional local Python virtual environment
if [ -d ".venv" ]; then
    echo -e "  ✔ Python virtual environment (.venv) detected."
else
    echo -e "  Creating Python virtual environment (.venv)..."
    python3 -m venv --system-site-packages .venv 2>/dev/null || python3 -m venv .venv || true
    echo -e "  ✔ Virtual environment created."
fi

# ------------------------------------------------------------------------------
# STEP 5: Service Launch Option
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}${BOLD}[Step 5/5] Ready for Deployment${NC}"

AUTO_START=false
if [ "${START_ARG}" = true ]; then
    AUTO_START=true
elif [ "${DEFAULTS_ARG}" = true ] || [ ! -t 0 ]; then
    AUTO_START=false
else
    read -r -p "Do you want to start EnviroMesh (${TARGET}) now? [Y/n]: " choice_start
    if [[ "${choice_start:-y}" =~ ^([yY][eE][sS]|[yY]|"")$ ]]; then
        AUTO_START=true
    fi
fi

if [ "${AUTO_START}" = true ]; then
    echo -e "\n${BLUE}Starting EnviroMesh services for: ${TARGET}...${NC}"

    if [ "${TARGET}" = "unified" ]; then
        bash "${SCRIPT_DIR}/docker_control.sh" start
        echo -e "\n${GREEN}✔ Unified stack started!${NC}"
        echo -e "  Web Dashboard: ${BLUE}http://localhost:${WEB_PORT:-8080}${NC}"
        echo -e "  Default Admin: ${BOLD}admin@enviromesh.local${NC} / ${BOLD}Admin12345678!${NC}"

    elif [ "${TARGET}" = "core" ]; then
        cd "${PROJECT_ROOT}/raspberry_pi/core"
        docker compose up -d --build
        echo -e "\n${YELLOW}Provisioning EMQX authentication users...${NC}"
        sleep 5
        bash "${SCRIPT_DIR}/init_emqx_auth.sh" || true
        cd "${PROJECT_ROOT}"
        echo -e "\n${GREEN}✔ Core stack started!${NC}"
        echo -e "  Web Dashboard: ${BLUE}http://localhost:${WEB_PORT:-8080}${NC}"
        echo -e "  Default Admin: ${BOLD}admin@enviromesh.local${NC} / ${BOLD}Admin12345678!${NC}"

    elif [ "${TARGET}" = "gateway" ] || [ "${TARGET}" = "gw1" ] || [ "${TARGET}" = "gw2" ]; then
        cd "${PROJECT_ROOT}/raspberry_pi/gateway"
        docker compose up -d --build
        echo -e "\n${YELLOW}Provisioning EMQX authentication users...${NC}"
        sleep 5
        bash "${SCRIPT_DIR}/init_emqx_auth.sh" || true
        cd "${PROJECT_ROOT}"
        echo -e "\n${GREEN}✔ Gateway stack started!${NC}"
        echo -e "  Local Ingestion MQTT: ${BLUE}0.0.0.0:${MQTT_LOCAL_PORT:-1883}${NC}"
    fi

    echo -e "\nTo check service health at any time, run:"
    echo -e "  ${CYAN}python3 scripts/check_health.py${NC}"
else
    echo -e "\n${GREEN}✔ Setup complete!${NC}"
    echo -e "To start services manually when ready:"
    if [ "${TARGET}" = "unified" ]; then
        echo -e "  ${CYAN}./scripts/docker_control.sh start${NC}"
    elif [ "${TARGET}" = "core" ]; then
        echo -e "  ${CYAN}cd raspberry_pi/core && docker compose up -d${NC}"
    elif [ "${TARGET}" = "gateway" ] || [ "${TARGET}" = "gw1" ] || [ "${TARGET}" = "gw2" ]; then
        echo -e "  ${CYAN}cd raspberry_pi/gateway && docker compose up -d${NC}"
    fi
fi
