#!/usr/bin/env python
"""
Script to fix database locking issues and improve article processing
"""

import asyncio
import logging
import os
import sys
from typing import List, Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("fix_db")

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
from sqlalchemy import select, func, update
from datetime import datetime, timedelta


async def fix_database_config(db):
    """Fix database configuration to reduce locking issues"""
    try:
        # Execute PRAGMA statements to optimize SQLite for concurrent access
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA synchronous = NORMAL")
        await db.execute("PRAGMA temp_store = MEMORY")
        await db.execute("PRAGMA mmap_size = 30000000000")
        await db.execute("PRAGMA cache_size = 10000")

        logger.info("Applied SQLite optimizations to reduce database locking")

        # Commit the changes
        await db.commit()
    except Exception as e:
        logger.error(f"Error applying SQLite optimizations: {str(e)}")
        await db.rollback()


async def reset_processing_flags(db):
    """Reset processing flags for groups and releases"""
    try:
        # Reset any stuck processing flags in releases
        result = await db.execute(update(Release).where(Release.processed == True).values(processed=False))
        processed_count = result.rowcount
        logger.info(f"Reset processing flags for {processed_count} releases")

        # Commit the changes
        await db.commit()
    except Exception as e:
        logger.error(f"Error resetting processing flags: {str(e)}")
        await db.rollback()


async def force_process_binary_group(db, group_name: str, limit: int = 1000):
    """Force process a binary group to create releases"""
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

    logger.info(f"Force processing group: {group.name}")

    try:
        # Connect to NNTP server
        conn = nntp_service.connect()

        # Select the group
        resp, count, first, last, name = conn.group(group.name)

        # Close connection
        conn.quit()

        # Calculate a range of articles to process
        # Choose a range that's likely to contain binary posts
        # For most binary groups, recent articles are more likely to be binary posts
        process_end = last
        process_start = max(first, last - limit)

        logger.info(f"Processing articles {process_start} to {process_end} for group {group.name}")

        # Create article service with verbose logging
        article_service = ArticleService(nntp_service=nntp_service)

        # Process articles
        stats = await article_service.process_articles(
            db, group, process_start, process_end, limit
        )

        logger.info(f"Article processing stats: {stats}")

        # Update group's current_article_id
        group.current_article_id = process_end
        group.last_updated = datetime.utcnow()
        db.add(group)
        await db.commit()

        return stats
    except Exception as e:
        logger.error(f"Error processing group {group.name}: {str(e)}")
        await db.rollback()
        return None


async def check_nzb_directory(db):
    """Check and create NZB directory if it doesn't exist"""
    try:
        # Get app settings
        app_settings = await get_app_settings(db)

        # Check if NZB directory exists
        nzb_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nzb")
        if not os.path.exists(nzb_dir):
            os.makedirs(nzb_dir, exist_ok=True)
            logger.info(f"Created NZB directory: {nzb_dir}")
        else:
            logger.info(f"NZB directory exists: {nzb_dir}")

        # Check if the directory is writable
        test_file = os.path.join(nzb_dir, "test.txt")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            logger.info(f"NZB directory is writable")
        except Exception as e:
            logger.error(f"NZB directory is not writable: {str(e)}")
    except Exception as e:
        logger.error(f"Error checking NZB directory: {str(e)}")


async def fix_all_issues():
    """Fix all issues with database locks and article processing"""
    async with AsyncSessionLocal() as db:
        # Fix database configuration
        await fix_database_config(db)

        # Reset processing flags
        await reset_processing_flags(db)

        # Check NZB directory
        await check_nzb_directory(db)

        # Process binary groups that are most likely to contain binary posts
        binary_groups = [
            "alt.binaries.teevee",
            "alt.binaries.moovee",
            "alt.binaries.movies",
            "alt.binaries.hdtv",
            "alt.binaries.hdtv.x264",
            "alt.binaries.tv",
        ]

        for group_name in binary_groups:
            stats = await force_process_binary_group(db, group_name, limit=2000)
            if stats and stats.get("releases", 0) > 0:
                logger.info(f"Successfully created {stats['releases']} releases from group {group_name}")
                # If we've created some releases, we can stop
                break


if __name__ == "__main__":
    # Run the script
    asyncio.run(fix_all_issues())
    print("Database and article processing fixes applied!")
