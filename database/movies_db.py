import aiosqlite

from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("MoviesDatabaseManager")


class MoviesDatabaseManager:

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self.connection = connection

    @db_error_handler
    async def save_movie(
        self,
        guild_id: str,
        title: str,
        imdb_id: str,
        imdb_link: str,
        added_by_id: str,
        added_by_name: str,
        notes: str = None,
    ) -> bool:
        """Store movie information in the database."""

        await self.connection.execute(
            """
            INSERT INTO movies(guild_id, title, imdb_id, imdb_link, added_by_id, added_by_name, notes)
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
        await self.connection.commit()
        logger.info(f"Movie '{title}' added by {added_by_name} in guild {guild_id}")
        return True

    @db_error_handler
    async def get_movies(self, guild_id: str) -> list:
        """Retrieve all movies from the database for a specific guild."""
        cursor = await self.connection.execute(
            """
            SELECT title, imdb_id, imdb_link, added_by_name, notes
            FROM movies
            WHERE guild_id = ?
            ORDER BY title;
            """,
            (guild_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        # Map rows to a list of dictionaries for easier access
        movies = [
            {
                "title": row[0],
                "imdb_id": row[1],
                "imdb_link": row[2],
                "added_by_name": row[3],
                "notes": row[4],
            }
            for row in rows
        ]

        return movies
