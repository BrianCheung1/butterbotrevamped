import aiosqlite
from logger import setup_logger

logger = setup_logger("DatabaseManager")


class DatabaseManager:
    def __init__(self, *, connection: aiosqlite.Connection) -> None:
        self.connection = connection

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
        async with self.connection.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            # User doesn't exist → insert them with starting balance
            await self.create_user(user_id)
            return 0

        return row[0]

    async def set_balance(self, user_id: int, amount: int) -> None:
        """
        This function will set the balance of a user.
        :param user_id: The ID of the user whose balance should be set

        """
        if amount < 0:
            raise ValueError("Balance cannot be negative.")

        # Check if user exists
        async with self.connection.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            await self.create_user(user_id)

        # Upsert - either insert the user or update their balance if they exist
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
        # Check if user exists in the users table
        async with self.connection.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            user_exists = await cursor.fetchone()

        if not user_exists:
            # If user doesn't exist, you can insert them with default values
            await self.create_user(user_id)

        # If user exists, fetch stats from the game table
        async with self.connection.execute(
            "SELECT * FROM user_game_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            game_stats = await cursor.fetchone()

        return {
            "game_stats": game_stats,
        }
