import asyncio
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiohttp
from logger import setup_logger

logger = setup_logger("ValorantDataManager")


# Custom Exceptions
class ValorantAPIError(Exception):
    """Base exception for Valorant API errors."""

    pass


class RateLimitError(ValorantAPIError):
    """Raised when API rate limit is hit."""

    def __init__(self, retry_after: float = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after}s")


class PlayerNotFoundError(ValorantAPIError):
    """Raised when player is not found."""

    pass


class APIUnavailableError(ValorantAPIError):
    """Raised when API is unavailable."""

    pass


class ValorantDataManager:
    """
    Centralized manager for all Valorant API data with intelligent caching.
    Prevents duplicate API calls and coordinates rate limiting across cogs.
    """

    # API Configuration
    API_BASE = "https://api.henrikdev.xyz/valorant"

    CACHE_DURATIONS = {
        "mmr": 300,  # 5 minutes - player MMR data
        "match_history": 300,  # 5 minutes - match history
        "stored_matches": 600,  # 10 minutes - stored match data
        "mmr_history": 300,  # 5 minutes - MMR history
        "stored_mmr": 600,  # 10 minutes - stored MMR history
        "match_details": 3600,  # 60 minutes - detailed match data (rarely changes)
    }

    # Rate limiting
    MAX_REQUESTS_PER_MINUTE = 60
    RATE_LIMIT_WINDOW = 60  # seconds

    def __init__(self, bot):
        self.bot = bot
        self._cache = {}
        self._cache_timestamps = {}
        self._locks = defaultdict(asyncio.Lock)

        # Rate limiting
        self._request_times = []
        self._rate_limit_lock = asyncio.Lock()
        self._global_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests

        # API key
        self._api_key = os.getenv("VAL_KEY")
        if not self._api_key:
            logger.error("VAL_KEY not found in environment variables!")

        # Statistics
        self._stats = {
            "api_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "rate_limit_hits": 0,
            "errors": 0,
        }

    def _is_cache_valid(self, cache_key: str, cache_type: str) -> bool:
        """Check if cached data is still valid."""
        if cache_key not in self._cache_timestamps:
            return False

        age = datetime.now(timezone.utc).timestamp() - self._cache_timestamps[cache_key]
        max_age = self.CACHE_DURATIONS.get(cache_type, 300)
        return age < max_age

    async def _wait_for_rate_limit(self):
        """Implement rate limiting to avoid hitting API limits."""
        async with self._rate_limit_lock:
            now = datetime.now(timezone.utc).timestamp()

            # Remove old request times outside the window
            self._request_times = [
                t for t in self._request_times if now - t < self.RATE_LIMIT_WINDOW
            ]

            # Check if we're at the limit
            if len(self._request_times) >= self.MAX_REQUESTS_PER_MINUTE:
                # Calculate wait time
                oldest_request = self._request_times[0]
                wait_time = self.RATE_LIMIT_WINDOW - (now - oldest_request)

                if wait_time > 0:
                    logger.warning(f"Rate limit reached. Waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)

                    # Clean up again after waiting
                    now = datetime.now(timezone.utc).timestamp()
                    self._request_times = [
                        t
                        for t in self._request_times
                        if now - t < self.RATE_LIMIT_WINDOW
                    ]

            # Record this request
            self._request_times.append(now)

    async def _fetch_api(
        self, url: str, cache_key: str, cache_type: str, force_refresh: bool = False
    ) -> Dict:
        """
        Generic API fetch with caching, rate limiting, and error handling.

        Args:
            url: API endpoint URL
            cache_key: Unique cache key
            cache_type: Type of cache (for duration)
            force_refresh: Force bypass cache

        Returns:
            Dict with API response data

        Raises:
            RateLimitError: When rate limited
            PlayerNotFoundError: When player not found (404)
            APIUnavailableError: When API is down
        """
        # Check cache first
        if not force_refresh and self._is_cache_valid(cache_key, cache_type):
            self._stats["cache_hits"] += 1
            logger.debug(f"Cache hit for {cache_key}")
            return self._cache[cache_key]

        self._stats["cache_misses"] += 1

        # Use lock to prevent duplicate requests
        async with self._locks[cache_key]:
            # Double-check cache after acquiring lock
            if not force_refresh and self._is_cache_valid(cache_key, cache_type):
                return self._cache[cache_key]

            # Rate limiting
            await self._wait_for_rate_limit()

            # Use semaphore to limit concurrent requests
            async with self._global_semaphore:
                headers = {"Authorization": self._api_key}

                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            url,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=15),
                        ) as response:
                            self._stats["api_calls"] += 1

                            if response.status == 200:
                                data = await response.json()

                                # Cache the result
                                self._cache[cache_key] = data
                                self._cache_timestamps[cache_key] = datetime.now(
                                    timezone.utc
                                ).timestamp()

                                logger.info(f"✅ Fetched {cache_key} successfully")
                                return data

                            elif response.status == 404:
                                logger.warning(f"❌ 404 Not Found: {cache_key}")
                                raise PlayerNotFoundError(
                                    f"Player not found: {cache_key}"
                                )

                            elif response.status == 429:
                                retry_after = response.headers.get("Retry-After", "60")
                                try:
                                    wait_time = float(retry_after)
                                except ValueError:
                                    wait_time = 60

                                self._stats["rate_limit_hits"] += 1
                                logger.warning(
                                    f"⚠️ Rate limited. Retry after {wait_time}s"
                                )
                                raise RateLimitError(wait_time)

                            else:
                                logger.error(f"❌ API Error {response.status}: {url}")
                                self._stats["errors"] += 1
                                raise APIUnavailableError(
                                    f"API returned status {response.status}"
                                )

                except aiohttp.ClientError as e:
                    logger.error(f"❌ Network error fetching {cache_key}: {e}")
                    self._stats["errors"] += 1

                    # Return stale cache if available
                    if cache_key in self._cache:
                        logger.warning(f"Using stale cache for {cache_key}")
                        return self._cache[cache_key]

                    raise APIUnavailableError(f"Network error: {e}")

                except asyncio.TimeoutError:
                    logger.error(f"❌ Timeout fetching {cache_key}")
                    self._stats["errors"] += 1

                    # Return stale cache if available
                    if cache_key in self._cache:
                        logger.warning(f"Using stale cache for {cache_key}")
                        return self._cache[cache_key]

                    raise APIUnavailableError("Request timed out")

    async def get_player_mmr(
        self, name: str, tag: str, region: str = "na", force_refresh: bool = False
    ) -> Dict:
        """
        Get current MMR data for a player.

        Args:
            name: Player name
            tag: Player tag
            region: Region (na, eu, ap, kr)
            force_refresh: Force bypass cache

        Returns:
            Dict with MMR data
        """
        name, tag = name.lower(), tag.lower()
        cache_key = f"mmr_{region}_{name}_{tag}"
        url = f"{self.API_BASE}/v3/mmr/{region}/pc/{name}/{tag}"

        return await self._fetch_api(url, cache_key, "mmr", force_refresh)

    async def get_mmr_history(
        self, name: str, tag: str, region: str = "na", force_refresh: bool = False
    ) -> Dict:
        """
        Get recent MMR history for a player.

        Args:
            name: Player name
            tag: Player tag
            region: Region
            force_refresh: Force bypass cache

        Returns:
            Dict with MMR history
        """
        name, tag = name.lower(), tag.lower()
        cache_key = f"mmr_history_{region}_{name}_{tag}"
        url = f"{self.API_BASE}/v2/mmr-history/{region}/pc/{name}/{tag}"

        return await self._fetch_api(url, cache_key, "mmr_history", force_refresh)

    async def get_stored_mmr_history(
        self, name: str, tag: str, region: str = "na", force_refresh: bool = False
    ) -> Dict:
        """
        Get full stored MMR history for a player.

        Args:
            name: Player name
            tag: Player tag
            region: Region
            force_refresh: Force bypass cache

        Returns:
            Dict with stored MMR history
        """
        name, tag = name.lower(), tag.lower()
        cache_key = f"stored_mmr_{region}_{name}_{tag}"
        url = f"{self.API_BASE}/v2/stored-mmr-history/{region}/pc/{name}/{tag}"

        return await self._fetch_api(url, cache_key, "stored_mmr", force_refresh)

    async def get_match_history(
        self, name: str, tag: str, region: str = "na", force_refresh: bool = False
    ) -> Dict:
        """
        Get stored match history for a player.

        Args:
            name: Player name
            tag: Player tag
            region: Region
            force_refresh: Force bypass cache

        Returns:
            Dict with match history
        """
        name, tag = name.lower(), tag.lower()
        cache_key = f"matches_{region}_{name}_{tag}"
        url = f"{self.API_BASE}/v1/stored-matches/{region}/{name}/{tag}"

        return await self._fetch_api(url, cache_key, "stored_matches", force_refresh)

    async def get_match_details(
        self, match_id: str, force_refresh: bool = False
    ) -> Dict:
        """
        Get detailed information for a specific match.

        Args:
            match_id: Match ID
            force_refresh: Force bypass cache

        Returns:
            Dict with detailed match data including rounds and kill events

        Raises:
            PlayerNotFoundError: When match not found (404)
            APIUnavailableError: When API is down or network error
        """
        if not match_id:
            logger.warning("Empty match_id provided to get_match_details()")
            raise ValueError("match_id cannot be empty")

        cache_key = f"match_details_{match_id}"
        url = f"{self.API_BASE}/v2/match/{match_id}"

        return await self._fetch_api(url, cache_key, "match_details", force_refresh)

    async def batch_get_player_mmr(self, players, region="na", force_refresh=False):
        """
        Fetch MMR data for multiple players in parallel with proper error handling.

        Args:
            players: List of (name, tag) tuples
            region: Region to fetch from
            force_refresh: Force bypass cache

        Returns:
            Dict mapping (name, tag) -> mmr_data (or None if error)

        Raises:
            RateLimitError: If rate limited (stops all processing)
        """
        results = {}
        batch_size = 5

        for i in range(0, len(players), batch_size):
            batch = players[i : i + batch_size]
            tasks = [
                self.get_player_mmr(name, tag, region, force_refresh)
                for name, tag in batch
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for (name, tag), result in zip(batch, batch_results):
                if isinstance(result, RateLimitError):
                    logger.error(f"Rate limited during batch update!")
                    # Re-raise to stop processing
                    raise result
                elif isinstance(result, Exception):
                    logger.warning(
                        f"Error fetching MMR for {name}#{tag}: {result.__class__.__name__}: {result}"
                    )
                    results[(name, tag)] = None
                else:
                    results[(name, tag)] = result

        return results

    async def batch_get_match_details(self, match_ids: List[str]) -> Dict[str, Dict]:
        """
        Fetch detailed data for multiple matches in parallel.

        Args:
            match_ids: List of match IDs

        Returns:
            Dict mapping match_id -> match_data (or None if error)
        """
        if not match_ids:
            return {}

        results = {}
        tasks = [self.get_match_details(mid) for mid in match_ids if mid]

        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for mid, result in zip(match_ids, batch_results):
            if isinstance(result, Exception):
                logger.warning(
                    f"Error fetching match details for {mid}: {result.__class__.__name__}"
                )
                results[mid] = None
            else:
                results[mid] = result

        return results

    def parse_mmr_data(self, mmr_data: Dict) -> Dict:
        """
        Parse MMR data into a standardized format.

        Args:
            mmr_data: Raw MMR data from API

        Returns:
            Dict with parsed data: {rank, elo, games_needed}

        Raises:
            ValueError: If mmr_data is invalid
        """
        if not mmr_data:
            raise ValueError("mmr_data cannot be None")

        if "data" not in mmr_data:
            logger.warning(f"Invalid MMR data structure: {mmr_data}")
            raise ValueError("mmr_data missing 'data' key")

        current = mmr_data["data"].get("current", {})
        if not current:
            logger.warning("MMR data has no 'current' field")
            raise ValueError("mmr_data missing 'current' field")

        games_needed = current.get("games_needed_for_rating", 0)

        if games_needed > 0:
            return {"rank": "Unrated", "elo": 0, "games_needed": games_needed}

        rank = current.get("tier", {}).get("name", "Unknown")
        elo = current.get("rr", 0)

        if rank == "Unknown":
            logger.warning("Could not determine rank from MMR data")

        return {
            "rank": rank,
            "elo": elo,
            "games_needed": 0,
        }

    def clear_cache(self, cache_type: Optional[str] = None):
        """
        Clear cache for specific type or all caches.

        Args:
            cache_type: Specific cache type to clear (None = clear all)
        """
        if cache_type:
            keys_to_remove = [
                key for key in self._cache.keys() if key.startswith(cache_type)
            ]
            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
            logger.info(f"Cleared {len(keys_to_remove)} cache entries for {cache_type}")
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
            logger.info("Cleared all cache")

    def invalidate_player_cache(self, name: str, tag: str):
        """
        Invalidate all cached data for a specific player.

        Args:
            name: Player name
            tag: Player tag
        """
        name, tag = name.lower(), tag.lower()
        player_key = f"{name}_{tag}"

        keys_to_remove = [key for key in self._cache.keys() if player_key in key]

        for key in keys_to_remove:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)

        logger.info(
            f"Invalidated cache for {name}#{tag} ({len(keys_to_remove)} entries)"
        )

    def get_cache_stats(self) -> Dict:
        """Get statistics about current cache state and API usage."""
        now = datetime.now(timezone.utc).timestamp()

        stats = {
            "total_cached": len(self._cache),
            "by_type": defaultdict(int),
            "api_calls": self._stats["api_calls"],
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "cache_hit_rate": 0,
            "rate_limit_hits": self._stats["rate_limit_hits"],
            "errors": self._stats["errors"],
            "requests_in_window": len(self._request_times),
        }

        # Calculate cache hit rate
        total_requests = stats["cache_hits"] + stats["cache_misses"]
        if total_requests > 0:
            stats["cache_hit_rate"] = (stats["cache_hits"] / total_requests) * 100

        # Count by type
        for key in self._cache.keys():
            cache_type = key.split("_")[0]
            stats["by_type"][cache_type] += 1

        # Count fresh vs stale
        fresh = sum(
            1
            for key, timestamp in self._cache_timestamps.items()
            if now - timestamp < self.CACHE_DURATIONS.get(key.split("_")[0], 300)
        )
        stats["fresh_cache"] = fresh
        stats["stale_cache"] = len(self._cache) - fresh

        return stats

    def reset_stats(self):
        """Reset usage statistics."""
        self._stats = {
            "api_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "rate_limit_hits": 0,
            "errors": 0,
        }
        logger.info("Reset statistics")
