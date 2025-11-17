"""
TMDB/IMDB Metadata Matching Service

Match obfuscated hashes against movie/TV show databases to extract real titles.
"""

import logging
import re
from typing import Dict, List, Optional

import tmdbsimple as tmdb

logger = logging.getLogger(__name__)


class MetadataService:
    """
    Media metadata matching service using TMDB API

    Attempts to match obfuscated releases against known movies/TV shows
    by parsing release name patterns and querying metadata databases.
    """

    def __init__(self, tmdb_api_key: str):
        """
        Initialize metadata service

        Args:
            tmdb_api_key: TMDB API key (get from https://www.themoviedb.org/settings/api)
        """
        tmdb.API_KEY = tmdb_api_key
        self.search = tmdb.Search()

    def extract_release_info(self, release_name: str) -> Dict:
        """
        Extract information from release name

        Args:
            release_name: Release name to parse

        Returns:
            Dict with extracted info (title, year, quality, etc.)
        """
        info = {
            "title": None,
            "year": None,
            "quality": None,
            "source": None,
            "codec": None,
            "group": None,
            "season": None,
            "episode": None,
        }

        # Extract year (4 digits)
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", release_name)
        if year_match:
            info["year"] = int(year_match.group(1))

        # Extract quality (1080p, 720p, 2160p, etc.)
        quality_match = re.search(r"\b(\d{3,4}p|UHD|4K)\b", release_name, re.IGNORECASE)
        if quality_match:
            info["quality"] = quality_match.group(1)

        # Extract source (BluRay, WEB-DL, HDTV, etc.)
        source_match = re.search(
            r"\b(BluRay|BDRip|WEB-DL|WEBRip|HDTV|DVDRip|BRRip)\b",
            release_name,
            re.IGNORECASE,
        )
        if source_match:
            info["source"] = source_match.group(1)

        # Extract codec (x264, x265, HEVC, H.264, etc.)
        codec_match = re.search(
            r"\b(x264|x265|HEVC|H\.264|H\.265|XviD|DivX)\b",
            release_name,
            re.IGNORECASE,
        )
        if codec_match:
            info["codec"] = codec_match.group(1)

        # Extract group (after the last dash)
        group_match = re.search(r"-([A-Za-z0-9]+)$", release_name)
        if group_match:
            info["group"] = group_match.group(1)

        # Extract season/episode (S01E01, 1x01, etc.)
        se_match = re.search(
            r"\b[Ss](\d{1,2})[Ee](\d{1,2})\b", release_name
        ) or re.search(r"\b(\d{1,2})x(\d{1,2})\b", release_name)
        if se_match:
            info["season"] = int(se_match.group(1))
            info["episode"] = int(se_match.group(2))

        # Extract title (everything before year/quality/source markers)
        title_end = len(release_name)

        # Find first occurrence of metadata markers
        markers = [
            year_match.start() if year_match else title_end,
            quality_match.start() if quality_match else title_end,
            source_match.start() if source_match else title_end,
            se_match.start() if se_match else title_end,
        ]

        title_end = min(markers)
        title = release_name[:title_end].strip(".- ")

        # Replace dots/underscores with spaces
        title = re.sub(r"[._]", " ", title)
        title = re.sub(r"\s+", " ", title).strip()

        info["title"] = title

        return info

    async def search_movie(
        self, title: str, year: Optional[int] = None
    ) -> Optional[str]:
        """
        Search for a movie by title

        Args:
            title: Movie title
            year: Optional year to narrow search

        Returns:
            Full movie title if found
        """
        try:
            response = self.search.movie(query=title, year=year)
            results = response.get("results", [])

            if results and len(results) > 0:
                movie = results[0]
                movie_title = movie.get("title")
                release_year = movie.get("release_date", "")[:4]

                full_title = (
                    f"{movie_title} ({release_year})" if release_year else movie_title
                )
                logger.info(f"TMDB movie match: '{title}' -> '{full_title}'")
                return full_title

        except Exception as e:
            logger.debug(f"Error searching TMDB movies: {e}")

        return None

    async def search_tv(self, title: str, year: Optional[int] = None) -> Optional[str]:
        """
        Search for a TV show by title

        Args:
            title: TV show title
            year: Optional year to narrow search

        Returns:
            Full TV show title if found
        """
        try:
            response = self.search.tv(query=title, first_air_date_year=year)
            results = response.get("results", [])

            if results and len(results) > 0:
                show = results[0]
                show_title = show.get("name")
                first_air = show.get("first_air_date", "")[:4]

                full_title = f"{show_title} ({first_air})" if first_air else show_title
                logger.info(f"TMDB TV match: '{title}' -> '{full_title}'")
                return full_title

        except Exception as e:
            logger.debug(f"Error searching TMDB TV: {e}")

        return None

    async def match_release(self, release_name: str) -> Optional[str]:
        """
        Match a release name against TMDB database

        Args:
            release_name: Release name to match

        Returns:
            Matched title with year if found
        """
        # Extract release info
        info = self.extract_release_info(release_name)

        if not info.get("title"):
            return None

        title = info["title"]
        year = info.get("year")

        # Determine if it's TV or movie based on season/episode
        if info.get("season") is not None or info.get("episode") is not None:
            # It's a TV show
            result = await self.search_tv(title, year)
        else:
            # Try movie first, then TV
            result = await self.search_movie(title, year)
            if not result:
                result = await self.search_tv(title, year)

        return result

    async def enrich_release_metadata(self, release_name: str) -> Dict:
        """
        Extract and enrich release metadata

        Args:
            release_name: Release name to analyze

        Returns:
            Dict with enriched metadata
        """
        info = self.extract_release_info(release_name)

        # Try to match against TMDB
        matched_title = await self.match_release(release_name)
        if matched_title:
            info["matched_title"] = matched_title

        return info
