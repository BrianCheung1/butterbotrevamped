import asyncio
import time
from collections import defaultdict
from typing import Dict, List, Optional

import aiohttp


class OSRSDataManager:
    """
    Centralized manager for all OSRS API data with intelligent caching.
    Prevents duplicate API calls across multiple cogs.
    """

    # API Endpoints
    WIKI_BASE = "https://prices.runescape.wiki/api/v1/osrs"
    ENDPOINTS = {
        "latest": f"{WIKI_BASE}/latest",
        "mapping": f"{WIKI_BASE}/mapping",
        "5m": f"{WIKI_BASE}/5m",
        "1h": f"{WIKI_BASE}/1h",
        "6h": f"{WIKI_BASE}/6h",
        "24h": f"{WIKI_BASE}/24h",
        "timeseries": f"{WIKI_BASE}/timeseries",
        "weirdgloop": "https://api.weirdgloop.org/exchange/history/osrs/latest",
    }

    # Cache durations (in seconds)
    CACHE_DURATIONS = {
        "latest": 60,  # 1 minute - price data changes frequently
        "mapping": 3600,  # 1 hour - item list rarely changes
        "5m": 60,  # 1 minute
        "1h": 300,  # 5 minutes
        "6h": 600,  # 10 minutes
        "24h": 1800,  # 30 minutes
        "timeseries": 60,  # 1 minute
        "weirdgloop": 60,  # 1 minute
    }

    def __init__(self, bot):
        self.bot = bot
        self._cache = {}
        self._cache_timestamps = {}
        self._locks = defaultdict(asyncio.Lock)

        # Pre-built indices for fast lookups
        self.name_to_id = {}
        self.id_to_item = {}
        self._items_loaded = False

        # Search indices for autocomplete
        self.indices = defaultdict(lambda: defaultdict(list))

    async def initialize(self):
        """Load initial data on startup."""
        await self.get_mapping()
        self.bot.logger.info("[OSRSDataManager] Initialized with item mappings")

    def _is_cache_valid(self, cache_key: str, endpoint_type: str) -> bool:
        """Check if cached data is still valid."""
        if cache_key not in self._cache_timestamps:
            return False

        age = time.time() - self._cache_timestamps[cache_key]
        max_age = self.CACHE_DURATIONS.get(endpoint_type, 60)
        return age < max_age

    async def _fetch_with_cache(
        self, cache_key: str, endpoint_type: str, url: str, force_refresh: bool = False
    ) -> Dict:
        """Generic fetch method with caching and locking."""
        # Check cache first
        if not force_refresh and self._is_cache_valid(cache_key, endpoint_type):
            return self._cache[cache_key]

        # Use lock to prevent duplicate requests
        async with self._locks[cache_key]:
            # Double-check cache after acquiring lock
            if not force_refresh and self._is_cache_valid(cache_key, endpoint_type):
                return self._cache[cache_key]

            # Fetch fresh data
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=15)
                    ) as response:
                        response.raise_for_status()
                        data = await response.json()

                # Cache the result
                self._cache[cache_key] = data
                self._cache_timestamps[cache_key] = time.time()
                return data

            except Exception as e:
                self.bot.logger.error(
                    f"[OSRSDataManager] Error fetching {cache_key}: {e}"
                )
                # Return stale cache if available, otherwise raise
                if cache_key in self._cache:
                    self.bot.logger.warning(
                        f"[OSRSDataManager] Using stale cache for {cache_key}"
                    )
                    return self._cache[cache_key]
                raise

    async def get_latest_prices(
        self, item_ids: Optional[List[int]] = None, force_refresh: bool = False
    ) -> Dict:
        """
        Get latest prices for items.

        Args:
            item_ids: Specific item IDs to fetch (None = all items)
            force_refresh: Force bypass cache

        Returns:
            Dict with 'data' key containing price data
        """
        url = self.ENDPOINTS["latest"]
        if item_ids:
            url += f"?id={','.join(map(str, item_ids))}"

        cache_key = f"latest_{','.join(map(str, item_ids)) if item_ids else 'all'}"
        return await self._fetch_with_cache(cache_key, "latest", url, force_refresh)

    async def get_mapping(self, force_refresh: bool = False) -> List[Dict]:
        """Get item mapping data (ID to name, etc)."""
        data = await self._fetch_with_cache(
            "mapping", "mapping", self.ENDPOINTS["mapping"], force_refresh
        )

        # Build lookup indices on first load
        if not self._items_loaded:
            self._build_indices(data)
            self._items_loaded = True

        return data

    def _build_indices(self, items: List[Dict]):
        """Build search indices for fast autocomplete."""
        self.name_to_id = {item["name"].lower(): item["id"] for item in items}
        self.id_to_item = {item["id"]: item for item in items}

        # Build autocomplete indices
        for item in items:
            name_lower = item["name"].lower()

            # Exact match
            self.indices["exact"][name_lower] = item

            # Prefix indices (all lengths)
            for length in range(1, len(name_lower) + 1):
                prefix = name_lower[:length]
                if len(self.indices["prefix"][prefix]) < 200:
                    self.indices["prefix"][prefix].append(item)

            # Word indices
            for word in name_lower.split():
                if len(word) >= 2:
                    if len(self.indices["word"][word]) < 100:
                        self.indices["word"][word].append(item)

            # Substring indices for abbreviations
            for i in range(len(name_lower)):
                for j in range(i + 3, min(i + 8, len(name_lower) + 1)):
                    substring = name_lower[i:j]
                    if len(self.indices["substring"][substring]) < 50:
                        self.indices["substring"][substring].append(item)

    async def get_timeseries(
        self, item_id: int, timestep: str = "5m", force_refresh: bool = False
    ) -> List[Dict]:
        """
        Get timeseries data for an item.

        Args:
            item_id: Item ID
            timestep: Time interval (5m, 1h, 6h, 24h)
            force_refresh: Force bypass cache

        Returns:
            List of data points
        """
        url = f"{self.ENDPOINTS['timeseries']}?timestep={timestep}&id={item_id}"
        cache_key = f"timeseries_{item_id}_{timestep}"

        data = await self._fetch_with_cache(cache_key, timestep, url, force_refresh)
        return data.get("data", [])

    async def get_period_data(
        self, period: str = "5m", force_refresh: bool = False
    ) -> Dict:
        """
        Get aggregated period data (5m, 1h, 6h, 24h).

        Args:
            period: Time period (5m, 1h, 6h, 24h)
            force_refresh: Force bypass cache

        Returns:
            Dict with item data
        """
        url = self.ENDPOINTS[period]
        data = await self._fetch_with_cache(
            f"period_{period}", period, url, force_refresh
        )
        return data.get("data", {})

    async def get_weirdgloop_volumes(
        self, item_names: List[str], force_refresh: bool = False
    ) -> Dict:
        """
        Get volume data from Weirdgloop API.
        Automatically chunks large requests.

        Args:
            item_names: List of item names
            force_refresh: Force bypass cache

        Returns:
            Dict mapping item names to volume data
        """
        # Check if we can use cached data
        cache_key = "weirdgloop_all"
        if not force_refresh and self._is_cache_valid(cache_key, "weirdgloop"):
            cached = self._cache[cache_key]
            return {name: cached[name] for name in item_names if name in cached}

        # Fetch fresh data in chunks
        async with self._locks[cache_key]:
            chunk_size = 100
            name_chunks = [
                item_names[i : i + chunk_size]
                for i in range(0, len(item_names), chunk_size)
            ]

            volume_data = {}

            async def fetch_chunk(chunk):
                """Fetch a single chunk."""
                params = {"name": "|".join(chunk)}
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self.ENDPOINTS["weirdgloop"],
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        response.raise_for_status()
                        return await response.json()

            # Fetch chunks in batches of 5 concurrent requests
            batch_size = 5
            for i in range(0, len(name_chunks), batch_size):
                batch = name_chunks[i : i + batch_size]
                tasks = [fetch_chunk(chunk) for chunk in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        self.bot.logger.error(
                            f"[OSRSDataManager] Error fetching Weirdgloop chunk: {result}"
                        )
                        continue
                    volume_data.update(result)

            # Cache all results
            self._cache[cache_key] = volume_data
            self._cache_timestamps[cache_key] = time.time()

            return volume_data

    async def get_comprehensive_item_data(
        self, item_id: int, force_refresh: bool = False
    ) -> Dict:
        """
        Get all available data for a single item.
        Used by price checker cog.

        Returns:
            Dict with keys: latest, history (5m, 1h, 6h, 24h), metadata
        """
        # Fetch all data concurrently
        tasks = {
            "latest": self.get_latest_prices([item_id], force_refresh),
            "5m": self.get_timeseries(item_id, "5m", force_refresh),
            "1h": self.get_timeseries(item_id, "1h", force_refresh),
            "6h": self.get_timeseries(item_id, "6h", force_refresh),
            "24h": self.get_timeseries(item_id, "24h", force_refresh),
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        # Build response
        data = {}
        for key, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                self.bot.logger.error(
                    f"[OSRSDataManager] Error fetching {key} for item {item_id}: {result}"
                )
                data[key] = {} if key == "latest" else []
            else:
                data[key] = result

        # Get latest for this specific item
        latest_data = data["latest"].get("data", {}).get(str(item_id), {})

        return {
            "latest": latest_data,
            "history": {
                "5m": data["5m"],
                "1h": data["1h"],
                "6h": data["6h"],
                "24h": data["24h"],
            },
            "metadata": self.id_to_item.get(item_id, {}),
        }

    def get_item_id(self, item_name: str) -> Optional[int]:
        """Get item ID from name (cached lookup)."""
        return self.name_to_id.get(item_name.lower())

    def get_item_info(self, item_id: int) -> Optional[Dict]:
        """Get item metadata from ID (cached lookup)."""
        return self.id_to_item.get(item_id)

    def autocomplete_items(self, query: str, limit: int = 25) -> List[Dict]:
        """
        Fast autocomplete for items using pre-built indices.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching items
        """
        if not query:
            return list(self.id_to_item.values())[:limit]

        query_lower = query.lower().strip()
        matches = []
        seen = set()

        # Strategy 1: Exact match
        if query_lower in self.indices["exact"]:
            item = self.indices["exact"][query_lower]
            matches.append(item)
            seen.add(item["name"].lower())

        # Strategy 2: Prefix match
        prefix_key = query_lower[: min(3, len(query_lower))]
        for item in self.indices["prefix"].get(prefix_key, []):
            if len(matches) >= limit * 2:  # Gather more for sorting
                break
            name_lower = item["name"].lower()
            if query_lower in name_lower and name_lower not in seen:
                matches.append(item)
                seen.add(name_lower)

        # Strategy 3: Word match
        if len(matches) < limit:
            for word in query_lower.split():
                if len(word) >= 2:
                    for item in self.indices["word"].get(word, []):
                        if len(matches) >= limit * 2:
                            break
                        name_lower = item["name"].lower()
                        if query_lower in name_lower and name_lower not in seen:
                            matches.append(item)
                            seen.add(name_lower)

        # Strategy 4: Substring match
        if len(matches) < limit and len(query_lower) >= 3:
            for item in self.indices["substring"].get(query_lower, []):
                if len(matches) >= limit * 2:
                    break
                name_lower = item["name"].lower()
                if name_lower not in seen:
                    matches.append(item)
                    seen.add(name_lower)

        # Sort by relevance
        def sort_key(item):
            name = item["name"].lower()
            return (
                name != query_lower,  # Exact match first
                not name.startswith(query_lower),  # Starts with second
                name,  # Alphabetical
            )

        matches.sort(key=sort_key)
        return matches[:limit]

    def clear_cache(self, endpoint_type: Optional[str] = None):
        """
        Clear cache for specific endpoint type or all caches.

        Args:
            endpoint_type: Specific endpoint to clear (None = clear all)
        """
        if endpoint_type:
            keys_to_remove = [
                key for key in self._cache.keys() if key.startswith(endpoint_type)
            ]
            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
            self.bot.logger.info(
                f"[OSRSDataManager] Cleared {len(keys_to_remove)} cache entries for {endpoint_type}"
            )
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
            self.bot.logger.info("[OSRSDataManager] Cleared all cache")

    def get_cache_stats(self) -> Dict:
        """Get statistics about current cache state."""
        now = time.time()
        stats = {
            "total_cached": len(self._cache),
            "by_type": defaultdict(int),
            "staleness": {},
        }

        for key, timestamp in self._cache_timestamps.items():
            cache_type = key.split("_")[0]
            stats["by_type"][cache_type] += 1
            age = now - timestamp
            stats["staleness"][key] = {
                "age_seconds": int(age),
                "is_fresh": age < self.CACHE_DURATIONS.get(cache_type, 60),
            }

        return stats
