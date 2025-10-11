import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from utils.channels import CHANNEL_TYPES, get_channel_display_info
from utils.checks import is_owner_or_mod_check
from logger import setup_logger

logger = setup_logger("GuildChannels")


class GuildChannels(commands.Cog):
    """Commands for managing guild notification channels."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="channel-set",
        description="Set the current channel for a specific purpose (admin only).",
    )
    @app_commands.choices(
        channel_type=[
            Choice(name=name, value=db_field)
            for name, db_field in CHANNEL_TYPES.items()
        ]
    )
    @app_commands.check(is_owner_or_mod_check)
    async def set_channel(
        self,
        interaction: discord.Interaction,
        channel_type: Choice[str],
    ):
        """
        Set a notification channel for a specific purpose.

        Args:
            channel_type: The type of notification channel to set
        """
        try:
            # Get the display name for the channel type
            display_name = next(
                name
                for name, field in CHANNEL_TYPES.items()
                if field == channel_type.value
            )

            # Validate channel permissions
            if not self._validate_channel_permissions(interaction.channel):
                await interaction.response.send_message(
                    "⚠️ This channel doesn't support being set as a notification channel. "
                    "Please use a text channel, not a voice channel or thread.",
                    ephemeral=True,
                )
                return

            # Set the channel in the database
            await self.bot.database.guild_db.set_channel(
                guild_id=interaction.guild.id,
                channel_type=channel_type.value,
                channel_id=interaction.channel.id,
            )

            logger.info(
                f"Set {display_name} channel to {interaction.channel.id} in guild {interaction.guild.id}"
            )

            # Build response with helpful info
            embed = discord.Embed(
                title="✅ Channel Set Successfully",
                description=f"**{display_name}** notifications will be sent to {interaction.channel.mention}",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Channel Details",
                value=f"Channel ID: `{interaction.channel.id}`\nChannel Name: #{interaction.channel.name}",
                inline=False,
            )
            embed.set_footer(text="Use /channel-remove to unset this channel.")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting channel: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while setting the channel. Please try again.",
                ephemeral=True,
            )

    @app_commands.command(
        name="channel-remove",
        description="Unset a specific announcement/feature channel (admin only).",
    )
    @app_commands.choices(
        channel_type=[
            Choice(name=name, value=db_field)
            for name, db_field in CHANNEL_TYPES.items()
        ]
    )
    @app_commands.check(is_owner_or_mod_check)
    async def remove_channel(
        self,
        interaction: discord.Interaction,
        channel_type: Choice[str],
    ):
        """
        Remove a notification channel setting.

        Args:
            channel_type: The type of notification channel to unset
        """
        try:
            # Get the display name for the channel type
            display_name = next(
                name
                for name, field in CHANNEL_TYPES.items()
                if field == channel_type.value
            )

            # Get the current channel before removing
            current_channel_id = await self.bot.database.guild_db.get_channel(
                interaction.guild.id, channel_type.value
            )

            # Remove the channel
            removed = await self.bot.database.guild_db.remove_channel(
                guild_id=interaction.guild.id,
                channel_type=channel_type.value,
            )

            logger.info(
                f"Removed {display_name} channel from guild {interaction.guild.id}"
            )

            if removed:
                embed = discord.Embed(
                    title="✅ Channel Unset Successfully",
                    description=f"**{display_name}** notifications are now disabled.",
                    color=discord.Color.green(),
                )
                if current_channel_id:
                    try:
                        channel = await self.bot.fetch_channel(current_channel_id)
                        embed.add_field(
                            name="Previous Channel",
                            value=f"{channel.mention}",
                            inline=False,
                        )
                    except discord.NotFound:
                        pass
            else:
                embed = discord.Embed(
                    title="ℹ️ No Channel Set",
                    description=f"**{display_name}** channel was not previously set.",
                    color=discord.Color.blue(),
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error removing channel: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while removing the channel. Please try again.",
                ephemeral=True,
            )

    @app_commands.command(
        name="channels-list",
        description="Show all configured notification channels (admin only).",
    )
    @app_commands.check(is_owner_or_mod_check)
    async def list_channels(self, interaction: discord.Interaction):
        """
        Display all configured notification channels for the guild.
        """
        try:
            # Get all settings
            settings = await self.bot.database.guild_db.get_all_settings(
                interaction.guild.id
            )

            embed = discord.Embed(
                title="📋 Configured Notification Channels",
                description=f"Guild: {interaction.guild.name}",
                color=discord.Color.blue(),
            )

            if not settings or all(v is None for v in settings.values()):
                embed.add_field(
                    name="No channels configured",
                    value="Use `/channel-set` to configure notification channels.",
                    inline=False,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            configured_count = 0

            for display_name, db_field in CHANNEL_TYPES.items():
                channel_id = settings.get(db_field)

                if channel_id:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                        embed.add_field(
                            name=f"✅ {display_name}",
                            value=f"{channel.mention} (ID: `{channel_id}`)",
                            inline=False,
                        )
                        configured_count += 1
                    except discord.NotFound:
                        embed.add_field(
                            name=f"❌ {display_name}",
                            value=f"Channel deleted (ID: `{channel_id}`)",
                            inline=False,
                        )
                else:
                    embed.add_field(
                        name=f"⚪ {display_name}",
                        value="Not configured",
                        inline=False,
                    )

            embed.set_footer(
                text=f"{configured_count}/{len(CHANNEL_TYPES)} channels configured"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing channels: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while retrieving channels. Please try again.",
                ephemeral=True,
            )

    @staticmethod
    def _validate_channel_permissions(channel: discord.abc.GuildChannel) -> bool:
        """
        Validate that the channel is suitable for notifications.

        Args:
            channel: The Discord channel to validate

        Returns:
            True if valid, False otherwise
        """
        # Only text channels and forum channels are valid
        if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return False

        # Threads are technically allowed but might not be ideal
        # You can customize this logic as needed
        if isinstance(channel, discord.Thread) and channel.archived:
            return False

        return True


async def setup(bot) -> None:
    """Load the GuildChannels cog."""
    await bot.add_cog(GuildChannels(bot))
