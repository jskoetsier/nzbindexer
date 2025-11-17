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
                                # CRITICAL FIX: NNTP OVER command returns a dict, not a simple tuple!
                                # The second element is a dictionary with all the header info
                                article_num, headers_dict = article

                                # Extract fields from the dictionary with safe int conversion
                                subject = headers_dict.get("subject", "")
                                from_addr = headers_dict.get("from", "")
                                date_str = headers_dict.get("date", "")
                                message_id = headers_dict.get("message-id", "")
                                references = headers_dict.get("references", "")

                                # Safe int conversion - handle empty strings and invalid values
                                try:
                                    bytes_str = headers_dict.get(":bytes", "0")
                                    bytes_count = (
                                        int(bytes_str)
                                        if bytes_str and bytes_str.strip()
                                        else 0
                                    )
                                except (ValueError, AttributeError):
                                    bytes_count = 0

                                try:
                                    lines_str = headers_dict.get(":lines", "0")
                                    lines_count = (
                                        int(lines_str)
                                        if lines_str and lines_str.strip()
                                        else 0
                                    )
                                except (ValueError, AttributeError):
                                    lines_count = 0

                                other = {}

                                # Log successful extraction for first few articles
                                if stats["processed"] < 3:
                                    logger.info(
                                        f"[FIX] Extracted from dict: article={article_num}, subject='{subject}'"
                                    )
                            else:
                                # Handle other unexpected formats
                                logger.warning(f"Unexpected article format: {article}")
                                stats["skipped"] += 1
                                continue

                            # Skip articles with no subject or message_id
                            if not subject or not message_id:
                                # CRITICAL DEBUG: Log why article is being skipped
                                if stats["skipped"] < 5:
                                    logger.warning(
                                        f"[CRITICAL] Article {article_num} skipped: subject={repr(subject)}, message_id={repr(message_id)}"
                                    )
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

                            # AGGRESSIVE DEBUG: Log EVERY subject for the first 20 articles
                            if stats["processed"] < 20:
                                logger.info(
                                    f"[DEBUG] Article {article_num}: subject='{subject}', bytes={bytes_count}, message_id={message_id}"
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
                                    f"✓ Found binary post: {subject} -> {binary_result}"
                                )
                            elif stats["processed"] < 20:
                                logger.warning(
                                    f"✗ SKIPPED article {article_num}: {subject}"
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
        Enhanced to handle obfuscated posts efficiently
        """
        # Ensure subject is not None
        if subject is None:
            subject = ""

        # First, try to parse subject to extract binary name and part info
        binary_name, part_num, total_parts = self._parse_binary_subject(subject)

        # If subject parsing succeeded, check if the binary name is actually meaningful
        if binary_name and part_num:
            # Check if the parsed binary name is a hash-like obfuscated name
            subject_no_ext = re.sub(
                r"\.(rar|par2?|zip|7z|r\d+|vol\d+)$",
                "",
                binary_name,
                flags=re.IGNORECASE,
            )

            is_hash_name = (
                re.match(r"^[a-fA-F0-9]{16,}$", subject_no_ext)  # Hex hash (16+ chars)
                or re.match(
                    r"^[a-fA-F0-9]{16,}$", binary_name
                )  # Hex hash with extension
                or re.match(
                    r"^[a-zA-Z0-9_-]{22,}$", subject_no_ext
                )  # Base64-like (22+ chars, no spaces)
                or len(binary_name) < 10  # Too short
            )

            if is_hash_name:
                # Even though we parsed it, it's still obfuscated - mark it as such
                logger.debug(
                    f"Parsed binary name is hash-like, marking as obfuscated: {binary_name}"
                )
                binary_name = (
                    f"obfuscated_{hash(binary_name or message_id) & 0x7FFFFFFF}"
                )
            else:
                logger.debug(
                    f"Parsed binary from subject: {binary_name} part {part_num}/{total_parts}"
                )
        else:
            # Subject parsing failed - might be obfuscated or non-standard format
            # But first check if it still looks like a binary post

            # Check if this looks like a binary post at all
            has_binary_indicators = any(
                [
                    "yenc" in subject.lower(),
                    "yEnc" in subject,
                    re.search(r"\[\d+/\d+\]", subject),  # Has part indicator [01/50]
                    re.search(r"\(\d+/\d+\)", subject),  # Has part indicator (01/50)
                    re.search(r"\d+/\d+", subject),  # Has any number pattern like 01/50
                    bytes_count > 1000,  # Fairly small threshold (1KB)
                    len(subject) > 10,  # Has some subject text
                ]
            )

            if not has_binary_indicators:
                # Not a binary post, skip silently
                return

            # Extract part numbers from subject if available
            part_match = re.search(r"[\[\(]?(\d+)/(\d+)[\]\)]?", subject)
            if part_match:
                part_num = int(part_match.group(1))
                total_parts = int(part_match.group(2))
            else:
                # No part info in subject, assume single part for now
                part_num = 1
                total_parts = 1

            # For posts without proper naming, use the subject as binary name if it's meaningful
            # Remove part numbers for grouping
            subject_base = re.sub(r"[\[\(]?\d+/\d+[\]\)]?", "", subject).strip()
            subject_base = re.sub(
                r"-\s*yEnc.*$", "", subject_base, flags=re.IGNORECASE
            ).strip()
            subject_base = re.sub(
                r"\s*yEnc.*$", "", subject_base, flags=re.IGNORECASE
            ).strip()

            # Check if this is a hash-like obfuscated name
            # Strip common extensions first
            subject_no_ext = re.sub(
                r"\.(rar|par2?|zip|7z|r\d+|vol\d+)$",
                "",
                subject_base,
                flags=re.IGNORECASE,
            )

            is_hash_name = (
                re.match(r"^[a-fA-F0-9]{16,}$", subject_no_ext)  # Hex hash (16+ chars)
                or re.match(
                    r"^[a-fA-F0-9]{16,}$", subject_base
                )  # Hex hash with extension
                or re.match(
                    r"^[a-zA-Z0-9_-]{22,}$", subject_no_ext
                )  # Base64-like (22+ chars, no spaces)
                or len(subject_base) < 10  # Too short
            )

            # If we have a meaningful subject (at least 10 chars AND not a hash), use it
            if len(subject_base) >= 10 and not is_hash_name:
                binary_name = subject_base
                logger.debug(
                    f"Using subject as binary name: {binary_name} part {part_num}/{total_parts}"
                )
            else:
                # Mark as obfuscated - use hash for grouping
                binary_name = (
                    f"obfuscated_{hash(subject_base or message_id) & 0x7FFFFFFF}"
                )
                logger.debug(
                    f"Detected obfuscated post: {subject} -> {binary_name} part {part_num}/{total_parts}"
                )

        # Create or update binary entry
        binary_key = self._get_binary_key(binary_name)

        if binary_key not in binaries:
            binaries[binary_key] = {
                "name": binary_name,
                "parts": {},
                "total_parts": total_parts or 0,
                "size": 0,
                "obfuscated": binary_name.startswith(
                    "obfuscated_"
                ),  # Track if this is obfuscated
                "message_ids": [],  # Store message IDs for later yEnc header fetching
            }
            binary_subjects[binary_key] = subject

        # Add part to binary
        if part_num not in binaries[binary_key]["parts"]:
            binaries[binary_key]["parts"][part_num] = {
                "message_id": message_id,
                "size": bytes_count,
                "subject": subject,  # Store subject for debugging
            }
            binaries[binary_key]["size"] += bytes_count
            binaries[binary_key]["message_ids"].append(message_id)

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

    async def _get_real_filename_from_yenc(self, message_id: str) -> Optional[str]:
        """
        Fetch the real filename from yEnc headers for an obfuscated post
        """
        try:
            # Get the article body
            body_lines = await self.nntp_service.get_article_body(message_id)

            if not body_lines:
                logger.debug(f"No body found for message_id: {message_id}")
                return None

            # Look for yEnc header line (=ybegin)
            for line in body_lines[:50]:  # Check first 50 lines
                if line.startswith("=ybegin"):
                    # Parse yEnc header: =ybegin part=1 total=50 line=128 size=500000 name=actual_filename.ext
                    match = re.search(r"name=(.+?)(?:\s|$)", line)
                    if match:
                        filename = match.group(1).strip()
                        logger.info(
                            f"Deobfuscated filename from yEnc header: {filename}"
                        )
                        return filename

            logger.debug(f"No yEnc header found in message_id: {message_id}")
            return None

        except Exception as e:
            logger.warning(f"Error fetching yEnc filename for {message_id}: {str(e)}")
            return None

    async def _extract_release_name_from_nfo(self, binary: Dict) -> Optional[str]:
        """
        Extract the real release name from NFO files in the binary
        NFO files typically contain release information that can help deobfuscate
        """
        try:
            # Look for .nfo files in the binary parts
            nfo_message_ids = []
            
            for part_num, part_info in binary.get("parts", {}).items():
                subject = part_info.get("subject", "")
                message_id = part_info.get("message_id", "")
                
                # Check if this part contains an NFO file
                if ".nfo" in subject.lower() or "nfo" in subject.lower():
                    nfo_message_ids.append((message_id, subject))
                    logger.info(f"Found potential NFO file in part {part_num}: {subject}")
            
            # Try to download and parse NFO files
            for message_id, subject in nfo_message_ids[:3]:  # Try first 3 NFO files
                try:
                    # Get yEnc filename first
                    yenc_filename = await self._get_real_filename_from_yenc(message_id)
                    
                    if yenc_filename and ".nfo" in yenc_filename.lower():
                        # Get the article body
                        body_lines = await self.nntp_service.get_article_body(message_id)
                        
                        if body_lines:
                            # Decode yEnc content
                            nfo_content = self._decode_yenc_body(body_lines)
                            
                            if nfo_content:
                                # Parse NFO for release name
                                release_name = self._parse_nfo_for_release_name(nfo_content)
                                
                                if release_name:
                                    logger.info(
                                        f"Successfully extracted release name from NFO: {release_name}"
                                    )
                                    return release_name
                
                except Exception as e:
                    logger.debug(f"Error processing NFO {message_id}: {str(e)}")
                    continue
            
            logger.debug("No usable NFO files found or could not extract release name")
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting release name from NFO: {str(e)}")
            return None

    def _decode_yenc_body(self, body_lines: List[str]) -> Optional[str]:
        """
        Decode yEnc encoded body to get the actual content
        Simple implementation - just tries to decode the content
        """
        try:
            decoded_bytes = bytearray()
            in_yenc_data = False
            
            for line in body_lines:
                line = line.strip()
                
                if line.startswith("=ybegin"):
                    in_yenc_data = True
                    continue
                elif line.startswith("=yend"):
                    break
                elif line.startswith("=ypart"):
                    continue
                    
                if in_yenc_data and line and not line.startswith("="):
                    # Basic yEnc decoding: subtract 42 from each byte
                    for char in line:
                        byte_val = ord(char)
                        # Handle yEnc escape sequences (=)
                        if char == '=':
                            continue
                        decoded_byte = (byte_val - 42) % 256
                        decoded_bytes.append(decoded_byte)
            
            # Try to decode as ASCII/UTF-8
            try:
                content = decoded_bytes.decode('utf-8', errors='ignore')
                return content
            except:
                content = decoded_bytes.decode('latin-1', errors='ignore')
                return content
                
        except Exception as e:
            logger.debug(f"Error decoding yEnc body: {str(e)}")
            return None

    def _parse_nfo_for_release_name(self, nfo_content: str) -> Optional[str]:
        """
        Parse NFO content to extract the release name
        Looks for common patterns in NFO files
        """
        try:
            # Common patterns in NFO files
            patterns = [
                r'Release[:\s]+(.+)',
                r'Title[:\s]+(.+)',
                r'Name[:\s]+(.+)',
                r'(\S+\.\S+\.\S+\.\S+)',  # Dotted release name pattern
                r'━+\s*(.+?)\s*━+',  # Text between box drawing characters
                r'═+\s*(.+?)\s*═+',  # Text between double lines
            ]
            
            lines = nfo_content.split('\n')
            
            # Look for release name patterns
            for pattern in patterns:
                for line in lines[:100]:  # Check first 100 lines
                    line = line.strip()
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        potential_name = match.group(1).strip()
                        
                        # Clean up the name
                        potential_name = re.sub(r'[^\w\s\.\-\(\)]', '', potential_name)
                        potential_name = potential_name.strip()
                        
                        # Validate it looks like a release name
                        if (len(potential_name) > 10 and 
                            len(potential_name) < 200 and
                            not potential_name.startswith('http') and
                            '.' in potential_name):
                            
                            logger.info(f"Found potential release name in NFO: {potential_name}")
                            return potential_name
            
            return None
            
        except Exception as e:
            logger.debug(f"Error parsing NFO content: {str(e)}")
            return None

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

                    # Deobfuscate the binary name if it's obfuscated
                    release_name = binary["name"]
                    if binary.get("obfuscated", False) and binary.get("message_ids"):
                        # Try to get the real filename from yEnc headers
                        logger.info(
                            f"Attempting to deobfuscate binary: {binary['name']}"
                        )

                        # Helper function to check if a filename is still a hash
                        def is_filename_hash(filename: str) -> bool:
                            """Check if a filename (after deobfuscation) is still a hash"""
                            # Strip extensions and part numbers
                            name_no_ext = re.sub(
                                r'\.(rar|par2?|zip|7z|r\d+|vol\d+|part\d+)$', 
                                '', 
                                filename, 
                                flags=re.IGNORECASE
                            )
                            # Also strip .partXX. pattern
                            name_no_ext = re.sub(r'\.part\d+\.', '.', name_no_ext, flags=re.IGNORECASE)
                            
                            # Check for hash patterns
                            return bool(
                                re.match(r'^[a-fA-F0-9]{16,}$', name_no_ext) or  # Hex hash (16+ chars)
                                re.match(r'^[a-zA-Z0-9]{18,}$', name_no_ext) or  # Alphanumeric only (18+ chars, no dashes/underscores)
                                re.match(r'^[a-zA-Z0-9_-]{22,}$', name_no_ext) or  # Base64-like with separators (22+ chars)
                                (len(name_no_ext) < 10 and not re.search(r'[a-z]{3,}', name_no_ext.lower()))  # Too short and no real words
                            )

                        # Try up to 10 message IDs to find a non-hash filename
                        found_real_name = False
                        for message_id in binary["message_ids"][:10]:
                            real_filename = await self._get_real_filename_from_yenc(
                                message_id
                            )
                            if real_filename:
                                # Check if this "deobfuscated" name is still a hash
                                if is_filename_hash(real_filename):
                                    logger.debug(
                                        f"yEnc filename is still a hash: {real_filename}"
                                    )
                                    continue  # Try next message ID
                                else:
                                    # Found a real filename!
                                    release_name = real_filename
                                    found_real_name = True
                                    logger.info(
                                        f"Successfully deobfuscated: {binary['name']} -> {release_name}"
                                    )
                                    break

                        if not found_real_name:
                            # All yEnc attempts yielded hash names - try NFO files
                            logger.info(
                                f"All yEnc filenames are hashes, trying NFO extraction for {binary['name']}"
                            )
                            nfo_release_name = await self._extract_release_name_from_nfo(binary)
                            
                            if nfo_release_name:
                                release_name = nfo_release_name
                                found_real_name = True
                                logger.info(
                                    f"Successfully extracted from NFO: {binary['name']} -> {release_name}"
                                )
                            else:
                                # Double-obfuscated with no NFO - skip this release
                                logger.warning(
                                    f"Double-obfuscated post detected: {binary['name']} - all yEnc filenames are hashes and no NFO found. SKIPPING."
                                )
                                # Skip creating this release entirely
                                continue

                    # Check if release already exists
                    from app.services.release import create_release_guid

                    guid = create_release_guid(release_name, group.name)

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
                    subject = binary_subjects.get(binary_key, release_name)
                    logger.info(
                        f"Creating release for binary: {release_name} with {len(binary['parts'])}/{binary['total_parts']} parts"
                    )

                    from app.schemas.release import ReleaseCreate

                    # Create release
                    from app.services.release import create_release

                    release_data = ReleaseCreate(
                        name=release_name,
                        search_name=self._create_search_name(release_name),
                        guid=guid,
                        size=binary["size"],
                        files=len(binary["parts"]),
                        completion=completion,
                        posted_date=datetime.utcnow(),  # Use timezone-naive datetime to match DB schema
                        status=1,  # Active
                        passworded=0,  # Unknown
                        category_id=default_category.id,
                        group_id=group.id,
                    )

                    release = await create_release(db, release_data)

                    # Try to categorize better based on name and group
                    from app.services.release import (
                        determine_release_category,
                        extract_release_metadata,
                    )

                    metadata = extract_release_metadata(release_name)
                    better_category_id = await determine_release_category(
                        db, release_name, metadata, group.name
                    )

                    if better_category_id and better_category_id != default_category.id:
                        release.category_id = better_category_id
                        db.add(release)
                        await db.commit()
                        await db.refresh(release)

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
