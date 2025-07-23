import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from utils.checks import is_owner_or_mod_check

CHANNEL_TYPES = {
    "Interest": "interest_channel_id",
    "Patch Notes": "patchnotes_channel_id",
    "Steam Games": "steam_games_channel_id",
    "Leaderboard Announcements": "leaderboard_announcements_channel_id",  # <-- new
}


class GuildChannels(commands.Cog):
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
        await self.bot.database.guild_db.set_channel(
            guild_id=interaction.guild.id,
            channel_type=channel_type.value,
            channel_id=interaction.channel.id,
        )

        await interaction.response.send_message(
            f"✅ {channel_type.name} channel has been set to {interaction.channel.mention}.",
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
        removed = await self.bot.database.guild_db.remove_channel(
            guild_id=interaction.guild.id,
            channel_type=channel_type.value,
        )

        if removed:
            msg = f"✅ {channel_type.name} channel has been unset."
        else:
            msg = f"ℹ️ {channel_type.name} channel was not set."

        await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(GuildChannels(bot))
