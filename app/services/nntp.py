"""
NNTP service for connecting to Usenet servers and retrieving newsgroups
"""

import asyncio
import logging

import nntplib
import re
from datetime import datetime
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

    def __init__(self):
        self.server = settings.NNTP_SERVER
        self.port = settings.NNTP_SSL_PORT if settings.NNTP_SSL else settings.NNTP_PORT
        self.use_ssl = settings.NNTP_SSL
        self.username = settings.NNTP_USERNAME
        self.password = settings.NNTP_PASSWORD

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
                groups = [g for g in groups if pattern_regex.match(g[0])]

            # Extract group name and description
            result = [(g[0].decode(), g[1].decode()) for g in groups]

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

            info = {
                "name": name.decode(),
                "count": count,
                "first": first,
                "last": last,
            }

            conn.quit()
            return info
        except Exception as e:
            logger.error(f"Failed to get group info for {group_name}: {str(e)}")
            raise


async def discover_newsgroups(
    db: AsyncSession, pattern: str = "*", active: bool = False
) -> Dict[str, any]:
    """
    Discover newsgroups from the NNTP server and add them to the database
    Returns statistics about the discovery process
    """
    stats = {
        "total": 0,
        "added": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
    }

    try:
        # Check if NNTP server is configured
        if not settings.NNTP_SERVER:
            raise ValueError("NNTP server not configured")

        # Get newsgroups from server
        nntp_service = NNTPService()
        newsgroups = nntp_service.get_newsgroups(pattern)
        stats["total"] = len(newsgroups)

        # Process each newsgroup
        for group_name, group_description in newsgroups:
            try:
                # Check if group already exists
                existing_group = await get_group_by_name(db, group_name)

                if existing_group:
                    # Update existing group
                    existing_group.description = group_description
                    existing_group.updated_at = datetime.utcnow()
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
                        logger.error(f"Failed to create group {group_name}: {str(e)}")
                        stats["failed"] += 1
            except Exception as e:
                logger.error(f"Error processing group {group_name}: {str(e)}")
                stats["failed"] += 1

        # Commit changes
        await db.commit()

        return stats
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to discover newsgroups: {str(e)}")
        raise
