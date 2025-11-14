#!/usr/bin/env python
"""
Script to add binary-focused newsgroups to the database
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


async def add_group(db, name: str, description: str = None, active: bool = True, backfill: bool = True) -> bool:
    """Add a group to the database if it doesn't exist"""
    try:
        # Check if group already exists
        query = select(Group).filter(Group.name == name)
        result = await db.execute(query)
        group = result.scalars().first()

        if group:
            logger.info(f"Group '{name}' already exists")

            # Update group settings
            group.active = active
            group.backfill = backfill
            if description:
                group.description = description

            db.add(group)
            await db.commit()
            logger.info(f"Updated group '{name}' settings")
            return True

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

        # Connect to NNTP server
        conn = nntp_service.connect()

        # Check if group exists on server
        try:
            resp, count, first, last, group_name = conn.group(name)

            # Create group
            group = Group(
                name=name,
                description=description or f"Added by add_binary_groups.py script",
                active=active,
                backfill=backfill,
                first_article_id=first,
                last_article_id=last,
                current_article_id=last,  # Start from the most recent
                backfill_target=max(first, last - 1000),  # Set backfill target to 1000 articles back
                min_files=1,
                min_size=0,
            )
            db.add(group)
            await db.commit()
            logger.info(f"Added group '{name}' with {count} articles, range {first}-{last}")
            return True

        except Exception as e:
            logger.error(f"Error checking group '{name}' on server: {str(e)}")
            return False
        finally:
            conn.quit()

    except Exception as e:
        logger.error(f"Error adding group '{name}': {str(e)}")
        return False


async def add_binary_groups():
    """Add binary-focused newsgroups to the database"""
    async with AsyncSessionLocal() as db:
        # List of common binary newsgroups
        binary_groups = [
            # Movies
            ("alt.binaries.movies", "Movie binary posts"),
            ("alt.binaries.movies.divx", "DivX movie binary posts"),
            ("alt.binaries.movies.xvid", "XviD movie binary posts"),
            ("alt.binaries.hdtv", "HDTV binary posts"),
            ("alt.binaries.hdtv.x264", "x264 HDTV binary posts"),

            # TV
            ("alt.binaries.tv", "TV show binary posts"),
            ("alt.binaries.tvseries", "TV series binary posts"),
            ("alt.binaries.multimedia", "Multimedia binary posts"),

            # Music
            ("alt.binaries.sounds.mp3", "MP3 audio binary posts"),
            ("alt.binaries.sounds.lossless", "Lossless audio binary posts"),
            ("alt.binaries.sounds", "Audio binary posts"),

            # Games
            ("alt.binaries.games", "Game binary posts"),
            ("alt.binaries.games.xbox", "Xbox game binary posts"),
            ("alt.binaries.games.wii", "Wii game binary posts"),
            ("alt.binaries.games.nintendo-ds", "Nintendo DS game binary posts"),

            # Applications
            ("alt.binaries.apps", "Application binary posts"),
            ("alt.binaries.mac", "Mac application binary posts"),

            # E-books
            ("alt.binaries.e-books", "E-book binary posts"),
            ("alt.binaries.ebooks", "E-book binary posts"),

            # Other popular binary groups
            ("alt.binaries.teevee", "TV binary posts"),
            ("alt.binaries.moovee", "Movie binary posts"),
            ("alt.binaries.cd.image", "CD image binary posts"),
            ("alt.binaries.dvd", "DVD binary posts"),
            ("alt.binaries.blu-ray", "Blu-ray binary posts"),
        ]

        success_count = 0
        for name, description in binary_groups:
            if await add_group(db, name, description):
                success_count += 1

        logger.info(f"Successfully added/updated {success_count} of {len(binary_groups)} binary groups")


if __name__ == "__main__":
    asyncio.run(add_binary_groups())
    print("Binary groups added successfully!")
