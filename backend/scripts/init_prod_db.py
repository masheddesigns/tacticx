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
    logger.info("Checking database initialization...")
    from app.db.session import get_engine, get_session_local
    from app.config import get_settings
    
    settings = get_settings()
    engine = get_engine()
    
    # 1. Run Alembic migrations to head
    try:
        import alembic.config
        logger.info("Running Alembic migrations to head...")
        cur_dir = os.getcwd()
        if os.path.exists("alembic.ini"):
            alembic.config.main(argv=["--raiseerr", "upgrade", "head"])
        elif os.path.exists("backend/alembic.ini"):
            os.chdir("backend")
            alembic.config.main(argv=["--raiseerr", "upgrade", "head"])
            os.chdir(cur_dir)
        logger.info("Alembic migrations completed successfully.")
    except Exception as e:
        logger.error(f"Alembic migration error: {e}")
        try:
            from app.db.base import Base
            Base.metadata.create_all(bind=engine)
            logger.info("Base.metadata.create_all completed.")
        except Exception as ex:
            logger.error(f"Fallback create_all failed: {ex}")

    # 2. Check if matches are already seeded
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
                with open(sql_file, "r") as f:
                    sql_content = f.read()
                raw_conn = engine.raw_connection()
                try:
                    cursor = raw_conn.cursor()
                    cursor.execute(sql_content)
                    raw_conn.commit()
                    cursor.close()
                    logger.info("Production database seeded successfully.")
                finally:
                    raw_conn.close()
            else:
                logger.warning("seed_production.sql file not found.")
    except Exception as e:
        logger.error(f"Seeding check failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
