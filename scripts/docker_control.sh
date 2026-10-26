#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Docker Compose Stack Controller
# Simplifies starting, stopping, restarting, and inspecting the EnviroMesh services:
# - emqx (MQTT broker 5.8.8)
# - timescaledb (PostgreSQL 16 + TimescaleDB 2.17.2)
# - backend (FastAPI + MQTT consumer + LoRa receiver)
# - dashboard (Nginx static frontend)
# - nginx (Gateway reverse proxy on port 8080)
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

    echo -e "\n${GREEN}✔ Services started! Current status:${NC}"
    docker compose ps
    echo -e "\nService endpoints:"
    echo -e "  • Web Dashboard & API Proxy: ${BLUE}http://localhost:${web_port}${NC}"
    echo -e "  • EMQX Dashboard:           ${BLUE}http://localhost:18083${NC} (admin)"
    echo -e "  • MQTT Broker Port:         ${BLUE}localhost:1883${NC}"
    echo -e "  • Backend Health Endpoint:  ${BLUE}http://localhost:${web_port}/api/health${NC}"
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
