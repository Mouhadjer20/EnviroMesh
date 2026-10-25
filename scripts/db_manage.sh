#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Database Management Utility
# Handles schema migrations, seed data, database shell, and verification.
# Supports both Docker container execution and native psql CLI.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Load environment variables if available
if [ -f "${PROJECT_ROOT}/.env" ]; then
    # Export only non-comment, non-empty lines
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
fi

DB_CONTAINER="${DB_CONTAINER:-enviromesh-timescaledb}"
DB_NAME="${POSTGRES_DB:-enviromesh}"
DB_USER="${POSTGRES_USER:-enviromesh_app}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

usage() {
    cat << EOF
EnviroMesh Database Management Script

Usage:
  ./scripts/db_manage.sh [command]

Commands:
  init        Run complete database setup (extensions, migrations, seeds, verification)
  migrate     Apply schema migrations (001_create_registry.sql, 001_create_telemetry.sql)
  seed        Load reference seed data (groups, students, devices, sensors)
  verify      Run verification queries and print database summary
  status      Show current row counts for all tables and hypertables
  shell       Open an interactive psql session in the database container
  reset       Drop existing tables and re-initialize completely (destructive!)
  help        Show this help message

Options:
  Set USE_DOCKER=0 to execute commands with local 'psql' instead of 'docker exec'.
EOF
}

# Determine execution mode: Docker container vs local psql
use_docker() {
    if [ "${USE_DOCKER:-1}" = "1" ]; then
        if docker ps --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
            return 0
        fi
    fi
    return 1
}

run_sql_file() {
    local file_path=$1
    local description=$2

    echo -e "${YELLOW}Applying ${description} (${file_path})...${NC}"

    if use_docker; then
        docker exec -i "${DB_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" < "${file_path}"
    else
        PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -f "${file_path}"
    fi

    echo -e "${GREEN}✔ ${description} applied successfully.${NC}"
}

run_sql_query() {
    local query=$1
    if use_docker; then
        docker exec -i "${DB_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" -c "${query}"
    else
        PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -c "${query}"
    fi
}

check_connection() {
    echo -e "${BLUE}Checking database connection...${NC}"
    if use_docker; then
        echo -e "  Using Docker container: ${BLUE}${DB_CONTAINER}${NC}"
        if ! docker exec -i "${DB_CONTAINER}" pg_isready -U "${DB_USER}" -d "${DB_NAME}" >/dev/null 2>&1; then
            echo -e "${RED}Error: Container '${DB_CONTAINER}' is not responding or not ready.${NC}"
            echo -e "Start containers first using: ./scripts/docker_control.sh start"
            exit 1
        fi
    else
        echo -e "  Using direct connection to: ${BLUE}${DB_HOST}:${DB_PORT}/${DB_NAME}${NC}"
        if ! command -v psql >/dev/null 2>&1; then
            echo -e "${RED}Error: 'psql' CLI not found and container '${DB_CONTAINER}' is not running.${NC}"
            exit 1
        fi
    fi
    echo -e "${GREEN}✔ Database is accessible.${NC}"
}

cmd_migrate() {
    check_connection
    echo -e "\n${BLUE}=== Enabling extensions ===${NC}"
    run_sql_query "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
    run_sql_query "CREATE EXTENSION IF NOT EXISTS timescaledb;"

    echo -e "\n${BLUE}=== Applying Relational Schema (Registry) ===${NC}"
    run_sql_file "${PROJECT_ROOT}/raspberry_pi/db/migration/001_create_registry.sql" "Registry Migration"

    echo -e "\n${BLUE}=== Applying Time-Series Schema (Telemetry) ===${NC}"
    run_sql_file "${PROJECT_ROOT}/raspberry_pi/db/migration/001_create_telemetry.sql" "Telemetry Migration"
}

cmd_seed() {
    check_connection
    echo -e "\n${BLUE}=== Seeding Reference Data ===${NC}"
    run_sql_file "${PROJECT_ROOT}/raspberry_pi/db/seed/001_seed_registry.sql" "Seed Registry Data"
}

cmd_verify() {
    check_connection
    echo -e "\n${BLUE}=== Running Seed Verification Queries ===${NC}"
    run_sql_file "${PROJECT_ROOT}/raspberry_pi/db/seed/001_verify_seed_registry.sql" "Verification Query Suite"
}

cmd_status() {
    check_connection
    echo -e "\n${BLUE}=== EnviroMesh Database Status ===${NC}"
    local query="
        SELECT 'groups' AS table_name, count(*) AS count FROM groups
        UNION ALL
        SELECT 'users', count(*) FROM users
        UNION ALL
        SELECT 'sensors', count(*) FROM sensors
        UNION ALL
        SELECT 'devices', count(*) FROM devices
        UNION ALL
        SELECT 'sensor_devices', count(*) FROM sensor_devices
        UNION ALL
        SELECT 'sensor_telemetry', count(*) FROM sensor_telemetry
        UNION ALL
        SELECT 'raw_sensor_packets', count(*) FROM raw_sensor_packets;
    "
    run_sql_query "${query}"
}

cmd_shell() {
    check_connection
    echo -e "${GREEN}Opening interactive psql session (${DB_NAME}). Press Ctrl+D to exit.${NC}"
    if use_docker; then
        docker exec -it "${DB_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}"
    else
        PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}"
    fi
}

cmd_reset() {
    check_connection
    echo -e "${RED}WARNING: This will drop and re-create all EnviroMesh tables!${NC}"
    read -r -p "Are you sure you want to proceed? [y/N] " response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo -e "${YELLOW}Dropping tables and hypertables...${NC}"
        local drop_query="
            DROP TABLE IF EXISTS raw_sensor_packets CASCADE;
            DROP TABLE IF EXISTS sensor_telemetry CASCADE;
            DROP TABLE IF EXISTS sensor_devices CASCADE;
            DROP TABLE IF EXISTS devices CASCADE;
            DROP TABLE IF EXISTS sensors CASCADE;
            DROP TABLE IF EXISTS users CASCADE;
            DROP TABLE IF EXISTS groups CASCADE;
        "
        run_sql_query "${drop_query}"
        echo -e "${GREEN}✔ Dropped all tables.${NC}"
        cmd_migrate
        cmd_seed
        cmd_verify
    else
        echo -e "Reset cancelled."
    fi
}

# Main routing
ACTION="${1:-help}"

case "${ACTION}" in
    init)
        cmd_migrate
        cmd_seed
        cmd_verify
        cmd_status
        ;;
    migrate)
        cmd_migrate
        ;;
    seed)
        cmd_seed
        ;;
    verify)
        cmd_verify
        ;;
    status)
        cmd_status
        ;;
    shell)
        cmd_shell
        ;;
    reset)
        cmd_reset
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
