import os
import platform
from datetime import datetime
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner_or_mod_check

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class Development(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.patch_notes = [] 
        bot.tree.on_error = self.on_app_command_error

    @app_commands.command(
        name="sync",
        description="Synchonizes the slash commands.",
    )
    @app_commands.describe(scope="The scope of the sync. Can be `global` or `guild`")
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
        """
        Synchonizes the slash commands.

        :param interaction: The command interaction.
        :param scope: The scope of the sync. Can be `global` or `guild`.
        """
        await interaction.response.defer()
        if scope.value == "global":
            num_of_guilds = await self.bot.tree.sync()
            embed = discord.Embed(
                description=f"{len(num_of_guilds)} Slash commands have been globally synchronized.",
                color=0xBEBEFE,
            )
            await interaction.followup.send(embed=embed)
            return
        elif scope.value == "guild":
            self.bot.tree.copy_global_to(guild=interaction.guild)
            num_of_guilds = await self.bot.tree.sync(guild=interaction.guild)
            embed = discord.Embed(
                description=f"{len(num_of_guilds)} Slash commands have been synchronized in this guild.",
                color=0xBEBEFE,
            )
            await interaction.followup.send(embed=embed)
            return
        embed = discord.Embed(
            description="The scope must be `global` or `guild`.", color=0xE02B2B
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

    @app_commands.command(name="reload", description="Reloads a cog.")
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
                # Reload a specific cog
                await self.bot.reload_extension(f"cogs.{cog}")
                embed = discord.Embed(
                    description=f"✅ Successfully reloaded the `{cog}` cog.",
                    color=0xBEBEFE,
                )
            else:
                # Reload all cogs
                cogs_to_reload = [
                    os.path.splitext(os.path.join(root, file))[0].replace(os.sep, ".")
                    for root, _, files in os.walk("cogs")
                    for file in files
                    if file.endswith(".py") and not file.startswith("_")
                ]

                failed_cogs = []
                for name in cogs_to_reload:
                    try:
                        await self.bot.reload_extension(name)
                        self.bot.logger.info(f"Reloaded {name} cog.")
                    except Exception as e:
                        failed_cogs.append(f"`{name}`: {e}")

                if failed_cogs:
                    embed = discord.Embed(
                        description="⚠️ Some cogs failed to reload:\n"
                        + "\n".join(failed_cogs),
                        title="Failed to Reload Cogs",
                        color=0xE02B2B,
                    )
                else:
                    embed = discord.Embed(
                        description="✅ Successfully reloaded all cogs!", color=0xBEBEFE
                    )

        except Exception as e:
            embed = discord.Embed(
                description=f"❌ Failed to reload `{cog}` cog.\n```{e}```",
                color=0xE02B2B,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

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

    @app_commands.command(name="stats", description="Show stats of the bot.")
    @app_commands.check(is_owner_or_mod_check)
    async def stats(self, interaction: discord.Interaction):
        """
        Provides statistics about the bot, including latency, uptime, and more.
        """
        # Gather stats
        guild_count = len(self.bot.guilds)
        user_count = sum(guild.member_count or 0 for guild in self.bot.guilds)

        # Safely get cog count (handle missing or empty directory)
        cog_count = 0
        try:
            cog_count = len(
                [
                    filename
                    for filename in os.listdir("cogs/")
                    if filename.endswith(".py")
                ]
            )
        except FileNotFoundError:
            cog_count = 0

        slash_command_count = len(self.bot.tree.get_commands())

        # Uptime calculation
        uptime = datetime.now() - self.bot.start_time
        total_seconds = int(uptime.total_seconds())
        days, remainder = divmod(total_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Formatted uptime with pluralization
        duration_formatted = f"{days} {'Day' if days == 1 else 'Days'}:{hours} {'Hour' if hours == 1 else 'Hours'}:{minutes} {'Minute' if minutes == 1 else 'Minutes'}:{seconds} {'Second' if seconds == 1 else 'Seconds'}"

        # Creating the embed message
        embed = discord.Embed(
            title=f"{self.bot.user.display_name} Stats",
            color=discord.Color.blurple(),
            timestamp=datetime.now(),
        )

        # Set a fallback thumbnail if the bot doesn't have one
        avatar_url = (
            self.bot.user.display_avatar.url
            if self.bot.user.display_avatar
            else "https://path/to/default/avatar.png"
        )
        embed.set_thumbnail(url=avatar_url)

        # Add fields to the embed
        embed.add_field(
            name="Ping", value=f"{round(self.bot.latency * 1000)}ms", inline=True
        )
        embed.add_field(name="Total Servers", value=str(guild_count), inline=True)
        embed.add_field(name="Total Members", value=str(user_count), inline=True)
        embed.add_field(name="Uptime", value=duration_formatted, inline=True)
        embed.add_field(
            name="Discord.py Version",
            value=f"{discord.__version__.split()[0]}",
            inline=True,
        )
        embed.add_field(
            name="Python Version", value=platform.python_version(), inline=True
        )
        embed.add_field(name="Total Cogs", value=str(cog_count), inline=True)
        embed.add_field(
            name="Total Slash Commands", value=str(slash_command_count), inline=True
        )

        # Send the embed message
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_app_command_completion(
        self, interaction: discord.Interaction, command: app_commands.Command
    ) -> None:
        """
        This event is triggered when a slash command has been successfully executed.

        :param interaction: The interaction of the command.
        :param command: The command that was executed.
        """
        executed_command = command.qualified_name
        if interaction.guild:
            self.bot.logger.info(
                f"Executed /{executed_command} in {interaction.guild.name} (ID: {interaction.guild.id}) "
                f"by {interaction.user} (ID: {interaction.user.id})"
            )
        else:
            self.bot.logger.info(
                f"Executed /{executed_command} by {interaction.user} (ID: {interaction.user.id}) in DMs"
            )

    @app_commands.command(
        name="debug",
        description="Debug the bot.",
    )
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.user.id))
    @app_commands.guilds(DEV_GUILD_ID)
    async def debug(self, interaction: discord.Interaction) -> None:
        """
        Debug the bot.

        :param interaction: The command interaction.
        """
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="Debug Information",
            description="This is a debug command.",
            color=0xBEBEFE,
        )
        embed.add_field(name="Bot Name", value=self.bot.user.name, inline=True)
        embed.add_field(name="Bot ID", value=self.bot.user.id, inline=True)
        embed.add_field(name="Bot Version", value="1.0.0", inline=True)
        embed.add_field(
            name="Python Version", value=platform.python_version(), inline=True
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="migrate",
        description="Migrate a user's level data to 25% XP scaling.",
    )
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def migrate(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        """
        Migrate a single user's work stats to new XP formula with logging.

        :param interaction: The command interaction.
        :param user: The user to migrate.
        """
        await interaction.response.send_message(
            "Starting migration to 25% level growth...", ephemeral=True
        )
        await self.bot.database.work_db.migrate_work_levels_to_25_percent_growth()
        await interaction.followup.send("✅ Migration complete!", ephemeral=True)

    @app_commands.command(name="ping", description="Get the bot's latency.")
    async def ping(self, interaction: discord.Interaction):
        # Fetching bot's latency
        latency = self.bot.latency * 1000  # convert from seconds to milliseconds
        await interaction.response.send_message(f"Pong! 🏓 Latency: {latency:.2f}ms")

    @commands.Cog.listener()
    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """
        This event is triggered when an error occurs while executing a slash command.

        :param interaction: The interaction of the command.
        :param error: The error that occurred.
        """
        command_name = interaction.command.name if interaction.command else "unknown"
        guild_name = interaction.guild.name if interaction.guild else "DMs"
        guild_id = interaction.guild.id if interaction.guild else "N/A"

        # Log the error including the traceback
        if interaction.guild:
            self.bot.logger.error(
                f"Error in /{command_name} command: {error} in {guild_name} (ID: {guild_id}) "
                f"by {interaction.user} (ID: {interaction.user.id})",
                exc_info=True,
            )
        else:
            self.bot.logger.error(
                f"Error in /{command_name} command: {error} in DMs by {interaction.user} (ID: {interaction.user.id})",
                exc_info=True,
            )

        # Check if already responded
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        # If already deferred, you can safely send followup
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.followup.send(
                f"This command is on cooldown. Try again in {error.retry_after:.2f} seconds.",
                ephemeral=True,
            )
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.followup.send(
                "You do not have permission to use this command.", ephemeral=True
            )
        elif isinstance(error, app_commands.BotMissingPermissions):
            await interaction.followup.send(
                "I do not have permission to execute this command.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"An error occurred: {error}", ephemeral=True
            )


async def setup(bot) -> None:
    await bot.add_cog(Development(bot))
