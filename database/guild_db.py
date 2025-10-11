import aiosqlite
from logger import setup_logger
from utils.channels import VALID_CHANNEL_TYPES
from utils.database_errors import db_error_handler

logger = setup_logger("GuildSettingsDatabaseManager")


class GuildSettingsDatabaseManager:
    """Manager for guild-level settings and configuration."""

    def __init__(
        self, connection: aiosqlite.Connection, db_manager: "DatabaseManager"
    ) -> None:
        self.connection = connection
        self.db_manager = db_manager

    def _validate_channel_type(self, channel_type: str) -> None:
        """
        Validate that the channel type is supported.

        Args:
            channel_type: The database field name to validate

        Raises:
            ValueError: If channel_type is not valid
        """
        if channel_type not in VALID_CHANNEL_TYPES:
            raise ValueError(
                f"Invalid channel_type '{channel_type}'. "
                f"Valid types: {', '.join(sorted(VALID_CHANNEL_TYPES))}"
            )

    @db_error_handler
    async def set_channel(
        self, guild_id: int, channel_type: str, channel_id: int
    ) -> bool:
        """
        Set a specific channel type for the guild.

        Args:
            guild_id: Discord guild ID
            channel_type: Database field name (e.g., 'interest_channel_id')
            channel_id: Discord channel ID to set

        Returns:
            True if successful, False otherwise

        Raises:
            ValueError: If channel_type is invalid
        """
        self._validate_channel_type(channel_type)

        try:
            async with self.db_manager.transaction():
                await self.connection.execute(
                    f"""
                    INSERT INTO guild_settings (guild_id, {channel_type})
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET {channel_type} = excluded.{channel_type}
                    """,
                    (guild_id, channel_id),
                )
            logger.info(
                f"Set {channel_type} to channel {channel_id} for guild {guild_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Error setting channel: {e}", exc_info=True)
            return False

    @db_error_handler
    async def get_channel(self, guild_id: int, channel_type: str) -> int | None:
        """
        Get the channel ID of the specified type for the guild.

        Args:
            guild_id: Discord guild ID
            channel_type: Database field name (e.g., 'interest_channel_id')

        Returns:
            Channel ID if set, None otherwise

        Raises:
            ValueError: If channel_type is invalid
        """
        self._validate_channel_type(channel_type)

        try:
            async with self.connection.execute(
                f"SELECT {channel_type} FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()

            result = row[0] if row else None
            logger.debug(f"Retrieved {channel_type} for guild {guild_id}: {result}")
            return result
        except Exception as e:
            logger.error(f"Error getting channel: {e}", exc_info=True)
            return None

    @db_error_handler
    async def get_all_settings(self, guild_id: int) -> dict:
        """
        Retrieve all settings for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            Dictionary mapping column names to their values
        """
        try:
            async with self.connection.execute(
                "SELECT * FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    logger.debug(f"No settings found for guild {guild_id}")
                    return {}

                column_names = [description[0] for description in cursor.description]
                settings = dict(zip(column_names, row))
                logger.debug(
                    f"Retrieved settings for guild {guild_id}: {len(settings)} fields"
                )
                return settings
        except Exception as e:
            logger.error(f"Error getting all settings: {e}", exc_info=True)
            return {}

    @db_error_handler
    async def remove_channel(self, guild_id: int, channel_type: str) -> bool:
        """
        Remove (unset) the channel of the specified type for the guild by setting it to NULL.

        Args:
            guild_id: Discord guild ID
            channel_type: Database field name (e.g., 'interest_channel_id')

        Returns:
            True if a channel was removed, False if none was set

        Raises:
            ValueError: If channel_type is invalid
        """
        self._validate_channel_type(channel_type)

        try:
            async with self.db_manager.transaction():
                cursor = await self.connection.execute(
                    f"""
                    UPDATE guild_settings
                    SET {channel_type} = NULL
                    WHERE guild_id = ? AND {channel_type} IS NOT NULL
                    """,
                    (guild_id,),
                )
                removed = cursor.rowcount > 0

                if removed:
                    logger.info(f"Removed {channel_type} from guild {guild_id}")
                else:
                    logger.debug(f"{channel_type} not set for guild {guild_id}")

                return removed
        except Exception as e:
            logger.error(f"Error removing channel: {e}", exc_info=True)
            return False

    @db_error_handler
    async def get_configured_channels_count(self, guild_id: int) -> int:
        """
        Get the count of configured channels for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            Number of configured channels
        """
        try:
            settings = await self.get_all_settings(guild_id)
            # Count non-None, non-guild_id values
            count = sum(
                1
                for key, value in settings.items()
                if key != "guild_id" and value is not None
            )
            return count
        except Exception as e:
            logger.error(f"Error counting configured channels: {e}", exc_info=True)
            return 0

    @db_error_handler
    async def reset_all_channels(self, guild_id: int) -> bool:
        """
        Reset all notification channels for a guild to NULL.
        Useful for cleanup or guild reconfiguration.

        Args:
            guild_id: Discord guild ID

        Returns:
            True if successful, False otherwise
        """
        try:
            async with self.db_manager.transaction():
                # Build dynamic SET clause for all channel fields
                set_clause = ", ".join(
                    f"{field} = NULL" for field in VALID_CHANNEL_TYPES
                )

                await self.connection.execute(
                    f"""
                    UPDATE guild_settings
                    SET {set_clause}
                    WHERE guild_id = ?
                    """,
                    (guild_id,),
                )

            logger.info(f"Reset all channels for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Error resetting channels: {e}", exc_info=True)
            return False
