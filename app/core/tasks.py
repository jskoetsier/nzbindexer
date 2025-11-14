"""
Background task manager for NZB Indexer
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
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

            # Create NNTP service with settings from database
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

            # Get group info from NNTP server
            try:
                group_info = nntp_service.get_group_info(group.name)

                # Update group with new info
                group.last_article_id = group_info["last"]
                group.last_updated = datetime.now(timezone.utc)

                # If current_article_id is 0, set it to last_article_id to start from recent articles
                if group.current_article_id == 0:
                    group.current_article_id = group_info["last"]

                # Save changes
                db.add(group)
                await db.commit()

                logger.info(f"Updated group {group.name}: {group_info}")

                # Process new articles
                from app.services.article import process_group_update

                await process_group_update(db, group, nntp_service=nntp_service)

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

            # Create NNTP service with settings from database
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

            # Get group info from NNTP server
            try:
                group_info = nntp_service.get_group_info(group.name)

                # Calculate backfill target based on days instead of article count
                # This is more intuitive and reliable than trying to estimate article counts
                backfill_distance = group.current_article_id - group.backfill_target

                # Always recalculate backfill target based on backfill_days setting
                # Invalid cases that need recalculation:
                # 1. target is 0 (never set)
                # 2. target >= current_article_id (invalid)
                # 3. distance > 200k articles (unreasonably large backfill)
                should_recalculate = (
                    group.backfill_target == 0
                    or group.backfill_target >= group.current_article_id
                    or backfill_distance > 200000
                )

                if should_recalculate:
                    logger.info(
                        f"Backfill recalculation needed for {group.name}: current={group.current_article_id}, target={group.backfill_target}, distance={backfill_distance}"
                    )

                    # Calculate target based on estimated articles per day
                    # Use retention period to estimate posting rate
                    try:
                        total_articles = group_info["last"] - group_info["first"]
                        articles_per_day = total_articles / max(
                            1, app_settings.retention_days
                        )

                        # Calculate how many articles to backfill based on backfill_days
                        target_articles = int(
                            articles_per_day * app_settings.backfill_days
                        )

                        # Apply reasonable limits to prevent extreme values
                        # Min: 1000 articles (at least some content)
                        # Max: 100000 articles (prevent overwhelming the system)
                        target_articles = max(1000, min(100000, target_articles))

                        logger.info(
                            f"Calculated backfill for {group.name}: {articles_per_day:.0f} articles/day * {app_settings.backfill_days} days = {target_articles} articles"
                        )
                    except Exception as e:
                        # Fallback to 10,000 articles if calculation fails
                        target_articles = 10000
                        logger.warning(
                            f"Failed to calculate backfill for {group.name}, using default {target_articles} articles: {e}"
                        )

                    # Set backfill_target to go back 'target_articles' from current position
                    # Ensure we don't go below the first article in the group
                    group.backfill_target = max(
                        group_info["first"], group.current_article_id - target_articles
                    )

                    logger.info(
                        f"Set backfill target for {group.name} to {group.backfill_target} (backfilling ~{app_settings.backfill_days} days / {target_articles} articles from current {group.current_article_id})"
                    )

                # Update group with new info
                group.last_updated = datetime.now(timezone.utc)

                # Save changes
                db.add(group)
                await db.commit()

                logger.info(
                    f"Backfilling group {group.name} to target {group.backfill_target}"
                )

                # Process backfill articles
                from app.services.article import process_group_backfill

                await process_group_backfill(db, group, nntp_service=nntp_service)

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
