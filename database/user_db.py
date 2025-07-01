import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("UserDatabaseManager")


class UserDatabaseManager:

    def __init__(
        self, connection: aiosqlite.Connection, db_manager: "DatabaseManager"
    ) -> None:
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def get_balance(self, user_id: int) -> int:
        await self.db_manager._create_user_if_not_exists(user_id)
        async with self.connection.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row[0]

    @db_error_handler
    async def set_balance(self, user_id: int, amount: int) -> None:
        """
        This function will set the balance of a user.

        :param user_id: The ID of the user whose balance should be set
        :param amount: The new balance to set for the user
        """
        if amount < 0:
            raise ValueError("Balance cannot be negative.")

        # Ensure the user exists before updating their balance
        await self.db_manager._create_user_if_not_exists(user_id)

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

    @db_error_handler
    async def increment_balance(self, user_id: int, amount: int) -> int:
        """
        Atomically increment or decrement a user's balance.

        :param user_id: The ID of the user.
        :param amount: The amount to increment (can be negative).
        :return: The new balance.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.connection.execute(
            """
            UPDATE users
            SET balance = balance + ?
            WHERE user_id = ? AND balance + ? >= 0
            RETURNING balance
            """,
            (amount, user_id, amount),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                raise ValueError("Resulting balance would be negative.")
            await self.connection.commit()
            return row[0]

    @db_error_handler
    async def get_daily(self, user_id: int) -> tuple[int, str | None]:
        """
        Retrieve the user's current daily streak and last claim timestamp.

        :param user_id: The ID of the user
        :return: A tuple (daily_streak, last_daily_at)
        """
        await self.db_manager._create_user_if_not_exists(user_id)
        async with self.connection.execute(
            "SELECT daily_streak, last_daily_at FROM users WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            return row["daily_streak"], row["last_daily_at"]
        return 0, None

    @db_error_handler
    async def set_daily(self, user_id: int, daily_streak: int | None = None) -> None:
        """
        Update the user's daily streak and set the current timestamp.

        :param user_id: The ID of the user
        :param daily_streak: If provided, sets the streak directly; otherwise, increments it by 1
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        if daily_streak is not None:
            await self.connection.execute(
                "UPDATE users SET daily_streak = ?, last_daily_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (daily_streak, user_id),
            )
        else:
            await self.connection.execute(
                "UPDATE users SET daily_streak = daily_streak + 1, last_daily_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,),
            )

        await self.connection.commit()
