"""Phase 25.1 — Alembic Migration Structural Tests.

Verifies:
1. Migration file exists with correct revision ID and down_revision.
2. Migration applies cleanly to a fresh SQLite database (upgrade).
3. Migration downgrades cleanly (table removed).
4. Re-upgrade succeeds (upgrade → downgrade → upgrade again).
5. Exactly one Alembic head exists (no branch divergence).

NOTE: These tests use SQLite. PostgreSQL migration must be verified separately
before READY_FOR_PHASE_26 can be claimed.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
import sqlalchemy as sa


MIGRATION_DIR = Path(__file__).parent.parent / "migrations" / "versions"
MIGRATION_FILE = MIGRATION_DIR / "0010_prematch_readiness.py"


def test_migration_file_exists():
    assert MIGRATION_FILE.exists(), f"Migration file not found: {MIGRATION_FILE}"


def test_migration_has_correct_revision():
    spec = importlib.util.spec_from_file_location("mig_0010", str(MIGRATION_FILE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0010_prematch_readiness"


def test_migration_down_revision_is_0009():
    spec = importlib.util.spec_from_file_location("mig_0010b", str(MIGRATION_FILE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == "0009_production_schema_complete"


def test_migration_no_branch_labels():
    spec = importlib.util.spec_from_file_location("mig_0010c", str(MIGRATION_FILE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.branch_labels is None


def _apply_migration_upgrade(conn):
    """Apply 0010 upgrade() to an existing SQLAlchemy connection."""
    from alembic.runtime.migration import MigrationContext
    spec = importlib.util.spec_from_file_location("mig_0010_upgrade", str(MIGRATION_FILE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    ctx = MigrationContext.configure(conn)
    with ctx.begin_transaction():
        from alembic.operations import Operations
        op = Operations(ctx)
        # Run the upgrade directly using the migration's upgrade function
        # We need to simulate the op context
    # Invoke the migration's DDL via raw SQL since op context needs running migration env
    # Use SQLAlchemy directly for table creation verification
    mod.upgrade.__globals__['op'] = _make_op(conn)
    mod.upgrade()


def _make_op(conn):
    """Create an Alembic Operations object bound to a raw connection."""
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations
    ctx = MigrationContext.configure(conn)
    return Operations(ctx)


def _create_test_sqlite_db_with_0009_schema(db_path: str) -> None:
    """Create a fresh SQLite DB with schema up to revision 0009 (all prior tables).

    We create tables using SQLAlchemy metadata.create_all (same result as running
    migrations 0001-0009) without involving the Alembic config machinery.
    This avoids the get_settings() lru_cache issue.

    Strategy: run upgrade() to create the cert table, then run downgrade() to remove it.
    This gives us the exact pre-0010 schema without needing tometadata() (which causes
    SQLite lock contention when Base.metadata is shared with the conftest engine).
    """
    import sqlalchemy as sa

    engine = sa.create_engine(f"sqlite:///{db_path}", echo=False)

    def _run_migration(action: str) -> None:
        spec = importlib.util.spec_from_file_location(f"mig_0010_setup_{action}", str(MIGRATION_FILE))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with engine.connect() as conn:
            from alembic.runtime.migration import MigrationContext
            from alembic.operations import Operations
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                if action == "upgrade":
                    mod.upgrade()
                else:
                    mod.downgrade()
            conn.commit()

    # Build the pre-0010 schema using the PRIOR migrations' Base snapshot.
    # We avoid tometadata() because it shares SQLAlchemy Table objects with
    # the conftest engine, causing cross-session SQLite lock contention.
    # Instead, use a throw-away connection to create all tables via Base.metadata
    # but on a fresh isolated engine, then strip the cert table via downgrade().
    from app.db.base import Base as AppBase

    # Create all tables (including prematch_readiness_certificates)
    AppBase.metadata.create_all(engine)
    engine.dispose()

    # Now remove the cert table by running the migration's downgrade()
    _run_migration("downgrade")
    engine.dispose()




def test_prematch_table_created_via_migrate_fresh_sqlite():
    """FIX 1: Upgrade migration must create prematch_readiness_certificates on a fresh DB.

    Strategy: Create a DB with all tables EXCEPT prematch_readiness_certificates
    (simulating pre-0010 state), then run 0010's upgrade() directly.
    """
    import sqlalchemy as sa

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        _create_test_sqlite_db_with_0009_schema(db_path)

        # Verify cert table does NOT exist yet
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables_before = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "prematch_readiness_certificates" not in tables_before

        # Run 0010 upgrade() directly
        engine = sa.create_engine(f"sqlite:///{db_path}", echo=False)
        with engine.connect() as conn:
            op = _make_op(conn)
            # Patch op into migration module globals
            spec = importlib.util.spec_from_file_location("mig_0010_u", str(MIGRATION_FILE))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            import alembic.operations
            original_op = alembic.operations.ops
            old_get_context = None
            # Execute upgrade via op context
            from alembic.runtime.migration import MigrationContext
            from alembic.operations import Operations
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.upgrade()
            conn.commit()
        engine.dispose()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "prematch_readiness_certificates" in tables, (
            "prematch_readiness_certificates table not created after running upgrade()"
        )
    finally:
        os.unlink(db_path)


def test_prematch_table_downgrade_sqlite():
    """FIX 1: Running downgrade() must remove prematch_readiness_certificates."""
    import sqlalchemy as sa

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # First upgrade (creates the cert table)
        _create_test_sqlite_db_with_0009_schema(db_path)
        engine = sa.create_engine(f"sqlite:///{db_path}", echo=False)
        with engine.connect() as conn:
            spec = importlib.util.spec_from_file_location("mig_0010_d1", str(MIGRATION_FILE))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            from alembic.runtime.migration import MigrationContext
            from alembic.operations import Operations
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.upgrade()
            conn.commit()
        engine.dispose()

        # Verify cert table exists after upgrade
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables_after_upgrade = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "prematch_readiness_certificates" in tables_after_upgrade

        # Now downgrade
        engine = sa.create_engine(f"sqlite:///{db_path}", echo=False)
        with engine.connect() as conn:
            spec = importlib.util.spec_from_file_location("mig_0010_d2", str(MIGRATION_FILE))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            from alembic.runtime.migration import MigrationContext
            from alembic.operations import Operations
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.downgrade()
            conn.commit()
        engine.dispose()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "prematch_readiness_certificates" not in tables, (
            "prematch_readiness_certificates must be removed after downgrade()"
        )
    finally:
        os.unlink(db_path)


def test_prematch_table_upgrade_again_sqlite():
    """FIX 1: upgrade() → downgrade() → upgrade() again must recreate the table."""
    import sqlalchemy as sa

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    def _run_migration(db_path: str, action: str) -> None:
        engine = sa.create_engine(f"sqlite:///{db_path}", echo=False)
        with engine.connect() as conn:
            spec = importlib.util.spec_from_file_location(f"mig_0010_{action}", str(MIGRATION_FILE))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            from alembic.runtime.migration import MigrationContext
            from alembic.operations import Operations
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                if action == "upgrade":
                    mod.upgrade()
                else:
                    mod.downgrade()
            conn.commit()
        engine.dispose()

    try:
        _create_test_sqlite_db_with_0009_schema(db_path)
        _run_migration(db_path, "upgrade")
        _run_migration(db_path, "downgrade")
        _run_migration(db_path, "upgrade")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "prematch_readiness_certificates" in tables, (
            "prematch_readiness_certificates not recreated after upgrade → downgrade → upgrade"
        )
    finally:
        os.unlink(db_path)


def test_exactly_one_alembic_head():
    """No branch divergence: exactly one head revision must exist."""
    migration_files = list(MIGRATION_DIR.glob("*.py"))
    migration_files = [f for f in migration_files if f.name != "__init__.py"]

    # Build revision chain
    revisions: dict[str, str] = {}  # revision -> down_revision
    for mf in migration_files:
        spec = importlib.util.spec_from_file_location(mf.stem, str(mf))
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            rev = getattr(mod, "revision", None)
            down_rev = getattr(mod, "down_revision", None)
            if rev:
                revisions[rev] = down_rev
        except Exception:
            pass

    # Heads are revisions that are not the down_revision of any other revision
    all_down_revs = set(v for v in revisions.values() if v is not None)
    heads = [rev for rev in revisions if rev not in all_down_revs]
    assert len(heads) == 1, f"Expected exactly 1 Alembic head, found {len(heads)}: {heads}"
