#!/usr/bin/env python
"""
Comprehensive fix for NZB Indexer issues
This script addresses multiple potential issues with binary processing and NZB generation
"""

import asyncio
import logging
import os
import sys
import re
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG for maximum information
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("comprehensive_fix")

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


async def optimize_database(db):
    """Optimize the SQLite database to reduce locking issues"""
    try:
        # Execute PRAGMA statements to optimize SQLite for concurrent access
        await db.execute(text("PRAGMA journal_mode = WAL"))
        await db.execute(text("PRAGMA synchronous = NORMAL"))
        await db.execute(text("PRAGMA temp_store = MEMORY"))
        await db.execute(text("PRAGMA cache_size = 10000"))

        # Vacuum the database to reclaim space and optimize
        await db.execute(text("VACUUM"))

        # Analyze the database to optimize query planning
        await db.execute(text("ANALYZE"))

        logger.info("Applied SQLite optimizations to reduce database locking")

        # Commit the changes
        await db.commit()
        return True
    except Exception as e:
        logger.error(f"Error optimizing database: {str(e)}")
        await db.rollback()
        return False


async def reset_group_article_ids(db, nntp_service):
    """Reset article IDs for all groups"""
    # Get all active groups
    query = select(Group).filter(Group.active == True)
    result = await db.execute(query)
    groups = result.scalars().all()

    logger.info(f"Resetting article IDs for {len(groups)} active groups")

    # Reset each group
    for group in groups:
        try:
            # Connect to NNTP server
            conn = nntp_service.connect()

            # Select the group
            resp, count, first, last, name = conn.group(group.name)

            # Close connection
            conn.quit()

            # Handle both string and bytes for name
            name_str = name if isinstance(name, str) else name.decode()

            logger.info(f"Group {name_str}: {count} articles, {first}-{last}")

            # Calculate a reasonable backfill target (e.g., 1000 articles back from last)
            backfill_amount = min(10000, (last - first) // 2)
            backfill_target = max(first, last - backfill_amount)

            # Update group's article IDs
            old_first = group.first_article_id
            old_last = group.last_article_id
            old_current = group.current_article_id
            old_backfill = group.backfill_target

            # Set current_article_id to a value less than last_article_id
            # This ensures there are articles to process
            current_article_id = last - 1000  # Set current to 1000 articles before last

            group.first_article_id = first
            group.last_article_id = last
            group.current_article_id = current_article_id
            group.backfill_target = backfill_target

            # Save changes
            db.add(group)
            await db.commit()

            logger.info(f"Updated group {group.name}:")
            logger.info(f"  First: {old_first} -> {first}")
            logger.info(f"  Last: {old_last} -> {last}")
            logger.info(f"  Current: {old_current} -> {current_article_id}")
            logger.info(f"  Backfill Target: {old_backfill} -> {backfill_target}")

        except Exception as e:
            logger.error(f"Error resetting group {group.name}: {str(e)}")
            await db.rollback()


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
            return True
        except Exception as e:
            logger.error(f"NZB directory is not writable: {str(e)}")
            return False
    except Exception as e:
        logger.error(f"Error checking NZB directory: {str(e)}")
        return False


async def process_binary_group(db, group_name, nntp_service, limit=100):
    """Process articles from a binary group to create releases"""
    # Get group
    query = select(Group).filter(Group.name == group_name)
    result = await db.execute(query)
    group = result.scalars().first()

    if not group:
        logger.error(f"Group {group_name} not found")
        return False

    logger.info(f"Processing articles from group: {group.name}")

    # Create article service
    article_service = ArticleService(nntp_service=nntp_service)

    # Process articles
    try:
        # Connect to NNTP server
        conn = nntp_service.connect()

        # Select the group
        resp, count, first, last, name = conn.group(group.name)

        # Close connection
        conn.quit()

        # Calculate range to process
        process_start = last - limit
        process_end = last

        logger.info(f"Processing articles {process_start} to {process_end} for group {group.name}")

        # Process articles
        stats = await article_service.process_articles(
            db, group, process_start, process_end, limit
        )

        logger.info(f"Article processing stats: {stats}")

        # Update group's current_article_id
        if stats["processed"] > 0:
            group.current_article_id = process_end
            group.last_updated = datetime.utcnow()
            db.add(group)
            await db.commit()
            logger.info(f"Updated group {group.name} current_article_id to {process_end}")

        return stats["releases"] > 0

    except Exception as e:
        logger.error(f"Error processing group {group.name}: {str(e)}")
        return False


async def check_releases(db):
    """Check if there are any releases in the database"""
    try:
        # Count releases
        query = select(func.count(Release.id))
        result = await db.execute(query)
        count = result.scalar()

        logger.info(f"Found {count} releases in the database")

        # Get a sample of releases
        query = select(Release).limit(5)
        result = await db.execute(query)
        releases = result.scalars().all()

        if releases:
            logger.info("Sample releases:")
            for release in releases:
                logger.info(f"  ID: {release.id}, Name: {release.name}, Files: {release.files}, Size: {release.size}")

                # Check if NZB file exists
                nzb_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nzb", f"{release.guid}.nzb")
                if os.path.exists(nzb_path):
                    logger.info(f"  NZB file exists: {nzb_path}")
                else:
                    logger.warning(f"  NZB file does not exist: {nzb_path}")

                    # Try to generate NZB file
                    try:
                        nzb_service = NZBService()
                        nzb_path = await nzb_service.generate_nzb(db, release.id)
                        if nzb_path:
                            logger.info(f"  Generated NZB file: {nzb_path}")
                        else:
                            logger.warning(f"  Failed to generate NZB file")
                    except Exception as e:
                        logger.error(f"  Error generating NZB file: {str(e)}")

        return count > 0

    except Exception as e:
        logger.error(f"Error checking releases: {str(e)}")
        return False


async def check_nzb_service(db):
    """Check the NZB service functionality"""
    try:
        # Get a release
        query = select(Release).limit(1)
        result = await db.execute(query)
        release = result.scalar()

        if not release:
            logger.warning("No releases found to test NZB generation")
            return False

        # Create NZB service
        nzb_service = NZBService()

        # Generate NZB file
        nzb_path = await nzb_service.generate_nzb(db, release.id)

        if nzb_path:
            logger.info(f"Successfully generated NZB file: {nzb_path}")
            return True
        else:
            logger.warning("Failed to generate NZB file")
            return False

    except Exception as e:
        logger.error(f"Error checking NZB service: {str(e)}")
        return False


async def force_process_all_binary_groups(db, nntp_service, limit_per_group=100):
    """Force process all binary groups to create releases"""
    # List of binary groups to process
    binary_groups = [
        "alt.binaries.teevee",
        "alt.binaries.moovee",
        "alt.binaries.movies",
        "alt.binaries.hdtv",
        "alt.binaries.hdtv.x264",
        "alt.binaries.tv",
        "alt.binaries.multimedia",
        "alt.binaries.sounds.mp3",
        "alt.binaries.sounds.lossless",
    ]

    success = False

    # Process each group
    for group_name in binary_groups:
        logger.info(f"Processing binary group: {group_name}")
        result = await process_binary_group(db, group_name, nntp_service, limit_per_group)
        if result:
            success = True
            logger.info(f"Successfully created releases from group {group_name}")
        else:
            logger.warning(f"No releases created from group {group_name}")

    return success


async def comprehensive_fix():
    """Apply all fixes to resolve binary processing and NZB generation issues"""
    logger.info("Starting comprehensive fix")

    async with AsyncSessionLocal() as db:
        # Step 1: Optimize database
        logger.info("Step 1: Optimizing database")
        await optimize_database(db)

        # Step 2: Get app settings
        app_settings = await get_app_settings(db)

        # Step 3: Create NNTP service
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

        # Step 4: Reset group article IDs
        logger.info("Step 4: Resetting group article IDs")
        await reset_group_article_ids(db, nntp_service)

        # Step 5: Check NZB directory
        logger.info("Step 5: Checking NZB directory")
        await check_nzb_directory(db)

        # Step 6: Force process binary groups
        logger.info("Step 6: Processing binary groups")
        success = await force_process_all_binary_groups(db, nntp_service, 200)

        # Step 7: Check releases
        logger.info("Step 7: Checking releases")
        has_releases = await check_releases(db)

        # Step 8: Check NZB service
        if has_releases:
            logger.info("Step 8: Checking NZB service")
            await check_nzb_service(db)

        # Summary
        logger.info("Comprehensive fix complete")
        if success:
            logger.info("Successfully created releases from binary groups")
        else:
            logger.warning("No releases were created from binary groups")

        if has_releases:
            logger.info("Releases exist in the database")
        else:
            logger.warning("No releases found in the database")


if __name__ == "__main__":
    asyncio.run(comprehensive_fix())
    print("Comprehensive fix complete!")
