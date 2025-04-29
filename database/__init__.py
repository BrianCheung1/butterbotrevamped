import aiosqlite
import json
from logger import setup_logger

logger = setup_logger("DatabaseManager")


class DatabaseManager:
    def __init__(self, *, connection: aiosqlite.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = aiosqlite.Row

    async def _create_user_if_not_exists(self, user_id: int) -> None:
        """
        Ensures that a user exists. If not, creates a new user with default entries across related tables.
        """
        async with self.connection.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            user_exists = await cursor.fetchone()

        if not user_exists:
            await self.create_user(user_id)

    async def create_user(self, user_id: int) -> None:
        """
        Creates a new user with default entries across all related tables.
        """
        queries = [
            ("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0)),
            ("INSERT INTO user_game_stats (user_id) VALUES (?)", (user_id,)),
            ("INSERT INTO user_heist_stats (user_id) VALUES (?)", (user_id,)),
            ("INSERT INTO user_steal_stats (user_id) VALUES (?)", (user_id,)),
            ("INSERT INTO user_player_stats (user_id) VALUES (?)", (user_id,)),
            ("INSERT INTO user_bank_stats (user_id) VALUES (?)", (user_id,)),
            ("INSERT INTO user_work_stats (user_id) VALUES (?)", (user_id,)),
        ]

        try:
            async with self.connection.execute("BEGIN"):
                for query, params in queries:
                    await self.connection.execute(query, params)
                await self.connection.commit()
        except Exception as e:
            logger.error(f"Error creating user {user_id}: {e}")

    async def get_balance(self, user_id: int) -> int:
        """
        This function will return the balance of a user.

        :param user_id: The ID of the user whose balance should be returned.
        """
        await self._create_user_if_not_exists(
            user_id
        )  # Ensure the user exists before getting their balance

        async with self.connection.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        return row[0]  # Returns the user's balance

    async def set_balance(self, user_id: int, amount: int) -> None:
        """
        This function will set the balance of a user.

        :param user_id: The ID of the user whose balance should be set
        :param amount: The new balance to set for the user
        """
        if amount < 0:
            raise ValueError("Balance cannot be negative.")

        # Ensure the user exists before updating their balance
        await self._create_user_if_not_exists(user_id)

        # Update the balance of the user
        await self.connection.execute(
            """
            INSERT INTO users (user_id, balance)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET balance = excluded.balance
            """,
            (user_id, amount),
        )
        await self.connection.commit()

    async def get_user_game_stats(self, user_id: int):
        """
        This function will return the game stats of a user.

        :param user_id: The ID of the user whose game stats should be returned.
        """

        # If user exists, fetch stats from the game table
        async with self.connection.execute(
            "SELECT * FROM user_game_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            game_stats = await cursor.fetchone()

        return {
            "game_stats": game_stats,
        }

    async def get_user_work_stats(self, user_id: int):
        """
        This function will return the work stats of a user.

        :param user_id: The ID of the user whose work stats should be returned.
        """
        await self._create_user_if_not_exists(user_id)

        async with self.connection.execute(
            "SELECT * FROM user_work_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            work_stats = await cursor.fetchone()

        return {"work_stats": work_stats}

    async def set_work_stats(self, user_id: int, value: int, xp: int, work_type: str):
        """
        Updates the user's work stats, XP, and handles level-ups based on the work type (mining, fishing, etc.).
        """
        await self._create_user_if_not_exists(user_id)

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

        # Calculate updated values
        updates[total_field] = work_stats[total_field] + 1
        updates[value_field] = work_stats[value_field] + value
        new_xp = work_stats[xp_field] + xp
        updates[xp_field] = new_xp
        new_next_level_xp = work_stats[next_level_xp_field]

        # Level-up check
        if new_xp >= work_stats[next_level_xp_field]:
            new_next_level_xp = int(
                work_stats[next_level_xp_field] * 1.5
            )  # Level scaling
            updates[next_level_xp_field] = new_next_level_xp

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
        return new_xp, new_next_level_xp
