#!/usr/bin/env python
"""
Diagnostic script to help identify why releases aren't being processed
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("diagnose_releases.log"),
    ],
)
logger = logging.getLogger("diagnose")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application modules
from app.db.session import AsyncSessionLocal
from app.db.models.group import Group
from app.db.models.release import Release
from app.services.nntp import NNTPService
from app.services.article import ArticleService
from app.services.setting import get_app_settings

from sqlalchemy import select


async def diagnose_groups():
    """Check group configuration and status"""
    logger.info("Diagnosing groups...")

    async with AsyncSessionLocal() as db:
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

            # Check if group has a valid article range
            if group.last_article_id <= group.current_article_id:
                logger.warning(f"    WARNING: Group has no new articles to process (last_article_id <= current_article_id)")

            if group.backfill and group.backfill_target >= group.current_article_id:
                logger.warning(f"    WARNING: Group has invalid backfill target (backfill_target >= current_article_id)")


async def diagnose_releases():
    """Check release status"""
    logger.info("Diagnosing releases...")

    async with AsyncSessionLocal() as db:
        # Get all releases
        query = select(Release)
        result = await db.execute(query)
        releases = result.scalars().all()

        logger.info(f"Found {len(releases)} releases in the database")

        # Check active releases
        active_releases = [r for r in releases if r.status == 1]
        logger.info(f"Active releases: {len(active_releases)}")

        # Show some sample releases if available
        if active_releases:
            logger.info("Sample releases:")
            for release in active_releases[:5]:
                logger.info(f"  - {release.name} (ID: {release.id})")
                logger.info(f"    Size: {release.size}, Files: {release.files}")
                logger.info(f"    Category: {release.category_id}, Group: {release.group_id}")
                logger.info(f"    Added: {release.added_date}")


async def diagnose_nntp_connection():
    """Test NNTP connection and article retrieval"""
    logger.info("Diagnosing NNTP connection...")

    async with AsyncSessionLocal() as db:
        # Get app settings
        app_settings = await get_app_settings(db)

        logger.info(f"NNTP Server: {app_settings.nntp_server}")
        logger.info(f"NNTP Port: {app_settings.nntp_port} (SSL: {app_settings.nntp_ssl}, SSL Port: {app_settings.nntp_ssl_port})")
        logger.info(f"NNTP Username: {'Set' if app_settings.nntp_username else 'Not set'}")
        logger.info(f"NNTP Password: {'Set' if app_settings.nntp_password else 'Not set'}")

        # Test connection
        try:
            nntp_service = NNTPService(
                server=app_settings.nntp_server,
                port=(app_settings.nntp_ssl_port if app_settings.nntp_ssl else app_settings.nntp_port),
                use_ssl=app_settings.nntp_ssl,
                username=app_settings.nntp_username,
                password=app_settings.nntp_password,
            )

            conn = nntp_service.connect()
            logger.info("NNTP connection successful!")

            # Get server capabilities
            resp, caps = conn.capabilities()
            logger.info(f"Server capabilities: {caps}")

            # Get active groups
            query = select(Group).filter(Group.active == True)
            result = await db.execute(query)
            active_groups = result.scalars().all()

            if active_groups:
                # Test article retrieval for first active group
                group = active_groups[0]
                logger.info(f"Testing article retrieval for group: {group.name}")

                try:
                    resp, count, first, last, name = conn.group(group.name)
                    logger.info(f"Group info: {count} articles, {first}-{last}")

                    # Get a sample of articles
                    sample_size = 10
                    sample_start = max(first, last - sample_size)
                    logger.info(f"Getting sample of {sample_size} articles from {sample_start} to {last}")

                    resp, articles = conn.over((sample_start, last))
                    logger.info(f"Retrieved {len(articles)} articles")

                    # Check for binary posts
                    article_service = ArticleService(nntp_service=nntp_service)
                    binary_count = 0

                    for article in articles:
                        if len(article) >= 2:
                            article_num = article[0]
                            subject = article[1] if len(article) > 1 else None

                            if subject:
                                subject_str = subject.decode() if isinstance(subject, bytes) else subject
                                binary_name, part_num, total_parts = article_service._parse_binary_subject(subject_str)

                                if binary_name and part_num:
                                    binary_count += 1
                                    logger.info(f"Found binary post: {binary_name} [{part_num}/{total_parts}]")

                    logger.info(f"Found {binary_count} binary posts out of {len(articles)} articles")

                    if binary_count == 0:
                        logger.warning("WARNING: No binary posts found in the sample. This could be why no releases are being created.")
                        logger.warning("The system is looking for subjects with patterns like '[01/10]', '(01/10)', etc.")

                        # Show some sample subjects
                        logger.info("Sample subjects:")
                        for i, article in enumerate(articles[:5]):
                            if len(article) >= 2:
                                subject = article[1] if len(article) > 1 else None
                                if subject:
                                    subject_str = subject.decode() if isinstance(subject, bytes) else subject
                                    logger.info(f"  {i+1}. {subject_str}")

                except Exception as e:
                    logger.error(f"Error testing article retrieval: {str(e)}")

            conn.quit()

        except Exception as e:
            logger.error(f"NNTP connection failed: {str(e)}")


async def diagnose_article_processing():
    """Test article processing for a sample group"""
    logger.info("Diagnosing article processing...")

    async with AsyncSessionLocal() as db:
        # Get app settings
        app_settings = await get_app_settings(db)

        # Get active groups
        query = select(Group).filter(Group.active == True)
        result = await db.execute(query)
        active_groups = result.scalars().all()

        if not active_groups:
            logger.warning("No active groups found")
            return

        # Select a group to test
        group = active_groups[0]
        logger.info(f"Testing article processing for group: {group.name}")

        # Create NNTP service
        nntp_service = NNTPService(
            server=app_settings.nntp_server,
            port=(app_settings.nntp_ssl_port if app_settings.nntp_ssl else app_settings.nntp_port),
            use_ssl=app_settings.nntp_ssl,
            username=app_settings.nntp_username,
            password=app_settings.nntp_password,
        )

        # Create article service
        article_service = ArticleService(nntp_service=nntp_service)

        try:
            # Connect to NNTP server
            conn = nntp_service.connect()

            # Get group info
            resp, count, first, last, name = conn.group(group.name)
            logger.info(f"Group info: {count} articles, {first}-{last}")

            # Process a small batch of articles
            batch_size = 100
            start_id = max(first, last - batch_size)
            end_id = last

            logger.info(f"Processing articles from {start_id} to {end_id}")

            # Process articles
            stats = await article_service.process_articles(db, group, start_id, end_id, batch_size)

            logger.info(f"Article processing stats: {stats}")

            if stats["binaries"] == 0:
                logger.warning("WARNING: No binaries were found in the processed articles.")
                logger.warning("This could be why no releases are being created.")

            if stats["releases"] == 0:
                logger.warning("WARNING: No releases were created from the processed articles.")

                if stats["binaries"] > 0:
                    logger.warning("Binaries were found but no releases were created. This could be because:")
                    logger.warning("1. The binaries are incomplete (not all parts are available)")
                    logger.warning("2. The binaries don't meet the minimum requirements (min_files, min_size)")
                    logger.warning("3. The releases already exist in the database")

            conn.quit()

        except Exception as e:
            logger.error(f"Error testing article processing: {str(e)}")


async def main():
    """Run all diagnostics"""
    logger.info("Starting diagnostics...")
    logger.info("=" * 80)

    await diagnose_groups()
    logger.info("=" * 80)

    await diagnose_releases()
    logger.info("=" * 80)

    await diagnose_nntp_connection()
    logger.info("=" * 80)

    await diagnose_article_processing()
    logger.info("=" * 80)

    logger.info("Diagnostics complete. Check the log file for details.")


if __name__ == "__main__":
    asyncio.run(main())
