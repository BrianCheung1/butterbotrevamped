import aiosqlite

from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("PlayersDatabaseManager")


class PlayersDatabaseManager:

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self.connection = connection

    @db_error_handler
    async def save_player(self, name: str, tag: str) -> None:
        """Store player information in the database."""
        if not name or not tag:
            raise ValueError("Both name and tag are required.")

        # Ensure name and tag are case-insensitive
        name = name.lower()
        tag = tag.lower()

        try:
            # Save or update the player information in the database
            await self.connection.execute(
                """
                INSERT OR REPLACE INTO players (name, tag)
                VALUES (?, ?)
                """,
                (name, tag),
            )
            await self.connection.commit()
        except Exception as e:
            # Handle any unexpected errors here
            logger.error(f"Error saving player {name}#{tag}: {e}")
            raise Exception(f"Error saving player: {e}")

    @db_error_handler
    async def get_saved_players(self) -> list[tuple[str, str]]:
        """Retrieve all saved player name/tag pairs."""
        try:
            async with self.connection.execute(
                "SELECT name, tag FROM players"
            ) as cursor:
                rows = await cursor.fetchall()
                return [(row[0], row[1]) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching players from database: {e}")
        return []
