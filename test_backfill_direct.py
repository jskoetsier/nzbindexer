#!/usr/bin/env python3
"""
Direct test of backfill processing to diagnose why no releases are being created
"""

import asyncio
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_backfill():
    """Test backfill processing directly"""
    from app.db.session import AsyncSessionLocal
    from app.db.models.group import Group
    from app.services.article import process_group_backfill
    from app.services.setting import get_app_settings
    from app.services.nntp import NNTPService
    from sqlalchemy import select
    
    logger.info("=" * 80)
    logger.info("DIRECT BACKFILL TEST - Diagnosing why no releases are created")
    logger.info("=" * 80)
    
    async with AsyncSessionLocal() as db:
        # Get a backfill group
        query = select(Group).filter(Group.backfill == True, Group.active == True).limit(1)
        result = await db.execute(query)
        group = result.scalars().first()
        
        if not group:
            logger.error("No backfill groups found!")
            return
        
        logger.info(f"\nTesting backfill for group: {group.name}")
        logger.info(f"  current_article_id: {group.current_article_id}")
        logger.info(f"  backfill_target: {group.backfill_target}")
        logger.info(f"  backfill distance: {group.current_article_id - group.backfill_target}")
        
        # Get settings
        app_settings = await get_app_settings(db)
        logger.info(f"\nApp Settings:")
        logger.info(f"  NNTP Server: {app_settings.nntp_server}")
        logger.info(f"  NNTP Port: {app_settings.nntp_port}")
        logger.info(f"  Backfill Days: {app_settings.backfill_days}")
        logger.info(f"  Retention Days: {app_settings.retention_days}")
        
        # Create NNTP service
        logger.info(f"\nCreating NNTP service...")
        nntp_service = NNTPService(
            server=app_settings.nntp_server,
            port=app_settings.nntp_ssl_port if app_settings.nntp_ssl else app_settings.nntp_port,
            use_ssl=app_settings.nntp_ssl,
            username=app_settings.nntp_username,
            password=app_settings.nntp_password,
        )
        
        # Call process_group_backfill with limit of 100 articles for testing
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Calling process_group_backfill with limit=100...")
        logger.info(f"{'=' * 80}\n")
        
        try:
            stats = await process_group_backfill(db, group, limit=100, nntp_service=nntp_service)
            logger.info(f"\n{'=' * 80}")
            logger.info(f"Backfill completed! Stats: {stats}")
            logger.info(f"{'=' * 80}")
        except Exception as e:
            import traceback
            logger.error(f"\n{'=' * 80}")
            logger.error(f"ERROR during backfill: {str(e)}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            logger.error(f"{'=' * 80}")
        
        # Check if releases were created
        from app.db.models.release import Release
        query = select(Release)
        result = await db.execute(query)
        releases = result.scalars().all()
        
        logger.info(f"\nTotal releases in database: {len(releases)}")
        if releases:
            logger.info("Recent releases:")
            for release in releases[:5]:
                logger.info(f"  - {release.name} (files: {release.files}, size: {release.size})")

async def main():
    """Main entry point"""
    await test_backfill()

if __name__ == "__main__":
    asyncio.run(main())
