import aiosqlite
from logger import setup_logger

from .ai_db import AIDatabaseManager
from .bank_db import BankDatabaseManager
from .buffs_db import BuffsDatabaseManager
from .game_db import GameDatabaseManager
from .guild_db import GuildSettingsDatabaseManager
from .heist_db import HeistDatabaseManager
from .inventory_db import InventoryDatabaseManager
from .movies_db import MoviesDatabaseManager
from .patch_notes_db import PatchNotesDatabaseManager
from .players_db import PlayersDatabaseManager
from .reminders_db import RemindersDatabaseManager
from .steal_db import StealDatabaseManager
from .steam_games_db import SteamGamesDatabaseManager
from .user_db import UserDatabaseManager
from .work_db import WorkDatabaseManager

logger = setup_logger("DatabaseManagerBase")


class DatabaseManager:
    def __init__(self, *, connection: aiosqlite.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = aiosqlite.Row

        # Economy Database
        self.user_db = UserDatabaseManager(connection, self)
        self.work_db = WorkDatabaseManager(connection, self)
        self.steal_db = StealDatabaseManager(connection, self)
        self.game_db = GameDatabaseManager(connection, self)
        self.bank_db = BankDatabaseManager(connection, self)
        self.inventory_db = InventoryDatabaseManager(connection, self)
        self.heist_db = HeistDatabaseManager(connection, self)
        self.buffs_db = BuffsDatabaseManager(connection, self)

        # Valorant Database
        self.players_db = PlayersDatabaseManager(connection)

        # Movies Database
        self.movies_db = MoviesDatabaseManager(connection)

        # Guild Database
        self.guild_db = GuildSettingsDatabaseManager(connection)

        # AI Database
        self.ai_db = AIDatabaseManager(connection)

        # Steam Games Database
        self.steam_games_db = SteamGamesDatabaseManager(connection)

        # Patch Notes Database
        self.patch_notes_db = PatchNotesDatabaseManager(connection)

        # Reminders Database
        self.reminders_db = RemindersDatabaseManager(connection)

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
            ("INSERT INTO user_equipped_tools (user_id) VALUES (?)", (user_id,)),
        ]
        try:
            async with self.connection.execute("BEGIN"):
                for query, params in queries:
                    await self.connection.execute(query, params)
                await self.connection.commit()
        except Exception as e:
            logger.error(f"Error creating user {user_id}: {e}")

    async def get_leaderboard_data(self, leaderboard_type: str) -> list:
        """
        Get leaderboard data for a specific category (e.g., balance, mining level, etc.).

        :param leaderboard_type: Type of leaderboard ('balance', 'mining_level', 'fishing_level', 'bank_balance')
        :param limit: How many entries to return (default is 10)
        :return: List of leaderboard entries
        """
        LEADERBOARD_QUERIES = {
            "balance": (
                "SELECT user_id, balance FROM users "
                "WHERE balance > 0 "
                "ORDER BY balance DESC LIMIT 100"
            ),
            "mining_level": (
                "SELECT user_id, mining_level, mining_xp FROM user_work_stats "
                "WHERE mining_level > 1 OR mining_xp > 0 "
                "ORDER BY mining_level DESC, mining_xp DESC LIMIT 100"
            ),
            "fishing_level": (
                "SELECT user_id, fishing_level, fishing_xp FROM user_work_stats "
                "WHERE fishing_level > 1 OR fishing_xp > 0 "
                "ORDER BY fishing_level DESC, fishing_xp DESC LIMIT 100"
            ),
            "bank_balance": (
                "SELECT user_id, bank_balance FROM user_bank_stats "
                "WHERE bank_balance > 0 "
                "ORDER BY bank_balance DESC LIMIT 100"
            ),
        }

        query = LEADERBOARD_QUERIES.get(leaderboard_type)
        if not query:
            raise ValueError("Invalid leaderboard type.")

        async with self.connection.execute(query) as cursor:
            rows = await cursor.fetchall()

        return rows
