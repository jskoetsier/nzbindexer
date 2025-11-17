"""
Script to clean up all releases from the database
This should be run before re-backfilling with deobfuscation enabled
"""

import asyncio
import logging
import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.models.release import Release
from app.db.session import AsyncSessionLocal
from sqlalchemy import delete, select

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def clean_releases():
    """Clean up all releases from the database"""
    async with AsyncSessionLocal() as db:
        try:
            # Count existing releases
            query = select(Release)
            result = await db.execute(query)
            releases = result.scalars().all()
            count = len(releases)

            logger.info(f"Found {count} releases in the database")

            if count == 0:
                logger.info("No releases to clean up")
                return

            # Ask for confirmation
            print(f"\nThis will delete ALL {count} releases from the database!")
            confirmation = input("Are you sure you want to continue? (yes/no): ")

            if confirmation.lower() != "yes":
                logger.info("Operation cancelled by user")
                return

            # Delete all releases
            logger.info("Deleting all releases...")
            delete_stmt = delete(Release)
            await db.execute(delete_stmt)
            await db.commit()

            logger.info(f"Successfully deleted {count} releases")

            # Also clean up NZB files
            from app.core.config import settings

            nzb_dir = settings.NZB_DIR

            if os.path.exists(nzb_dir):
                nzb_files = [f for f in os.listdir(nzb_dir) if f.endswith(".nzb")]
                logger.info(f"Found {len(nzb_files)} NZB files to delete")

                for nzb_file in nzb_files:
                    try:
                        os.remove(os.path.join(nzb_dir, nzb_file))
                    except Exception as e:
                        logger.warning(f"Failed to delete {nzb_file}: {str(e)}")

                logger.info("NZB files cleaned up")

        except Exception as e:
            logger.error(f"Error cleaning up releases: {str(e)}")
            await db.rollback()
            raise


if __name__ == "__main__":
    logger.info("Starting release cleanup script")
    asyncio.run(clean_releases())
    logger.info("Release cleanup complete!")
