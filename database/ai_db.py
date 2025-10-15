from datetime import datetime, timezone

import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("AIDatabaseManager")


class AIDatabaseManager:
    def __init__(self, connection: aiosqlite.Connection, db_manager):
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def log_interaction(
        self, user_id: int, user_message: str, bot_response: str
    ) -> bool:
        """
        Log a user-bot interaction to the database.

        Args:
            user_id: Discord user ID
            user_message: Message from user
            bot_response: Response from bot

        Returns:
            True if successful, False otherwise
        """
        try:
            async with self.db_manager.transaction():
                await self.connection.execute(
                    """
                    INSERT INTO interactions (user_id, user_message, bot_response, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        user_message,
                        bot_response,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            logger.info(f"✅ Logged interaction for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error logging interaction: {e}", exc_info=True)
            return False

    @db_error_handler
    async def get_user_history(
        self, user_id: int, limit: int = 12
    ) -> list[tuple[str, str]]:
        """
        Get conversation history for a user.

        Args:
            user_id: Discord user ID
            limit: Number of messages to retrieve (default 12, means 6 exchanges)

        Returns:
            List of (user_message, bot_response) tuples, newest first
        """
        try:
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

            if rows:
                # Reverse to get chronological order (oldest first)
                # This is important for the AI to understand conversation flow
                rows.reverse()
                logger.debug(
                    f"✅ Retrieved {len(rows)} history entries for user {user_id}"
                )
            else:
                logger.debug(f"No history found for user {user_id}")

            return rows
        except Exception as e:
            logger.error(f"Error retrieving user history: {e}", exc_info=True)
            return []

    @db_error_handler
    async def get_user_stats(self, user_id: int) -> dict:
        """
        Get statistics about a user's interactions.

        Args:
            user_id: Discord user ID

        Returns:
            Dict with interaction count and first/last interaction timestamps
        """
        try:
            cursor = await self.connection.execute(
                """
                SELECT
                    COUNT(*) as total_interactions,
                    MIN(timestamp) as first_interaction,
                    MAX(timestamp) as last_interaction
                FROM interactions
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()

            if row and row[0] > 0:
                return {
                    "total_interactions": row[0],
                    "first_interaction": row[1],
                    "last_interaction": row[2],
                }
            return {
                "total_interactions": 0,
                "first_interaction": None,
                "last_interaction": None,
            }
        except Exception as e:
            logger.error(f"Error retrieving user stats: {e}", exc_info=True)
            return {}

    @db_error_handler
    async def clear_user_history(self, user_id: int) -> bool:
        """
        Clear all conversation history for a user.

        Args:
            user_id: Discord user ID

        Returns:
            True if successful, False otherwise
        """
        try:
            async with self.db_manager.transaction():
                cursor = await self.connection.execute(
                    "DELETE FROM interactions WHERE user_id = ?",
                    (user_id,),
                )
                deleted = cursor.rowcount
                await cursor.close()

            if deleted > 0:
                logger.info(f"✅ Cleared {deleted} interactions for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing user history: {e}", exc_info=True)
            return False

    @db_error_handler
    async def get_recent_interactions(self, limit: int = 10) -> list[dict]:
        """
        Get recent interactions from all users (for monitoring).

        Args:
            limit: Number of recent interactions to retrieve

        Returns:
            List of interaction dicts with user_id, messages, and timestamp
        """
        try:
            cursor = await self.connection.execute(
                """
                SELECT user_id, user_message, bot_response, timestamp
                FROM interactions
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            await cursor.close()

            interactions = [
                {
                    "user_id": row[0],
                    "user_message": row[1],
                    "bot_response": row[2],
                    "timestamp": row[3],
                }
                for row in rows
            ]
            return interactions
        except Exception as e:
            logger.error(f"Error retrieving recent interactions: {e}", exc_info=True)
            return []
