"""
Background task manager for NZB Indexer
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from app.core.config import settings
from app.db.models.group import Group
from app.db.session import AsyncSessionLocal
from app.services.nntp import NNTPService
from app.services.setting import get_app_settings

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Global variables to track background tasks
running_tasks: Dict[str, asyncio.Task] = {}
active_groups: Set[int] = set()


async def get_active_groups(db: AsyncSession) -> List[Group]:
    """
    Get all active groups from the database
    """
    query = select(Group).filter(Group.active == True)
    result = await db.execute(query)
    return result.scalars().all()


async def update_group(group_id: int) -> None:
    """
    Update a group with new articles
    """
    # Add group to active groups
    active_groups.add(group_id)

    try:
        async with AsyncSessionLocal() as db:
            # Get group from database
            query = select(Group).filter(Group.id == group_id)
            result = await db.execute(query)
            group = result.scalars().first()

            if not group:
                logger.error(f"Group with ID {group_id} not found")
                return

            # Get app settings
            app_settings = await get_app_settings(db)

            # Create NNTP service
            nntp_service = NNTPService()

            # Get group info from NNTP server
            try:
                group_info = nntp_service.get_group_info(group.name)

                # Update group with new info
                group.last_article_id = group_info["last"]
                group.last_updated = datetime.utcnow()

                # If current_article_id is 0, set it to first_article_id
                if group.current_article_id == 0:
                    group.current_article_id = group_info["first"]

                # Save changes
                db.add(group)
                await db.commit()

                logger.info(f"Updated group {group.name}: {group_info}")

                # TODO: Process new articles
                # This would involve fetching articles between current_article_id and last_article_id
                # and processing them into releases

            except Exception as e:
                logger.error(f"Error updating group {group.name}: {str(e)}")

    except Exception as e:
        logger.error(f"Error in update_group task for group {group_id}: {str(e)}")

    finally:
        # Remove group from active groups
        active_groups.discard(group_id)


async def backfill_group(group_id: int) -> None:
    """
    Backfill a group with old articles
    """
    # Add group to active groups
    active_groups.add(group_id)

    try:
        async with AsyncSessionLocal() as db:
            # Get group from database
            query = select(Group).filter(Group.id == group_id)
            result = await db.execute(query)
            group = result.scalars().first()

            if not group:
                logger.error(f"Group with ID {group_id} not found")
                return

            # Check if backfill is enabled
            if not group.backfill:
                logger.info(f"Backfill disabled for group {group.name}")
                return

            # Get app settings
            app_settings = await get_app_settings(db)

            # Create NNTP service
            nntp_service = NNTPService()

            # Get group info from NNTP server
            try:
                group_info = nntp_service.get_group_info(group.name)

                # Calculate backfill target if not set
                if group.backfill_target == 0:
                    # Calculate target based on backfill days
                    # This is a simplified calculation and might need adjustment
                    articles_per_day = (
                        group_info["last"] - group_info["first"]
                    ) / app_settings.retention_days
                    target_articles = int(articles_per_day * app_settings.backfill_days)
                    group.backfill_target = max(
                        group_info["first"], group_info["last"] - target_articles
                    )

                # Update group with new info
                group.last_updated = datetime.utcnow()

                # Save changes
                db.add(group)
                await db.commit()

                logger.info(
                    f"Backfilling group {group.name} to target {group.backfill_target}"
                )

                # TODO: Process backfill articles
                # This would involve fetching articles between backfill_target and current_article_id
                # and processing them into releases

            except Exception as e:
                logger.error(f"Error backfilling group {group.name}: {str(e)}")

    except Exception as e:
        logger.error(f"Error in backfill_group task for group {group_id}: {str(e)}")

    finally:
        # Remove group from active groups
        active_groups.discard(group_id)


async def update_groups_task() -> None:
    """
    Background task to update all active groups
    """
    logger.info("Starting update_groups_task")

    while True:
        try:
            # Get app settings
            async with AsyncSessionLocal() as db:
                app_settings = await get_app_settings(db)
                active_groups_list = await get_active_groups(db)

            # Create a semaphore to limit concurrent updates
            semaphore = asyncio.Semaphore(app_settings.update_threads)

            async def update_with_semaphore(group: Group) -> None:
                """Update a group with semaphore to limit concurrency"""
                async with semaphore:
                    # Skip groups that are already being processed
                    if group.id in active_groups:
                        logger.debug(
                            f"Skipping group {group.name} (already being processed)"
                        )
                        return

                    await update_group(group.id)

            # Update all active groups
            update_tasks = [
                update_with_semaphore(group) for group in active_groups_list
            ]
            await asyncio.gather(*update_tasks)

            # Sleep for a while before checking again
            await asyncio.sleep(60)  # Check every minute

        except Exception as e:
            logger.error(f"Error in update_groups_task: {str(e)}")
            await asyncio.sleep(60)  # Sleep and try again


async def backfill_groups_task() -> None:
    """
    Background task to backfill groups
    """
    logger.info("Starting backfill_groups_task")

    while True:
        try:
            # Get app settings
            async with AsyncSessionLocal() as db:
                app_settings = await get_app_settings(db)

                # Get backfill groups
                query = select(Group).filter(
                    Group.active == True, Group.backfill == True
                )
                result = await db.execute(query)
                backfill_groups = result.scalars().all()

            # Create a semaphore to limit concurrent backfills
            semaphore = asyncio.Semaphore(max(1, app_settings.update_threads // 2))

            async def backfill_with_semaphore(group: Group) -> None:
                """Backfill a group with semaphore to limit concurrency"""
                async with semaphore:
                    # Skip groups that are already being processed
                    if group.id in active_groups:
                        logger.debug(
                            f"Skipping backfill for group {group.name} (already being processed)"
                        )
                        return

                    await backfill_group(group.id)

            # Backfill all groups
            backfill_tasks = [
                backfill_with_semaphore(group) for group in backfill_groups
            ]
            await asyncio.gather(*backfill_tasks)

            # Sleep for a while before checking again
            await asyncio.sleep(300)  # Check every 5 minutes

        except Exception as e:
            logger.error(f"Error in backfill_groups_task: {str(e)}")
            await asyncio.sleep(300)  # Sleep and try again


def start_background_tasks() -> None:
    """
    Start all background tasks
    """
    logger.info("Starting background tasks")

    # Create event loop
    loop = asyncio.get_event_loop()

    # Start update task
    update_task = loop.create_task(update_groups_task())
    running_tasks["update_groups"] = update_task

    # Start backfill task
    backfill_task = loop.create_task(backfill_groups_task())
    running_tasks["backfill_groups"] = backfill_task

    logger.info("Background tasks started")


def stop_background_tasks() -> None:
    """
    Stop all background tasks
    """
    logger.info("Stopping background tasks")

    # Cancel all running tasks
    for name, task in running_tasks.items():
        if not task.done():
            logger.info(f"Cancelling task {name}")
            task.cancel()

    # Clear running tasks
    running_tasks.clear()

    logger.info("Background tasks stopped")
