import os

import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner_or_mod_check

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class Sync(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="sync",
        description="Synchronizes the slash commands globally or in this guild.",
    )
    @app_commands.describe(scope="Where to sync the commands: `global` or `guild`")
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="Global", value="global"),
            app_commands.Choice(name="Guild", value="guild"),
        ]
    )
    @app_commands.guilds(DEV_GUILD_ID)
    async def sync(
        self, interaction: discord.Interaction, scope: app_commands.Choice[str]
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if scope.value == "global":
            synced = await self.bot.tree.sync()
            embed = discord.Embed(
                description=f"✅ Synced {len(synced)} commands globally.",
                color=0xBEBEFE,
            )
        elif scope.value == "guild":
            synced = await self.bot.tree.sync(guild=interaction.guild)
            embed = discord.Embed(
                description=f"✅ Synced {len(synced)} commands in this guild only.",
                color=0xBEBEFE,
            )
        else:
            embed = discord.Embed(
                description="❌ Invalid scope. Must be `global` or `guild`.",
                color=0xE02B2B,
            )

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="unsync",
        description="Unsynchonizes the slash commands.",
    )
    @app_commands.describe(
        scope="The scope of the sync. Can be `global`, `current_guild` or `guild`"
    )
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="Global", value="global"),
            app_commands.Choice(name="Guild", value="guild"),
        ]
    )
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def unsync(
        self, interaction: discord.Interaction, scope: app_commands.Choice[str]
    ) -> None:
        """
        Unsynchonizes the slash commands.

        :param interaction: The command interaction.
        :param scope: The scope of the sync. Can be `global`, `current_guild` or `guild`.
        """
        await interaction.response.defer()
        if scope.value == "global":
            self.bot.tree.clear_commands(guild=None)
            await self.bot.tree.sync()
            embed = discord.Embed(
                description="Slash commands have been globally unsynchronized.",
                color=0xBEBEFE,
            )
            await interaction.followup.send(embed=embed)
            return
        elif scope.value == "guild":
            self.bot.tree.clear_commands(guild=interaction.guild)
            await self.bot.tree.sync(guild=interaction.guild)
            embed = discord.Embed(
                description="Slash commands have been unsynchronized in this guild.",
                color=0xBEBEFE,
            )
            await interaction.followup.send(embed=embed)
            return
        embed = discord.Embed(
            description="The scope must be `global` or `guild`.", color=0xE02B2B
        )
        await interaction.followup.send(embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(Sync(bot))
