import aiosqlite

from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("GuildSettingsDatabaseManager")


class GuildSettingsDatabaseManager:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self.connection = connection

    @db_error_handler
    async def set_channel(
        self, guild_id: int, channel_type: str, channel_id: int
    ) -> None:
        """
        Set a specific channel type (e.g., 'interest_channel_id') for the guild.
        """
        if channel_type not in {
            "interest_channel_id",
            "patchnotes_channel_id",
        }:
            raise ValueError(f"Invalid channel_type '{channel_type}'")

        await self.connection.execute("BEGIN IMMEDIATE")
        await self.connection.execute(
            f"""
            INSERT INTO guild_settings (guild_id, {channel_type})
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET {channel_type} = excluded.{channel_type}
            """,
            (guild_id, channel_id),
        )
        await self.connection.commit()

    @db_error_handler
    async def get_channel(self, guild_id: int, channel_type: str) -> int | None:
        """
        Get the channel ID of the specified type for the guild.
        """
        if channel_type not in {
            "interest_channel_id",
            "patchnotes_channel_id",
        }:
            raise ValueError(f"Invalid channel_type '{channel_type}'")

        async with self.connection.execute(
            f"SELECT {channel_type} FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        return row[0] if row else None

    @db_error_handler
    async def get_all_settings(self, guild_id: int) -> dict:
        """
        Retrieve all settings for a guild.
        """
        async with self.connection.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return {}

        column_names = [description[0] for description in cursor.description]
        return dict(zip(column_names, row))

    @db_error_handler
    async def remove_channel(self, guild_id: int, channel_type: str) -> None:
        """
        Remove (unset) the channel of the specified type for the guild by setting it to NULL.
        """
        if channel_type not in {
            "interest_channel_id",
            "interest_channel_id",
            "patchnotes_channel_id",
        }:
            raise ValueError(f"Invalid channel_type '{channel_type}'")

        await self.connection.execute(
            f"""
            UPDATE guild_settings
            SET {channel_type} = NULL
            WHERE guild_id = ?
            """,
            (guild_id,),
        )
        await self.connection.commit()
