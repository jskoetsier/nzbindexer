#!/usr/bin/env python
"""
Script to fix article processing issues and create releases
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
logger = logging.getLogger("fix_article")

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


async def reset_group_article_ids(db, group_id: Optional[int] = None):
    """Reset article IDs for a group or all groups"""
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

    # Get groups
    if group_id:
        query = select(Group).filter(Group.id == group_id)
    else:
        query = select(Group).filter(Group.active == True)

    result = await db.execute(query)
    groups = result.scalars().all()

    logger.info(f"Resetting article IDs for {len(groups)} groups")

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


async def process_group_articles(db, group_id: int, limit: int = 100):
    """Process articles for a specific group"""
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
    query = select(Group).filter(Group.id == group_id)
    result = await db.execute(query)
    group = result.scalars().first()

    if not group:
        logger.error(f"Group with ID {group_id} not found")
        return

    logger.info(f"Processing articles for group: {group.name}")

    # Create article service
    article_service = ArticleService(nntp_service=nntp_service)

    # Process articles
    stats = await article_service.process_articles(
        db, group, group.current_article_id, group.last_article_id, limit
    )

    logger.info(f"Article processing stats: {stats}")

    # Update group's current_article_id if articles were processed
    if stats["processed"] > 0:
        group.current_article_id = min(group.last_article_id, group.current_article_id + stats["processed"])
        group.last_updated = datetime.utcnow()
        db.add(group)
        await db.commit()
        logger.info(f"Updated group {group.name} current_article_id to {group.current_article_id}")


async def fix_article_processing():
    """Fix article processing issues"""
    async with AsyncSessionLocal() as db:
        # Reset article IDs for all groups
        await reset_group_article_ids(db)

        # Get binary groups that are most likely to contain binary posts
        binary_groups = [
            "alt.binaries.movies",
            "alt.binaries.tv",
            "alt.binaries.hdtv",
            "alt.binaries.teevee",
            "alt.binaries.moovee",
        ]

        # Process articles for each binary group
        for group_name in binary_groups:
            query = select(Group).filter(Group.name == group_name)
            result = await db.execute(query)
            group = result.scalars().first()

            if group:
                logger.info(f"Processing articles for binary group: {group.name}")
                await process_group_articles(db, group.id, limit=500)
            else:
                logger.warning(f"Binary group {group_name} not found in database")


if __name__ == "__main__":
    # Add missing import
    from datetime import datetime

    # Run the script
    asyncio.run(fix_article_processing())
    print("Article processing fixes applied!")
