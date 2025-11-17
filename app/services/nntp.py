"""
NNTP service for connecting to Usenet servers and retrieving newsgroups
"""

import logging
import nntplib
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union

from app.core.config import settings
from app.db.models.group import Group
from app.schemas.group import GroupCreate
from app.services.group import create_group, get_group_by_name
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class NNTPService:
    """
    Service for interacting with NNTP servers
    """

    def __init__(
        self,
        server: str = None,
        port: int = None,
        use_ssl: bool = None,
        username: str = None,
        password: str = None,
    ):
        self.server = server or settings.NNTP_SERVER
        self.use_ssl = use_ssl if use_ssl is not None else settings.NNTP_SSL
        self.port = port or (
            settings.NNTP_SSL_PORT if self.use_ssl else settings.NNTP_PORT
        )
        self.username = username if username is not None else settings.NNTP_USERNAME
        self.password = password if password is not None else settings.NNTP_PASSWORD

    def connect(self) -> nntplib.NNTP:
        """
        Connect to the NNTP server
        """
        try:
            if self.use_ssl:
                conn = nntplib.NNTP_SSL(
                    host=self.server,
                    port=self.port,
                    user=self.username if self.username else None,
                    password=self.password if self.password else None,
                )
            else:
                conn = nntplib.NNTP(
                    host=self.server,
                    port=self.port,
                    user=self.username if self.username else None,
                    password=self.password if self.password else None,
                )
            logger.info(f"Connected to NNTP server {self.server}:{self.port}")
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to NNTP server: {str(e)}")
            raise

    def get_newsgroups(self, pattern: str = "*") -> List[Tuple[str, str]]:
        """
        Get a list of newsgroups from the server
        Returns a list of tuples (group_name, group_description)
        """
        try:
            conn = self.connect()
            resp, groups = conn.list()

            # Filter groups by pattern if provided
            if pattern and pattern != "*":
                pattern_regex = re.compile(pattern.replace("*", ".*"))
                groups = [
                    g
                    for g in groups
                    if pattern_regex.match(
                        g[0] if isinstance(g[0], str) else g[0].decode()
                    )
                ]

            # Extract group name and description
            result = []
            for g in groups:
                name = g[0] if isinstance(g[0], str) else g[0].decode()
                desc = g[1] if isinstance(g[1], str) else g[1].decode()
                result.append((name, desc))

            conn.quit()
            logger.info(f"Retrieved {len(result)} newsgroups from server")
            return result
        except Exception as e:
            logger.error(f"Failed to get newsgroups: {str(e)}")
            raise

    def get_group_info(self, group_name: str) -> Dict[str, Union[str, int]]:
        """
        Get information about a specific newsgroup
        """
        try:
            conn = self.connect()
            resp, count, first, last, name = conn.group(group_name)

            # Handle both string and bytes for name
            name_str = name if isinstance(name, str) else name.decode()

            info = {
                "name": name_str,
                "count": count,
                "first": first,
                "last": last,
            }

            conn.quit()
            return info
        except Exception as e:
            logger.error(f"Failed to get group info for {group_name}: {str(e)}")
            raise

    async def get_article_body(self, message_id: str) -> Optional[List[str]]:
        """
        Get the body of an article by message ID
        Returns a list of lines from the article body
        """
        try:
            conn = self.connect()
            resp, info = conn.body(message_id)

            # Convert bytes to strings if needed
            lines = []
            for line in info.lines:
                if isinstance(line, bytes):
                    lines.append(line.decode("utf-8", errors="replace"))
                else:
                    lines.append(line)

            conn.quit()
            return lines
        except Exception as e:
            logger.debug(f"Failed to get article body for {message_id}: {str(e)}")
            return None


async def discover_newsgroups(
    db: AsyncSession, pattern: str = "*", active: bool = False, batch_size: int = 100
) -> Dict[str, any]:
    """
    Discover newsgroups from the NNTP server and add them to the database
    Returns statistics about the discovery process

    Args:
        db: Database session
        pattern: Pattern to filter newsgroups (e.g., "alt.*", "comp.sys.*")
        active: Whether to set discovered groups as active
        batch_size: Number of groups to process in each batch

    Returns:
        Dictionary with statistics about the discovery process
    """
    # Import the global cancel flag
    from app.main import discovery_cancel, discovery_running

    # Set the global running flag
    global discovery_running
    global discovery_cancel

    # Check if discovery is already running
    if discovery_running:
        raise ValueError("Discovery is already running")

    # Reset cancel flag and set running flag
    discovery_cancel = False
    discovery_running = True

    stats = {
        "total": 0,
        "added": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "processed": 0,
        "cancelled": False,
    }

    try:
        # Get app settings from database
        from app.services.setting import get_app_settings

        app_settings = await get_app_settings(db)

        # Check if NNTP server is configured
        if not app_settings.nntp_server:
            discovery_running = False
            raise ValueError("NNTP server not configured")

        # Get newsgroups from server using settings from database
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

        logger.info(f"Retrieving newsgroups with pattern: {pattern}")
        newsgroups = nntp_service.get_newsgroups(pattern)
        stats["total"] = len(newsgroups)
        logger.info(f"Found {stats['total']} newsgroups matching pattern: {pattern}")

        # Process newsgroups in batches
        for i in range(0, len(newsgroups), batch_size):
            # Check if cancellation was requested
            if discovery_cancel:
                logger.info("Discovery cancelled by user")
                stats["cancelled"] = True
                break

            # Get the current batch
            batch = newsgroups[i : i + batch_size]
            logger.info(
                f"Processing batch {i//batch_size + 1}/{(len(newsgroups) + batch_size - 1)//batch_size} ({len(batch)} groups)"
            )

            # Process each newsgroup in the batch
            for group_name, group_description in batch:
                try:
                    # Check if cancellation was requested
                    if discovery_cancel:
                        logger.info("Discovery cancelled by user")
                        stats["cancelled"] = True
                        break

                    # Check if group already exists
                    existing_group = await get_group_by_name(db, group_name)

                    if existing_group:
                        # Update existing group
                        existing_group.description = group_description
                        existing_group.updated_at = datetime.now(timezone.utc)
                        db.add(existing_group)
                        stats["updated"] += 1
                    else:
                        # Create new group
                        try:
                            # Get additional group info
                            group_info = nntp_service.get_group_info(group_name)

                            # Create group
                            group_data = GroupCreate(
                                name=group_name,
                                description=group_description,
                                active=active,
                                backfill=False,
                                min_files=1,
                                min_size=0,
                            )

                            new_group = await create_group(db, group_data)

                            # Update article IDs
                            new_group.first_article_id = group_info["first"]
                            new_group.last_article_id = group_info["last"]
                            new_group.current_article_id = group_info["first"]
                            db.add(new_group)

                            stats["added"] += 1
                        except Exception as e:
                            logger.error(
                                f"Failed to create group {group_name}: {str(e)}"
                            )
                            stats["failed"] += 1
                except Exception as e:
                    logger.error(f"Error processing group {group_name}: {str(e)}")
                    stats["failed"] += 1

                # Update processed count
                stats["processed"] += 1

            # Commit changes for this batch
            await db.commit()

            # Log progress
            logger.info(
                f"Progress: {stats['processed']}/{stats['total']} groups processed"
            )
            logger.info(
                f"Stats so far: added={stats['added']}, updated={stats['updated']}, failed={stats['failed']}"
            )

        # Reset running flag
        discovery_running = False

        return stats
    except Exception as e:
        await db.rollback()
        discovery_running = False
        logger.error(f"Failed to discover newsgroups: {str(e)}")
        raise
