#!/usr/bin/env python
"""
Debug script for article processing
This script provides detailed logging of the article processing steps
"""

import asyncio
import logging
import os
import sys
import re
from typing import List, Optional, Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG for maximum information
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger("debug_article")

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
from app.services.nzb import NZBService
from sqlalchemy import select, update, func, text


class DebugArticleService(ArticleService):
    """
    Extended ArticleService with detailed logging
    """

    async def process_articles(
        self,
        db,
        group,
        start_id,
        end_id,
        limit=1000,
    ):
        """
        Process articles from a group with detailed logging
        """
        logger.info(f"Starting debug article processing for group {group.name}")
        logger.info(f"Processing articles from {start_id} to {end_id} (limit: {limit})")

        # Call the original method
        stats = await super().process_articles(db, group, start_id, end_id, limit)

        logger.info(f"Article processing stats: {stats}")
        return stats

    async def _process_binary_post(
        self,
        subject: str,
        message_id: str,
        bytes_count: int,
        binaries: Dict[str, Dict],
        binary_subjects: Dict[str, str],
    ):
        """
        Process a binary post with detailed logging
        """
        logger.debug(f"Processing binary post: subject='{subject}', message_id='{message_id}'")

        # First, try to parse subject to extract binary name and part info
        binary_name, part_num, total_parts = self._parse_binary_subject(subject)
        logger.debug(f"Subject parsing result: binary_name='{binary_name}', part_num={part_num}, total_parts={total_parts}")

        # If we couldn't extract binary info from the subject, check if this is an obfuscated binary post
        if not binary_name or not part_num:
            logger.debug("Subject parsing failed, checking for obfuscated binary post")

            # For obfuscated posts, we need to get the article content to check for yEnc headers
            try:
                # Connect to NNTP server if needed
                if not hasattr(self, '_conn') or self._conn is None:
                    logger.debug("Connecting to NNTP server")
                    self._conn = self.nntp_service.connect()

                # Get the article content
                try:
                    logger.debug(f"Getting article content for message_id: {message_id}")
                    resp, article_info = self._conn.article(f"<{message_id}>")

                    # Look for yEnc headers in the article content
                    yenc_begin = None
                    yenc_part = None
                    yenc_name = None

                    logger.debug("Searching for yEnc headers in article content")
                    for i, line in enumerate(article_info.lines[:30]):  # Check first 30 lines
                        try:
                            line_str = line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line
                            logger.debug(f"Line {i}: {line_str[:100]}")  # Log first 100 chars of each line

                            # Check for yEnc begin line
                            if line_str.startswith("=ybegin "):
                                yenc_begin = line_str
                                logger.debug(f"Found yEnc begin line: {yenc_begin}")

                                # Extract part info
                                part_match = re.search(r"part=(\d+)\s+total=(\d+)", line_str)
                                if part_match:
                                    part_num = int(part_match.group(1))
                                    total_parts = int(part_match.group(2))
                                    logger.debug(f"Extracted part info: part_num={part_num}, total_parts={total_parts}")

                                # Extract name
                                name_match = re.search(r"name=(.*?)$", line_str)
                                if name_match:
                                    yenc_name = name_match.group(1).strip()
                                    logger.debug(f"Extracted name: {yenc_name}")

                            # Check for yEnc part line
                            elif line_str.startswith("=ypart "):
                                yenc_part = line_str
                                logger.debug(f"Found yEnc part line: {yenc_part}")

                            # If we found both yEnc begin and part lines, we can stop
                            if yenc_begin and yenc_part and yenc_name:
                                break
                        except Exception as line_e:
                            logger.error(f"Error processing line {i}: {str(line_e)}")

                    # If we found yEnc headers, use the name from the yEnc header as the binary name
                    if yenc_name and part_num and total_parts:
                        binary_name = yenc_name
                        logger.info(f"Found obfuscated binary post: {subject} -> {binary_name} (part {part_num}/{total_parts})")
                    else:
                        logger.debug("No yEnc headers found in article content")

                except Exception as e:
                    logger.error(f"Error getting article content: {str(e)}")

            except Exception as e:
                logger.error(f"Error checking for obfuscated binary post: {str(e)}")

        # If we still couldn't extract binary info, skip this post
        if not binary_name or not part_num:
            logger.debug("Could not extract binary info, skipping post")
            return

        # Create or update binary entry
        binary_key = self._get_binary_key(binary_name)
        logger.debug(f"Binary key: {binary_key}")

        if binary_key not in binaries:
            binaries[binary_key] = {
                "name": binary_name,
                "parts": {},
                "total_parts": total_parts or 0,
                "size": 0,
            }
            binary_subjects[binary_key] = subject
            logger.debug(f"Created new binary entry: {binary_key}")

        # Add part to binary
        if part_num not in binaries[binary_key]["parts"]:
            binaries[binary_key]["parts"][part_num] = {
                "message_id": message_id,
                "size": bytes_count,
            }
            binaries[binary_key]["size"] += bytes_count
            logger.debug(f"Added part {part_num} to binary {binary_key}")

        # Update total parts if we have a new value
        if total_parts and binaries[binary_key]["total_parts"] < total_parts:
            binaries[binary_key]["total_parts"] = total_parts
            logger.debug(f"Updated total parts for binary {binary_key} to {total_parts}")

        # Return binary info for logging
        return f"{binary_name} (part {part_num}/{total_parts})"

    async def _process_binaries_to_releases(
        self,
        db,
        group,
        binaries,
        binary_subjects,
    ):
        """
        Process completed binaries into releases with detailed logging
        """
        logger.info(f"Processing {len(binaries)} binaries to releases for group {group.name}")

        # Log binary details
        for binary_key, binary in binaries.items():
            logger.info(f"Binary: {binary['name']}")
            logger.info(f"  Parts: {len(binary['parts'])}/{binary['total_parts']}")
            logger.info(f"  Size: {binary['size']}")

            # Check if this binary should be converted to a release
            create_release_conditions = [
                # Condition 1: Binary is complete (all parts available)
                binary["total_parts"] > 0 and len(binary["parts"]) >= binary["total_parts"],

                # Condition 2: Binary has at least 1 part and we don't know the total parts
                binary["total_parts"] == 0 and len(binary["parts"]) >= 1,

                # Condition 3: Binary has at least 50% of parts and at least 3 parts
                binary["total_parts"] > 0 and len(binary["parts"]) >= max(3, binary["total_parts"] // 2)
            ]

            logger.info(f"  Create release conditions: {create_release_conditions}")
            logger.info(f"  Should create release: {any(create_release_conditions)}")

        # Call the original method
        releases_created = await super()._process_binaries_to_releases(db, group, binaries, binary_subjects)

        logger.info(f"Created {releases_created} releases")
        return releases_created


async def debug_article_processing(group_name: str, limit: int = 200):
    """Debug article processing for a specific group"""
    logger.info(f"Starting debug article processing for group {group_name}")

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

        # Get group
        query = select(Group).filter(Group.name == group_name)
        result = await db.execute(query)
        group = result.scalars().first()

        if not group:
            logger.error(f"Group {group_name} not found")
            return

        # Create debug article service
        article_service = DebugArticleService(nntp_service=nntp_service)

        # Connect to NNTP server
        conn = nntp_service.connect()

        # Select the group
        resp, count, first, last, name = conn.group(group.name)

        # Close connection
        conn.quit()

        # Calculate range to process
        process_start = last - limit
        process_end = last

        logger.info(f"Processing articles {process_start} to {process_end} for group {group.name}")

        # Process articles
        stats = await article_service.process_articles(
            db, group, process_start, process_end, limit
        )

        logger.info(f"Article processing stats: {stats}")

        # Check if any releases were created
        query = select(func.count(Release.id))
        result = await db.execute(query)
        release_count = result.scalar()

        logger.info(f"Total releases in database: {release_count}")

        # Get a sample of releases
        query = select(Release).limit(5)
        result = await db.execute(query)
        releases = result.scalars().all()

        if releases:
            logger.info("Sample releases:")
            for release in releases:
                logger.info(f"  ID: {release.id}, Name: {release.name}, Files: {release.files}, Size: {release.size}")
        else:
            logger.info("No releases found in database")


async def main():
    """Main function"""
    # List of binary groups to test
    binary_groups = [
        "alt.binaries.teevee",
        "alt.binaries.moovee",
        "alt.binaries.movies",
        "alt.binaries.hdtv",
        "alt.binaries.hdtv.x264",
        "alt.binaries.tv",
        "alt.binaries.multimedia",
    ]

    # Process each group
    for group_name in binary_groups:
        await debug_article_processing(group_name, 50)
        print("\n" + "-" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
    print("Debug article processing complete!")
