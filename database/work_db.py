import aiosqlite

from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("WorkDatabaseManager")


class WorkDatabaseManager:

    def __init__(
        self, connection: aiosqlite.Connection, db_manager: "DatabaseManager"
    ) -> None:
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def get_user_work_stats(self, user_id: int):
        """
        This function will return the work stats of a user.

        :param user_id: The ID of the user whose work stats should be returned.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.connection.execute(
            "SELECT * FROM user_work_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            work_stats = await cursor.fetchone()

        return {"work_stats": work_stats}

    @db_error_handler
    async def set_work_stats(self, user_id: int, value: int, xp: int, work_type: str):
        """
        Updates the user's work stats, XP, and handles level-ups based on the work type (mining, fishing, etc.).
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.connection.execute(
            "SELECT * FROM user_work_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            work_stats = await cursor.fetchone()

        if not work_stats:
            return

        updates = {}

        # Dynamically get field names based on work_type
        total_field = f"total_{work_type}"
        value_field = f"total_{work_type}_value"
        xp_field = f"{work_type}_xp"
        next_level_xp_field = f"{work_type}_next_level_xp"
        next_level_field = f"{work_type}_level"

        # Calculate updated values
        updates[total_field] = work_stats[total_field] + 1
        updates[value_field] = work_stats[value_field] + value
        new_xp = work_stats[xp_field] + xp
        updates[xp_field] = new_xp
        new_next_level_xp = work_stats[next_level_xp_field]

        # Level-up check
        if new_xp >= work_stats[next_level_xp_field]:
            new_next_level_xp = int(
                work_stats[next_level_xp_field] * 1.25
            )  # Level scaling
            updates[next_level_xp_field] = new_next_level_xp
            updates[next_level_field] = work_stats[next_level_field] + 1

        # Prepare the SQL update
        set_clause = ", ".join([f"{field} = ?" for field in updates.keys()])
        params = list(updates.values()) + [user_id]

        await self.connection.execute(
            f"""
            UPDATE user_work_stats
            SET {set_clause}
            WHERE user_id = ?
            """,
            params,
        )

        await self.connection.commit()
        current_level = updates.get(next_level_field, work_stats[next_level_field])
        return new_xp, new_next_level_xp, current_level

    async def migrate_work_levels_to_25_percent_growth(self):
        async with self.connection.execute("SELECT user_id, mining_xp, fishing_xp FROM user_work_stats") as cursor:
            users = await cursor.fetchall()

        for user in users:
            user_id, mining_xp, fishing_xp = user

            def calculate_level_and_next_xp(xp):
                level = 1
                xp_required = 50
                total_needed = 0

                while xp >= total_needed + xp_required:
                    total_needed += xp_required
                    xp_required = int(xp_required * 1.25)
                    level += 1

                return level, xp_required

            mining_level, mining_next_xp = calculate_level_and_next_xp(mining_xp)
            fishing_level, fishing_next_xp = calculate_level_and_next_xp(fishing_xp)

            await self.connection.execute(
                """
                UPDATE user_work_stats
                SET
                    mining_level = ?, mining_next_level_xp = ?,
                    fishing_level = ?, fishing_next_level_xp = ?
                WHERE user_id = ?
                """,
                (mining_level, mining_next_xp, fishing_level, fishing_next_xp, user_id),
            )

        await self.connection.commit()
