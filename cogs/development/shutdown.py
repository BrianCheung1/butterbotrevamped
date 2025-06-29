import os

import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner_or_mod_check

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class Development(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="shutdown",
        description="Make the bot shutdown.",
    )
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def shutdown(self, interaction: discord.Interaction) -> None:
        """
        Shuts down the bot.

        :param interaction: The hybrid command interaction.
        """
        embed = discord.Embed(description="Shutting down. Bye! :wave:", color=0xBEBEFE)
        await interaction.response.send_message(embed=embed)
        await self.bot.close()


async def setup(bot) -> None:
    await bot.add_cog(Development(bot))
