import datetime
from datetime import timezone
from typing import Optional

import aiosqlite

from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("BuffsDatabaseManager")


class BuffsDatabaseManager:

    def __init__(
        self, connection: aiosqlite.Connection, db_manager: "DatabaseManager"
    ) -> None:
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def set_buff(
        self, user_id: int, buff_type: str, multiplier: float, duration_minutes: int
    ):
        """
        Sets or updates an active buff for a user.

        :param user_id: Discord user ID.
        :param buff_type: Type of buff (e.g., 'mining_xp', 'fishing_value').
        :param multiplier: The multiplier to apply (e.g., 1.5 for +50%).
        :param duration_minutes: Duration of the buff in minutes.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        expires_at = datetime.datetime.utcnow() + datetime.timedelta(
            minutes=duration_minutes
        )

        query = """
        INSERT INTO user_buffs (user_id, buff_type, multiplier, expires_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, buff_type)
        DO UPDATE SET multiplier = excluded.multiplier, expires_at = excluded.expires_at
        """
        await self.connection.execute(
            query, (user_id, buff_type, multiplier, expires_at)
        )
        await self.connection.commit()

    @db_error_handler
    async def get_buffs(self, user_id: int) -> dict:
        """
        Retrieves the active buffs for a user.

        :param user_id: Discord user ID.
        :return: A dictionary where keys are buff types (e.g., 'mining_xp') and values are dicts with 'multiplier' and 'expires_at'.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        query = """
        SELECT buff_type, multiplier, expires_at
        FROM user_buffs
        WHERE user_id = ? AND expires_at > CURRENT_TIMESTAMP
        """
        async with self.connection.execute(query, (user_id,)) as cursor:
            rows = await cursor.fetchall()

        return {
            row["buff_type"]: {
                "multiplier": row["multiplier"],
                "expires_at": datetime.datetime.strptime(
                    row["expires_at"], "%Y-%m-%d %H:%M:%S.%f"
                ).replace(tzinfo=timezone.utc),
            }
            for row in rows
        }
