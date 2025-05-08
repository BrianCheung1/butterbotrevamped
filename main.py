import os
from datetime import datetime

import aiosqlite
import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import DatabaseManager
from logger import setup_logger

# Load environment variables from .env file
load_dotenv()

# Setup logger
logger = setup_logger("Butterbot")


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="`",
            intents=discord.Intents.all(),
            help_command=None,
        )
        self.logger = logger
        self.database = None
        self.invite_link = os.getenv("INVITE_LINK")
        self.active_blackjack_players = set()

    async def init_db(self) -> None:
        async with aiosqlite.connect(
            f"{os.path.realpath(os.path.dirname(__file__))}/database/database.db"
        ) as db:
            with open(
                f"{os.path.realpath(os.path.dirname(__file__))}/database/schema.sql",
                encoding="utf-8",
            ) as file:
                await db.executescript(file.read())
            await db.commit()

    async def load_cogs(self):
        for root, _, files in os.walk("cogs"):
            for file in files:
                if file.endswith(".py") and not file.startswith("_"):
                    # Convert file path to Python module path
                    module = os.path.splitext(os.path.join(root, file))[0].replace(
                        os.sep, "."
                    )
                    try:
                        await bot.load_extension(module)
                        self.logger.info(f"Loaded extension '{module}'")
                    except Exception as e:
                        self.logger.error(f"Failed to load extension {module}\n{e}")

    async def on_ready(self) -> None:
        """
        This will just be executed when the bot starts the first time.
        """
        self.logger.info("-------------------")
        self.logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
        self.logger.info(f"Time: {datetime.now().strftime('%H:%M:%S')}")
        self.logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        self.logger.info(f"Ping: {round(self.latency * 1000)} ms")
        self.logger.info("-------------------")
        await self.init_db()
        self.database = DatabaseManager(
            connection=await aiosqlite.connect(
                f"{os.path.realpath(os.path.dirname(__file__))}/database/database.db"
            )
        )
        await self.load_cogs()

    async def on_message(self, message: discord.Message) -> None:
        """
        The code in this event is executed every time someone sends a message, with or without the prefix

        :param message: The message that was sent.
        """
        if message.author == self.user or message.author.bot:
            return
        await self.process_commands(message)


# Initialize and run the bot with error handling
try:
    bot = MyBot()
    bot.start_time = datetime.now()
    bot.run(os.getenv("TOKEN"))
except discord.LoginFailure:
    logger.error("Invalid token provided. Please check your .env file.")
except Exception as e:
    logger.error(f"An error occurred: {e}")
