#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# TacticX PostgreSQL Backup Script
# Creates a compressed, timestamped, checksummed PostgreSQL database dump.
# ==============================================================================

BACKUP_DIR="${BACKUP_DIR:-./data/backups}"
mkdir -p "${BACKUP_DIR}"

PG_USER="${PGUSER:-${POSTGRES_USER:-sivek}}"
PG_HOST="${PGHOST:-localhost}"
PG_PORT="${PGPORT:-5432}"
PG_DB="${PGDATABASE:-${POSTGRES_DB:-betpredictor}}"

TIMESTAMP="$(date -u +"%Y%m%d_%H%M%SZ")"
BACKUP_FILE="${BACKUP_DIR}/tacticx_backup_${PG_DB}_${TIMESTAMP}.sql.gz"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"

echo "[BACKUP] Starting backup for database '${PG_DB}' on ${PG_HOST}:${PG_PORT}..."

# Execute pg_dump directly with gzip
pg_dump -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" --no-owner --clean --if-exists "${PG_DB}" | gzip -9 > "${BACKUP_FILE}"

if [[ ! -s "${BACKUP_FILE}" ]]; then
    echo "[ERROR] Backup file is empty or missing: ${BACKUP_FILE}" >&2
    exit 1
fi

# Generate SHA-256 checksum (using basename so it is portable)
if command -v shasum >/dev/null 2>&1; then
    (cd "$(dirname "${BACKUP_FILE}")" && shasum -a 256 "$(basename "${BACKUP_FILE}")" > "$(basename "${CHECKSUM_FILE}")")
elif command -v sha256sum >/dev/null 2>&1; then
    (cd "$(dirname "${BACKUP_FILE}")" && sha256sum "$(basename "${BACKUP_FILE}")" > "$(basename "${CHECKSUM_FILE}")")
else
    echo "[WARNING] Neither shasum nor sha256sum available; skipping checksum file."
fi

BACKUP_SIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"
echo "[BACKUP] Backup completed successfully."
echo "         Archive:  ${BACKUP_FILE} (${BACKUP_SIZE})"
echo "         Checksum: ${CHECKSUM_FILE}"
