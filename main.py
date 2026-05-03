import os
from datetime import datetime

import aiosqlite
import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import DatabaseManager
from logger import setup_logger
from utils.valorant_player_cache import PlayerCacheManager
from utils.osrs_data_manager import OSRSDataManager
from utils.valorant_data_manager import ValorantDataManager
from utils.valorant_helpers import load_cached_players_from_db

load_dotenv()

logger = setup_logger("Butterbot")

DB_PATH = os.path.join(
    os.path.realpath(os.path.dirname(__file__)), "database", "database.db"
)
SCHEMA_PATH = os.path.join(
    os.path.realpath(os.path.dirname(__file__)), "database", "schema.sql"
)


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="`",
            intents=discord.Intents.all(),
            help_command=None,
        )
        self.logger = logger
        self.database: DatabaseManager | None = None
        self._db_connection: aiosqlite.Connection | None = None
        self.invite_link = os.getenv("INVITE_LINK")
        self.active_blackjack_players: set[int] = set()
        self.valorant_players = PlayerCacheManager()
        self.osrs_data = OSRSDataManager(self)
        self.valorant_data = ValorantDataManager(self)
        self.start_time = datetime.now()

    async def setup_hook(self) -> None:
        """
        Called once after login, before connecting to the gateway.
        This is the correct place for one-time async initialization:
        database setup, cog loading, and background task prep.

        Unlike on_ready, this is guaranteed to run exactly once even
        if the bot reconnects after a network drop.
        """
        await self._init_db()
        await self._load_cogs()

    async def _init_db(self) -> None:
        """
        Initialize the database: run schema migrations, open a persistent
        connection, and wire up all the database manager sub-classes.

        Keeping a single long-lived connection (stored on self._db_connection)
        means we can close it cleanly in close() rather than leaking it on
        reconnects, which was the bug with the old on_ready approach.
        """
        # Apply schema (CREATE TABLE IF NOT EXISTS is idempotent, safe to run on every start)
        async with aiosqlite.connect(DB_PATH) as db:
            with open(SCHEMA_PATH, encoding="utf-8") as f:
                await db.executescript(f.read())
            await db.commit()

        # Apply performance pragmas before handing the connection to the manager.
        # WAL mode allows concurrent reads during writes and is safer for bots
        # that have multiple cogs hitting the DB simultaneously.
        conn = await aiosqlite.connect(DB_PATH)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(
            "PRAGMA synchronous=NORMAL"
        )  # safe with WAL, faster than FULL
        await conn.execute("PRAGMA cache_size=10000")  # ~40 MB page cache in memory
        await conn.execute("PRAGMA foreign_keys=ON")  # enforce FK constraints
        await conn.commit()

        self._db_connection = conn
        self.database = DatabaseManager(connection=conn)
        self.logger.info("Database initialised.")

    async def _load_cogs(self) -> None:
        """
        Discover and load every cog module under the cogs/ directory.
        Private files (starting with _) are skipped.
        """
        cogs_to_load = [
            os.path.splitext(os.path.join(root, file))[0].replace(os.sep, ".")
            for root, _, files in os.walk("cogs")
            for file in files
            if file.endswith(".py") and not file.startswith("_")
        ]

        failed_cogs: list[str] = []
        logged_folders: set[str] = set()

        for name in cogs_to_load:
            parts = name.split(".")
            top_level_name = ".".join(parts[:2]) if len(parts) >= 2 else name

            try:
                await self.load_extension(name)
                if top_level_name not in logged_folders:
                    self.logger.info(f"Loaded {top_level_name} cog.")
                    logged_folders.add(top_level_name)
            except Exception as e:
                failed_cogs.append(f"`{name}`: {e}")
                self.logger.error(f"Failed to load extension {name}\n{e}")

        if failed_cogs:
            self.logger.error(
                "Failed to load the following cogs:\n" + "\n".join(failed_cogs)
            )

    async def on_ready(self) -> None:
        """
        Fired every time the bot (re)connects to Discord — including after
        network drops. Only do gateway-dependent work here (presence, cache
        warm-up). Never put one-time init here.
        """
        self.logger.info("-------------------")
        self.logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
        self.logger.info(f"Time: {datetime.now().strftime('%H:%M:%S')}")
        self.logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        self.logger.info(f"Ping: {round(self.latency * 1000)} ms")
        self.logger.info("-------------------")

        # Set presence — needs the gateway, so it belongs here.
        activity = discord.Game(name="Butterbot")
        await self.change_presence(status=discord.Status.online, activity=activity)

        # Warm up in-memory caches that require data from the DB / external APIs.
        # These are fast reads so it's fine to redo them on reconnect.
        cached_players = await load_cached_players_from_db(self.database.players_db)
        await self.valorant_players.batch_set(cached_players)
        self.logger.info(f"Loaded {len(cached_players)} Valorant players into cache.")

        await self.osrs_data.initialize()

    async def close(self) -> None:
        """
        Graceful shutdown: close the DB connection before the event loop stops.
        Without this, aiosqlite can log "Future exception was never retrieved"
        warnings and WAL checkpoint may not flush cleanly to disk.
        """
        self.logger.info("Shutting down — closing database connection...")
        if self._db_connection:
            await self._db_connection.close()
            self.logger.info("Database connection closed.")
        await super().close()

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user or message.author.bot:
            return
        await self.process_commands(message)


try:
    bot = MyBot()
    bot.run(os.getenv("TOKEN"))
except discord.LoginFailure:
    logger.error("Invalid token provided. Please check your .env file.")
except Exception as e:
    logger.error(f"An error occurred: {e}")
