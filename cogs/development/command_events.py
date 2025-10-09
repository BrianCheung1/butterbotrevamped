from datetime import datetime

import discord
from discord import app_commands
from discord.app_commands import (AppCommandError, BotMissingPermissions,
                                  CheckFailure, CommandOnCooldown,
                                  MissingPermissions)
from discord.ext import commands


class CommandEvents(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        bot.tree.on_error = self.on_app_command_error

    @commands.Cog.listener()
    async def on_app_command_completion(
        self, interaction: discord.Interaction, command: app_commands.Command
    ) -> None:
        """
        This event is triggered when a slash command has been successfully executed.
        """
        executed_command = f"/{command.qualified_name}"
        user = interaction.user
        now = datetime.now().strftime("%I:%M:%S:%p")  # 12-hour format

        GREEN = "\x1b[32m"
        RESET = "\x1b[0m"

        if interaction.guild:
            guild_name = interaction.guild.name
            channel_name = (
                interaction.channel.name
                if isinstance(interaction.channel, discord.TextChannel)
                else "Unknown"
            )
            log_msg = f"{GREEN}[{guild_name}][#{channel_name}][{now}] {user}: {executed_command} Successfully executed.{RESET}"
        else:
            log_msg = f"{GREEN}[DMs][{now}] {user}: {executed_command} Successfully executed.{RESET}"

        self.bot.logger.info(log_msg)

    @commands.Cog.listener()
    async def on_app_command_error(
        self, interaction: discord.Interaction, error: AppCommandError
    ) -> None:
        """
        This event is triggered when an error occurs while executing a slash command.
        """
        command_name = (
            f"/{interaction.command.name}" if interaction.command else "/unknown"
        )
        user = interaction.user
        now = datetime.now().strftime("%I:%M:%S:%p")  # 12-hour format

        RED = "\x1b[31m"
        RESET = "\x1b[0m"

        if interaction.guild:
            guild_name = interaction.guild.name
            channel_name = (
                interaction.channel.name
                if isinstance(interaction.channel, discord.TextChannel)
                else "Unknown"
            )
            log_msg = f"{RED}[{guild_name}][#{channel_name}][{now}] {user}: ERROR in {command_name} — {error}{RESET}"
        else:
            log_msg = (
                f"{RED}[DMs][{now}] {user}: ERROR in {command_name} — {error}{RESET}"
            )

        self.bot.logger.error(log_msg, exc_info=True)

        # Respond to the user if possible
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if isinstance(error, CommandOnCooldown):
            await interaction.followup.send(
                f"This command is on cooldown. Try again in {error.retry_after:.2f} seconds.",
                ephemeral=True,
            )
        elif isinstance(error, MissingPermissions):
            await interaction.followup.send(
                "You do not have permission to use this command.", ephemeral=True
            )
        elif isinstance(error, BotMissingPermissions):
            await interaction.followup.send(
                "I do not have permission to execute this command.", ephemeral=True
            )
        elif isinstance(error, CheckFailure):
            await interaction.followup.send(
                "You do not have permission to use this command.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"An error occurred: {error}", ephemeral=True
            )


async def setup(bot) -> None:
    await bot.add_cog(CommandEvents(bot))
