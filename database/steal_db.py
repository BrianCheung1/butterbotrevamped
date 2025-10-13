import aiosqlite
from constants.steal_config import StealEventType
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("StealDatabaseManager")


class StealDatabaseManager:

    def __init__(self, connection: aiosqlite.Connection, db_manager):
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def get_user_steal_stats(self, user_id: int):
        """
        This function will return the steal stats of a user.

        :param user_id: The ID of the user whose steal stats should be returned.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.connection.execute(
            "SELECT * FROM user_steal_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            steal_stats = await cursor.fetchone()

        return {"steal_stats": steal_stats}

    @db_error_handler
    async def set_user_steal_stats(
        self, user_id: int, amount: int, event_type: StealEventType
    ) -> None:
        """
        Updates the user's steal stats based on the steal event type.

        :param user_id: The ID of the user involved in the event.
        :param amount: The amount stolen or gained/lost.
        :param event_type: The type of steal event.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        if event_type == StealEventType.STEAL_SUCCESS:
            query = """
                INSERT INTO user_steal_stats (
                    user_id, steals_attempted, steals_successful, total_amount_stolen, last_stole_from_other_at
                ) VALUES (?, 1, 1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    steals_attempted = steals_attempted + 1,
                    steals_successful = steals_successful + 1,
                    total_amount_stolen = total_amount_stolen + excluded.total_amount_stolen,
                    last_stole_from_other_at = CURRENT_TIMESTAMP
            """
        elif event_type == StealEventType.STEAL_FAIL:
            query = """
                INSERT INTO user_steal_stats (
                    user_id, steals_attempted, steals_failed, amount_lost_to_failed_steals, last_stole_from_other_at
                ) VALUES (?, 1, 1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    steals_attempted = steals_attempted + 1,
                    steals_failed = steals_failed + 1,
                    amount_lost_to_failed_steals = amount_lost_to_failed_steals + excluded.amount_lost_to_failed_steals,
                    last_stole_from_other_at = CURRENT_TIMESTAMP
            """
        elif event_type == StealEventType.VICTIM_SUCCESS:
            query = """
                INSERT INTO user_steal_stats (
                    user_id, amount_stolen_by_others, times_stolen_from, last_stolen_from_at
                ) VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    amount_stolen_by_others = amount_stolen_by_others + excluded.amount_stolen_by_others,
                    times_stolen_from = times_stolen_from + 1,
                    last_stolen_from_at = CURRENT_TIMESTAMP
            """
        elif event_type == StealEventType.VICTIM_FAIL:
            query = """
                INSERT INTO user_steal_stats (
                    user_id, amount_gained_from_failed_steals, times_stolen_from, last_stolen_from_at
                ) VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    amount_gained_from_failed_steals = amount_gained_from_failed_steals + excluded.amount_gained_from_failed_steals,
                    times_stolen_from = times_stolen_from + 1,
                    last_stolen_from_at = CURRENT_TIMESTAMP
            """
        else:
            raise ValueError("Invalid StealEventType provided.")

        async with self.db_manager.transaction():
            await self.connection.execute(query, (user_id, amount))

    @db_error_handler
    async def get_all_steal_stats(self):
        """
        Returns a list of dictionaries with user_id and their steal cooldown timestamps.
        """
        query = """
        SELECT user_id, last_stolen_from_at, last_stole_from_other_at
        FROM user_steal_stats
        WHERE last_stolen_from_at IS NOT NULL
        ORDER BY last_stolen_from_at ASC
        """
        async with self.connection.execute(query) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "user_id": row["user_id"],
                "last_stolen_from_at": (
                    row["last_stolen_from_at"] if row["last_stolen_from_at"] else None
                ),
                "last_stole_from_other_at": (
                    row["last_stole_from_other_at"]
                    if row["last_stole_from_other_at"]
                    else None
                ),
            }
            for row in rows
        ]
