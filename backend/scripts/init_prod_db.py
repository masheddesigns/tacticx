"""Automatic production database initialization & migration runner.
Executes safely on container startup before Uvicorn starts.
"""
import os
import sys
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_prod_db")

def main():
    logger.info("Starting production database initialization...")
    from app.db.session import get_engine, get_session_local
    from app.config import get_settings
    
    settings = get_settings()
    engine = get_engine()
    
    # 1. Run Alembic migrations programmatically
    try:
        from alembic import command
        from alembic.config import Config
        logger.info("Running Alembic migrations to head...")
        
        cfg_path = "alembic.ini"
        if not os.path.exists(cfg_path) and os.path.exists("backend/alembic.ini"):
            cfg_path = "backend/alembic.ini"
            
        cfg = Config(cfg_path)
        command.upgrade(cfg, "head")
        logger.info("Alembic migrations completed successfully.")
    except Exception as e:
        logger.error(f"Alembic migration error (falling back to Base.metadata): {e}")
        try:
            from app.db.base import Base
            Base.metadata.create_all(bind=engine)
            logger.info("Base.metadata.create_all completed.")
        except Exception as ex:
            logger.error(f"Fallback create_all failed: {ex}")

    # 2. Check and seed database if empty
    Session = get_session_local()
    db = Session()
    try:
        match_count = db.execute(text("SELECT count(*) FROM matches")).scalar()
        logger.info(f"Existing match count in DB: {match_count}")
        if match_count == 0 or match_count is None:
            logger.info("Seeding production database from seed_production.sql...")
            sql_file = None
            for candidate in [
                "scripts/seed_production.sql",
                "backend/scripts/seed_production.sql",
                "/app/scripts/seed_production.sql"
            ]:
                if os.path.exists(candidate):
                    sql_file = candidate
                    break
            
            if sql_file:
                logger.info(f"Reading seed file: {sql_file}")
                with open(sql_file, "r") as f:
                    statements = [line.strip() for line in f if line.strip().startswith("INSERT INTO")]
                
                raw_conn = engine.raw_connection()
                try:
                    cursor = raw_conn.cursor()
                    success_count = 0
                    for stmt in statements:
                        try:
                            # Strip 'public.' if sqlite
                            if engine.dialect.name == "sqlite":
                                stmt = stmt.replace("public.", "")
                            cursor.execute(stmt)
                            success_count += 1
                        except Exception as insert_err:
                            pass
                    raw_conn.commit()
                    cursor.close()
                    logger.info(f"Successfully seeded {success_count} records into production database.")
                finally:
                    raw_conn.close()
            else:
                logger.warning("seed_production.sql not found.")
        else:
            logger.info("Database already contains matches. Skipping initial seed.")
            
        # 3. Ensure full October 2026 fixtures across Top 5 leagues and UCL are seeded
        try:
            try:
                from scripts.seed_full_october_fixtures import seed_all_fixtures
            except ImportError:
                from backend.scripts.seed_full_october_fixtures import seed_all_fixtures
            logger.info("Running seed_full_october_fixtures for Top 5 European leagues & UCL...")
            seed_all_fixtures()
            logger.info("seed_full_october_fixtures finished successfully.")
        except Exception as seed_err:
            logger.error(f"Error running seed_full_october_fixtures: {seed_err}")
    except Exception as e:
        logger.error(f"Seeding check failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
