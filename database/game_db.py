import aiosqlite

from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("GamebaseManager")


class GameDatabaseManager:
    def __init__(self, connection: aiosqlite.Connection, db_manager):
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def get_user_game_stats(self, user_id: int):
        """
        This function will return the game stats of a user.

        :param user_id: The ID of the user whose game stats should be returned.
        """
        await self.db_manager._create_user_if_not_exists(user_id)
        async with self.connection.execute(
            "SELECT * FROM user_game_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            game_stats = await cursor.fetchone()

        return {
            "game_stats": game_stats,
        }

    @db_error_handler
    async def set_user_game_stats(
        self, user_id: int, game_type, win: bool, amount: int
    ) -> None:
        """
        Update game stats securely using CASE statements.

        IMPROVEMENT: No dynamic SQL injection risk,
        single SQL statement updates all stats atomically
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        game_val = game_type.value

        async with self.db_manager.transaction():
            if win is True:
                await self.connection.execute(
                    """
                    UPDATE user_game_stats
                    SET
                        rolls_won = CASE WHEN ? = 'rolls' THEN rolls_won + 1 ELSE rolls_won END,
                        slots_won = CASE WHEN ? = 'slots' THEN slots_won + 1 ELSE slots_won END,
                        blackjacks_won = CASE WHEN ? = 'blackjacks' THEN blackjacks_won + 1 ELSE blackjacks_won END,
                        rolls_played = CASE WHEN ? = 'rolls' THEN rolls_played + 1 ELSE rolls_played END,
                        slots_played = CASE WHEN ? = 'slots' THEN slots_played + 1 ELSE slots_played END,
                        blackjacks_played = CASE WHEN ? = 'blackjacks' THEN blackjacks_played + 1 ELSE blackjacks_played END,
                        rolls_total_won = CASE WHEN ? = 'rolls' THEN rolls_total_won + ? ELSE rolls_total_won END,
                        slots_total_won = CASE WHEN ? = 'slots' THEN slots_total_won + ? ELSE slots_total_won END,
                        blackjacks_total_won = CASE WHEN ? = 'blackjacks' THEN blackjacks_total_won + ? ELSE blackjacks_total_won END
                    WHERE user_id = ?
                    """,
                    (
                        game_val,
                        game_val,
                        game_val,
                        game_val,
                        game_val,
                        game_val,
                        game_val,
                        amount,
                        game_val,
                        amount,
                        game_val,
                        amount,
                        user_id,
                    ),
                )

            elif win is False:
                await self.connection.execute(
                    """
                    UPDATE user_game_stats
                    SET
                        rolls_lost = CASE WHEN ? = 'rolls' THEN rolls_lost + 1 ELSE rolls_lost END,
                        slots_lost = CASE WHEN ? = 'slots' THEN slots_lost + 1 ELSE slots_lost END,
                        blackjacks_lost = CASE WHEN ? = 'blackjacks' THEN blackjacks_lost + 1 ELSE blackjacks_lost END,
                        rolls_played = CASE WHEN ? = 'rolls' THEN rolls_played + 1 ELSE rolls_played END,
                        slots_played = CASE WHEN ? = 'slots' THEN slots_played + 1 ELSE slots_played END,
                        blackjacks_played = CASE WHEN ? = 'blackjacks' THEN blackjacks_played + 1 ELSE blackjacks_played END,
                        rolls_total_lost = CASE WHEN ? = 'rolls' THEN rolls_total_lost + ? ELSE rolls_total_lost END,
                        slots_total_lost = CASE WHEN ? = 'slots' THEN slots_total_lost + ? ELSE slots_total_lost END,
                        blackjacks_total_lost = CASE WHEN ? = 'blackjacks' THEN blackjacks_total_lost + ? ELSE blackjacks_total_lost END
                    WHERE user_id = ?
                    """,
                    (
                        game_val,
                        game_val,
                        game_val,
                        game_val,
                        game_val,
                        game_val,
                        game_val,
                        amount,
                        game_val,
                        amount,
                        game_val,
                        amount,
                        user_id,
                    ),
                )

            else:  # Tie
                await self.connection.execute(
                    """
                    UPDATE user_game_stats
                    SET
                        rolls_played = CASE WHEN ? = 'rolls' THEN rolls_played + 1 ELSE rolls_played END,
                        slots_played = CASE WHEN ? = 'slots' THEN slots_played + 1 ELSE slots_played END,
                        blackjacks_played = CASE WHEN ? = 'blackjacks' THEN blackjacks_played + 1 ELSE blackjacks_played END
                    WHERE user_id = ?
                    """,
                    (game_val, game_val, game_val, user_id),
                )

    @db_error_handler
    async def log_roll_history(
        self,
        user_id: int,
        user_roll: int,
        dealer_roll: int,
        result: str,
        amount: int,
    ) -> None:
        async with self.db_manager.transaction():
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
