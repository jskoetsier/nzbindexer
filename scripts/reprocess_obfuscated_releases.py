#!/usr/bin/env python3
"""
Reprocess Obfuscated Releases

This script attempts to deobfuscate all existing obfuscated releases using:
1. ORN Cache lookups
2. NEW: Regex Pattern Matching
3. RequestID extraction and matching
4. PreDB API lookups
5. Archive header extraction (if message IDs available)

This is particularly useful after:
- Adding the regex pattern database
- Updating deobfuscation logic
- Growing the ORN cache
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.models.orn_mapping import ORNMapping
from app.db.models.release import Release
from app.db.session import AsyncSessionLocal
from app.services.deobfuscation import DeobfuscationService
from app.services.predb import PreDBService
from app.services.regex_matcher import RegexMatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ReleaseReprocessor:
    """Reprocess obfuscated releases with improved deobfuscation"""

    def __init__(self):
        self.stats = {
            "total": 0,
            "obfuscated": 0,
            "already_clean": 0,
            "deobfuscated": 0,
            "still_obfuscated": 0,
            "methods": {
                "orn_cache": 0,
                "regex_pattern": 0,
                "requestid": 0,
                "predb": 0,
                "archive": 0,
            },
        }
        self.deobfuscation_service = DeobfuscationService()

    async def reprocess_all_releases(
        self, limit: Optional[int] = None, dry_run: bool = False
    ):
        """
        Reprocess all obfuscated releases

        Args:
            limit: Maximum number of releases to process (None = all)
            dry_run: If True, don't update database, just report what would be done
        """
        logger.info("=" * 70)
        logger.info("Starting Obfuscated Release Reprocessing")
        logger.info("=" * 70)

        if dry_run:
            logger.warning("DRY RUN MODE - No database changes will be made")

        async with AsyncSessionLocal() as db:
            # Get all releases
            query = select(Release)
            if limit:
                query = query.limit(limit)

            result = await db.execute(query)
            releases = result.scalars().all()

            self.stats["total"] = len(releases)
            logger.info(f"Found {self.stats['total']} total releases to check")

            # Process each release
            for idx, release in enumerate(releases, 1):
                if idx % 100 == 0:
                    logger.info(
                        f"Progress: {idx}/{self.stats['total']} releases processed"
                    )

                await self._process_release(db, release, dry_run)

            # Commit changes if not dry run
            if not dry_run:
                await db.commit()
                logger.info("✓ Database changes committed")
            else:
                logger.info("✓ Dry run completed - no changes made")

        # Print statistics
        self._print_statistics()

    async def _process_release(self, db: AsyncSession, release: Release, dry_run: bool):
        """Process a single release"""

        # Check if release name is obfuscated
        if not self._is_obfuscated(release.name):
            self.stats["already_clean"] += 1
            return

        self.stats["obfuscated"] += 1

        # Try to deobfuscate using various methods
        new_name = await self._try_deobfuscate(db, release)

        if new_name and new_name != release.name:
            # Successfully deobfuscated!
            self.stats["deobfuscated"] += 1

            logger.info(f"✓ DEOBFUSCATED: '{release.name}' -> '{new_name}'")

            if not dry_run:
                # Update release
                release.name = new_name
                release.search_name = self._create_search_name(new_name)
                db.add(release)
        else:
            self.stats["still_obfuscated"] += 1
            if self.stats["still_obfuscated"] <= 10:  # Only log first 10
                logger.debug(f"✗ Still obfuscated: {release.name}")

    def _is_obfuscated(self, name: str) -> bool:
        """Check if a release name is obfuscated"""
        # Check for our obfuscated_ prefix
        if name.startswith("obfuscated_"):
            return True

        # Use deobfuscation service to check if it's a hash
        return self.deobfuscation_service.is_obfuscated_hash(name)

    async def _try_deobfuscate(
        self, db: AsyncSession, release: Release
    ) -> Optional[str]:
        """
        Try to deobfuscate a release using multiple methods

        Returns:
            New release name if successful, None otherwise
        """

        # Method 1: Check ORN cache
        result = await self._try_orn_cache(db, release.name)
        if result:
            self.stats["methods"]["orn_cache"] += 1
            return result

        # Method 2: Try Regex Pattern Matching (NEW!)
        # We need the group to do this properly
        if release.group_id:
            from app.db.models.group import Group

            group_query = select(Group).filter(Group.id == release.group_id)
            group_result = await db.execute(group_query)
            group = group_result.scalars().first()

            if group:
                result = await self._try_regex_patterns(db, release, group.name)
                if result:
                    self.stats["methods"]["regex_pattern"] += 1
                    return result

        # Method 3: Try RequestID matching (if we can extract from name/searchname)
        # This is less likely to work from stored release name, but worth trying

        # Method 4: Try PreDB lookup
        result = await self._try_predb(db, release.name)
        if result:
            self.stats["methods"]["predb"] += 1
            return result

        # Method 5: Archive extraction would require message IDs which we don't have
        # in the release table, so we skip this for now

        return None

    async def _try_orn_cache(self, db: AsyncSession, name: str) -> Optional[str]:
        """Try to find release name in ORN cache"""
        try:
            query = select(ORNMapping).filter(ORNMapping.hash == name)
            result = await db.execute(query)
            mapping = result.scalars().first()

            if mapping:
                logger.debug(f"ORN cache hit: {name} -> {mapping.real_name}")
                return mapping.real_name
        except Exception as e:
            logger.debug(f"ORN cache lookup error: {e}")

        return None

    async def _try_regex_patterns(
        self, db: AsyncSession, release: Release, group_name: str
    ) -> Optional[str]:
        """Try to match using regex patterns"""

        # We need some kind of subject to match against
        # Try using the search_name or name as a proxy for the original subject
        # This won't be perfect but might catch some patterns

        subject = release.search_name or release.name

        # If it's just obfuscated_XXXXX, we can't do much
        if subject.startswith("obfuscated_"):
            return None

        try:
            regex_matcher = RegexMatcher(db)
            result = await regex_matcher.match_release_name(subject, group_name)

            if result:
                new_name, pattern_id = result
                logger.debug(
                    f"Regex match: {subject} -> {new_name} (pattern {pattern_id})"
                )

                # Cache this in ORN database
                try:
                    orn_mapping = ORNMapping(
                        hash=release.name,
                        real_name=new_name,
                        source=f"regex_pattern_{pattern_id}_reprocess",
                    )
                    db.add(orn_mapping)
                except Exception as cache_error:
                    logger.debug(f"Error caching regex match: {cache_error}")

                return new_name
        except Exception as e:
            logger.debug(f"Regex pattern matching error: {e}")

        return None

    async def _try_predb(self, db: AsyncSession, name: str) -> Optional[str]:
        """Try PreDB API lookup"""

        predb_service = PreDBService(db)
        try:
            result = await predb_service.lookup_obfuscated_name(name)
            if result:
                logger.debug(f"PreDB hit: {name} -> {result}")

                # Cache this in ORN database
                try:
                    orn_mapping = ORNMapping(
                        hash=name, real_name=result, source="predb_reprocess"
                    )
                    db.add(orn_mapping)
                except Exception as cache_error:
                    logger.debug(f"Error caching PreDB result: {cache_error}")

                return result
        except Exception as e:
            logger.debug(f"PreDB lookup error: {e}")
        finally:
            await predb_service.close()

        return None

    def _create_search_name(self, name: str) -> str:
        """Create a search-friendly name"""
        import re

        search_name = name.lower()
        search_name = re.sub(r"[^a-z0-9\s]", " ", search_name)
        search_name = re.sub(r"\s+", " ", search_name).strip()
        return search_name

    def _print_statistics(self):
        """Print reprocessing statistics"""
        logger.info("\n" + "=" * 70)
        logger.info("Reprocessing Statistics")
        logger.info("=" * 70)
        logger.info(f"Total Releases:        {self.stats['total']:>8}")
        logger.info(f"Already Clean:         {self.stats['already_clean']:>8}")
        logger.info(f"Obfuscated:            {self.stats['obfuscated']:>8}")
        logger.info("-" * 70)
        logger.info(f"✓ Deobfuscated:        {self.stats['deobfuscated']:>8}")
        logger.info(f"✗ Still Obfuscated:    {self.stats['still_obfuscated']:>8}")
        logger.info("-" * 70)

        if self.stats["deobfuscated"] > 0:
            logger.info("Deobfuscation Methods:")
            for method, count in self.stats["methods"].items():
                if count > 0:
                    percentage = (count / self.stats["deobfuscated"]) * 100
                    logger.info(f"  {method:20s} {count:>8} ({percentage:>5.1f}%)")

        logger.info("=" * 70)

        # Calculate success rate
        if self.stats["obfuscated"] > 0:
            success_rate = (self.stats["deobfuscated"] / self.stats["obfuscated"]) * 100
            logger.info(f"\n✓ Success Rate: {success_rate:.1f}%")

            if self.stats["deobfuscated"] > 0:
                logger.info(
                    f"✓ {self.stats['deobfuscated']} releases successfully deobfuscated!"
                )

        logger.info("")


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Reprocess obfuscated releases with improved deobfuscation"
    )
    parser.add_argument(
        "--limit", type=int, help="Maximum number of releases to process (default: all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't update database, just show what would be done",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    reprocessor = ReleaseReprocessor()
    await reprocessor.reprocess_all_releases(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
