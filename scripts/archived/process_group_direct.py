#!/usr/bin/env python
"""
Direct group processing script
This script directly processes a group and creates releases from it
"""

import asyncio
import logging
import os
import sys
import re
from typing import Dict, List, Optional, Set, Tuple, Union
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger("process_group")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application modules
from app.db.session import AsyncSessionLocal
from app.db.models.group import Group
from app.db.models.release import Release
from app.db.models.category import Category
from app.services.nntp import NNTPService
from app.services.setting import get_app_settings
from app.services.article import ArticleService
from app.services.nzb import NZBService
from sqlalchemy import select, update, func, text


async def process_group_direct(group_name: str, limit: int = 50):
    """Process a group directly"""
    logger.info(f"Processing group {group_name} directly")

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

            # Get group
            query = select(Group).filter(Group.name == group_name)
            result = await db.execute(query)
            group = result.scalars().first()

            if not group:
                logger.error(f"Group {group_name} not found")
                return

            # Create article service
            article_service = ArticleService(nntp_service=nntp_service)

            # Connect to NNTP server
            conn = nntp_service.connect()

            # Select the group
            resp, count, first, last, name = conn.group(group.name)
            # Handle both string and bytes for name
            name_str = name if isinstance(name, str) else name.decode()
            logger.info(f"Selected group {name_str}: {count} articles, {first}-{last}")

            # Close connection
            conn.quit()

            # Calculate range to process - use the most recent articles
            process_start = last - limit
            process_end = last

            logger.info(f"Processing articles {process_start} to {process_end} for group {group.name}")

            # Process articles
            stats = await article_service.process_articles(
                db, group, process_start, process_end, limit
            )

            logger.info(f"Article processing stats: {stats}")

            # Check if any releases were created
            query = select(func.count(Release.id))
            result = await db.execute(query)
            release_count = result.scalar()

            logger.info(f"Total releases in database: {release_count}")

            # Get a sample of releases
            query = select(Release).limit(5)
            result = await db.execute(query)
            releases = result.scalars().all()

            if releases:
                logger.info("Sample releases:")
                for release in releases:
                    logger.info(f"  ID: {release.id}, Name: {release.name}, Files: {release.files}, Size: {release.size}")

                    # Check if NZB file exists
                    if release.nzb_guid:
                        nzb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nzb", f"{release.nzb_guid}.nzb")
                        if os.path.exists(nzb_path):
                            logger.info(f"  NZB file exists: {nzb_path}")
                        else:
                            logger.warning(f"  NZB file does not exist: {nzb_path}")
                    else:
                        logger.warning(f"  Release {release.id} has no NZB GUID")
            else:
                logger.info("No releases found in database")

            return stats

        except Exception as e:
            logger.error(f"Error processing group {group_name}: {str(e)}")
            await db.rollback()
            return None


async def main():
    """Main function"""
    # List of binary groups to test
    binary_groups = [
        "alt.binaries.teevee",
        "alt.binaries.moovee",
        "alt.binaries.movies",
        "alt.binaries.hdtv",
        "alt.binaries.hdtv.x264",
        "alt.binaries.tv",
        "alt.binaries.multimedia",
    ]

    # Process each group
    for group_name in binary_groups:
        await process_group_direct(group_name, 50)
        print("\n" + "-" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
    print("Group processing complete!")
