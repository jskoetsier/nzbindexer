#!/usr/bin/env python
"""
Script to fix detection of obfuscated binary posts
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
logger = logging.getLogger("fix_obfuscated")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application modules
from app.db.session import AsyncSessionLocal
from app.db.models.group import Group
from app.services.nntp import NNTPService
from app.services.setting import get_app_settings
from sqlalchemy import select


async def update_article_processing_code():
    """Update the article processing code to handle obfuscated binary posts"""
    # Path to the article.py file
    article_py_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "app", "services", "article.py")

    # Check if the file exists
    if not os.path.exists(article_py_path):
        logger.error(f"Article processing code not found at {article_py_path}")
        return False

    # Read the current content
    with open(article_py_path, "r") as f:
        content = f.read()

    # Check if the file contains the _process_binary_post method
    if "_process_binary_post" not in content:
        logger.error("Could not find _process_binary_post method in article.py")
        return False

    # Update the _process_binary_post method to handle obfuscated binary posts
    updated_content = content.replace(
        "async def _process_binary_post(",
        """async def _process_binary_post_original(
        self,
        subject: str,
        message_id: str,
        bytes_count: int,
        binaries: Dict[str, Dict],
        binary_subjects: Dict[str, str],
    ) -> None:
        \"\"\"
        Original process_binary_post method
        \"\"\"
        # Parse subject to extract binary name and part info
        binary_name, part_num, total_parts = self._parse_binary_subject(subject)

        if not binary_name or not part_num:
            return

        # Create or update binary entry
        binary_key = self._get_binary_key(binary_name)

        if binary_key not in binaries:
            binaries[binary_key] = {
                "name": binary_name,
                "parts": {},
                "total_parts": total_parts or 0,
                "size": 0,
            }
            binary_subjects[binary_key] = subject

        # Add part to binary
        if part_num not in binaries[binary_key]["parts"]:
            binaries[binary_key]["parts"][part_num] = {
                "message_id": message_id,
                "size": bytes_count,
            }
            binaries[binary_key]["size"] += bytes_count

        # Update total parts if we have a new value
        if total_parts and binaries[binary_key]["total_parts"] < total_parts:
            binaries[binary_key]["total_parts"] = total_parts

    async def _process_binary_post(",
    )

    # Update the _process_binary_post method to check for yEnc headers in the article content
    updated_content = updated_content.replace(
        "# Parse subject to extract binary name and part info",
        """# First, try to parse subject to extract binary name and part info
        binary_name, part_num, total_parts = self._parse_binary_subject(subject)

        # If we couldn't extract binary info from the subject, check if this is an obfuscated binary post
        # by looking for yEnc headers in the article content
        if not binary_name or not part_num:
            # For obfuscated posts, we need to get the article content to check for yEnc headers
            try:
                # Connect to NNTP server if needed
                if not hasattr(self, '_conn') or self._conn is None:
                    self._conn = self.nntp_service.connect()

                # Get the article content
                try:
                    resp, article_info = self._conn.article(f"<{message_id}>")

                    # Look for yEnc headers in the article content
                    yenc_begin = None
                    yenc_part = None
                    yenc_name = None

                    for line in article_info.lines:
                        line_str = line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line

                        # Check for yEnc begin line
                        if line_str.startswith("=ybegin "):
                            yenc_begin = line_str

                            # Extract part info
                            part_match = re.search(r"part=(\d+)\s+total=(\d+)", line_str)
                            if part_match:
                                part_num = int(part_match.group(1))
                                total_parts = int(part_match.group(2))

                            # Extract name
                            name_match = re.search(r"name=(.*?)$", line_str)
                            if name_match:
                                yenc_name = name_match.group(1).strip()

                        # Check for yEnc part line
                        elif line_str.startswith("=ypart "):
                            yenc_part = line_str

                        # If we found both yEnc begin and part lines, we can stop
                        if yenc_begin and yenc_part and yenc_name:
                            break

                    # If we found yEnc headers, use the name from the yEnc header as the binary name
                    if yenc_name and part_num and total_parts:
                        binary_name = yenc_name
                        logger.debug(f"Found obfuscated binary post: {subject} -> {binary_name} (part {part_num}/{total_parts})")

                except Exception as e:
                    logger.debug(f"Error getting article content: {str(e)}")

            except Exception as e:
                logger.debug(f"Error checking for obfuscated binary post: {str(e)}")

        # If we still couldn't extract binary info, skip this post
        if not binary_name or not part_num:
            return

        # Parse subject to extract binary name and part info (original code continues here)""",
    )

    # Write the updated content back to the file
    with open(article_py_path, "w") as f:
        f.write(updated_content)

    logger.info(f"Updated article processing code to handle obfuscated binary posts")
    return True


async def test_obfuscated_binary_detection(db, group_name: str, limit: int = 10):
    """Test detection of obfuscated binary posts"""
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

    logger.info(f"Testing obfuscated binary detection on group: {group.name}")

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

        # Test each article for obfuscated binary content
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

                # Get the article content
                try:
                    resp, article_info = conn.article(f"{article_num}")

                    # Look for yEnc headers in the article content
                    yenc_begin = None
                    yenc_part = None
                    yenc_name = None

                    for line in article_info.lines[:20]:  # Check first 20 lines
                        line_str = line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line

                        # Check for yEnc begin line
                        if line_str.startswith("=ybegin "):
                            yenc_begin = line_str

                            # Extract part info
                            part_match = re.search(r"part=(\d+)\s+total=(\d+)", line_str)
                            if part_match:
                                part_num = int(part_match.group(1))
                                total_parts = int(part_match.group(2))
                            else:
                                part_num = 1
                                total_parts = 1

                            # Extract name
                            name_match = re.search(r"name=(.*?)$", line_str)
                            if name_match:
                                yenc_name = name_match.group(1).strip()

                        # Check for yEnc part line
                        elif line_str.startswith("=ypart "):
                            yenc_part = line_str

                        # If we found both yEnc begin and part lines, we can stop
                        if yenc_begin and yenc_name:
                            break

                    # If we found yEnc headers, this is an obfuscated binary post
                    if yenc_begin and yenc_name:
                        logger.info(f"Found obfuscated binary post: {article_num}")
                        logger.info(f"  Subject: {subject}")
                        logger.info(f"  yEnc name: {yenc_name}")
                        if part_match:
                            logger.info(f"  Part: {part_num}/{total_parts}")
                        logger.info("")

                except Exception as e:
                    logger.debug(f"Error getting article content: {str(e)}")

            except Exception as e:
                logger.error(f"Error testing article: {str(e)}")

        # Close connection
        conn.quit()

    except Exception as e:
        logger.error(f"Error testing obfuscated binary detection: {str(e)}")


async def main():
    """Main function"""
    logger.info("Starting obfuscated binary fix")

    async with AsyncSessionLocal() as db:
        # Test obfuscated binary detection on a few groups
        binary_groups = [
            "alt.binaries.teevee",
            "alt.binaries.moovee",
            "alt.binaries.movies",
            "alt.binaries.hdtv",
            "alt.binaries.multimedia",
        ]

        for group_name in binary_groups:
            await test_obfuscated_binary_detection(db, group_name, limit=5)
            print("\n" + "-" * 80 + "\n")  # Add separator between groups

        # Update article processing code
        await update_article_processing_code()

    logger.info("Obfuscated binary fix complete")


if __name__ == "__main__":
    asyncio.run(main())
    print("Obfuscated binary fix complete!")
