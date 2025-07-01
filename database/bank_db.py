import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("BankDatabaseManager")


class BankDatabaseManager:

    def __init__(
        self, connection: aiosqlite.Connection, db_manager: "DatabaseManager"
    ) -> None:
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def get_bank_balance(self, user_id: int) -> int:
        await self.db_manager._create_user_if_not_exists(user_id)
        async with self.connection.execute(
            "SELECT bank_balance FROM user_bank_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row[0]

    @db_error_handler
    async def get_user_bank_stats(self, user_id: int) -> dict:
        """
        This function will return the bank stats of a user.

        :param user_id: The ID of the user whose bank stats should be returned.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.connection.execute(
            "SELECT * FROM user_bank_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            bank_stats = await cursor.fetchone()

        return {
            "bank_stats": bank_stats,
        }

    @db_error_handler
    async def set_bank_balance(self, user_id: int, amount) -> None:
        """
        This function will set the bank balance of a user.

        :param user_id: The ID of the user whose bank balance should be set
        :param amount: The new bank balance to set for the user
        """
        if amount < 0:
            raise ValueError("Bank balance cannot be negative.")

        # Ensure the user exists before updating their bank balance
        await self.db_manager._create_user_if_not_exists(user_id)

        await self.connection.execute("BEGIN IMMEDIATE")
        # Update the bank balance of the user
        await self.connection.execute(
            """
            INSERT INTO user_bank_stats (user_id, bank_balance)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET bank_balance = excluded.bank_balance
            """,
            (user_id, amount),
        )
        await self.connection.commit()

    @db_error_handler
    async def set_bank_level_and_cap(self, user_id: int) -> None:
        await self.db_manager._create_user_if_not_exists(user_id)

        # Start a transaction to lock the row
        await self.connection.execute("BEGIN IMMEDIATE")

        async with self.connection.execute(
            "SELECT bank_level, bank_cap FROM user_bank_stats WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

        current_level = row[0] if row else 1
        current_cap = row[1] if row else 1_000_000

        new_level = current_level + 1
        new_cap = current_cap + 500_000

        await self.connection.execute(
            """
            UPDATE user_bank_stats
            SET bank_level = ?, bank_cap = ?
            WHERE user_id = ?
            """,
            (new_level, new_cap, user_id),
        )

        await self.connection.commit()

    @db_error_handler
    async def get_all_bank_users(self) -> list[int]:
        async with self.connection.execute(
            "SELECT user_id FROM user_bank_stats WHERE bank_balance > 0"
        ) as cursor:
            rows = await cursor.fetchall()
        return [row[0] for row in rows]
