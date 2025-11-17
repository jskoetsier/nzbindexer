"""
Script to test and debug article processing, deobfuscation, and categorization
"""

import asyncio
import logging
import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.models.group import Group
from app.db.models.release import Release
from app.db.session import AsyncSessionLocal
from app.services.article import ArticleService
from app.services.nntp import NNTPService
from app.services.setting import get_app_settings
from sqlalchemy import select

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_article_processing():
    """Test article processing with debug output"""
    async with AsyncSessionLocal() as db:
        try:
            # Get app settings
            app_settings = await get_app_settings(db)

            # Create NNTP service
            nntp_service = NNTPService(
                server=app_settings.nntp_server,
                port=(
                    app_settings.nntp_ssl_port
                    if app_settings.nntp_ssl
                    else app_settings.nntp_port
                ),
                use_ssl=app_settings.nntp_ssl,
                username=app_settings.nntp_username,
                password=app_settings.nntp_password,
            )

            # Get a backfill group
            query = (
                select(Group)
                .filter(Group.backfill == True, Group.active == True)
                .limit(1)
            )
            result = await db.execute(query)
            group = result.scalars().first()

            if not group:
                logger.error("No backfill groups found!")
                return

            logger.info(f"\nTesting article processing for group: {group.name}")

            # Create article service
            article_service = ArticleService(nntp_service=nntp_service)

            # Process a small batch
            start_id = group.backfill_target
            end_id = start_id + 10  # Just 10 articles for testing

            logger.info(f"Processing articles {start_id} to {end_id}")

            stats = await article_service.process_articles(
                db, group, start_id, end_id, limit=10
            )

            logger.info(f"\nProcessing stats: {stats}")

            # Check recent releases
            query = select(Release).order_by(Release.id.desc()).limit(5)
            result = await db.execute(query)
            releases = result.scalars().all()

            logger.info(f"\nRecent releases:")
            for release in releases:
                logger.info(f"  ID: {release.id}")
                logger.info(f"  Name: {release.name}")
                logger.info(f"  GUID: {release.guid}")
                logger.info(f"  Category ID: {release.category_id}")
                logger.info(f"  Group ID: {release.group_id}")
                logger.info("")

        except Exception as e:
            logger.error(f"Error testing article processing: {str(e)}")
            import traceback

            logger.error(traceback.format_exc())


if __name__ == "__main__":
    logger.info("Starting article processing test")
    asyncio.run(test_article_processing())
    logger.info("Test complete!")
