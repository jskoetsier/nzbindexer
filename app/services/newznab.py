"""
Newznab Protocol Client

Query other Usenet indexers via Newznab API protocol for cross-indexer deobfuscation.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class NewznabClient:
    """
    Newznab API protocol client for querying other Usenet indexers

    Supports:
    - Search by hash/name
    - Release lookups
    - Cross-indexer deobfuscation
    """

    def __init__(self, base_url: str, api_key: str):
        """
        Initialize Newznab client

        Args:
            base_url: Base URL of the Newznab indexer (e.g., "https://api.nzbgeek.info")
            api_key: API key for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=15)

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
        Search for releases by query

        Args:
            query: Search query (hash, release name, etc.)
            limit: Maximum number of results

        Returns:
            List of release dicts
        """
        try:
            session = await self._get_session()

            params = {
                "t": "search",
                "apikey": self.api_key,
                "q": query,
                "limit": limit,
                "o": "json",  # Request JSON output (fallback to XML if not supported)
            }

            url = f"{self.base_url}/api"

            logger.debug(f"Newznab search: {url} with query '{query}'")

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    content_type = response.headers.get("Content-Type", "")

                    # Try JSON first
                    if "json" in content_type:
                        data = await response.json()
                        return self._parse_json_response(data)
                    else:
                        # Fall back to XML
                        text = await response.text()
                        return self._parse_xml_response(text)
                else:
                    logger.warning(f"Newznab search failed: HTTP {response.status}")
                    return []

        except Exception as e:
            logger.error(f"Error querying Newznab API: {e}")
            return []

    def _parse_json_response(self, data: Dict) -> List[Dict]:
        """Parse JSON response from Newznab API"""
        try:
            items = data.get("channel", {}).get("item", [])

            # Handle single item (not in array)
            if isinstance(items, dict):
                items = [items]

            releases = []
            for item in items:
                release = {
                    "title": item.get("title"),
                    "guid": item.get("guid"),
                    "link": item.get("link"),
                    "pubDate": item.get("pubDate"),
                    "category": item.get("category"),
                    "size": item.get("size", 0),
                    "files": item.get("files", 0),
                }

                # Parse attributes
                attrs = item.get("attr", [])
                for attr in attrs:
                    name = attr.get("@attributes", {}).get("name")
                    value = attr.get("@attributes", {}).get("value")
                    if name and value:
                        release[name] = value

                releases.append(release)

            return releases

        except Exception as e:
            logger.error(f"Error parsing Newznab JSON: {e}")
            return []

    def _parse_xml_response(self, xml_text: str) -> List[Dict]:
        """Parse XML response from Newznab API"""
        try:
            root = ET.fromstring(xml_text)
            channel = root.find("channel")

            if channel is None:
                return []

            releases = []
            for item in channel.findall("item"):
                release = {
                    "title": self._get_elem_text(item, "title"),
                    "guid": self._get_elem_text(item, "guid"),
                    "link": self._get_elem_text(item, "link"),
                    "pubDate": self._get_elem_text(item, "pubDate"),
                    "category": self._get_elem_text(item, "category"),
                    "size": int(self._get_elem_text(item, "size", "0")),
                    "files": int(self._get_elem_text(item, "files", "0")),
                }

                # Parse newznab:attr elements
                for attr in item.findall(
                    "{http://www.newznab.com/DTD/2010/feeds/attributes/}attr"
                ):
                    name = attr.get("name")
                    value = attr.get("value")
                    if name and value:
                        release[name] = value

                releases.append(release)

            return releases

        except Exception as e:
            logger.error(f"Error parsing Newznab XML: {e}")
            return []

    def _get_elem_text(self, parent, tag: str, default: str = "") -> str:
        """Get text content of XML element"""
        elem = parent.find(tag)
        return elem.text if elem is not None and elem.text else default

    async def lookup_by_hash(self, hash_value: str) -> Optional[str]:
        """
        Lookup a release by hash value

        Args:
            hash_value: Hash/obfuscated name to lookup

        Returns:
            Real release name if found
        """
        results = await self.search(hash_value, limit=1)

        if results and len(results) > 0:
            title = results[0].get("title")
            if title and title != hash_value:
                logger.info(f"Newznab match: '{hash_value}' -> '{title}'")
                return title

        return None


class NewznabPool:
    """
    Pool of Newznab indexers for parallel querying
    """

    def __init__(self):
        self.indexers: List[NewznabClient] = []

    def add_indexer(self, base_url: str, api_key: str):
        """Add an indexer to the pool"""
        client = NewznabClient(base_url, api_key)
        self.indexers.append(client)
        logger.info(f"Added Newznab indexer: {base_url}")

    async def close_all(self):
        """Close all indexer sessions"""
        for indexer in self.indexers:
            await indexer.close()

    async def search_all(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search all indexers in parallel

        Args:
            query: Search query
            limit: Results per indexer

        Returns:
            Combined results from all indexers
        """
        import asyncio

        tasks = [indexer.search(query, limit) for indexer in self.indexers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine and deduplicate results
        combined = []
        seen_guids = set()

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error in parallel search: {result}")
                continue

            for release in result:
                guid = release.get("guid")
                if guid and guid not in seen_guids:
                    combined.append(release)
                    seen_guids.add(guid)

        return combined

    async def lookup_by_hash(self, hash_value: str) -> Optional[str]:
        """
        Lookup hash across all indexers in parallel

        Args:
            hash_value: Hash to lookup

        Returns:
            First matching release name found
        """
        import asyncio

        tasks = [indexer.lookup_by_hash(hash_value) for indexer in self.indexers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Return first successful match
        for result in results:
            if isinstance(result, str) and result:
                return result

        return None
