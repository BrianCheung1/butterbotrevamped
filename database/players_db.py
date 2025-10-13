from __future__ import annotations

from typing import Dict, List, Optional

import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("PlayersDatabaseManager")


class PlayersDatabaseManager:
    def __init__(self, connection: aiosqlite.Connection, db_manager):
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def get_player(self, name: str, tag: str) -> Optional[Dict]:
        """Get a specific player from the database."""
        name, tag = name.lower(), tag.lower()

        async with self.connection.execute(
            "SELECT name, tag, rank, elo, last_updated FROM players WHERE name = ? AND tag = ?",
            (name, tag),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))

    @db_error_handler
    async def save_player(
        self, name: str, tag: str, rank: Optional[str] = None, elo: Optional[int] = None
    ) -> None:
        """Insert or update player information in the database."""
        if not name or not tag:
            raise ValueError("Both name and tag are required.")

        name, tag = name.lower(), tag.lower()

        async with self.db_manager.transaction():
            await self.connection.execute(
                """
                INSERT INTO players (name, tag, rank, elo, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name, tag) DO UPDATE SET
                    rank = excluded.rank,
                    elo = excluded.elo,
                    last_updated = CURRENT_TIMESTAMP
                """,
                (name, tag, rank, elo),
            )

    @db_error_handler
    async def get_all_player_mmr(self) -> List[Dict]:
        """Get all stored player MMR data."""
        async with self.connection.execute(
            "SELECT name, tag, rank, elo, last_updated FROM players WHERE rank IS NOT NULL AND elo IS NOT NULL"
        ) as cursor:
            rows = await cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    @db_error_handler
    async def delete_player(self, name: str, tag: str) -> bool:
        """Delete a specific player from the database."""
        name, tag = name.lower(), tag.lower()

        async with self.db_manager.transaction():
            cursor = await self.connection.execute(
                "DELETE FROM players WHERE name = ? AND tag = ?", (name, tag)
            )
            return cursor.rowcount > 0

    @db_error_handler
    async def batch_save_players(self, players: list) -> None:
        """
        Batch insert/update multiple players efficiently.

        IMPROVEMENT: Single executemany() instead of loop,
        minimizes lock time and transaction overhead
        """
        if not players:
            return

        # Normalize data
        normalized = [
            (name.lower(), tag.lower(), rank, elo) for name, tag, rank, elo in players
        ]

        async with self.db_manager.transaction():
            await self.connection.executemany(
                """
                INSERT INTO players (name, tag, rank, elo, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name, tag) DO UPDATE SET
                    rank = excluded.rank,
                    elo = excluded.elo,
                    last_updated = CURRENT_TIMESTAMP
                """,
                normalized,
            )

    @db_error_handler
    async def batch_delete_players(self, players: list) -> None:
        """
        Batch delete multiple players efficiently.

        IMPROVEMENT: executemany() in single transaction
        """
        if not players:
            return

        normalized = [(name.lower(), tag.lower()) for name, tag in players]

        async with self.db_manager.transaction():
            await self.connection.executemany(
                "DELETE FROM players WHERE name = ? AND tag = ?",
                normalized,
            )
