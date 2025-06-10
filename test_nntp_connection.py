#!/usr/bin/env python
"""
Script to test NNTP connection and authentication
"""

import asyncio
import logging
import os
import sys
import nntplib
import time
from typing import List, Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("nntp_test")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application modules
from app.db.session import AsyncSessionLocal
from app.services.setting import get_app_settings


async def test_nntp_connection():
    """Test NNTP connection and authentication"""
    async with AsyncSessionLocal() as db:
        # Get app settings
        app_settings = await get_app_settings(db)

        # Log NNTP settings
        logger.info(f"NNTP Server: {app_settings.nntp_server}")
        logger.info(f"NNTP Port: {app_settings.nntp_port}")
        logger.info(f"NNTP SSL: {app_settings.nntp_ssl}")
        logger.info(f"NNTP SSL Port: {app_settings.nntp_ssl_port}")
        logger.info(f"NNTP Username: {'Set' if app_settings.nntp_username else 'Not set'}")
        logger.info(f"NNTP Password: {'Set' if app_settings.nntp_password else 'Not set'}")

        # Test connection without authentication
        try:
            logger.info("Testing connection without authentication...")
            if app_settings.nntp_ssl:
                conn = nntplib.NNTP_SSL(
                    host=app_settings.nntp_server,
                    port=app_settings.nntp_ssl_port,
                )
            else:
                conn = nntplib.NNTP(
                    host=app_settings.nntp_server,
                    port=app_settings.nntp_port,
                )

            logger.info("Connection successful without authentication")
            logger.info(f"Server welcome message: {conn.welcome}")

            # Test basic commands
            resp, count, first, last, name = conn.group("alt.binaries.teevee")
            logger.info(f"Group info: {count} articles, {first}-{last}")

            conn.quit()
        except Exception as e:
            logger.error(f"Connection without authentication failed: {str(e)}")

        # Test connection with authentication
        try:
            logger.info("Testing connection with authentication...")
            if app_settings.nntp_ssl:
                conn = nntplib.NNTP_SSL(
                    host=app_settings.nntp_server,
                    port=app_settings.nntp_ssl_port,
                    user=app_settings.nntp_username,
                    password=app_settings.nntp_password,
                )
            else:
                conn = nntplib.NNTP(
                    host=app_settings.nntp_server,
                    port=app_settings.nntp_port,
                    user=app_settings.nntp_username,
                    password=app_settings.nntp_password,
                )

            logger.info("Connection successful with authentication")
            logger.info(f"Server welcome message: {conn.welcome}")

            # Test basic commands
            resp, count, first, last, name = conn.group("alt.binaries.teevee")
            logger.info(f"Group info: {count} articles, {first}-{last}")

            # Try to get a specific article
            article_id = last - 100  # Try an article that's 100 back from the last
            try:
                logger.info(f"Trying to get article {article_id}...")
                resp, article_info = conn.article(f"{article_id}")

                # Print article headers
                logger.info("Article headers:")
                for i, line in enumerate(article_info.lines[:20]):  # Print first 20 lines
                    line_str = line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line
                    logger.info(f"  {line_str}")

                    # If this is a binary post, it should have a subject line and some binary content
                    if line_str.startswith("Subject:"):
                        logger.info(f"  Subject: {line_str[8:].strip()}")
            except Exception as article_e:
                logger.error(f"Error getting article {article_id}: {str(article_e)}")

            # Try to list available groups
            try:
                logger.info("Listing available groups...")
                resp, groups = conn.list()

                # Count groups
                binary_groups = [g for g in groups if b'alt.binaries.' in g[0] or 'alt.binaries.' in g[0]]
                logger.info(f"Found {len(binary_groups)} binary groups out of {len(groups)} total groups")

                # Print first 10 binary groups
                logger.info("First 10 binary groups:")
                for i, group in enumerate(binary_groups[:10]):
                    group_name = group[0].decode('utf-8', errors='replace') if isinstance(group[0], bytes) else group[0]
                    logger.info(f"  {group_name}")
            except Exception as list_e:
                logger.error(f"Error listing groups: {str(list_e)}")

            # Try a different binary group
            try:
                logger.info("Trying alt.binaries.multimedia...")
                resp, count, first, last, name = conn.group("alt.binaries.multimedia")
                logger.info(f"Group info: {count} articles, {first}-{last}")

                # Try to get a specific article
                article_id = last - 100  # Try an article that's 100 back from the last
                logger.info(f"Trying to get article {article_id}...")
                resp, article_info = conn.article(f"{article_id}")

                # Print article headers
                logger.info("Article headers:")
                for i, line in enumerate(article_info.lines[:20]):  # Print first 20 lines
                    line_str = line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line
                    logger.info(f"  {line_str}")
            except Exception as e:
                logger.error(f"Error with alt.binaries.multimedia: {str(e)}")

            conn.quit()
        except Exception as e:
            logger.error(f"Connection with authentication failed: {str(e)}")


async def main():
    """Main function"""
    logger.info("Starting NNTP connection test")
    await test_nntp_connection()
    logger.info("NNTP connection test complete")


if __name__ == "__main__":
    asyncio.run(main())
    print("NNTP connection test complete!")
