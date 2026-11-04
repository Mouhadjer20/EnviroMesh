#!/usr/bin/env bash
# ==============================================================================
# EnviroMesh — Automated TimescaleDB Backup Script
# ==============================================================================
# Performs a compressed pg_dump of the PostgreSQL/TimescaleDB database
# running on RPi 2 (Core), saves it with an ISO timestamp, and enforces
# a retention policy (default: retain 7 days).
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../raspberry_pi/core" && pwd)"
BACKUP_DIR="${CORE_DIR}/backups"
RETENTION_DAYS=7

mkdir -p "${BACKUP_DIR}"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
BACKUP_FILE="${BACKUP_DIR}/enviromesh_backup_${TIMESTAMP}.sql.gz"

echo "=== EnviroMesh Database Backup ==="
echo "Destination: ${BACKUP_FILE}"

if [[ ! -f "${CORE_DIR}/.env" ]]; then
    echo "ERROR: .env not found in ${CORE_DIR}"
    exit 1
fi

set -a
# shellcheck disable=SC1091
source "${CORE_DIR}/.env"
set +a

# Execute pg_dump from inside container and gzip stream
docker compose -f "${CORE_DIR}/docker-compose.yml" exec -T timescaledb \
    pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists | gzip > "${BACKUP_FILE}"

SIZE=$(ls -lh "${BACKUP_FILE}" | awk '{print $5}')
echo "Backup created successfully. Size: ${SIZE}"

# Enforce retention policy
echo "Enforcing ${RETENTION_DAYS}-day retention policy..."
find "${BACKUP_DIR}" -name "enviromesh_backup_*.sql.gz" -type f -mtime "+${RETENTION_DAYS}" -delete
echo "Retention clean completed."

