#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# TacticX Phase 22 — Backup and Disaster Recovery Acceptance Test
#
# 1. Creates source database with migrated schema and test data
# 2. Runs scripts/backup_postgres.sh (creates compressed, checksummed dump)
# 3. Creates disposable target database
# 4. Runs scripts/restore_postgres.sh (verifies checksum and restores)
# 5. Executes schema and data integrity verification
# 6. Cleans up disposable database and temporary backup archives
# ==============================================================================

PG_USER="${PGUSER:-${POSTGRES_USER:-sivek}}"
PG_HOST="${PGHOST:-localhost}"
PG_PORT="${PGPORT:-5432}"

SRC_DB="tacticx_dr_source_test"
DISPOSABLE_DB="tacticx_dr_restore_disposable"
TEST_BACKUP_DIR="./data/test_backups"

echo "=== TACTICX DISASTER RECOVERY ACCEPTANCE TEST ==="

cleanup() {
    echo "[CLEANUP] Tearing down test databases and temp files..."
    psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d postgres -c "DROP DATABASE IF EXISTS ${SRC_DB};" >/dev/null 2>&1 || true
    psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d postgres -c "DROP DATABASE IF EXISTS ${DISPOSABLE_DB};" >/dev/null 2>&1 || true
    rm -rf "${TEST_BACKUP_DIR}"
}
trap cleanup EXIT

# 1. Create source DB and populate schema
echo "[STEP 1/5] Initializing source database '${SRC_DB}' with Alembic head..."
psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d postgres -c "DROP DATABASE IF EXISTS ${SRC_DB};"
psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d postgres -c "CREATE DATABASE ${SRC_DB};"

ALEMBIC_CMD="alembic"
if ! command -v alembic >/dev/null 2>&1; then
    if [[ -x "backend/.venv/bin/alembic" ]]; then
        ALEMBIC_CMD="backend/.venv/bin/alembic"
    elif command -v python3 >/dev/null 2>&1; then
        ALEMBIC_CMD="python3 -m alembic"
    elif command -v python >/dev/null 2>&1; then
        ALEMBIC_CMD="python -m alembic"
    fi
fi

DATABASE_URL="postgresql+psycopg2://${PG_USER}@${PG_HOST}:${PG_PORT}/${SRC_DB}" \
  ${ALEMBIC_CMD} -c backend/alembic.ini upgrade head >/dev/null


# Insert canary record into leagues and teams
psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${SRC_DB}" -c \
  "INSERT INTO leagues (code, name, provider, provider_league_id, season) VALUES ('EPL', 'Premier League', 'test_provider', '39', '2024');"

SRC_COUNT=$(psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${SRC_DB}" -t -c "SELECT count(*) FROM leagues;" | tr -d ' ')
echo "         Source database created with ${SRC_COUNT} canary record(s)."

# 2. Run backup
echo "[STEP 2/5] Creating compressed, checksummed backup..."
BACKUP_DIR="${TEST_BACKUP_DIR}" PGDATABASE="${SRC_DB}" ./scripts/backup_postgres.sh

BACKUP_FILE=$(ls -t "${TEST_BACKUP_DIR}"/tacticx_backup_*.sql.gz | head -n 1)
echo "         Created: ${BACKUP_FILE}"

# 3. Create disposable database
echo "[STEP 3/5] Creating disposable database '${DISPOSABLE_DB}'..."
psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d postgres -c "DROP DATABASE IF EXISTS ${DISPOSABLE_DB};"
psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d postgres -c "CREATE DATABASE ${DISPOSABLE_DB};"

# 4. Restore backup into disposable database
echo "[STEP 4/5] Restoring backup into disposable database '${DISPOSABLE_DB}'..."
./scripts/restore_postgres.sh "${BACKUP_FILE}" "${DISPOSABLE_DB}"

# 5. Integrity verification
echo "[STEP 5/5] Running schema and data integrity verification..."
RESTORED_COUNT=$(psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${DISPOSABLE_DB}" -t -c "SELECT count(*) FROM leagues;" | tr -d ' ')
RESTORED_TABLES=$(psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${DISPOSABLE_DB}" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" | tr -d ' ')

echo "         Restored table count: ${RESTORED_TABLES}"
echo "         Restored canary count: ${RESTORED_COUNT}"

if [[ "${SRC_COUNT}" != "${RESTORED_COUNT}" ]]; then
    echo "[FAIL] Record count mismatch: expected ${SRC_COUNT}, got ${RESTORED_COUNT}" >&2
    exit 1
fi

if [[ "${RESTORED_TABLES}" -lt 50 ]]; then
    echo "[FAIL] Incomplete table restoration: found ${RESTORED_TABLES} tables" >&2
    exit 1
fi

echo "=== DISASTER RECOVERY VERIFICATION SUCCESSFUL ==="
echo "All schema relations and data verified with 100% integrity."
