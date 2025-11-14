"""
Article service for processing Usenet articles
"""

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple, Union

from app.core.config import settings
from app.db.models.group import Group
from app.db.models.release import Release
from app.db.session import AsyncSession
from app.services.nntp import NNTPService

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ArticleService:
    """
    Service for processing Usenet articles
    """

    def __init__(self, nntp_service: Optional[NNTPService] = None):
        """
        Initialize the article service
        """
        self.nntp_service = nntp_service or NNTPService()

    async def process_articles(
        self,
        db: AsyncSession,
        group: Group,
        start_id: int,
        end_id: int,
        limit: int = 1000,
    ) -> Dict[str, any]:
        """
        Process articles from a group
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

            # Process articles in batches
            batch_size = 100
            current_id = start_id

            # Track binaries and parts
            binaries = {}  # Dict to track binary parts by message-id
            binary_subjects = {}  # Dict to track binary names by subject

            while current_id <= end_id:
                batch_end = min(current_id + batch_size - 1, end_id)

                try:
                    # Try to get article headers for the batch using OVER command with string format
                    try:
                        resp, articles = conn.over(f"{current_id}-{batch_end}")
                    except Exception as e:
                        # If OVER command fails, try using HEAD command for each article
                        logger.warning(
                            f"OVER command failed: {str(e)}. Falling back to HEAD command."
                        )
                        articles = []
                        for article_id in range(current_id, batch_end + 1):
                            try:
                                # Get article headers using HEAD command
                                resp, article_info = conn.head(f"<{article_id}>")

                                # Extract basic info from headers
                                article_num = article_id
                                subject = None
                                message_id = None

                                # Parse headers
                                for line in article_info.lines:
                                    line_str = (
                                        line.decode()
                                        if isinstance(line, bytes)
                                        else line
                                    )
                                    if line_str.startswith("Subject:"):
                                        subject = line_str[8:].strip()
                                    elif line_str.startswith("Message-ID:"):
                                        message_id = line_str[10:].strip()

                                if subject and message_id:
                                    articles.append(
                                        (
                                            article_num,
                                            subject,
                                            None,
                                            None,
                                            message_id,
                                            None,
                                            0,
                                            0,
                                            {},
                                        )
                                    )
                            except Exception as article_e:
                                # Skip articles that can't be retrieved
                                logger.debug(
                                    f"Skipping article {article_id}: {str(article_e)}"
                                )
                                continue

                    # Process each article
                    for article in articles:
                        article_num = (
                            None  # Initialize article_num to avoid reference errors
                        )
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

                            # Skip articles with no subject or message_id
                            if not subject or not message_id:
                                stats["skipped"] += 1
                                continue

                            # Decode bytes to strings with error handling
                            try:
                                subject = (
                                    subject.decode("utf-8", errors="replace")
                                    if isinstance(subject, bytes)
                                    else subject
                                )
                                # Replace any surrogate characters that might cause encoding issues
                                subject = "".join(
                                    c if ord(c) < 0xD800 or ord(c) > 0xDFFF else "?"
                                    for c in subject
                                )
                            except Exception:
                                subject = "Unknown Subject"

                            try:
                                message_id = (
                                    message_id.decode("utf-8", errors="replace")
                                    if isinstance(message_id, bytes)
                                    else message_id
                                )
                                # Replace any surrogate characters that might cause encoding issues
                                message_id = "".join(
                                    c if ord(c) < 0xD800 or ord(c) > 0xDFFF else "?"
                                    for c in message_id
                                )
                            except Exception:
                                message_id = f"unknown-{article_num}@placeholder.nzb"

                            # Log the subject for debugging
                            if stats["processed"] % 100 == 0:  # Log every 100th article
                                logger.info(
                                    f"Sample subject at article {article_num}: {subject}"
                                )

                            # Process binary post
                            binary_result = await self._process_binary_post(
                                subject,
                                message_id,
                                bytes_count,
                                binaries,
                                binary_subjects,
                            )

                            if binary_result:
                                logger.info(
                                    f"Found binary post: {subject} -> {binary_result}"
                                )

                            stats["processed"] += 1

                        except Exception as e:
                            error_msg = f"Error processing article: {str(e)}"
                            if article_num is not None:
                                error_msg = (
                                    f"Error processing article {article_num}: {str(e)}"
                                )
                            logger.error(error_msg)
                            stats["failed"] += 1

                except Exception as e:
                    logger.error(
                        f"Error getting articles {current_id}-{batch_end}: {str(e)}"
                    )
                    stats["failed"] += batch_end - current_id + 1

                # Move to next batch
                current_id = batch_end + 1

            # Process completed binaries into releases
            stats["binaries"] = len(binaries)
            releases_created = await self._process_binaries_to_releases(
                db, group, binaries, binary_subjects
            )
            stats["releases"] = releases_created

            # Close connection
            conn.quit()

            return stats

        except Exception as e:
            logger.error(f"Failed to process articles: {str(e)}")
            raise

    async def _process_binary_post(
        self,
        subject: str,
        message_id: str,
        bytes_count: int,
        binaries: Dict[str, Dict],
        binary_subjects: Dict[str, str],
    ) -> None:
        """
        Process a binary post from a newsgroup
        """
        # Ensure subject is not None
        if subject is None:
            subject = ""

        # First, try to parse subject to extract binary name and part info
        binary_name, part_num, total_parts = self._parse_binary_subject(subject)

        # Check if this is likely a binary post by looking for yEnc in the subject
        is_likely_binary = False
        if "yenc" in subject.lower() or "yEnc" in subject:
            is_likely_binary = True
            logger.debug(f"Likely binary post (yEnc in subject): {subject}")

        # If we couldn't extract binary info from the subject, check if this is an obfuscated binary post
        # by looking for yEnc headers in the article content
        if not binary_name or not part_num:
            # For obfuscated posts, we need to get the article content to check for yEnc headers
            try:
                # Connect to NNTP server if needed
                if not hasattr(self, "_conn") or self._conn is None:
                    self._conn = self.nntp_service.connect()

                # Get the article content
                try:
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
                                logger.debug(
                                    f"Trying to get article by number: {article_num}"
                                )
                                resp, article_info = self._conn.article(article_num)
                            else:
                                raise Exception(
                                    "Could not extract article number from message ID"
                                )
                        except Exception as article_num_error:
                            # Re-raise the original error
                            raise msg_id_error

                    # Look for yEnc headers in the article content
                    yenc_begin = None
                    yenc_part = None
                    yenc_name = None

                    for line in article_info.lines[:30]:  # Check first 30 lines
                        line_str = (
                            line.decode("utf-8", errors="replace")
                            if isinstance(line, bytes)
                            else line
                        )

                        # Check for yEnc begin line
                        if line_str.startswith("=ybegin "):
                            yenc_begin = line_str
                            logger.debug(f"Found yEnc begin line: {yenc_begin}")

                            # Extract part info
                            part_match = re.search(
                                r"part=(\d+)\s+total=(\d+)", line_str
                            )
                            if part_match:
                                part_num = int(part_match.group(1))
                                total_parts = int(part_match.group(2))
                                logger.debug(
                                    f"Extracted part info: part_num={part_num}, total_parts={total_parts}"
                                )

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
                        if yenc_begin and (yenc_part or part_match) and yenc_name:
                            break

                    # If we found yEnc headers, use the name from the yEnc header as the binary name
                    if yenc_name and part_num and total_parts:
                        binary_name = yenc_name
                        logger.info(
                            f"Found obfuscated binary post: {subject} -> {binary_name} (part {part_num}/{total_parts})"
                        )
                    elif yenc_name and part_num:
                        binary_name = yenc_name
                        total_parts = 1  # Assume single part if total not specified
                        logger.info(
                            f"Found obfuscated binary post with unknown total parts: {subject} -> {binary_name} (part {part_num})"
                        )
                    elif is_likely_binary:
                        # If we think it's a binary post but couldn't extract all info, try to use what we have
                        if not binary_name and yenc_name:
                            binary_name = yenc_name
                        if not part_num:
                            part_num = 1  # Assume part 1 if not specified
                        if not total_parts:
                            total_parts = 1  # Assume single part if not specified
                        logger.info(
                            f"Reconstructed binary post info: {subject} -> {binary_name} (part {part_num}/{total_parts})"
                        )

                except Exception as e:
                    logger.debug(f"Error getting article content: {str(e)}")

            except Exception as e:
                logger.debug(f"Error checking for obfuscated binary post: {str(e)}")

        # If we still couldn't extract binary info, skip this post
        if not binary_name or not part_num:
            logger.debug(
                f"Skipping article - could not extract binary info from subject: {subject}"
            )
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

        # Return binary info for logging
        return f"{binary_name} (part {part_num}/{total_parts})"

    def _parse_binary_subject(
        self, subject: str
    ) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        """
        Parse a binary subject to extract name and part information
        Returns (binary_name, part_number, total_parts)
        """
        # Remove common prefixes
        subject = re.sub(r"^Re: ", "", subject)

        # Try to match common binary post patterns

        # Pattern: "name [01/10] - description"
        match = re.search(r"^(.*?)\s*\[(\d+)/(\d+)\]", subject)
        if match:
            name = match.group(1).strip()
            part = int(match.group(2))
            total = int(match.group(3))
            return name, part, total

        # Pattern: "name (01/10) - description"
        match = re.search(r"^(.*?)\s*\((\d+)/(\d+)\)", subject)
        if match:
            name = match.group(1).strip()
            part = int(match.group(2))
            total = int(match.group(3))
            return name, part, total

        # Pattern: "name - 01/10 - description"
        match = re.search(r"^(.*?)\s*-\s*(\d+)/(\d+)", subject)
        if match:
            name = match.group(1).strip()
            part = int(match.group(2))
            total = int(match.group(3))
            return name, part, total

        # Pattern: "name - Part 01 of 10 - description"
        match = re.search(r"^(.*?)\s*-\s*[Pp]art\s*(\d+)\s*of\s*(\d+)", subject)
        if match:
            name = match.group(1).strip()
            part = int(match.group(2))
            total = int(match.group(3))
            return name, part, total

        # Pattern: "name - File 01 of 10 - description"
        match = re.search(r"^(.*?)\s*-\s*[Ff]ile\s*(\d+)\s*of\s*(\d+)", subject)
        if match:
            name = match.group(1).strip()
            part = int(match.group(2))
            total = int(match.group(3))
            return name, part, total

        # Pattern: "name - yEnc (01/10) - description"
        match = re.search(r"^(.*?)\s*-\s*yEnc\s*\((\d+)/(\d+)\)", subject)
        if match:
            name = match.group(1).strip()
            part = int(match.group(2))
            total = int(match.group(3))
            return name, part, total

        # Pattern: "name - yEnc - (01/10) - description"
        match = re.search(r"^(.*?)\s*-\s*yEnc\s*-\s*\((\d+)/(\d+)\)", subject)
        if match:
            name = match.group(1).strip()
            part = int(match.group(2))
            total = int(match.group(3))
            return name, part, total

        # Pattern: "name (yEnc 01/10) - description"
        match = re.search(r"^(.*?)\s*\(yEnc\s*(\d+)/(\d+)\)", subject)
        if match:
            name = match.group(1).strip()
            part = int(match.group(2))
            total = int(match.group(3))
            return name, part, total

        # Pattern: "name - yEnc (01/10)"
        match = re.search(r"^(.*?)\s*-\s*yEnc\s*\((\d+)/(\d+)\)\s*$", subject)
        if match:
            name = match.group(1).strip()
            part = int(match.group(2))
            total = int(match.group(3))
            return name, part, total

        # Pattern: "name [01/10]"
        match = re.search(r"^(.*?)\s*\[(\d+)/(\d+)\]\s*$", subject)
        if match:
            name = match.group(1).strip()
            part = int(match.group(2))
            total = int(match.group(3))
            return name, part, total

        # Pattern: "name (01/10)"
        match = re.search(r"^(.*?)\s*\((\d+)/(\d+)\)\s*$", subject)
        if match:
            name = match.group(1).strip()
            part = int(match.group(2))
            total = int(match.group(3))
            return name, part, total

        # Single file pattern: "name - yEnc"
        match = re.search(r"^(.*?)\s*-\s*yEnc\s*$", subject)
        if match:
            name = match.group(1).strip()
            return name, 1, 1  # Treat as a single part

        # No pattern matched
        return None, None, None

    def _get_binary_key(self, binary_name: str) -> str:
        """
        Generate a consistent key for a binary name
        """
        # Normalize the binary name to create a consistent key
        key = binary_name.lower()
        key = re.sub(r"[^a-z0-9]", "", key)
        return key

    async def _process_binaries_to_releases(
        self,
        db: AsyncSession,
        group: Group,
        binaries: Dict[str, Dict],
        binary_subjects: Dict[str, str],
    ) -> int:
        """
        Process completed binaries into releases
        Returns the number of releases created
        """
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
                # Check if we should create a release for this binary
                create_release_conditions = [
                    # Condition 1: Binary is complete (all parts available)
                    binary["total_parts"] > 0
                    and len(binary["parts"]) >= binary["total_parts"],
                    # Condition 2: Binary has at least 1 part and we don't know the total parts
                    binary["total_parts"] == 0 and len(binary["parts"]) >= 1,
                    # Condition 3: Binary has at least 25% of parts and at least 2 parts (more relaxed)
                    binary["total_parts"] > 0
                    and len(binary["parts"]) >= max(2, binary["total_parts"] // 4),
                    # Condition 4: Binary has at least 5 parts (for large binaries)
                    len(binary["parts"]) >= 5,
                ]

                logger.info(f"Binary: {binary['name']}")
                logger.info(f"  Parts: {len(binary['parts'])}/{binary['total_parts']}")
                logger.info(f"  Size: {binary['size']}")
                logger.info(f"  Create release conditions: {create_release_conditions}")
                logger.info(
                    f"  Should create release: {any(create_release_conditions)}"
                )

                if any(create_release_conditions):
                    # Calculate completion percentage
                    completion = 100.0
                    if binary["total_parts"] > 0:
                        completion = min(
                            100.0,
                            (len(binary["parts"]) / binary["total_parts"]) * 100.0,
                        )

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
                            logger.info(
                                f"Updated release {existing_release.id} with more parts: {len(binary['parts'])}"
                            )
                        continue

                    # Create new release
                    subject = binary_subjects.get(binary_key, binary["name"])
                    logger.info(
                        f"Creating release for binary: {binary['name']} with {len(binary['parts'])}/{binary['total_parts']} parts"
                    )

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
                        posted_date=datetime.now(
                            timezone.utc
                        ),  # Should use article date
                        status=1,  # Active
                        passworded=0,  # Unknown
                        category_id=default_category.id,
                        group_id=group.id,
                    )

                    release = await create_release(db, release_data)

                    # Generate NZB file for the release
                    from app.services.nzb import NZBService

                    nzb_service = NZBService(nntp_service=self.nntp_service)
                    nzb_path = await nzb_service.generate_nzb(db, release.id)

                    if nzb_path:
                        logger.info(
                            f"Generated NZB file for release {release.id}: {nzb_path}"
                        )
                    else:
                        logger.warning(
                            f"Failed to generate NZB file for release {release.id}"
                        )

                    releases_created += 1

            except Exception as e:
                logger.error(
                    f"Error creating release for binary {binary['name']}: {str(e)}"
                )

        return releases_created

    def _create_search_name(self, name: str) -> str:
        """
        Create a search-friendly name
        """
        # Remove special characters and convert to lowercase
        search_name = name.lower()
        search_name = re.sub(r"[^a-z0-9\s]", " ", search_name)
        search_name = re.sub(r"\s+", " ", search_name).strip()
        return search_name


async def process_group_update(
    db: AsyncSession,
    group: Group,
    limit: int = 1000,
    nntp_service: Optional[NNTPService] = None,
) -> Dict[str, any]:
    """
    Process new articles for a group
    """
    # Get app settings if nntp_service is not provided
    if not nntp_service:
        from app.services.setting import get_app_settings

        app_settings = await get_app_settings(db)

        # Create NNTP service with settings from database
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

    article_service = ArticleService(nntp_service=nntp_service)

    # Process articles from current_article_id to last_article_id
    stats = await article_service.process_articles(
        db, group, group.current_article_id, group.last_article_id, limit
    )

    # Update group's current_article_id
    if stats["processed"] > 0:
        group.current_article_id = group.last_article_id
        group.last_updated = datetime.now(timezone.utc)
        db.add(group)
        await db.commit()

    return stats


async def process_group_backfill(
    db: AsyncSession,
    group: Group,
    limit: int = 1000,
    nntp_service: Optional[NNTPService] = None,
) -> Dict[str, any]:
    """
    Process backfill articles for a group
    """
    # Get app settings if nntp_service is not provided
    if not nntp_service:
        from app.services.setting import get_app_settings

        app_settings = await get_app_settings(db)

        # Create NNTP service with settings from database
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

    article_service = ArticleService(nntp_service=nntp_service)

    # Ensure backfill_target is valid
    if group.backfill_target <= 0:
        logger.warning(
            f"Invalid backfill target for group {group.name}: {group.backfill_target}"
        )
        return {
            "processed": 0,
            "total": 0,
            "skipped": 0,
            "failed": 0,
            "binaries": 0,
            "releases": 0,
        }

    # Determine the range of articles to process
    start_id = group.backfill_target
    end_id = group.current_article_id - 1

    # If backfill_target is greater than current_article_id, we need to fix this
    if start_id >= end_id:
        logger.warning(
            f"Backfill target {start_id} is greater than or equal to current article ID {end_id} for group {group.name}"
        )

        # Get the actual first and last article IDs from the server
        try:
            conn = nntp_service.connect()
            resp, count, first, last, name = conn.group(group.name)
            conn.quit()

            logger.info(
                f"Group {group.name} has article range {first}-{last} on server"
            )

            # Update the group's article IDs in the database
            group.first_article_id = first
            group.last_article_id = last
            group.current_article_id = (
                last  # Set current to last to start from the most recent
            )

            # Set backfill target to a reasonable value (e.g., 1000 articles back from last)
            backfill_amount = min(1000, (last - first) // 2)
            group.backfill_target = max(first, last - backfill_amount)

            db.add(group)
            await db.commit()

            # Update our local variables
            start_id = group.backfill_target
            end_id = group.current_article_id - 1

            logger.info(
                f"Updated group article IDs: first={first}, last={last}, current={group.current_article_id}, backfill_target={group.backfill_target}"
            )
            logger.info(f"New backfill range: {start_id}-{end_id}")

        except Exception as e:
            logger.error(f"Error updating group article IDs: {str(e)}")
            # Fallback to the old behavior
            end_id = start_id
            start_id = max(1, start_id - limit)
            logger.info(
                f"Adjusted backfill range to {start_id}-{end_id} for group {group.name}"
            )

    # Process articles from backfill_target to current_article_id
    logger.info(
        f"Processing articles for {group.name} from {start_id} to {end_id} (range: {end_id - start_id + 1} articles)"
    )
    stats = await article_service.process_articles(db, group, start_id, end_id, limit)

    logger.info(
        f"Backfill stats for {group.name}: processed={stats['processed']}, binaries={stats.get('binaries', 0)}, releases={stats.get('releases', 0)}, skipped={stats.get('skipped', 0)}, failed={stats.get('failed', 0)}"
    )

    # Update group's backfill_target if we processed some articles
    if stats["processed"] > 0:
        # Move backfill_target forward
        group.backfill_target = start_id + stats["processed"]
        group.last_updated = datetime.now(timezone.utc)
        db.add(group)
        await db.commit()
        logger.info(
            f"Updated backfill target to {group.backfill_target} for group {group.name}"
        )
    else:
        logger.warning(
            f"No articles processed for {group.name} in range {start_id}-{end_id}"
        )

    return stats
