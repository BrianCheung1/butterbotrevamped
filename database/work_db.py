import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("WorkDatabaseManager")


class WorkDatabaseManager:
    def __init__(self, connection: aiosqlite.Connection, db_manager):
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def get_user_work_stats(self, user_id: int):
        """Retrieve work stats for a user."""
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.connection.execute(
            "SELECT * FROM user_work_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            work_stats = await cursor.fetchone()

        return {"work_stats": work_stats}

    @db_error_handler
    async def set_work_stats(self, user_id: int, value: int, xp: int, work_type: str):
        """
        Update work stats atomically using SQL calculations.

        IMPROVEMENT: All math happens in database, single UPDATE statement
        Returns: (new_xp, new_next_level_xp, current_level, leveled_up)
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.db_manager.transaction():
            # First, increment the stats and XP
            async with self.connection.execute(
                f"""
                UPDATE user_work_stats
                SET
                    total_{work_type} = total_{work_type} + 1,
                    total_{work_type}_value = total_{work_type}_value + ?,
                    {work_type}_xp = {work_type}_xp + ?
                WHERE user_id = ?
                RETURNING {work_type}_xp, {work_type}_level, {work_type}_next_level_xp
                """,
                (value, xp, user_id),
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                return None

            new_xp, current_level, next_level_xp = row[0], row[1], row[2]

            # Check if leveled up
            leveled_up = new_xp >= next_level_xp
            if leveled_up:
                # Calculate new level and XP requirement
                new_level = current_level + 1
                new_next_xp = int(next_level_xp * 1.25)

                await self.connection.execute(
                    f"""
                    UPDATE user_work_stats
                    SET
                        {work_type}_level = ?,
                        {work_type}_next_level_xp = ?
                    WHERE user_id = ?
                    """,
                    (new_level, new_next_xp, user_id),
                )

                return new_xp, new_next_xp, new_level, True

            return new_xp, next_level_xp, current_level, False
