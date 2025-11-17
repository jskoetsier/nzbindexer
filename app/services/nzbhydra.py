"""
NZBHydra2 Integration Service

NZBHydra2 is a meta-indexer that maintains its own deobfuscation database.
We can query it for hash lookups and import its mappings.
"""

import logging
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class NZBHydraService:
    """
    Integration with NZBHydra2 for hash lookups and deobfuscation

    NZBHydra2 API: https://github.com/theotherp/nzbhydra2
    """

    def __init__(self, hydra_url: str, api_key: str):
        """
        Initialize NZBHydra2 service

        Args:
            hydra_url: Base URL of NZBHydra2 instance (e.g., "http://localhost:5076")
            api_key: NZBHydra2 API key
        """
        self.hydra_url = hydra_url.rstrip("/")
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
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

    async def search(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search NZBHydra2 for releases

        Args:
            query: Search query (can be a hash)
            limit: Maximum results

        Returns:
            List of release dicts
        """
        try:
            session = await self._get_session()

            # NZBHydra2 API search endpoint
            url = f"{self.hydra_url}/api"

            params = {
                "apikey": self.api_key,
                "t": "search",
                "q": query,
                "limit": limit,
                "o": "json",
            }

            logger.debug(f"Searching NZBHydra2 for: {query}")

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    # Parse results
                    results = []
                    items = data.get("items", [])

                    for item in items:
                        results.append(
                            {
                                "title": item.get("title"),
                                "guid": item.get("guid"),
                                "link": item.get("link"),
                                "size": item.get("size"),
                                "pubDate": item.get("pubDate"),
                            }
                        )

                    return results
                else:
                    logger.warning(f"NZBHydra2 search failed: HTTP {response.status}")
                    return []

        except Exception as e:
            logger.error(f"Error querying NZBHydra2: {e}")
            return []

    async def lookup_hash(self, hash_value: str) -> Optional[str]:
        """
        Lookup a hash in NZBHydra2

        Args:
            hash_value: Obfuscated hash to lookup

        Returns:
            Real release name if found
        """
        results = await self.search(hash_value, limit=1)

        if results and len(results) > 0:
            title = results[0].get("title")
            if title and title != hash_value:
                logger.info(f"NZBHydra2 match: '{hash_value}' -> '{title}'")
                return title

        return None
