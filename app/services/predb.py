"""
PreDB (Pre-Release Database) Service

Integrates with external PreDB APIs to lookup obfuscated release names.
Includes caching and fallback to multiple API providers.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiohttp

from app.db.models.orn_mapping import ORNMapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PreDBService:
    """
    PreDB API integration service for deobfuscation

    Supports multiple PreDB API providers with automatic fallback.
    Caches results locally in ORN database.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.session: Optional[aiohttp.ClientSession] = None

        # PreDB API endpoints (in order of preference)
        self.predb_apis = [
            {
                "name": "predb.ovh",
                "url": "https://predb.ovh/api/v1/",
                "method": "posts",
                "query_param": "q",
            },
            {
                "name": "predb.me",
                "url": "https://predb.me/api/v1/",
                "method": "",
                "query_param": "q",
            },
        ]

        # Timeout for API requests
        self.timeout = aiohttp.ClientTimeout(total=10)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session

    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def lookup_in_cache(self, obfuscated_name: str) -> Optional[str]:
        """
        Look up obfuscated name in local ORN cache

        Args:
            obfuscated_name: The obfuscated hash/name to look up

        Returns:
            Real release name if found in cache, None otherwise
        """
        try:
            # Normalize the obfuscated name
            normalized = self._normalize_name(obfuscated_name)

            # Query the ORN mappings table
            query = select(ORNMapping).filter(ORNMapping.obfuscated_hash == normalized)
            result = await self.db.execute(query)
            mapping = result.scalars().first()

            if mapping:
                # Update last_used and use_count
                mapping.last_used = datetime.now(timezone.utc)
                mapping.use_count += 1
                await self.db.commit()

                logger.info(
                    f"Cache hit for '{obfuscated_name}' -> '{mapping.real_name}' (source: {mapping.source})"
                )
                return mapping.real_name

            return None

        except Exception as e:
            logger.error(f"Error looking up in cache: {e}")
            return None

    async def save_to_cache(
        self, obfuscated_name: str, real_name: str, source: str, confidence: float = 1.0
    ) -> bool:
        """
        Save mapping to local ORN cache

        Args:
            obfuscated_name: The obfuscated hash/name
            real_name: The real release name
            source: Source of the mapping (predb, manual, etc.)
            confidence: Confidence score (0.0 to 1.0)

        Returns:
            True if saved successfully
        """
        try:
            normalized = self._normalize_name(obfuscated_name)

            # Check if mapping already exists
            query = select(ORNMapping).filter(ORNMapping.obfuscated_hash == normalized)
            result = await self.db.execute(query)
            existing = result.scalars().first()

            if existing:
                # Update existing mapping if confidence is higher
                if confidence > existing.confidence:
                    existing.real_name = real_name
                    existing.source = source
                    existing.confidence = confidence
                    existing.last_used = datetime.now(timezone.utc)
                    existing.use_count += 1
                    logger.info(
                        f"Updated cache mapping: '{obfuscated_name}' -> '{real_name}'"
                    )
                else:
                    logger.debug(
                        f"Skipping cache update (lower confidence): '{obfuscated_name}'"
                    )
            else:
                # Create new mapping
                mapping = ORNMapping(
                    obfuscated_hash=normalized,
                    real_name=real_name,
                    source=source,
                    confidence=confidence,
                )
                self.db.add(mapping)
                logger.info(
                    f"Added to cache: '{obfuscated_name}' -> '{real_name}' (source: {source})"
                )

            await self.db.commit()
            return True

        except Exception as e:
            logger.error(f"Error saving to cache: {e}")
            await self.db.rollback()
            return False

    async def query_predb_api(
        self, obfuscated_name: str, api_config: Dict
    ) -> Optional[str]:
        """
        Query a single PreDB API

        Args:
            obfuscated_name: The obfuscated name to search for
            api_config: API configuration dict

        Returns:
            Real release name if found, None otherwise
        """
        try:
            session = await self._get_session()

            # Build API URL
            if api_config["method"]:
                url = f"{api_config['url']}{api_config['method']}"
            else:
                url = api_config["url"]

            # Add query parameter
            params = {api_config["query_param"]: obfuscated_name}

            logger.debug(f"Querying {api_config['name']}: {url} with params {params}")

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    # Parse response based on API
                    release_name = self._parse_predb_response(data, api_config["name"])

                    if release_name:
                        logger.info(
                            f"PreDB match from {api_config['name']}: '{obfuscated_name}' -> '{release_name}'"
                        )
                        return release_name
                else:
                    logger.debug(
                        f"PreDB API {api_config['name']} returned status {response.status}"
                    )

        except asyncio.TimeoutError:
            logger.warning(f"PreDB API {api_config['name']} timed out")
        except Exception as e:
            logger.debug(f"Error querying PreDB API {api_config['name']}: {e}")

        return None

    def _parse_predb_response(self, data: Dict, api_name: str) -> Optional[str]:
        """
        Parse PreDB API response to extract release name

        Args:
            data: JSON response from API
            api_name: Name of the API

        Returns:
            Release name if found
        """
        try:
            if api_name == "predb.ovh":
                # predb.ovh format: {"status": "success", "rowCount": 1, "data": [{"name": "..."}]}
                if data.get("status") == "success" and data.get("rowCount", 0) > 0:
                    posts = data.get("data", [])
                    if posts and len(posts) > 0:
                        return posts[0].get("name")

            elif api_name == "predb.me":
                # predb.me format: {"status": "success", "data": {"name": "..."}}
                if data.get("status") == "success":
                    release_data = data.get("data", {})
                    if isinstance(release_data, dict):
                        return release_data.get("name")
                    elif isinstance(release_data, list) and len(release_data) > 0:
                        return release_data[0].get("name")

        except Exception as e:
            logger.debug(f"Error parsing PreDB response from {api_name}: {e}")

        return None

    async def lookup_obfuscated_name(self, obfuscated_name: str) -> Optional[str]:
        """
        Full lookup pipeline: cache -> PreDB APIs -> cache result

        Args:
            obfuscated_name: The obfuscated hash/name to deobfuscate

        Returns:
            Real release name if found, None otherwise
        """
        # Step 1: Check local cache
        cached_result = await self.lookup_in_cache(obfuscated_name)
        if cached_result:
            return cached_result

        # Step 2: Try PreDB APIs in order
        for api_config in self.predb_apis:
            result = await self.query_predb_api(obfuscated_name, api_config)

            if result:
                # Save to cache
                await self.save_to_cache(
                    obfuscated_name,
                    result,
                    source=f"predb_{api_config['name']}",
                    confidence=0.95,
                )
                return result

        logger.debug(f"No PreDB match found for: {obfuscated_name}")
        return None

    async def bulk_lookup(
        self, obfuscated_names: List[str]
    ) -> Dict[str, Optional[str]]:
        """
        Lookup multiple obfuscated names in parallel

        Args:
            obfuscated_names: List of obfuscated names to look up

        Returns:
            Dict mapping obfuscated names to real names (or None)
        """
        tasks = [self.lookup_obfuscated_name(name) for name in obfuscated_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dict
        result_dict = {}
        for name, result in zip(obfuscated_names, results):
            if isinstance(result, Exception):
                logger.error(f"Error in bulk lookup for '{name}': {result}")
                result_dict[name] = None
            else:
                result_dict[name] = result

        return result_dict

    def _normalize_name(self, name: str) -> str:
        """
        Normalize obfuscated name for consistent cache lookups

        Args:
            name: Name to normalize

        Returns:
            Normalized name
        """
        # Remove common extensions and part numbers
        normalized = name

        # Strip extensions
        normalized = re.sub(
            r"\.(rar|par2?|zip|7z|nfo|sfv|r\d{2,3}|part\d+|vol\d+\+?\d*)$",
            "",
            normalized,
            flags=re.IGNORECASE,
        )

        # Strip part numbers
        normalized = re.sub(r"\.part\d+$", "", normalized, flags=re.IGNORECASE)

        # Strip trailing dots, dashes, underscores
        normalized = normalized.strip(".-_")

        # Lowercase for consistency
        normalized = normalized.lower()

        return normalized

    async def add_manual_mapping(self, obfuscated_name: str, real_name: str) -> bool:
        """
        Manually add a mapping to the ORN database

        Args:
            obfuscated_name: The obfuscated hash/name
            real_name: The real release name

        Returns:
            True if added successfully
        """
        return await self.save_to_cache(
            obfuscated_name, real_name, source="manual", confidence=1.0
        )

    async def get_cache_stats(self) -> Dict:
        """
        Get statistics about the ORN cache

        Returns:
            Dict with cache statistics
        """
        try:
            from sqlalchemy import func

            # Total mappings
            total_query = select(func.count(ORNMapping.id))
            total_result = await self.db.execute(total_query)
            total = total_result.scalar()

            # Mappings by source
            by_source_query = select(
                ORNMapping.source, func.count(ORNMapping.id).label("count")
            ).group_by(ORNMapping.source)
            by_source_result = await self.db.execute(by_source_query)
            by_source = {row[0]: row[1] for row in by_source_result}

            # Most used mappings
            most_used_query = (
                select(ORNMapping).order_by(ORNMapping.use_count.desc()).limit(10)
            )
            most_used_result = await self.db.execute(most_used_query)
            most_used = most_used_result.scalars().all()

            return {
                "total_mappings": total,
                "by_source": by_source,
                "most_used": [
                    {
                        "obfuscated": m.obfuscated_hash,
                        "real_name": m.real_name,
                        "use_count": m.use_count,
                    }
                    for m in most_used
                ],
            }

        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}
