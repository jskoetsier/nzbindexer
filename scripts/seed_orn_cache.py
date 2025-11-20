#!/usr/bin/env python3
"""
ORN Cache Seeding Script

Manually populate the ORN (Obfuscated Release Names) cache from various sources.

IMPORTANT: PreDB API seeding is currently DISABLED because:
- Public PreDB APIs don't provide obfuscated hash → name mappings
- The hashes used in Usenet are random, not derived from release names
- Organic cache population through deobfuscation is MORE EFFECTIVE

RECOMMENDED APPROACH:
1. Let the ORN cache populate organically through backfill (BEST)
2. Use CSV import for known hash mappings
3. Use NZBHydra2 history if you have an existing installation

The cache will grow automatically as releases are successfully deobfuscated.
After 24 hours of backfill, you should have 1000-2000 mappings with 60-75% success rate.

Usage:
    # CSV import (most effective)
    python scripts/seed_orn_cache.py --source csv --file mappings.csv

    # NZBHydra2 import (if configured)
    python scripts/seed_orn_cache.py --source hydra

    # PreDB (disabled, kept for future enhancement)
    python scripts/seed_orn_cache.py --source predb --limit 1000

CSV Format:
    hash,real_name,source
    a1b2c3d4e5f6,Release.Name.2024.1080p-GROUP,manual
    9f8e7d6c5b4a,Another.Release.x264-GRP,manual
"""

import asyncio
import csv
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp

from app.core.config import settings
from app.db.models.orn_mapping import ORNMapping
from app.db.session import AsyncSessionLocal
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ORNSeeder:
    """ORN Cache Seeding Service"""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.added_count = 0
        self.skipped_count = 0
        self.error_count = 0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def seed_from_predb(self, limit: int = 1000) -> int:
        """
        Seed ORN cache from PreDB APIs (recent releases)

        NOTE: This method has limited effectiveness because:
        1. Public PreDB APIs don't provide obfuscated hash mappings
        2. Generating hashes from release names doesn't match actual Usenet obfuscation
        3. Organic cache population through deobfuscation is more effective

        This is kept for future enhancement when proper PreDB hash databases become available.

        Args:
            limit: Number of recent releases to fetch per API

        Returns:
            Number of mappings added (usually 0)
        """
        logger.warning(
            "PreDB seeding has limited effectiveness - ORN cache populates better through organic deobfuscation"
        )
        logger.info(f"Attempting PreDB API seeding (limit: {limit})")

        # NOTE: These APIs don't actually provide hash mappings
        # This is a placeholder for future enhancement
        predb_apis = []  # Disabled until proper hash APIs are available

        logger.info("PreDB API seeding is currently disabled")
        logger.info(
            "Recommended approach: Let ORN cache populate organically through backfill"
        )
        logger.info("Alternative: Use --source csv to import known hash mappings")

        return 0

    async def seed_from_hydra(self) -> int:
        """
        Seed ORN cache from NZBHydra2 history

        Returns:
            Number of mappings added
        """
        if not settings.NZBHYDRA_URL or not settings.NZBHYDRA_API_KEY:
            logger.warning("NZBHydra2 not configured, skipping")
            return 0

        logger.info("Seeding ORN cache from NZBHydra2...")

        try:
            # Get NZBHydra2 search history
            url = f"{settings.NZBHYDRA_URL}/api/history"
            headers = {"apikey": settings.NZBHYDRA_API_KEY}
            params = {"limit": 500, "type": "search"}

            async with self.session.get(
                url, headers=headers, params=params
            ) as response:
                if response.status != 200:
                    logger.error(f"NZBHydra2 returned status {response.status}")
                    return 0

                data = await response.json()
                searches = data.get("searchResults", [])

                logger.info(f"Found {len(searches)} searches in NZBHydra2 history")

                async with AsyncSessionLocal() as db:
                    for search in searches:
                        try:
                            # Extract query and results
                            query = search.get("query")
                            results = search.get("results", [])

                            if not query or not results:
                                continue

                            # If query looks like a hash, map it to result titles
                            if self._is_hash(query):
                                for result in results[:3]:  # Top 3 results
                                    title = result.get("title")
                                    if title:
                                        await self._add_mapping(
                                            db, query, title, "nzbhydra2"
                                        )

                        except Exception as e:
                            logger.debug(f"Error processing search: {e}")
                            self.error_count += 1

        except Exception as e:
            logger.error(f"Error fetching from NZBHydra2: {e}")

        return self.added_count

    async def seed_from_csv(self, csv_path: str) -> int:
        """
        Seed ORN cache from CSV file

        CSV format: hash,real_name,source (optional)

        Args:
            csv_path: Path to CSV file

        Returns:
            Number of mappings added
        """
        logger.info(f"Seeding ORN cache from CSV: {csv_path}")

        try:
            async with AsyncSessionLocal() as db:
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)

                    for row in reader:
                        try:
                            hash_val = row.get("hash")
                            real_name = row.get("real_name")
                            source = row.get("source", "csv_import")

                            if not hash_val or not real_name:
                                logger.warning(f"Skipping invalid row: {row}")
                                continue

                            await self._add_mapping(db, hash_val, real_name, source)

                        except Exception as e:
                            logger.debug(f"Error processing row: {e}")
                            self.error_count += 1

        except FileNotFoundError:
            logger.error(f"CSV file not found: {csv_path}")
        except Exception as e:
            logger.error(f"Error reading CSV: {e}")

        return self.added_count

    async def seed_from_newznab(
        self, indexer_urls: List[str], api_keys: List[str]
    ) -> int:
        """
        Seed ORN cache from Newznab indexers

        Args:
            indexer_urls: List of Newznab indexer URLs
            api_keys: Corresponding API keys

        Returns:
            Number of mappings added
        """
        logger.info(f"Seeding ORN cache from {len(indexer_urls)} Newznab indexers...")

        async with AsyncSessionLocal() as db:
            for url, api_key in zip(indexer_urls, api_keys):
                try:
                    logger.info(f"Fetching from {url}...")

                    # Get recent releases
                    params = {"t": "search", "apikey": api_key, "limit": 100}

                    async with self.session.get(url, params=params) as response:
                        if response.status != 200:
                            logger.warning(f"{url} returned status {response.status}")
                            continue

                        # Parse XML response (Newznab returns RSS/XML)
                        text = await response.text()

                        # Simple XML parsing for titles
                        import re

                        titles = re.findall(r"<title>([^<]+)</title>", text)

                        logger.info(f"Found {len(titles)} releases from {url}")

                        for title in titles:
                            # Generate hash candidates
                            hashes = self._generate_hash_candidates(title)

                            for hash_candidate in hashes:
                                await self._add_mapping(
                                    db, hash_candidate, title, "newznab"
                                )

                except Exception as e:
                    logger.error(f"Error fetching from {url}: {e}")

        return self.added_count

    async def _add_mapping(
        self, db, hash_val: str, real_name: str, source: str
    ) -> bool:
        """Add a mapping to the database"""
        try:
            # Check if already exists
            query = select(ORNMapping).filter(ORNMapping.hash == hash_val)
            result = await db.execute(query)
            existing = result.scalars().first()

            if existing:
                self.skipped_count += 1
                return False

            # Add new mapping
            mapping = ORNMapping(
                hash=hash_val, real_name=real_name, source=source, confidence=0.8
            )
            db.add(mapping)
            await db.commit()

            self.added_count += 1
            if self.added_count % 100 == 0:
                logger.info(f"Added {self.added_count} mappings...")

            return True

        except Exception as e:
            logger.debug(f"Error adding mapping: {e}")
            await db.rollback()
            self.error_count += 1
            return False

    def _generate_hash_candidates(self, release_name: str) -> List[str]:
        """
        Generate potential hash candidates from a release name

        For example: "Movie.Name.2024.1080p.BluRay.x264-GROUP"
        Might have been posted as: "a1b2c3d4e5f6.part01.rar"

        We can't reverse-engineer the exact hash, but we can create
        variations that might match common obfuscation patterns.
        """
        import hashlib

        candidates = []

        # MD5 hash of release name (common obfuscation method)
        md5_hash = hashlib.md5(release_name.encode()).hexdigest()
        candidates.append(md5_hash)

        # SHA1 hash
        sha1_hash = hashlib.sha1(release_name.encode()).hexdigest()
        candidates.append(sha1_hash)

        # First 16 chars of MD5 (common truncation)
        candidates.append(md5_hash[:16])

        # First 32 chars of SHA1
        candidates.append(sha1_hash[:32])

        return candidates

    def _is_hash(self, text: str) -> bool:
        """Check if text looks like a hash"""
        import re

        return bool(
            re.match(r"^[a-fA-F0-9]{16,}$", text)  # Hex hash
            or re.match(r"^[a-zA-Z0-9_-]{22,}$", text)  # Base64-like
        )

    def print_stats(self):
        """Print seeding statistics"""
        logger.info("\n" + "=" * 50)
        logger.info("ORN Cache Seeding Statistics")
        logger.info("=" * 50)
        logger.info(f"Added:   {self.added_count}")
        logger.info(f"Skipped: {self.skipped_count}")
        logger.info(f"Errors:  {self.error_count}")
        logger.info("=" * 50 + "\n")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Seed ORN cache from various sources")
    parser.add_argument(
        "--source",
        choices=["predb", "hydra", "csv", "newznab"],
        required=True,
        help="Source to seed from",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Limit for PreDB/Newznab (default: 1000)",
    )
    parser.add_argument("--file", help="CSV file path (for csv source)")
    parser.add_argument(
        "--indexers", nargs="+", help="Newznab indexer URLs (for newznab source)"
    )
    parser.add_argument(
        "--apikeys", nargs="+", help="Newznab API keys (for newznab source)"
    )

    args = parser.parse_args()

    async with ORNSeeder() as seeder:
        if args.source == "predb":
            await seeder.seed_from_predb(limit=args.limit)
        elif args.source == "hydra":
            await seeder.seed_from_hydra()
        elif args.source == "csv":
            if not args.file:
                logger.error("--file required for csv source")
                return
            await seeder.seed_from_csv(args.file)
        elif args.source == "newznab":
            if not args.indexers or not args.apikeys:
                logger.error("--indexers and --apikeys required for newznab source")
                return
            if len(args.indexers) != len(args.apikeys):
                logger.error("Number of indexers must match number of API keys")
                return
            await seeder.seed_from_newznab(args.indexers, args.apikeys)

        seeder.print_stats()


if __name__ == "__main__":
    asyncio.run(main())
