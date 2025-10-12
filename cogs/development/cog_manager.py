import os
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands.errors import ExtensionNotLoaded
from utils.checks import is_owner_or_mod_check
from logger import setup_logger

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))

logger = setup_logger("CogManager")


class CogManager(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="load",
        description="Load a cog",
    )
    @app_commands.describe(cog="The name of the cog to load")
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def load(self, interaction: discord.Interaction, cog: str) -> None:
        """
        The bot will load the given cog.

        :param interaction: The hybrid command interaction.
        :param cog: The name of the cog to load.
        """
        try:
            await self.bot.load_extension(f"cogs.{cog}")
        except Exception:
            embed = discord.Embed(
                description=f"Could not load the `{cog}` cog.", color=0xE02B2B
            )
            await interaction.response.send_message(embed=embed)
            return
        embed = discord.Embed(
            description=f"Successfully loaded the `{cog}` cog.", color=0xBEBEFE
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="unload",
        description="Unloads a cog.",
    )
    @app_commands.describe(cog="The name of the cog to unload")
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def unload(self, interaction: discord.Interaction, cog: str) -> None:
        """
        The bot will unload the given cog.

        :param interaction: The hybrid command interaction.
        :param cog: The name of the cog to unload.
        """
        try:
            await self.bot.unload_extension(f"cogs.{cog}")
        except Exception:
            embed = discord.Embed(
                description=f"Could not unload the `{cog}` cog.", color=0xE02B2B
            )
            await interaction.response.send_message(embed=embed)
            return
        embed = discord.Embed(
            description=f"Successfully unloaded the `{cog}` cog.", color=0xBEBEFE
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="reload", description="Reloads a cog or all cogs.")
    @app_commands.describe(cog="The name of the cog to reload")
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def reload(
        self,
        interaction: discord.Interaction,
        cog: Optional[Literal["development", "moderation"]] = None,
    ) -> None:
        """Reloads a specific cog, or all cogs if none is provided."""
        await interaction.response.defer(ephemeral=True)

        try:
            if cog:
                # Reload or load the specific cog
                cog_path = f"cogs.{cog}"
                try:
                    await self.bot.reload_extension(cog_path)
                    result = f"✅ Successfully reloaded the `{cog}` cog."
                except ExtensionNotLoaded:
                    await self.bot.load_extension(cog_path)
                    result = (
                        f"✅ Cog `{cog}` was not loaded, so it has now been loaded."
                    )
                embed = discord.Embed(description=result, color=0xBEBEFE)
            else:
                # Reload or load all cogs
                cogs_to_reload = [
                    os.path.splitext(os.path.join(root, file))[0].replace(os.sep, ".")
                    for root, _, files in os.walk("cogs")
                    for file in files
                    if file.endswith(".py") and not file.startswith("_")
                ]

                failed_cogs = []
                logged_folders = set()

                for name in cogs_to_reload:
                    parts = name.split(".")
                    top_level_name = ".".join(parts[:2]) if len(parts) >= 2 else name

                    try:
                        try:
                            await self.bot.reload_extension(name)
                        except ExtensionNotLoaded:
                            await self.bot.load_extension(name)

                        if top_level_name not in logged_folders:
                            logger.info(f"Reloaded {top_level_name} cog.")
                            logged_folders.add(top_level_name)

                    except Exception as e:
                        failed_cogs.append(f"`{name}`: {e}")
                        logger.error(f"Failed to reload or load {name} cog: {e}")

                if failed_cogs:
                    embed = discord.Embed(
                        title="⚠️ Some cogs failed to reload or load:",
                        description="\n".join(failed_cogs),
                        color=0xE02B2B,
                    )
                else:
                    embed = discord.Embed(
                        description="✅ Successfully reloaded or loaded all cogs!",
                        color=0xBEBEFE,
                    )

        except Exception as e:
            embed = discord.Embed(
                description=f"❌ An error occurred while reloading.\n```{e}```",
                color=0xE02B2B,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="reload_dev", description="Reloads a cog or all cogs.")
    @app_commands.describe(cog="The name of the cog to reload")
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def reload_dev(
        self,
        interaction: discord.Interaction,
        cog: Optional[Literal["development", "moderation"]] = None,
    ) -> None:
        """Reloads a specific cog, or all cogs if none is provided."""
        await interaction.response.defer(ephemeral=True)

        try:
            if cog:
                # Reload or load the specific cog
                cog_path = f"cogs.{cog}"
                try:
                    await self.bot.reload_extension(cog_path)
                    result = f"✅ Successfully reloaded the `{cog}` cog."
                except ExtensionNotLoaded:
                    await self.bot.load_extension(cog_path)
                    result = (
                        f"✅ Cog `{cog}` was not loaded, so it has now been loaded."
                    )
                embed = discord.Embed(description=result, color=0xBEBEFE)
            else:
                # Reload or load all cogs
                cogs_to_reload = [
                    os.path.splitext(os.path.join(root, file))[0].replace(os.sep, ".")
                    for root, _, files in os.walk("cogs")
                    for file in files
                    if file.endswith(".py") and not file.startswith("_")
                ]

                failed_cogs = []

                for name in cogs_to_reload:
                    try:
                        try:
                            await self.bot.reload_extension(name)
                            logger.info(f"Reloaded {name} cog.")
                        except ExtensionNotLoaded:
                            await self.bot.load_extension(name)
                            logger.info(f"Loaded new cog: {name}")
                    except Exception as e:
                        failed_cogs.append(f"`{name}`: {e}")

                if failed_cogs:
                    embed = discord.Embed(
                        title="⚠️ Some cogs failed to reload or load:",
                        description="\n".join(failed_cogs),
                        color=0xE02B2B,
                    )
                else:
                    embed = discord.Embed(
                        description="✅ Successfully reloaded or loaded all cogs!",
                        color=0xBEBEFE,
                    )

        except Exception as e:
            embed = discord.Embed(
                description=f"❌ An error occurred while reloading.\n```{e}```",
                color=0xE02B2B,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(CogManager(bot))
