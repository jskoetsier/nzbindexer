#!/usr/bin/env python
"""
Script to examine raw article subjects from newsgroups
"""

import asyncio
import logging
import os
import sys
import re
from typing import List, Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("examine")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application modules
from app.db.session import AsyncSessionLocal
from app.db.models.group import Group
from app.services.nntp import NNTPService
from app.services.setting import get_app_settings
from sqlalchemy import select


async def examine_articles(db, group_name: str, limit: int = 20):
    """Examine raw article subjects from a newsgroup"""
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

    logger.info(f"Examining articles from group: {group.name}")

    try:
        # Connect to NNTP server
        conn = nntp_service.connect()

        # Select the group
        resp, count, first, last, name = conn.group(group.name)

        # Get a sample of articles
        sample_start = max(first, last - limit)
        sample_end = last

        logger.info(f"Getting sample of {limit} articles from {sample_start} to {sample_end}")

        # Get article headers
        try:
            resp, articles = conn.over((sample_start, sample_end))
        except Exception as e:
            logger.error(f"Error getting articles with OVER command: {str(e)}")
            logger.info("Falling back to HEAD command for individual articles")

            articles = []
            for article_id in range(sample_start, sample_end + 1):
                try:
                    resp, article_info = conn.head(f"{article_id}")

                    # Extract basic info from headers
                    subject = None
                    message_id = None

                    # Parse headers
                    for line in article_info.lines:
                        line_str = line.decode() if isinstance(line, bytes) else line
                        if line_str.startswith("Subject:"):
                            subject = line_str[8:].strip()
                        elif line_str.startswith("Message-ID:"):
                            message_id = line_str[10:].strip()

                    if subject and message_id:
                        articles.append((article_id, subject, None, None, message_id, None, 0, 0, {}))
                except Exception as article_e:
                    logger.debug(f"Skipping article {article_id}: {str(article_e)}")
                    continue

        # Close connection
        conn.quit()

        # Print raw article subjects
        logger.info(f"Raw article subjects from {group.name}:")
        for article in articles:
            try:
                # Extract article info
                if len(article) >= 9:
                    article_num, subject, from_addr, date, message_id, references, bytes_count, lines_count, other = article
                elif len(article) == 2:
                    article_num, message_id = article
                    subject = ""
                    bytes_count = 0
                else:
                    logger.warning(f"Unexpected article format: {article}")
                    continue

                # Decode bytes to strings with error handling
                try:
                    subject = subject.decode('utf-8', errors='replace') if isinstance(subject, bytes) else subject
                    subject = ''.join(c if ord(c) < 0xD800 or ord(c) > 0xDFFF else '?' for c in subject)
                except Exception:
                    subject = "Unknown Subject"

                # Print article subject
                logger.info(f"  Article {article_num}: {subject}")

                # Check for common binary indicators
                has_yenc = "yenc" in subject.lower() or "yEnc" in subject
                has_part_pattern = re.search(r"\(\d+/\d+\)|\[\d+/\d+\]|\d+/\d+", subject) is not None
                has_file_ext = re.search(r"\.(mkv|avi|mp4|mov|wmv|iso|zip|rar|7z|tar|gz|mp3|flac|wav|epub|pdf|mobi|azw|doc|docx|xls|xlsx|ppt|pptx)$", subject, re.IGNORECASE) is not None

                binary_indicators = []
                if has_yenc:
                    binary_indicators.append("yEnc")
                if has_part_pattern:
                    binary_indicators.append("part pattern")
                if has_file_ext:
                    binary_indicators.append("file extension")

                if binary_indicators:
                    logger.info(f"    Binary indicators: {', '.join(binary_indicators)}")

            except Exception as e:
                logger.error(f"Error examining article: {str(e)}")

    except Exception as e:
        logger.error(f"Error examining articles: {str(e)}")


async def examine_multiple_groups(db, limit_per_group: int = 20):
    """Examine articles from multiple groups"""
    # List of groups to examine
    groups = [
        "alt.binaries.teevee",
        "alt.binaries.moovee",
        "alt.binaries.movies",
        "alt.binaries.hdtv",
        "alt.binaries.hdtv.x264",
        "alt.binaries.tv",
        # Add more groups as needed
    ]

    for group_name in groups:
        await examine_articles(db, group_name, limit_per_group)
        print("\n" + "-" * 80 + "\n")  # Add separator between groups


async def main():
    """Main function"""
    logger.info("Starting article examination")

    async with AsyncSessionLocal() as db:
        await examine_multiple_groups(db, limit_per_group=10)

    logger.info("Article examination complete")


if __name__ == "__main__":
    asyncio.run(main())
    print("Article examination complete!")
