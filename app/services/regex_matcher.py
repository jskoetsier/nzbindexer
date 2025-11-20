"""
Regex Matcher Service

Pattern-based release name extraction from obfuscated subjects.
Uses database of regex patterns ordered by priority.

Based on NNTmux's proven approach with 1000+ patterns achieving 15-25% improvement.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from app.db.models.release_regex import ReleaseRegex

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RegexMatcher:
    """
    Regex pattern matching service for release name extraction

    Applies database regex patterns in priority order to extract clean
    release names from obfuscated Usenet subjects.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._pattern_cache: Dict[str, List[Tuple[int, re.Pattern, str]]] = {}
        self._cache_loaded = False

    async def load_patterns(self, group_name: str) -> List[Tuple[int, re.Pattern, str]]:
        """
        Load regex patterns for a specific group

        Args:
            group_name: Usenet group name (e.g., "alt.binaries.teevee")

        Returns:
            List of (pattern_id, compiled_regex, description) tuples ordered by priority
        """
        # Check cache first
        if group_name in self._pattern_cache:
            return self._pattern_cache[group_name]

        patterns = []

        try:
            # Query database for matching patterns
            # Order by ordinal (priority), then by ID
            query = (
                select(ReleaseRegex)
                .filter(ReleaseRegex.active == True)
                .order_by(ReleaseRegex.ordinal, ReleaseRegex.id)
            )

            result = await self.db.execute(query)
            db_patterns = result.scalars().all()

            for pattern_row in db_patterns:
                # Check if group pattern matches
                if pattern_row.group_pattern == "*":
                    # Universal pattern - applies to all groups
                    group_matches = True
                else:
                    # Check if group name matches the pattern
                    try:
                        group_regex = re.compile(
                            pattern_row.group_pattern, re.IGNORECASE
                        )
                        group_matches = bool(group_regex.match(group_name))
                    except re.error as e:
                        logger.warning(
                            f"Invalid group pattern regex: {pattern_row.group_pattern} - {e}"
                        )
                        continue

                if not group_matches:
                    continue

                # Compile the regex pattern
                try:
                    compiled = re.compile(pattern_row.regex, re.IGNORECASE)
                    patterns.append(
                        (pattern_row.id, compiled, pattern_row.description or "")
                    )
                except re.error as e:
                    logger.warning(
                        f"Invalid regex pattern (id={pattern_row.id}): {pattern_row.regex} - {e}"
                    )
                    continue

            # Cache the compiled patterns
            self._pattern_cache[group_name] = patterns

            logger.info(
                f"Loaded {len(patterns)} regex patterns for group: {group_name}"
            )

        except Exception as e:
            logger.error(f"Error loading regex patterns: {e}")

        return patterns

    async def match_release_name(
        self, subject: str, group_name: str
    ) -> Optional[Tuple[str, int]]:
        """
        Try to extract release name from subject using regex patterns

        Args:
            subject: Article subject line
            group_name: Usenet group name

        Returns:
            Tuple of (release_name, pattern_id) if matched, None otherwise
        """
        # Load patterns for this group
        patterns = await self.load_patterns(group_name)

        if not patterns:
            logger.debug(f"No regex patterns available for group: {group_name}")
            return None

        # Try each pattern in order
        for pattern_id, compiled_regex, description in patterns:
            try:
                match = compiled_regex.search(subject)

                if match:
                    # Extract release name from named capture group
                    # Common group names: name, release, title
                    release_name = None

                    # Try common capture group names
                    for group in ["name", "release", "title", "releasename"]:
                        if group in match.groupdict():
                            release_name = match.group(group)
                            break

                    # If no named groups, use first captured group
                    if not release_name and match.groups():
                        release_name = match.group(1)

                    # If we got a match, validate and return
                    if release_name:
                        release_name = release_name.strip()

                        # Validate release name looks reasonable
                        if self._validate_release_name(release_name):
                            logger.info(
                                f"✓ REGEX MATCH (pattern {pattern_id}): '{subject[:80]}...' -> '{release_name}'"
                            )

                            # Update match count in database (async, don't wait)
                            await self._increment_match_count(pattern_id)

                            return (release_name, pattern_id)
                        else:
                            logger.debug(
                                f"Regex matched but release name invalid: '{release_name}'"
                            )

            except Exception as e:
                logger.debug(f"Error applying regex pattern {pattern_id}: {e}")
                continue

        return None

    def _validate_release_name(self, name: str) -> bool:
        """
        Validate that extracted release name looks reasonable

        Args:
            name: Extracted release name

        Returns:
            True if name looks valid
        """
        # Basic validation rules
        if not name or len(name) < 5:
            return False

        if len(name) > 250:
            return False

        # Should contain at least some alphanumeric characters
        if not re.search(r"[a-zA-Z0-9]{3,}", name):
            return False

        # Should not be just a hash
        if re.match(r"^[a-fA-F0-9]{16,}$", name):
            return False

        if re.match(r"^[a-zA-Z0-9_-]{22,}$", name) and "." not in name:
            return False

        return True

    async def _increment_match_count(self, pattern_id: int):
        """
        Increment match count for a pattern (for statistics)

        Args:
            pattern_id: ID of the pattern that matched
        """
        try:
            query = select(ReleaseRegex).filter(ReleaseRegex.id == pattern_id)
            result = await self.db.execute(query)
            pattern = result.scalars().first()

            if pattern:
                pattern.match_count += 1
                await self.db.commit()

        except Exception as e:
            logger.debug(f"Error updating match count: {e}")
            await self.db.rollback()

    async def clear_cache(self):
        """Clear the pattern cache (use after adding/updating patterns)"""
        self._pattern_cache.clear()
        self._cache_loaded = False
        logger.info("Regex pattern cache cleared")

    async def get_pattern_stats(self, limit: int = 20) -> List[Dict]:
        """
        Get statistics about pattern usage

        Args:
            limit: Number of top patterns to return

        Returns:
            List of pattern statistics
        """
        try:
            query = (
                select(ReleaseRegex)
                .filter(ReleaseRegex.active == True)
                .order_by(ReleaseRegex.match_count.desc())
                .limit(limit)
            )

            result = await self.db.execute(query)
            patterns = result.scalars().all()

            stats = []
            for pattern in patterns:
                stats.append(
                    {
                        "id": pattern.id,
                        "group_pattern": pattern.group_pattern,
                        "description": pattern.description,
                        "match_count": pattern.match_count,
                        "ordinal": pattern.ordinal,
                    }
                )

            return stats

        except Exception as e:
            logger.error(f"Error getting pattern stats: {e}")
            return []
