from typing import Optional

import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("HeistDatabaseManager")


class HeistDatabaseManager:
    def __init__(
        self, connection: aiosqlite.Connection, db_manager: "DatabaseManager"
    ) -> None:
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def get_user_heist_stats(self, user_id: int):
        """
        Return the heist stats of a user.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.connection.execute(
            "SELECT * FROM user_heist_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            heist_stats = await cursor.fetchone()

        return {"heist_stats": heist_stats}

    @db_error_handler
    async def set_user_heist_stats(
        self,
        user_id: int,
        win: Optional[bool],
        amount: int,
    ) -> None:
        """
        Updates the user's heist stats based on the result of the heist.
        Uses a safe transaction context to avoid partial updates or DB locks.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.db_manager.transaction():
            if win:
                await self.connection.execute(
                    """
                    UPDATE user_heist_stats
                    SET
                        heists_joined = heists_joined + 1,
                        heists_won = heists_won + 1,
                        total_loot_gained = total_loot_gained + ?
                    WHERE user_id = ?
                    """,
                    (amount, user_id),
                )
            else:
                await self.connection.execute(
                    """
                    UPDATE user_heist_stats
                    SET
                        heists_joined = heists_joined + 1,
                        heists_lost = heists_lost + 1,
                        total_loot_lost = total_loot_lost + ?
                    WHERE user_id = ?
                    """,
                    (amount, user_id),
                )
