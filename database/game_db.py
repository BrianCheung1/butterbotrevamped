from typing import Optional

import aiosqlite
from constants.game_config import GameEventType
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("GamebaseManager")


class GameDatabaseManager:

    def __init__(
        self, connection: aiosqlite.Connection, db_manager: "DatabaseManager"
    ) -> None:
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def get_user_game_stats(self, user_id: int):
        """
        This function will return the game stats of a user.

        :param user_id: The ID of the user whose game stats should be returned.
        """
        await self.db_manager._create_user_if_not_exists(user_id)
        # If user exists, fetch stats from the game table
        async with self.connection.execute(
            "SELECT * FROM user_game_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            game_stats = await cursor.fetchone()

        return {
            "game_stats": game_stats,
        }

    @db_error_handler
    async def set_user_game_stats(
        self,
        user_id: int,
        game_type: GameEventType,
        win: Optional[bool],
        amount: int,
    ) -> None:
        """
        Updates the user's game stats based on the game type (e.g., slots, blackjack, etc.).

        :param user_id: The ID of the user involved in the event.
        :param game_type: The type of game played (e.g., slots, blackjack).
        :param win: Whether the user won or lost.
        :param amount: The amount won or lost.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        # Access the game type via Enum name to create dynamic field names
        won_field = f"{game_type.value}_won"
        lost_field = f"{game_type.value}_lost"
        total_field = f"{game_type.value}_played"
        total_won_field = f"{game_type.value}_total_won"
        total_lost_field = f"{game_type.value}_total_lost"

        if win is True:
            await self.connection.execute(
                f"""
                INSERT INTO user_game_stats (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO UPDATE SET
                    {won_field} = {won_field} + 1,
                    {total_field} = {total_field} + 1,
                    {total_won_field} = {total_won_field} + ?
                """,
                (
                    user_id,
                    amount,
                ),
            )
        elif win is False:
            await self.connection.execute(
                f"""
                INSERT INTO user_game_stats (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO UPDATE SET
                    {lost_field} = {lost_field} + 1,
                    {total_field} = {total_field} + 1,
                    {total_lost_field} = {total_lost_field} + ?
                """,
                (
                    user_id,
                    amount,
                ),
            )
        else:
            await self.connection.execute(
                f"""
                INSERT INTO user_game_stats (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO UPDATE SET
                    {total_field} = {total_field} + 1
                """,
                (user_id,),
            )

        await self.connection.commit()

    @db_error_handler
    async def log_roll_history(
        self,
        user_id: int,
        user_roll: int,
        dealer_roll: int,
        result: str,
        amount: int,
    ) -> None:
        await self.connection.execute(
            """
            INSERT INTO roll_history (user_id, user_roll, dealer_roll, result, amount)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, user_roll, dealer_roll, result, amount),
        )

        # Optional: limit to 10 most recent entries
        await self.connection.execute(
            """
            DELETE FROM roll_history
            WHERE id NOT IN (
                SELECT id FROM roll_history
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 10
            ) AND user_id = ?
            """,
            (user_id, user_id),
        )

        await self.connection.commit()

    @db_error_handler
    async def get_roll_history(self, user_id: int, limit: int = 10) -> list[dict]:
        async with self.connection.execute(
            """
            SELECT user_roll, dealer_roll, result, amount, timestamp
            FROM roll_history
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (user_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "user_roll": row[0],
                "dealer_roll": row[1],
                "result": row[2],
                "amount": row[3],
                "timestamp": row[4],
            }
            for row in rows
        ]
