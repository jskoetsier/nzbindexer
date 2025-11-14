#!/usr/bin/env python
"""
Test script for direct article retrieval from NNTP server
This script tests the basic NNTP connection and article retrieval functionality
"""

import asyncio
import logging
import os
import sys
import re
import nntplib
from typing import List, Optional, Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger("test_article")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application modules
from app.db.session import AsyncSessionLocal
from app.services.nntp import NNTPService
from app.services.setting import get_app_settings
from sqlalchemy import select


async def test_nntp_connection():
    """Test the NNTP connection"""
    logger.info("Testing NNTP connection")

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

        # Connect to NNTP server
        try:
            conn = nntp_service.connect()
            logger.info(f"Successfully connected to NNTP server {app_settings.nntp_server}")

            # Get server capabilities
            try:
                resp, caps = conn.capabilities()
                logger.info(f"Server capabilities: {caps}")
            except Exception as e:
                logger.warning(f"Could not get server capabilities: {str(e)}")

            # Close connection
            conn.quit()
            logger.info("NNTP connection test successful")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to NNTP server: {str(e)}")
            return False


async def test_group_access(group_name: str):
    """Test access to a specific group"""
    logger.info(f"Testing access to group {group_name}")

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

        # Connect to NNTP server
        try:
            conn = nntp_service.connect()

            # Select the group
            try:
                resp, count, first, last, name = conn.group(group_name)
                # Handle both string and bytes for name
                name_str = name if isinstance(name, str) else name.decode()
                logger.info(f"Successfully selected group {name_str}: {count} articles, {first}-{last}")

                # Close connection
                conn.quit()
                return True, count, first, last
            except Exception as e:
                logger.error(f"Failed to select group {group_name}: {str(e)}")
                # Close connection
                conn.quit()
                return False, 0, 0, 0
        except Exception as e:
            logger.error(f"Failed to connect to NNTP server: {str(e)}")
            return False, 0, 0, 0


async def test_article_retrieval(group_name: str, article_range: int = 10):
    """Test article retrieval from a specific group"""
    logger.info(f"Testing article retrieval from group {group_name}")

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

        # Connect to NNTP server
        try:
            conn = nntp_service.connect()

            # Select the group
            resp, count, first, last, name = conn.group(group_name)
            # Handle both string and bytes for name
            name_str = name if isinstance(name, str) else name.decode()
            logger.info(f"Selected group {name_str}: {count} articles, {first}-{last}")

            # Calculate article range to test
            start_id = max(first, last - article_range)
            end_id = last

            logger.info(f"Testing article retrieval for range {start_id}-{end_id}")

            # Test OVER command
            try:
                logger.info("Testing OVER command")
                resp, articles = conn.over(f"{start_id}-{end_id}")
                logger.info(f"OVER command returned {len(articles)} articles")

                # Process a few articles to check their content
                for i, article in enumerate(articles[:5]):
                    try:
                        if len(article) >= 9:
                            article_num, subject, from_addr, date, message_id, references, bytes_count, lines_count, other = article
                        elif len(article) == 2:
                            article_num, message_id = article
                            subject = ""
                            from_addr = ""
                            date = None
                            references = ""
                            bytes_count = 0
                            lines_count = 0
                            other = {}
                        else:
                            logger.warning(f"Unexpected article format: {article}")
                            continue

                        # Decode subject and message_id if needed
                        subject = subject.decode('utf-8', errors='replace') if isinstance(subject, bytes) else subject
                        message_id = message_id.decode('utf-8', errors='replace') if isinstance(message_id, bytes) else message_id

                        logger.info(f"Article {article_num}: subject='{subject}', message_id='{message_id}'")

                        # Try to get article content
                        try:
                            logger.info(f"Getting article content for article {article_num}")
                            resp, article_info = conn.article(f"{article_num}")

                            # Check for yEnc headers in the article content
                            has_yenc = False
                            for j, line in enumerate(article_info.lines[:20]):
                                line_str = line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line
                                if line_str.startswith("=ybegin "):
                                    has_yenc = True
                                    logger.info(f"Found yEnc header in article {article_num}: {line_str}")
                                    break

                            if has_yenc:
                                logger.info(f"Article {article_num} contains yEnc data (binary post)")
                            else:
                                logger.info(f"Article {article_num} does not contain yEnc data")
                        except Exception as e:
                            logger.error(f"Failed to get article content for article {article_num}: {str(e)}")
                    except Exception as e:
                        logger.error(f"Error processing article: {str(e)}")
            except Exception as e:
                logger.error(f"OVER command failed: {str(e)}")

                # Try HEAD command for individual articles
                logger.info("Falling back to HEAD command for individual articles")
                for article_id in range(start_id, start_id + 5):
                    try:
                        logger.info(f"Getting headers for article {article_id}")
                        resp, article_info = conn.head(f"{article_id}")

                        # Extract basic info from headers
                        subject = None
                        message_id = None

                        # Parse headers
                        for line in article_info.lines:
                            line_str = line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line
                            if line_str.startswith("Subject:"):
                                subject = line_str[8:].strip()
                            elif line_str.startswith("Message-ID:"):
                                message_id = line_str[10:].strip()

                        logger.info(f"Article {article_id}: subject='{subject}', message_id='{message_id}'")

                        # Try to get article content
                        try:
                            logger.info(f"Getting article content for article {article_id}")
                            resp, article_info = conn.article(f"{article_id}")

                            # Check for yEnc headers in the article content
                            has_yenc = False
                            for j, line in enumerate(article_info.lines[:20]):
                                line_str = line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line
                                if line_str.startswith("=ybegin "):
                                    has_yenc = True
                                    logger.info(f"Found yEnc header in article {article_id}: {line_str}")
                                    break

                            if has_yenc:
                                logger.info(f"Article {article_id} contains yEnc data (binary post)")
                            else:
                                logger.info(f"Article {article_id} does not contain yEnc data")
                        except Exception as e:
                            logger.error(f"Failed to get article content for article {article_id}: {str(e)}")
                    except Exception as e:
                        logger.error(f"Failed to get headers for article {article_id}: {str(e)}")

            # Close connection
            conn.quit()
            logger.info("Article retrieval test complete")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to NNTP server: {str(e)}")
            return False


async def test_specific_article(group_name: str, article_id: int):
    """Test retrieval of a specific article"""
    logger.info(f"Testing retrieval of article {article_id} from group {group_name}")

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

        # Connect to NNTP server
        try:
            conn = nntp_service.connect()

            # Select the group
            resp, count, first, last, name = conn.group(group_name)
            # Handle both string and bytes for name
            name_str = name if isinstance(name, str) else name.decode()
            logger.info(f"Selected group {name_str}: {count} articles, {first}-{last}")

            # Check if article_id is within range
            if article_id < first or article_id > last:
                logger.warning(f"Article {article_id} is outside the range {first}-{last}")
                # Try a different article within range
                article_id = last - 10
                logger.info(f"Trying article {article_id} instead")

            # Try to get article headers
            try:
                logger.info(f"Getting headers for article {article_id}")
                resp, article_info = conn.head(f"{article_id}")

                # Extract basic info from headers
                subject = None
                message_id = None

                # Parse headers
                for line in article_info.lines:
                    line_str = line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line
                    if line_str.startswith("Subject:"):
                        subject = line_str[8:].strip()
                    elif line_str.startswith("Message-ID:"):
                        message_id = line_str[10:].strip()

                logger.info(f"Article {article_id}: subject='{subject}', message_id='{message_id}'")

                # Try to get article content
                try:
                    logger.info(f"Getting article content for article {article_id}")
                    resp, article_info = conn.article(f"{article_id}")

                    # Check for yEnc headers in the article content
                    has_yenc = False
                    for j, line in enumerate(article_info.lines[:20]):
                        line_str = line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line
                        logger.info(f"Line {j}: {line_str[:100]}")  # Log first 100 chars of each line
                        if line_str.startswith("=ybegin "):
                            has_yenc = True
                            logger.info(f"Found yEnc header in article {article_id}: {line_str}")
                            break

                    if has_yenc:
                        logger.info(f"Article {article_id} contains yEnc data (binary post)")
                    else:
                        logger.info(f"Article {article_id} does not contain yEnc data")
                except Exception as e:
                    logger.error(f"Failed to get article content for article {article_id}: {str(e)}")
            except Exception as e:
                logger.error(f"Failed to get headers for article {article_id}: {str(e)}")

            # Close connection
            conn.quit()
            logger.info("Specific article test complete")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to NNTP server: {str(e)}")
            return False


async def main():
    """Main function"""
    # Test NNTP connection
    connection_ok = await test_nntp_connection()
    if not connection_ok:
        logger.error("NNTP connection test failed, aborting further tests")
        return

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

    # Test access to each group
    for group_name in binary_groups:
        access_ok, count, first, last = await test_group_access(group_name)
        if access_ok:
            # Test article retrieval for this group
            await test_article_retrieval(group_name, 10)

            # Test a specific article from this group
            if last > 0:
                await test_specific_article(group_name, last - 5)

        print("\n" + "-" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
    print("Article retrieval tests complete!")
