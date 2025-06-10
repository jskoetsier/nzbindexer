#!/usr/bin/env python
"""
Script to reset article IDs for groups to enable processing
"""

import asyncio
import logging
import os
import sys
from typing import List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application modules
from app.db.session import AsyncSessionLocal
from app.db.models.group import Group
from app.services.nntp import NNTPService
from app.services.setting import get_app_settings
from sqlalchemy import select


async def reset_group(db, group: Group, nntp_service: NNTPService) -> bool:
    """Reset article IDs for a group"""
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
        backfill_amount = min(1000, (last - first) // 2)
        backfill_target = max(first, last - backfill_amount)

        # Update group's article IDs
        old_first = group.first_article_id
        old_last = group.last_article_id
        old_current = group.current_article_id
        old_backfill = group.backfill_target

        group.first_article_id = first
        group.last_article_id = last
        group.current_article_id = last  # Set current to last to start from the most recent
        group.backfill_target = backfill_target

        # Save changes
        db.add(group)
        await db.commit()

        logger.info(f"Updated group {group.name}:")
        logger.info(f"  First: {old_first} -> {first}")
        logger.info(f"  Last: {old_last} -> {last}")
        logger.info(f"  Current: {old_current} -> {last}")
        logger.info(f"  Backfill Target: {old_backfill} -> {backfill_target}")

        return True
    except Exception as e:
        logger.error(f"Error resetting group {group.name}: {str(e)}")
        return False


async def reset_all_groups(group_ids: Optional[List[int]] = None):
    """Reset article IDs for all groups or specific groups"""
    async with AsyncSessionLocal() as db:
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
        if group_ids:
            query = select(Group).filter(Group.id.in_(group_ids))
        else:
            query = select(Group).filter(Group.active == True)

        result = await db.execute(query)
        groups = result.scalars().all()

        logger.info(f"Found {len(groups)} groups to reset")

        # Reset each group
        success_count = 0
        for group in groups:
            if await reset_group(db, group, nntp_service):
                success_count += 1

        logger.info(f"Successfully reset {success_count} of {len(groups)} groups")


if __name__ == "__main__":
    # Parse command line arguments
    import argparse

    parser = argparse.ArgumentParser(description="Reset article IDs for groups")
    parser.add_argument(
        "--group-ids",
        type=int,
        nargs="+",
        help="IDs of groups to reset (default: all active groups)"
    )

    args = parser.parse_args()

    # Run the script
    asyncio.run(reset_all_groups(args.group_ids))
    print("Group article IDs reset complete!")
