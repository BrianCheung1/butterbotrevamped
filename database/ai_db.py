import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("AIDatabaseManager")


class AIDatabaseManager:
    def __init__(self, connection: aiosqlite.Connection):
        self.connection = connection

    @db_error_handler
    async def log_interaction(self, user_id: int, user_message: str, bot_response: str):
        await self.connection.execute(
            """
                INSERT INTO interactions (user_id, user_message, bot_response)
                VALUES (?,?,?)
                """,
            (user_id, user_message, bot_response),
        )
        await self.connection.commit()

    @db_error_handler
    async def get_user_history(
        self, user_id: int, limit: int = 15
    ) -> list[tuple[str, str]]:

        cursor = await self.connection.execute(
            """
            SELECT user_message, bot_response FROM interactions
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return rows
