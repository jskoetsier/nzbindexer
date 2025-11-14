#!/usr/bin/env python3
"""
Add backfill_days column to group table
This migration adds the backfill_days column for day-based backfill configuration
"""

import asyncio
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_database():
    """Add backfill_days column to group table"""
    # Get DATABASE_URL from environment
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL environment variable not set!")
        logger.info(
            "Example: export DATABASE_URL='postgresql+asyncpg://user:pass@localhost/dbname'"
        )
        return False

    # Ensure we're using asyncpg for PostgreSQL
    if "postgresql://" in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    logger.info(f"Connecting to database: {db_url.split('@')[1]}")  # Hide password

    # Create async engine
    engine = create_async_engine(db_url, echo=False)

    try:
        async with engine.begin() as conn:
            # Check if column already exists
            logger.info("Checking if backfill_days column exists...")
            result = await conn.execute(
                text(
                    """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'group' AND column_name = 'backfill_days'
            """
                )
            )
            existing = result.fetchone()

            if existing:
                logger.info("backfill_days column already exists, skipping migration")
                return True

            # Add backfill_days column
            logger.info("Adding backfill_days column to group table...")
            await conn.execute(
                text(
                    """
                ALTER TABLE "group"
                ADD COLUMN backfill_days INTEGER NOT NULL DEFAULT 0
            """
                )
            )

            logger.info("✓ Successfully added backfill_days column!")
            logger.info(
                "Groups will now use backfill_days (0 = use global setting) instead of fixed article counts"
            )

            return True

    except Exception as e:
        logger.error(f"Error during migration: {str(e)}")
        return False
    finally:
        await engine.dispose()


async def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("NZB Indexer - Add backfill_days Column Migration")
    logger.info("=" * 60)

    success = await migrate_database()

    if success:
        logger.info("\n" + "=" * 60)
        logger.info("Migration completed successfully!")
        logger.info("=" * 60)
        logger.info("\nNext steps:")
        logger.info("1. Restart the application to use the new backfill_days feature")
        logger.info(
            "2. Edit groups in the admin UI to set backfill days (0 = use global setting)"
        )
        logger.info("3. The backfill target will be auto-calculated from backfill days")
        sys.exit(0)
    else:
        logger.error("\nMigration failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
