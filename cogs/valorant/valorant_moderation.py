import os

import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner_or_mod_check
from utils.valorant_helpers import name_autocomplete, tag_autocomplete

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class ValorantModeration(commands.Cog):
    """Valorant Moderation"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="valorant-remove", description="Remove a Valorant player from the database"
    )
    @app_commands.describe(name="Player's username", tag="Player's tag")
    @app_commands.autocomplete(name=name_autocomplete, tag=tag_autocomplete)
    @app_commands.guilds(DEV_GUILD_ID)
    @app_commands.check(is_owner_or_mod_check)
    async def valorant_remove(
        self,
        interaction: discord.Interaction,
        name: str,
        tag: str,
    ):
        await interaction.response.defer(thinking=True)

        name = name.strip().lower()
        tag = tag.strip().lower()

        # Call delete_player from your PlayersDatabaseManager (and await it!)
        deleted = await self.bot.database.players_db.delete_player(name, tag)

        # Remove from in-memory cache too
        self.bot.valorant_players.pop((name, tag), None)

        if deleted:
            await interaction.followup.send(
                f"✅ Removed `{name}#{tag}` from the leaderboard."
            )
        else:
            await interaction.followup.send(
                f"⚠️ `{name}#{tag}` was not found in the database."
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantModeration(bot))
