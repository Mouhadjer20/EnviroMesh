#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Environment & Developer Setup Script
# Initializes local environment, .env file, permissions, and dependencies.
# ==============================================================================

set -euo pipefail

# ANSI color codes for friendly terminal output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Determine project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}   EnviroMesh — Environment & Workspace Setup         ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. Check prerequisites
echo -e "\n${YELLOW}[1/5] Checking system prerequisites...${NC}"

check_tool() {
    local tool=$1
    local name=$2
    if command -v "${tool}" >/dev/null 2>&1; then
        echo -e "  ✔ ${name} is installed: $(command -v "${tool}")"
    else
        echo -e "  ✖ ${RED}Warning: ${name} (${tool}) is not found in PATH.${NC}"
    fi
}

check_tool "docker" "Docker Engine"
check_tool "python3" "Python 3"
check_tool "git" "Git"

if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
        echo -e "  ✔ Docker Compose is available: $(docker compose version --short)"
    else
        echo -e "  ✖ ${RED}Docker Compose plugin not detected.${NC}"
    fi
fi

# 2. Check / Setup .env file
echo -e "\n${YELLOW}[2/5] Checking configuration (.env)...${NC}"
if [ -f ".env" ]; then
    echo -e "  ✔ Found existing .env file."
else
    echo -e "  ℹ No .env file found. Creating .env from .env.example..."
    cp .env.example .env
    chmod 600 .env
    echo -e "  ✔ Created .env with secure permissions (chmod 600)."
    echo -e "  ${YELLOW}Notice: Remember to review and update passwords in .env for production deployment!${NC}"
fi

# 3. Create missing directories if needed
echo -e "\n${YELLOW}[3/5] Verifying directory structure...${NC}"
mkdir -p infrastructure/emqx infrastructure/nginx infrastructure/systemd
mkdir -p raspberry_pi/backend/services raspberry_pi/backend/routes raspberry_pi/backend/auth
mkdir -p raspberry_pi/dashboard raspberry_pi/db/migration raspberry_pi/db/seed
mkdir -p firmware/nodes/node_g11/src firmware/nodes/node_g41/src/main firmware/nodes/node_g31/src firmware/nodes/node_g61_servo/src
echo -e "  ✔ Directory structure verified."

# 4. Make all scripts in scripts/ executable
echo -e "\n${YELLOW}[4/5] Setting executable permissions on utility scripts...${NC}"
chmod +x "${SCRIPT_DIR}"/*.sh 2>/dev/null || true
chmod +x "${SCRIPT_DIR}"/*.py 2>/dev/null || true
echo -e "  ✔ All scripts in scripts/ marked executable."

# 5. Virtual environment setup (optional prompt)
echo -e "\n${YELLOW}[5/5] Checking Python virtual environment...${NC}"
if [ -d ".venv" ]; then
    echo -e "  ✔ Virtual environment (.venv) detected."
else
    echo -e "  ℹ No .venv detected. Creating a Python virtual environment..."
    # Use --system-site-packages so system-level RPi hardware drivers (python3-spidev, python3-rpi.gpio)
    # installed via apt are directly accessible inside the virtual environment without compiling C extensions.
    python3 -m venv --system-site-packages .venv
    echo -e "  ✔ Created virtual environment in ${PROJECT_ROOT}/.venv"
fi

if [ -f ".venv/bin/activate" ]; then
    echo -e "  ℹ Installing backend dependencies in .venv..."
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install --quiet --upgrade pip || true
    if [ -f "raspberry_pi/backend/requirements.txt" ]; then
        if pip install -r raspberry_pi/backend/requirements.txt; then
            echo -e "  ✔ Installed core requirements from raspberry_pi/backend/requirements.txt"
        else
            echo -e "  ${YELLOW}Warning: Could not install core dependencies in .venv.${NC}"
        fi
    fi
    # Optional hardware dependencies for LoRa SX1278 (on Linux / RPi)
    if [ -f "raspberry_pi/backend/requirements-hardware.txt" ] && [ "$(uname -s)" = "Linux" ]; then
        pip install -r raspberry_pi/backend/requirements-hardware.txt 2>/dev/null && \
            echo -e "  ✔ Installed LoRa hardware drivers (spidev/RPi.GPIO)" || true
    fi
    deactivate || true
fi

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}   EnviroMesh setup completed successfully!           ${NC}"
echo -e "${GREEN}======================================================${NC}"
echo -e "Next steps:"
echo -e "  1. Review your credentials in: ${BLUE}.env${NC}"
echo -e "  2. Start Docker infrastructure: ${BLUE}./scripts/docker_control.sh start${NC}"
echo -e "  3. Migrate and seed database:   ${BLUE}./scripts/db_manage.sh init${NC}"
echo -e "  4. Test live telemetry stream:  ${BLUE}./scripts/simulate_telemetry.py --count 10${NC}"
echo -e "  5. Monitor MQTT in real-time:   ${BLUE}./scripts/mqtt_monitor.py${NC}"
