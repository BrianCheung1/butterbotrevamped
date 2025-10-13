from typing import List, Optional

import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("MoviesDatabaseManager")


class MoviesDatabaseManager:

    def __init__(self, connection: aiosqlite.Connection, db_manager):
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def save_movie(
        self,
        guild_id: str,
        title: str,
        imdb_id: str,
        imdb_link: str,
        added_by_id: str,
        added_by_name: str,
        notes: Optional[str] = None,
    ) -> bool:
        """Store a movie in the database. Returns False if it already exists."""
        async with self.db_manager.transaction():
            cursor = await self.connection.execute(
                """
                INSERT INTO movies (guild_id, title, imdb_id, imdb_link, added_by_id, added_by_name, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, imdb_id) DO NOTHING;
                """,
                (
                    guild_id,
                    title,
                    imdb_id,
                    imdb_link,
                    added_by_id,
                    added_by_name,
                    notes,
                ),
            )
            inserted = cursor.rowcount > 0

        if inserted:
            logger.info(f"Movie '{title}' added by {added_by_name} in guild {guild_id}")
        else:
            logger.info(f"Movie '{title}' already exists in guild {guild_id}")

        return inserted

    @db_error_handler
    async def get_movies(self, guild_id: str) -> List[dict]:
        """Retrieve all movies stored for a specific guild."""
        async with self.connection.execute(
            """
            SELECT title, imdb_id, imdb_link, added_by_name, notes
            FROM movies
            WHERE guild_id = ?
            ORDER BY title;
            """,
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "title": row[0],
                "imdb_id": row[1],
                "imdb_link": row[2],
                "added_by_name": row[3],
                "notes": row[4],
            }
            for row in rows
        ]

    @db_error_handler
    async def remove_movie(self, guild_id: str, imdb_id: str) -> bool:
        """Remove a specific movie from a guild. Returns True if a row was deleted."""
        async with self.db_manager.transaction():
            cursor = await self.connection.execute(
                """
                DELETE FROM movies
                WHERE guild_id = ? AND imdb_id = ?;
                """,
                (guild_id, imdb_id),
            )
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info(f"Movie {imdb_id} removed from guild {guild_id}")
        else:
            logger.warning(
                f"Tried to remove nonexistent movie {imdb_id} from guild {guild_id}"
            )

        return deleted

    @db_error_handler
    async def get_all_movies(self) -> List[dict]:
        """Retrieve all movies across all guilds."""
        async with self.connection.execute(
            """
            SELECT guild_id, title, imdb_id, imdb_link, added_by_name, notes
            FROM movies
            ORDER BY guild_id, title;
            """
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "guild_id": row[0],
                "title": row[1],
                "imdb_id": row[2],
                "imdb_link": row[3],
                "added_by_name": row[4],
                "notes": row[5],
            }
            for row in rows
        ]
