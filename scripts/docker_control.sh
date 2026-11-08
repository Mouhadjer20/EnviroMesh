#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Docker Compose Stack Controller
# Simplifies starting, stopping, restarting, and inspecting the EnviroMesh services:
# - emqx-local  (RPi 1 Local Gateway MQTT broker on port 1883)
# - gateway     (RPi 1 Gateway ingestion, SQLite WAL queue, forwarder)
# - emqx-core   (RPi 2 Central Core MQTT broker on TLS port 8883 / debug 1884)
# - timescaledb (RPi 2 PostgreSQL 16 + TimescaleDB 2.17)
# - backend     (RPi 2 FastAPI + MQTT subscriber + DB writer)
# - dashboard   (RPi 2 React + Vite dashboard static frontend)
# - nginx       (RPi 2 Gateway reverse proxy on port 8080)
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

cd "${PROJECT_ROOT}"

usage() {
    cat << EOF
EnviroMesh Docker Stack Controller

Usage:
  ./scripts/docker_control.sh [command] [options]

Commands:
  start | up       Build and start all EnviroMesh containers in background
  stop | down      Stop all running containers
  restart          Restart all services
  status | ps      Show status, ports, and health checks of all services
  logs [service]   Follow live container logs (e.g. logs backend, logs emqx)
  build            Rebuild container images (backend, dashboard)
  auth             Provision / synchronize EMQX authentication users
  clean            Stop containers and remove volumes (destructive!)
  help             Show this help message
EOF
}

check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${RED}Error: Docker is not installed or not in PATH.${NC}"
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        echo -e "${RED}Error: Docker daemon is not running. Please start Docker first.${NC}"
        exit 1
    fi
}

cmd_start() {
    check_docker
    echo -e "${BLUE}Starting EnviroMesh Docker Stack...${NC}"
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}Warning: .env not found. Copying .env.example...${NC}"
        cp .env.example .env
    fi

    docker compose up -d --build --remove-orphans

    # -- Initialize EMQX Authentication ---------------------------------------
    if [ -f "${SCRIPT_DIR}/init_emqx_auth.sh" ]; then
        echo -e "\n${YELLOW}Provisioning EMQX authentication users...${NC}"
        # Give EMQX dashboard HTTP listeners a brief moment to accept connections
        sleep 5
        bash "${SCRIPT_DIR}/init_emqx_auth.sh" || true
    fi

    # -- Health wait ---------------------------------------------------------
    # docker compose up -d returns before containers are fully ready.
    # Poll /api/health through Nginx until backend responds (max 60s).
    local web_port="${WEB_PORT:-8080}"
    echo -e "\n${YELLOW}⏳ Waiting for backend to become healthy...${NC}"
    local max_wait=60 waited=0
    until curl -sf "http://localhost:${web_port}/api/health" > /dev/null 2>&1; do
        if [ "${waited}" -ge "${max_wait}" ]; then
            echo -e "\n${RED}✘ Backend did not respond after ${max_wait}s. Check logs with:${NC}"
            echo -e "  ./scripts/docker_control.sh logs backend"
            break
        fi
        printf "  %ds / %ds ...\r" "${waited}" "${max_wait}"
        sleep 3
        waited=$((waited + 3))
    done
    if curl -sf "http://localhost:${web_port}/api/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✔ Backend is healthy!${NC}                    "
    fi
    # ------------------------------------------------------------------------

    echo -e "\n${GREEN}✔ Unified services started! Current status:${NC}"
    docker compose ps
    echo -e "\nService endpoints:"
    echo -e "  • Web Dashboard & API Proxy: ${BLUE}http://localhost:${web_port}${NC}"
    echo -e "  • Gateway Local EMQX:        ${BLUE}localhost:1883${NC} (Field nodes & simulator)"
    echo -e "  • Gateway EMQX Dashboard:    ${BLUE}http://localhost:18083${NC} (admin)"
    echo -e "  • Core Central EMQX (TLS):   ${BLUE}localhost:8883${NC}"
    echo -e "  • Core EMQX Dashboard:       ${BLUE}http://localhost:18084${NC} (admin)"
    echo -e "  • Backend Health Endpoint:   ${BLUE}http://localhost:${web_port}/api/health${NC}"
}

cmd_stop() {
    check_docker
    echo -e "${YELLOW}Stopping EnviroMesh services...${NC}"
    docker compose down
    echo -e "${GREEN}✔ All services stopped.${NC}"
}

cmd_restart() {
    check_docker
    echo -e "${BLUE}Restarting EnviroMesh services...${NC}"
    docker compose restart
    docker compose ps
}

cmd_status() {
    check_docker
    echo -e "${BLUE}=== EnviroMesh Container Status ===${NC}"
    docker compose ps -a
}

cmd_logs() {
    check_docker
    local target="${1:-}"
    if [ -n "${target}" ]; then
        echo -e "${BLUE}Tailing logs for service: ${target}...${NC}"
        docker compose logs -f "${target}"
    else
        echo -e "${BLUE}Tailing logs for all services (Ctrl+C to stop)...${NC}"
        docker compose logs -f --tail=100
    fi
}

cmd_build() {
    check_docker
    echo -e "${BLUE}Building container images...${NC}"
    docker compose build --pull
    echo -e "${GREEN}✔ Build finished.${NC}"
}

cmd_clean() {
    check_docker
    echo -e "${RED}WARNING: This will stop containers and delete database and EMQX persistent volumes!${NC}"
    read -r -p "Are you sure you want to delete all volumes? [y/N] " response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        docker compose down -v --remove-orphans
        echo -e "${GREEN}✔ Volumes and containers removed.${NC}"
    else
        echo -e "Clean cancelled."
    fi
}

ACTION="${1:-help}"
shift 2>/dev/null || true

case "${ACTION}" in
    start|up)
        cmd_start
        ;;
    stop|down)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    status|ps)
        cmd_status
        ;;
    logs)
        cmd_logs "${1:-}"
        ;;
    build)
        cmd_build
        ;;
    auth)
        bash "${SCRIPT_DIR}/init_emqx_auth.sh"
        ;;
    clean)
        cmd_clean
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo -e "${RED}Unknown command: ${ACTION}${NC}\n"
        usage
        exit 1
        ;;
esac
