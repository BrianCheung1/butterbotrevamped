from .user_db import UserDatabaseManager
from .work_db import WorkDatabaseManager
from .steal_db import StealDatabaseManager
from .game_db import GameDatabaseManager

import aiosqlite
from logger import setup_logger

logger = setup_logger("DatabaseManagerBase")


class DatabaseManager:
    def __init__(self, *, connection: aiosqlite.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = aiosqlite.Row

        self.user_db = UserDatabaseManager(connection, self)
        self.work_db = WorkDatabaseManager(connection, self)
        self.steal_db = StealDatabaseManager(connection, self)
        self.game_db = GameDatabaseManager(connection, self)

    async def _create_user_if_not_exists(self, user_id: int) -> None:
        async with self.connection.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            user_exists = await cursor.fetchone()

        if not user_exists:
            await self.create_user(user_id)

    async def create_user(self, user_id: int) -> None:
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
