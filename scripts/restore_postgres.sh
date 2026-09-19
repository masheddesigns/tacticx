#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# TacticX PostgreSQL Restore Script
# Restores a compressed, checksummed PostgreSQL database dump.
# ==============================================================================

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <path-to-backup.sql.gz> [target_database]"
    exit 1
fi

BACKUP_FILE="$1"
if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "[ERROR] Backup file not found: ${BACKUP_FILE}" >&2
    exit 1
fi

PG_USER="${PGUSER:-${POSTGRES_USER:-sivek}}"
PG_HOST="${PGHOST:-localhost}"
PG_PORT="${PGPORT:-5432}"
TARGET_DB="${2:-${PGDATABASE:-${POSTGRES_DB:-betpredictor}}}"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"

# Verify checksum if checksum file exists
if [[ -f "${CHECKSUM_FILE}" ]]; then
    echo "[RESTORE] Verifying archive checksum..."
    if command -v shasum >/dev/null 2>&1; then
        (cd "$(dirname "${BACKUP_FILE}")" && shasum -a 256 -c "$(basename "${CHECKSUM_FILE}")")
    elif command -v sha256sum >/dev/null 2>&1; then
        (cd "$(dirname "${BACKUP_FILE}")" && sha256sum -c "$(basename "${CHECKSUM_FILE}")")
    fi
    echo "[RESTORE] Checksum verification passed."
fi

echo "[RESTORE] Restoring into target database '${TARGET_DB}' on ${PG_HOST}:${PG_PORT}..."
gunzip -c "${BACKUP_FILE}" | psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${TARGET_DB}" -v ON_ERROR_STOP=1 --single-transaction

echo "[RESTORE] Database '${TARGET_DB}' restored successfully from ${BACKUP_FILE}."
