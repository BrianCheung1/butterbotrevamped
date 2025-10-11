"""
Thread-safe player cache manager to prevent race conditions.
Replace direct access to bot.valorant_players with this manager.
"""

import asyncio
from typing import Dict, Tuple, Optional
from logger import setup_logger

logger = setup_logger("PlayerCache")


class PlayerCacheManager:
    """
    Thread-safe manager for in-memory player data.
    Prevents concurrent write conflicts when multiple cogs update simultaneously.
    """

    def __init__(self):
        self._cache: Dict[Tuple[str, str], Dict] = {}
        self._lock = asyncio.Lock()

    async def get(self, name: str, tag: str) -> Optional[Dict]:
        """
        Get player data safely.

        Args:
            name: Player name
            tag: Player tag

        Returns:
            Player data dict or None if not found
        """
        async with self._lock:
            key = (name.lower(), tag.lower())
            return self._cache.get(key)

    async def get_all(self) -> Dict[Tuple[str, str], Dict]:
        """
        Get all cached players (for leaderboard).
        Returns a copy to prevent external mutations.

        Returns:
            Dict of all cached players
        """
        async with self._lock:
            return self._cache.copy()

    async def set(self, name: str, tag: str, data: Dict) -> None:
        """
        Update player data safely.

        Args:
            name: Player name
            tag: Player tag
            data: Player data dict with rank, elo, etc.
        """
        async with self._lock:
            key = (name.lower(), tag.lower())
            self._cache[key] = data
            logger.debug(f"Updated player cache for {name}#{tag}")

    async def batch_set(self, updates: Dict[Tuple[str, str], Dict]) -> None:
        """
        Update multiple players atomically.

        Args:
            updates: Dict mapping (name, tag) -> data
        """
        async with self._lock:
            for (name, tag), data in updates.items():
                key = (name.lower(), tag.lower())
                self._cache[key] = data
            logger.info(f"Batch updated {len(updates)} players in cache")

    async def delete(self, name: str, tag: str) -> bool:
        """
        Remove a player from cache.

        Args:
            name: Player name
            tag: Player tag

        Returns:
            True if player was deleted, False if not found
        """
        async with self._lock:
            key = (name.lower(), tag.lower())
            if key in self._cache:
                del self._cache[key]
                logger.info(f"Deleted {name}#{tag} from cache")
                return True
            return False

    async def batch_delete(self, players: list) -> int:
        """
        Delete multiple players atomically.

        Args:
            players: List of (name, tag) tuples

        Returns:
            Number of players deleted
        """
        async with self._lock:
            deleted_count = 0
            for name, tag in players:
                key = (name.lower(), tag.lower())
                if key in self._cache:
                    del self._cache[key]
                    deleted_count += 1
            logger.info(f"Batch deleted {deleted_count} players from cache")
            return deleted_count

    async def clear(self) -> None:
        """Clear all cached players."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cleared {count} players from cache")

    async def size(self) -> int:
        """Get number of cached players."""
        async with self._lock:
            return len(self._cache)

    async def exists(self, name: str, tag: str) -> bool:
        """Check if player exists in cache."""
        async with self._lock:
            key = (name.lower(), tag.lower())
            return key in self._cache