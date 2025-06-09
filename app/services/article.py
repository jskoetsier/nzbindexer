"""
Article service for processing Usenet articles
"""

import logging
import re
from datetime import datetime
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
                    # Try to get article headers for the batch using OVER command
                    try:
                        resp, articles = conn.over((current_id, batch_end))
                    except Exception as e:
                        # If OVER command fails, try using HEAD command for each article
                        logger.warning(f"OVER command failed: {str(e)}. Falling back to HEAD command.")
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
                                    line_str = line.decode() if isinstance(line, bytes) else line
                                    if line_str.startswith("Subject:"):
                                        subject = line_str[8:].strip()
                                    elif line_str.startswith("Message-ID:"):
                                        message_id = line_str[10:].strip()

                                if subject and message_id:
                                    articles.append((article_num, subject, None, None, message_id, None, 0, 0, {}))
                            except Exception as article_e:
                                # Skip articles that can't be retrieved
                                logger.debug(f"Skipping article {article_id}: {str(article_e)}")
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

                            # Decode bytes to strings
                            subject = (
                                subject.decode()
                                if isinstance(subject, bytes)
                                else subject
                            )
                            message_id = (
                                message_id.decode()
                                if isinstance(message_id, bytes)
                                else message_id
                            )

                            # Process binary post
                            await self._process_binary_post(
                                subject,
                                message_id,
                                bytes_count,
                                binaries,
                                binary_subjects,
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
                # Check if binary is complete
                if (
                    binary["total_parts"] > 0
                    and len(binary["parts"]) >= binary["total_parts"]
                ):
                    # Check if release already exists
                    from app.services.release import create_release_guid

                    guid = create_release_guid(binary["name"], group.name)

                    query = select(Release).filter(Release.guid == guid)
                    result = await db.execute(query)
                    existing_release = result.scalars().first()

                    if existing_release:
                        # Update existing release
                        continue

                    # Create new release
                    subject = binary_subjects.get(binary_key, binary["name"])

                    from app.schemas.release import ReleaseCreate

                    # Create release
                    from app.services.release import create_release

                    release_data = ReleaseCreate(
                        name=binary["name"],
                        search_name=self._create_search_name(binary["name"]),
                        guid=guid,
                        size=binary["size"],
                        files=len(binary["parts"]),
                        completion=100.0,  # Complete binary
                        posted_date=datetime.utcnow(),  # Should use article date
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
                        logger.info(f"Generated NZB file for release {release.id}: {nzb_path}")
                    else:
                        logger.warning(f"Failed to generate NZB file for release {release.id}")

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
        group.last_updated = datetime.utcnow()
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
        logger.warning(f"Invalid backfill target for group {group.name}: {group.backfill_target}")
        return {"processed": 0, "total": 0, "skipped": 0, "failed": 0, "binaries": 0, "releases": 0}

    # Determine the range of articles to process
    start_id = group.backfill_target
    end_id = group.current_article_id - 1

    # If backfill_target is greater than current_article_id, we need to fix this
    if start_id >= end_id:
        logger.warning(f"Backfill target {start_id} is greater than or equal to current article ID {end_id} for group {group.name}")

        # Get the actual first and last article IDs from the server
        try:
            conn = nntp_service.connect()
            resp, count, first, last, name = conn.group(group.name)
            conn.quit()

            logger.info(f"Group {group.name} has article range {first}-{last} on server")

            # Update the group's article IDs in the database
            group.first_article_id = first
            group.last_article_id = last
            group.current_article_id = last  # Set current to last to start from the most recent

            # Set backfill target to a reasonable value (e.g., 1000 articles back from last)
            backfill_amount = min(1000, (last - first) // 2)
            group.backfill_target = max(first, last - backfill_amount)

            db.add(group)
            await db.commit()

            # Update our local variables
            start_id = group.backfill_target
            end_id = group.current_article_id - 1

            logger.info(f"Updated group article IDs: first={first}, last={last}, current={group.current_article_id}, backfill_target={group.backfill_target}")
            logger.info(f"New backfill range: {start_id}-{end_id}")

        except Exception as e:
            logger.error(f"Error updating group article IDs: {str(e)}")
            # Fallback to the old behavior
            end_id = start_id
            start_id = max(1, start_id - limit)
            logger.info(f"Adjusted backfill range to {start_id}-{end_id} for group {group.name}")

    # Process articles from backfill_target to current_article_id
    stats = await article_service.process_articles(
        db, group, start_id, end_id, limit
    )

    # Update group's backfill_target if we processed some articles
    if stats["processed"] > 0:
        # Move backfill_target forward
        group.backfill_target = start_id + stats["processed"]
        group.last_updated = datetime.utcnow()
        db.add(group)
        await db.commit()
        logger.info(f"Updated backfill target to {group.backfill_target} for group {group.name}")

    return stats
