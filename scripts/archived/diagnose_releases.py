#!/usr/bin/env python
"""
Script to diagnose issues with releases and help fix them
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
logger = logging.getLogger("diagnose")

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
from sqlalchemy import select, func


async def diagnose_groups(db):
    """Diagnose issues with groups"""
    logger.info("=" * 80)
    logger.info("Diagnosing groups...")

    # Get all groups
    query = select(Group)
    result = await db.execute(query)
    groups = result.scalars().all()

    logger.info(f"Found {len(groups)} groups in the database")

    # Check active groups
    active_groups = [g for g in groups if g.active]
    logger.info(f"Active groups: {len(active_groups)}")

    for group in active_groups:
        logger.info(f"  - {group.name} (ID: {group.id})")
        logger.info(f"    First: {group.first_article_id}, Last: {group.last_article_id}, Current: {group.current_article_id}")
        logger.info(f"    Min Files: {group.min_files}, Min Size: {group.min_size}")
        logger.info(f"    Backfill: {group.backfill}, Backfill Target: {group.backfill_target}")
        logger.info(f"    Last Updated: {group.last_updated}")

        # Check if group has articles to process
        if group.last_article_id <= group.current_article_id:
            logger.warning(f"    WARNING: Group has no new articles to process (last_article_id <= current_article_id)")

        # Check if backfill target is valid
        if group.backfill and group.backfill_target >= group.current_article_id:
            logger.warning(f"    WARNING: Backfill target ({group.backfill_target}) is greater than or equal to current_article_id ({group.current_article_id})")


async def diagnose_releases(db):
    """Diagnose issues with releases"""
    logger.info("=" * 80)
    logger.info("Diagnosing releases...")

    # Check if there are any releases
    query = select(Release)
    result = await db.execute(query)
    releases = result.scalars().all()

    logger.info(f"Found {len(releases)} releases in the database")

    # Check active releases
    active_releases = [r for r in releases if r.status == 1]
    logger.info(f"Active releases: {len(active_releases)}")

    # Check releases by category
    query = select(Category.name, func.count(Release.id)).outerjoin(Release, Release.category_id == Category.id).group_by(Category.name)
    result = await db.execute(query)
    category_counts = result.all()

    if category_counts:
        logger.info("Releases by category:")
        for category_name, count in category_counts:
            logger.info(f"  - {category_name}: {count}")
    else:
        logger.info("No releases found in any category")


async def diagnose_nntp_connection(db):
    """Diagnose issues with NNTP connection"""
    logger.info("=" * 80)
    logger.info("Diagnosing NNTP connection...")

    # Get app settings
    app_settings = await get_app_settings(db)

    # Log NNTP settings
    logger.info(f"NNTP Server: {app_settings.nntp_server}")
    logger.info(f"NNTP Port: {app_settings.nntp_port} (SSL: {app_settings.nntp_ssl}, SSL Port: {app_settings.nntp_ssl_port})")
    logger.info(f"NNTP Username: {'Set' if app_settings.nntp_username else 'Not set'}")
    logger.info(f"NNTP Password: {'Set' if app_settings.nntp_password else 'Not set'}")

    # Test NNTP connection
    try:
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

        conn = nntp_service.connect()
        logger.info("NNTP connection successful!")

        # Get server capabilities
        resp, caps = conn.capabilities()
        capabilities = {}
        for cap_line in caps:
            cap_line = cap_line.decode() if isinstance(cap_line, bytes) else cap_line
            parts = cap_line.split()
            if parts:
                capabilities[parts[0]] = parts[1:] if len(parts) > 1 else []

        logger.info(f"Server capabilities: {capabilities}")

        # Test article retrieval for an active group
        query = select(Group).filter(Group.active == True)
        result = await db.execute(query)
        active_groups = result.scalars().all()

        if active_groups:
            group = active_groups[0]
            logger.info(f"Testing article retrieval for group: {group.name}")

            resp, count, first, last, name = conn.group(group.name)
            logger.info(f"Group info: {count} articles, {first}-{last}")

            # Get a sample of articles
            sample_size = 10
            sample_start = max(first, last - sample_size)
            logger.info(f"Getting sample of {sample_size} articles from {sample_start} to {last}")

            try:
                resp, articles = conn.over((sample_start, last))
                logger.info(f"Retrieved {len(articles)} articles")
            except Exception as e:
                logger.error(f"Error testing article retrieval: {str(e)}")

        conn.quit()
    except Exception as e:
        logger.error(f"NNTP connection failed: {str(e)}")


async def diagnose_article_processing(db):
    """Diagnose issues with article processing"""
    logger.info("=" * 80)
    logger.info("Diagnosing article processing...")

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

    # Get active groups
    query = select(Group).filter(Group.active == True)
    result = await db.execute(query)
    active_groups = result.scalars().all()

    if active_groups:
        # Test article processing for the first active group
        group = active_groups[0]
        logger.info(f"Testing article processing for group: {group.name}")

        # Connect to NNTP server
        conn = nntp_service.connect()
        resp, count, first, last, name = conn.group(group.name)
        logger.info(f"Group info: {count} articles, {first}-{last}")

        # Process a sample of articles
        article_service = ArticleService(nntp_service=nntp_service)

        # Process articles from first to last
        stats = await article_service.process_articles(
            db, group, first, last, limit=100
        )

        logger.info(f"Article processing stats: {stats}")

        if stats["binaries"] == 0:
            logger.warning("WARNING: No binaries were found in the processed articles.")
            logger.warning("This could be why no releases are being created.")

        if stats["releases"] == 0:
            logger.warning("WARNING: No releases were created from the processed articles.")


async def main():
    """Main function"""
    logger.info("Starting diagnostics...")

    async with AsyncSessionLocal() as db:
        await diagnose_groups(db)
        await diagnose_releases(db)
        await diagnose_nntp_connection(db)
        await diagnose_article_processing(db)

    logger.info("=" * 80)
    logger.info("Diagnostics complete. Check the log file for details.")


if __name__ == "__main__":
    asyncio.run(main())
