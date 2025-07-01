import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("PlayersDatabaseManager")


class PlayersDatabaseManager:

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self.connection = connection

    @db_error_handler
    async def get_player(self, name: str, tag: str) -> dict | None:
        """Get a specific player from the database."""
        name, tag = name.lower(), tag.lower()

        try:
            async with self.connection.execute(
                "SELECT name, tag, rank, elo, last_updated FROM players WHERE name = ? AND tag = ?",
                (name, tag),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "name": row[0],
                        "tag": row[1],
                        "rank": row[2],
                        "elo": row[3],
                        "last_updated": row[4],
                    }
                return None
        except Exception as e:
            logger.error(f"Error fetching player {name}#{tag} from database: {e}")
            return None

    @db_error_handler
    async def save_player(
        self, name: str, tag: str, rank: str = None, elo: int = None
    ) -> None:
        """Insert or update player information in the database."""
        if not name or not tag:
            raise ValueError("Both name and tag are required.")

        name, tag = name.lower(), tag.lower()

        try:
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
            await self.connection.commit()
        except Exception as e:
            logger.error(f"Error saving player {name}#{tag}: {e}")
            raise

    @db_error_handler
    async def get_all_player_mmr(self) -> list[dict]:
        """Get all stored player MMR data."""
        try:
            async with self.connection.execute(
                "SELECT name, tag, rank, elo, last_updated FROM players WHERE rank IS NOT NULL AND elo IS NOT NULL"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "name": row[0],
                        "tag": row[1],
                        "rank": row[2],
                        "elo": row[3],
                        "last_updated": row[4],
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Error loading player MMR from database: {e}")
            return []
