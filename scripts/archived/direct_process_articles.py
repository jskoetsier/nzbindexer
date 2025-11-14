#!/usr/bin/env python
"""
Direct article processing script
This script directly processes articles from a specific group and range
"""

import asyncio
import logging
import os
import sys
import re
from typing import Dict, List, Optional, Set, Tuple, Union
from datetime import datetime

# Configure logging - set to DEBUG for maximum information
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger("direct_process")

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


class DirectArticleService(ArticleService):
    """
    Enhanced ArticleService with direct processing capabilities
    """

    async def process_articles_direct(
        self,
        db,
        group,
        start_id,
        end_id,
        limit=100,  # Reduced batch size
        batch_size=10,  # Even smaller batch size for processing
    ):
        """
        Process articles directly with enhanced logging and error handling
        """
        stats = {
            "total": 0,
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "binaries": 0,
            "releases": 0,
        }

        try:
            # Connect to NNTP server
            conn = self.nntp_service.connect()

            # Select the group
            resp, count, first, last, name = conn.group(group.name)
            # Handle both string and bytes for name
            name_str = name if isinstance(name, str) else name.decode()
            logger.info(f"Selected group {name_str}: {count} articles, {first}-{last}")

            # Adjust start and end if needed
            start_id = max(start_id, first)
            end_id = min(end_id, last)

            # Limit the number of articles to process
            if end_id - start_id + 1 > limit:
                end_id = start_id + limit - 1

            stats["total"] = end_id - start_id + 1
            logger.info(f"Processing {stats['total']} articles from {start_id} to {end_id}")

            # Process articles in smaller batches
            current_id = start_id

            # Track binaries and parts
            binaries = {}  # Dict to track binary parts by message-id
            binary_subjects = {}  # Dict to track binary names by subject

            while current_id <= end_id:
                batch_end = min(current_id + batch_size - 1, end_id)
                logger.info(f"Processing batch {current_id}-{batch_end}")

                try:
                    # Try to get article headers for the batch using OVER command with string format
                    try:
                        logger.debug(f"Trying OVER command with range: {current_id}-{batch_end}")
                        resp, articles = conn.over(f"{current_id}-{batch_end}")
                    except Exception as e:
                        # If OVER command fails, try using HEAD command for each article
                        logger.warning(f"OVER command failed: {str(e)}. Falling back to HEAD command.")
                        articles = []
                        for article_id in range(current_id, batch_end + 1):
                            try:
                                # Get article headers using HEAD command
                                logger.debug(f"Trying HEAD command for article {article_id}")
                                resp, article_info = conn.head(f"{article_id}")

                                # Extract basic info from headers
                                article_num = article_id
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
                                    articles.append((article_num, subject, None, None, message_id, None, 0, 0, {}))
                                    logger.debug(f"Added article {article_id} with subject: {subject}")
                            except Exception as article_e:
                                # Skip articles that can't be retrieved
                                logger.debug(f"Skipping article {article_id}: {str(article_e)}")
                                continue

                    # Process each article
                    logger.info(f"Processing {len(articles)} articles in batch")
                    for article in articles:
                        article_num = None  # Initialize article_num to avoid reference errors
                        try:
                            # Extract article info - handle different tuple lengths
                            if len(article) >= 9:
                                (
                                    article_num,
                                    subject,
                                    from_addr,
                                    date,
                                    message_id,
                                    references,
                                    bytes_count,
                                    lines_count,
                                    other,
                                ) = article
                            elif len(article) == 2:
                                # Some NNTP servers return only article number and message ID
                                article_num, message_id = article
                                subject = ""
                                from_addr = ""
                                date = None
                                references = ""
                                bytes_count = 0
                                lines_count = 0
                                other = {}
                            else:
                                # Handle other unexpected formats
                                logger.warning(f"Unexpected article format: {article}")
                                stats["skipped"] += 1
                                continue

                            # Handle empty subjects or message_ids
                            if not subject:
                                subject = f"Unknown Subject {article_num}"
                                logger.debug(f"Using placeholder subject for article {article_num}")

                            if not message_id:
                                message_id = f"unknown-{article_num}@placeholder.nzb"
                                logger.debug(f"Using placeholder message_id for article {article_num}")

                            # Decode bytes to strings with error handling
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
                            logger.debug(f"Processing article {article_num}: {subject}")

                            # Check if this is likely a binary post by looking for yEnc in the subject
                            is_likely_binary = False
                            if "yenc" in subject.lower() or "yEnc" in subject:
                                is_likely_binary = True
                                logger.debug(f"Article {article_num} likely binary (yEnc in subject): {subject}")

                            # Process binary post with enhanced error handling
                            try:
                                binary_result = await self._process_binary_post_direct(
                                    article_num,
                                    subject,
                                    message_id,
                                    bytes_count,
                                    binaries,
                                    binary_subjects,
                                    is_likely_binary=is_likely_binary,
                                )

                                if binary_result:
                                    logger.info(f"Found binary post: {subject} -> {binary_result}")
                            except Exception as binary_e:
                                logger.error(f"Error processing binary post {article_num}: {str(binary_e)}")
                                # Continue processing other articles even if this one fails

                            stats["processed"] += 1

                        except Exception as e:
                            error_msg = f"Error processing article: {str(e)}"
                            if article_num is not None:
                                error_msg = f"Error processing article {article_num}: {str(e)}"
                            logger.error(error_msg)
                            stats["failed"] += 1

                except Exception as e:
                    logger.error(f"Error getting articles {current_id}-{batch_end}: {str(e)}")
                    stats["failed"] += batch_end - current_id + 1

                # Move to next batch
                current_id = batch_end + 1

                # Process binaries to releases after each batch to avoid memory issues
                if len(binaries) > 0:
                    logger.info(f"Processing {len(binaries)} binaries to releases after batch")
                    releases_created = await self._process_binaries_to_releases_direct(
                        db, group, binaries, binary_subjects
                    )
                    stats["releases"] += releases_created
                    stats["binaries"] = len(binaries)

                    # Clear processed binaries to free memory
                    binaries = {}
                    binary_subjects = {}

            # Process any remaining binaries into releases
            if len(binaries) > 0:
                logger.info(f"Processing {len(binaries)} remaining binaries to releases")
                releases_created = await self._process_binaries_to_releases_direct(
                    db, group, binaries, binary_subjects
                )
                stats["releases"] += releases_created
                stats["binaries"] = len(binaries)

            # Close connection
            conn.quit()

            return stats

        except Exception as e:
            logger.error(f"Failed to process articles: {str(e)}")
            raise

    async def _process_binary_post_direct(
        self,
        article_num,
        subject: str,
        message_id: str,
        bytes_count: int,
        binaries: Dict[str, Dict],
        binary_subjects: Dict[str, str],
        is_likely_binary: bool = False,
    ):
        """
        Process a binary post with enhanced error handling
        """
        logger.debug(f"Processing binary post: article={article_num}, subject='{subject}'")

        # Ensure subject is not None
        if subject is None:
            subject = ""

        # First, try to parse subject to extract binary name and part info
        binary_name, part_num, total_parts = self._parse_binary_subject(subject)
        logger.debug(f"Subject parsing result: binary_name='{binary_name}', part_num={part_num}, total_parts={total_parts}")

        # If we couldn't extract binary info from the subject, check if this is an obfuscated binary post
        if not binary_name or not part_num:
            logger.debug(f"Subject parsing failed for article {article_num}, checking for obfuscated binary post")

            # For obfuscated posts, we need to get the article content to check for yEnc headers
            try:
                # Connect to NNTP server if needed
                if not hasattr(self, '_conn') or self._conn is None:
                    logger.debug("Connecting to NNTP server")
                    self._conn = self.nntp_service.connect()

                # Get the article content
                try:
                    # Try to get the article by message ID first
                    try:
                        logger.debug(f"Getting article content for message_id: {message_id}")
                        resp, article_info = self._conn.article(f"<{message_id}>")
                    except Exception as msg_id_error:
                        # If that fails, try by article number
                        try:
                            logger.debug(f"Message ID failed, trying article number: {article_num}")
                            resp, article_info = self._conn.article(f"{article_num}")
                        except Exception as article_num_error:
                            # Re-raise the original error
                            raise msg_id_error

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
                        logger.debug(f"No yEnc headers found in article content for article {article_num}")

                except Exception as e:
                    logger.error(f"Error getting article content for article {article_num}: {str(e)}")

            except Exception as e:
                logger.error(f"Error checking for obfuscated binary post for article {article_num}: {str(e)}")

        # If we still couldn't extract binary info, skip this post
        if not binary_name or not part_num:
            logger.debug(f"Could not extract binary info for article {article_num}, skipping post")
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

    async def _process_binaries_to_releases_direct(
        self,
        db,
        group,
        binaries,
        binary_subjects,
    ):
        """
        Process completed binaries into releases with relaxed conditions
        """
        logger.info(f"Processing {len(binaries)} binaries to releases for group {group.name}")
        releases_created = 0

        # Get default category ID for uncategorized releases
        from app.db.models.category import Category

        try:
            query = select(Category).filter(Category.name == "Other")
            result = await db.execute(query)
            default_category = result.scalars().first()

            if not default_category:
                # Create default category if it doesn't exist
                default_category = Category(
                    name="Other",
                    description="Uncategorized releases",
                    active=True,
                    sort_order=999,
                )
                db.add(default_category)
                await db.commit()
                await db.refresh(default_category)
                logger.info("Created default 'Other' category")
        except Exception as e:
            # If there's an error creating the category (e.g., it already exists),
            # try to get it again
            logger.warning(f"Error creating default category: {str(e)}")
            await db.rollback()

            # Try to get the category again
            query = select(Category).filter(Category.name == "Other")
            result = await db.execute(query)
            default_category = result.scalars().first()

            # If we still can't get it, use the first available category
            if not default_category:
                query = select(Category).limit(1)
                result = await db.execute(query)
                default_category = result.scalars().first()

                # If there are no categories at all, we can't proceed
                if not default_category:
                    logger.error("No categories found in database")
                    return 0

        # Process each binary
        for binary_key, binary in binaries.items():
            try:
                # Log binary details
                logger.info(f"Binary: {binary['name']}")
                logger.info(f"  Parts: {len(binary['parts'])}/{binary['total_parts']}")
                logger.info(f"  Size: {binary['size']}")

                # Check if we should create a release for this binary
                # Use more relaxed conditions than the original code
                create_release_conditions = [
                    # Condition 1: Binary is complete (all parts available)
                    binary["total_parts"] > 0 and len(binary["parts"]) >= binary["total_parts"],

                    # Condition 2: Binary has at least 1 part and we don't know the total parts
                    binary["total_parts"] == 0 and len(binary["parts"]) >= 1,

                    # Condition 3: Binary has at least 25% of parts and at least 2 parts (more relaxed)
                    binary["total_parts"] > 0 and len(binary["parts"]) >= max(2, binary["total_parts"] // 4),

                    # Condition 4: Binary has at least 5 parts (for large binaries)
                    len(binary["parts"]) >= 5
                ]

                logger.info(f"  Create release conditions: {create_release_conditions}")
                logger.info(f"  Should create release: {any(create_release_conditions)}")

                if any(create_release_conditions):
                    # Calculate completion percentage
                    completion = 100.0
                    if binary["total_parts"] > 0:
                        completion = min(100.0, (len(binary["parts"]) / binary["total_parts"]) * 100.0)

                    # Check if release already exists
                    from app.services.release import create_release_guid

                    guid = create_release_guid(binary["name"], group.name)

                    query = select(Release).filter(Release.guid == guid)
                    result = await db.execute(query)
                    existing_release = result.scalars().first()

                    if existing_release:
                        # Update existing release if we have more parts now
                        if len(binary["parts"]) > existing_release.files:
                            existing_release.files = len(binary["parts"])
                            existing_release.size = binary["size"]
                            existing_release.completion = completion
                            db.add(existing_release)
                            await db.commit()
                            logger.info(f"Updated release {existing_release.id} with more parts: {len(binary['parts'])}")
                        continue

                    # Create new release
                    subject = binary_subjects.get(binary_key, binary["name"])
                    logger.info(f"Creating release for binary: {binary['name']} with {len(binary['parts'])}/{binary['total_parts']} parts")

                    from app.schemas.release import ReleaseCreate

                    # Create release
                    from app.services.release import create_release

                    release_data = ReleaseCreate(
                        name=binary["name"],
                        search_name=self._create_search_name(binary["name"]),
                        guid=guid,
                        size=binary["size"],
                        files=len(binary["parts"]),
                        completion=completion,
                        posted_date=datetime.utcnow(),  # Should use article date
                        status=1,  # Active
                        passworded=0,  # Unknown
                        category_id=default_category.id,
                        group_id=group.id,
                    )

                    try:
                        release = await create_release(db, release_data)
                        logger.info(f"Created release {release.id} for binary {binary['name']}")

                        # Generate NZB file for the release
                        try:
                            from app.services.nzb import NZBService
                            nzb_service = NZBService(nntp_service=self.nntp_service)
                            nzb_path = await nzb_service.generate_nzb(db, release.id)

                            if nzb_path:
                                logger.info(f"Generated NZB file for release {release.id}: {nzb_path}")
                            else:
                                logger.warning(f"Failed to generate NZB file for release {release.id}")
                        except Exception as nzb_e:
                            logger.error(f"Error generating NZB file for release {release.id}: {str(nzb_e)}")

                        releases_created += 1
                    except Exception as release_e:
                        logger.error(f"Error creating release for binary {binary['name']}: {str(release_e)}")
                        await db.rollback()

            except Exception as e:
                logger.error(f"Error processing binary {binary['name']}: {str(e)}")

        return releases_created


async def direct_process_group(group_name: str, limit: int = 200):
    """Process a specific group directly"""
    logger.info(f"Starting direct processing for group {group_name}")

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

        # Create direct article service
        article_service = DirectArticleService(nntp_service=nntp_service)

        # Connect to NNTP server
        conn = nntp_service.connect()

        # Select the group
        resp, count, first, last, name = conn.group(group.name)

        # Close connection
        conn.quit()

        # Calculate range to process - use the most recent articles
        process_start = last - limit
        process_end = last

        logger.info(f"Processing articles {process_start} to {process_end} for group {group.name}")

        # Process articles directly
        stats = await article_service.process_articles_direct(
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
        await direct_process_group(group_name, 50)
        print("\n" + "-" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
    print("Direct article processing complete!")
