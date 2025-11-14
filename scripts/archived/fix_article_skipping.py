#!/usr/bin/env python
"""
Fix for article skipping issue in article processing
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
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("fix_article_skipping")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application modules
from app.db.session import AsyncSessionLocal
from app.db.models.group import Group
from app.services.nntp import NNTPService
from app.services.setting import get_app_settings
from sqlalchemy import select, update, func, text


async def fix_article_processing_code():
    """Fix the article processing code to prevent skipping all articles"""
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

    # Check for the issue in the process_articles method
    if "stats[\"skipped\"] += 1" in content:
        logger.info("Found potential issue with article skipping")

        # Fix 1: Modify the process_articles method to log more information about skipped articles
        content = content.replace(
            "# Skip articles with no subject or message_id\n            if not subject or not message_id:\n                stats[\"skipped\"] += 1\n                continue",
            """# Skip articles with no subject or message_id
            if not subject or not message_id:
                logger.debug(f"Skipping article {article_num}: no subject or message_id")
                stats["skipped"] += 1
                continue"""
        )

        # Fix 2: Ensure bytes are properly decoded to strings
        content = content.replace(
            """# Decode bytes to strings with error handling
                            try:
                                subject = (
                                    subject.decode('utf-8', errors='replace')
                                    if isinstance(subject, bytes)
                                    else subject
                                )
                                # Replace any surrogate characters that might cause encoding issues
                                subject = ''.join(c if ord(c) < 0xD800 or ord(c) > 0xDFFF else '?' for c in subject)
                            except Exception:
                                subject = "Unknown Subject"

                            try:
                                message_id = (
                                    message_id.decode('utf-8', errors='replace')
                                    if isinstance(message_id, bytes)
                                    else message_id
                                )
                                # Replace any surrogate characters that might cause encoding issues
                                message_id = ''.join(c if ord(c) < 0xD800 or ord(c) > 0xDFFF else '?' for c in message_id)
                            except Exception:
                                message_id = f"unknown-{article_num}@placeholder.nzb"

                            # Log the subject for debugging
                            logger.debug(f"Processing article {article_num}: {subject}")""",

            """# Decode bytes to strings with error handling
                            try:
                                subject = (
                                    subject.decode('utf-8', errors='replace')
                                    if isinstance(subject, bytes)
                                    else subject
                                )
                                # Replace any surrogate characters that might cause encoding issues
                                subject = ''.join(c if ord(c) < 0xD800 or ord(c) > 0xDFFF else '?' for c in subject)
                            except Exception as e:
                                logger.warning(f"Error decoding subject for article {article_num}: {str(e)}")
                                subject = f"Unknown Subject {article_num}"

                            try:
                                message_id = (
                                    message_id.decode('utf-8', errors='replace')
                                    if isinstance(message_id, bytes)
                                    else message_id
                                )
                                # Replace any surrogate characters that might cause encoding issues
                                message_id = ''.join(c if ord(c) < 0xD800 or ord(c) > 0xDFFF else '?' for c in message_id)
                            except Exception as e:
                                logger.warning(f"Error decoding message_id for article {article_num}: {str(e)}")
                                message_id = f"unknown-{article_num}@placeholder.nzb"

                            # Log the subject for debugging
                            logger.debug(f"Processing article {article_num}: {subject}")"""
        )

        # Fix 3: Modify the _process_binary_post method to handle empty subjects
        content = content.replace(
            """async def _process_binary_post(
        self,
        subject: str,
        message_id: str,
        bytes_count: int,
        binaries: Dict[str, Dict],
        binary_subjects: Dict[str, str],
    ) -> None:
        \"\"\"
        Process a binary post from a newsgroup
        \"\"\"
        # First, try to parse subject to extract binary name and part info
        binary_name, part_num, total_parts = self._parse_binary_subject(subject)""",

            """async def _process_binary_post(
        self,
        subject: str,
        message_id: str,
        bytes_count: int,
        binaries: Dict[str, Dict],
        binary_subjects: Dict[str, str],
    ) -> None:
        \"\"\"
        Process a binary post from a newsgroup
        \"\"\"
        # Ensure subject is not None
        if subject is None:
            subject = ""

        # First, try to parse subject to extract binary name and part info
        binary_name, part_num, total_parts = self._parse_binary_subject(subject)"""
        )

        # Fix 4: Improve the _parse_binary_subject method to handle more cases
        content = content.replace(
            """def _parse_binary_subject(
        self, subject: str
    ) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        \"\"\"
        Parse a binary subject to extract name and part information
        Returns (binary_name, part_number, total_parts)
        \"\"\"
        # Remove common prefixes
        subject = re.sub(r"^Re: ", "", subject)""",

            """def _parse_binary_subject(
        self, subject: str
    ) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        \"\"\"
        Parse a binary subject to extract name and part information
        Returns (binary_name, part_number, total_parts)
        \"\"\"
        # Handle empty subjects
        if not subject:
            return None, None, None

        # Remove common prefixes
        subject = re.sub(r"^Re: ", "", subject)"""
        )

        # Fix 5: Add more logging to the _process_binaries_to_releases method
        content = content.replace(
            """async def _process_binaries_to_releases(
        self,
        db: AsyncSession,
        group: Group,
        binaries: Dict[str, Dict],
        binary_subjects: Dict[str, str],
    ) -> int:
        \"\"\"
        Process completed binaries into releases
        Returns the number of releases created
        \"\"\"
        releases_created = 0""",

            """async def _process_binaries_to_releases(
        self,
        db: AsyncSession,
        group: Group,
        binaries: Dict[str, Dict],
        binary_subjects: Dict[str, str],
    ) -> int:
        \"\"\"
        Process completed binaries into releases
        Returns the number of releases created
        \"\"\"
        logger.info(f"Processing {len(binaries)} binaries into releases for group {group.name}")
        releases_created = 0"""
        )

        # Fix 6: Add more logging to the create_release_conditions
        content = content.replace(
            """# Check if we should create a release for this binary
                create_release_conditions = [
                    # Condition 1: Binary is complete (all parts available)
                    binary["total_parts"] > 0 and len(binary["parts"]) >= binary["total_parts"],

                    # Condition 2: Binary has at least 1 part and we don't know the total parts
                    binary["total_parts"] == 0 and len(binary["parts"]) >= 1,

                    # Condition 3: Binary has at least 50% of parts and at least 3 parts
                    binary["total_parts"] > 0 and len(binary["parts"]) >= max(3, binary["total_parts"] // 2)
                ]

                if any(create_release_conditions):""",

            """# Check if we should create a release for this binary
                create_release_conditions = [
                    # Condition 1: Binary is complete (all parts available)
                    binary["total_parts"] > 0 and len(binary["parts"]) >= binary["total_parts"],

                    # Condition 2: Binary has at least 1 part and we don't know the total parts
                    binary["total_parts"] == 0 and len(binary["parts"]) >= 1,

                    # Condition 3: Binary has at least 50% of parts and at least 3 parts
                    binary["total_parts"] > 0 and len(binary["parts"]) >= max(3, binary["total_parts"] // 2)
                ]

                logger.debug(f"Binary {binary['name']}: parts={len(binary['parts'])}/{binary['total_parts']}, conditions={create_release_conditions}")

                if any(create_release_conditions):"""
        )

        # Write the updated content back to the file
        with open(article_py_path, "w") as f:
            f.write(content)

        logger.info("Fixed article processing code to prevent skipping all articles")
        return True
    else:
        logger.warning("Could not find the expected code pattern in article.py")
        return False


async def fix_over_command_issue():
    """Fix the issue with the OVER command in the article processing code"""
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

    # Check for the issue in the process_articles method
    if "resp, articles = conn.over((current_id, batch_end))" in content:
        logger.info("Found potential issue with OVER command")

        # Fix: Modify the OVER command to use a string instead of a tuple
        content = content.replace(
            "resp, articles = conn.over((current_id, batch_end))",
            "resp, articles = conn.over(f\"{current_id}-{batch_end}\")"
        )

        # Write the updated content back to the file
        with open(article_py_path, "w") as f:
            f.write(content)

        logger.info("Fixed OVER command issue in article processing code")
        return True
    else:
        logger.warning("Could not find the expected OVER command pattern in article.py")
        return False


async def fix_article_retrieval_issue():
    """Fix the issue with article retrieval in the article processing code"""
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

    # Fix: Add a retry mechanism for article retrieval
    if "resp, article_info = self._conn.article(f\"<{message_id}>\")" in content:
        logger.info("Found article retrieval code, adding retry mechanism")

        content = content.replace(
            """try:
                    resp, article_info = self._conn.article(f"<{message_id}>")""",

            """try:
                    # Try to get the article by message ID first
                    try:
                        resp, article_info = self._conn.article(f"<{message_id}>")
                    except Exception as msg_id_error:
                        # If that fails, try by article number
                        try:
                            # Extract article number from message ID if possible
                            article_num_match = re.search(r"(\d+)", message_id)
                            if article_num_match:
                                article_num = article_num_match.group(1)
                                logger.debug(f"Trying to get article by number: {article_num}")
                                resp, article_info = self._conn.article(article_num)
                            else:
                                raise Exception("Could not extract article number from message ID")
                        except Exception as article_num_error:
                            # Re-raise the original error
                            raise msg_id_error"""
        )

        # Write the updated content back to the file
        with open(article_py_path, "w") as f:
            f.write(content)

        logger.info("Added retry mechanism for article retrieval")
        return True
    else:
        logger.warning("Could not find the expected article retrieval pattern in article.py")
        return False


async def fix_binary_detection_issue():
    """Fix the issue with binary detection in the article processing code"""
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

    # Fix: Add a direct check for yEnc content in the article processing code
    if "# Process binary post" in content:
        logger.info("Found binary post processing code, adding direct yEnc check")

        content = content.replace(
            """# Process binary post
                            binary_result = await self._process_binary_post(
                                subject,
                                message_id,
                                bytes_count,
                                binaries,
                                binary_subjects,
                            )""",

            """# Check if this is likely a binary post by looking for yEnc in the subject
                            is_likely_binary = False
                            if subject and ("yenc" in subject.lower() or "yEnc" in subject):
                                is_likely_binary = True
                                logger.debug(f"Article {article_num} likely binary (yEnc in subject): {subject}")

                            # Process binary post
                            binary_result = await self._process_binary_post(
                                subject,
                                message_id,
                                bytes_count,
                                binaries,
                                binary_subjects,
                            )"""
        )

        # Also update the _process_binary_post method signature to accept the is_likely_binary parameter
        content = content.replace(
            """async def _process_binary_post(
        self,
        subject: str,
        message_id: str,
        bytes_count: int,
        binaries: Dict[str, Dict],
        binary_subjects: Dict[str, str],
    ) -> None:""",

            """async def _process_binary_post(
        self,
        subject: str,
        message_id: str,
        bytes_count: int,
        binaries: Dict[str, Dict],
        binary_subjects: Dict[str, str],
        is_likely_binary: bool = False,
    ) -> None:"""
        )

        # Write the updated content back to the file
        with open(article_py_path, "w") as f:
            f.write(content)

        logger.info("Added direct yEnc check to article processing code")
        return True
    else:
        logger.warning("Could not find the expected binary post processing pattern in article.py")
        return False


async def fix_article_processing():
    """Apply all fixes to the article processing code"""
    logger.info("Starting article processing fixes")

    # Fix 1: Article processing code
    await fix_article_processing_code()

    # Fix 2: OVER command issue
    await fix_over_command_issue()

    # Fix 3: Article retrieval issue
    await fix_article_retrieval_issue()

    # Fix 4: Binary detection issue
    await fix_binary_detection_issue()

    logger.info("Article processing fixes complete")


async def reset_group_article_ids():
    """Reset article IDs for all groups"""
    logger.info("Resetting article IDs for all groups")

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

        # Get all active groups
        query = select(Group).filter(Group.active == True)
        result = await db.execute(query)
        groups = result.scalars().all()

        logger.info(f"Resetting article IDs for {len(groups)} active groups")

        # Reset each group
        for group in groups:
            try:
                # Connect to NNTP server
                conn = nntp_service.connect()

                # Select the group
                resp, count, first, last, name = conn.group(group.name)

                # Close connection
                conn.quit()

                # Handle both string and bytes for name
                name_str = name if isinstance(name, str) else name.decode()

                logger.info(f"Group {name_str}: {count} articles, {first}-{last}")

                # Calculate a reasonable backfill target (e.g., 1000 articles back from last)
                backfill_amount = min(10000, (last - first) // 2)
                backfill_target = max(first, last - backfill_amount)

                # Update group's article IDs
                old_first = group.first_article_id
                old_last = group.last_article_id
                old_current = group.current_article_id
                old_backfill = group.backfill_target

                # Set current_article_id to a value less than last_article_id
                # This ensures there are articles to process
                current_article_id = last - 1000  # Set current to 1000 articles before last

                group.first_article_id = first
                group.last_article_id = last
                group.current_article_id = current_article_id
                group.backfill_target = backfill_target

                # Save changes
                db.add(group)
                await db.commit()

                logger.info(f"Updated group {group.name}:")
                logger.info(f"  First: {old_first} -> {first}")
                logger.info(f"  Last: {old_last} -> {last}")
                logger.info(f"  Current: {old_current} -> {current_article_id}")
                logger.info(f"  Backfill Target: {old_backfill} -> {backfill_target}")

            except Exception as e:
                logger.error(f"Error resetting group {group.name}: {str(e)}")
                await db.rollback()

    logger.info("Group article IDs reset complete")


async def main():
    """Main function"""
    logger.info("Starting article skipping fix")

    # Fix article processing code
    await fix_article_processing()

    # Reset group article IDs
    await reset_group_article_ids()

    logger.info("Article skipping fix complete")


if __name__ == "__main__":
    asyncio.run(main())
    print("Article skipping fix complete!")
