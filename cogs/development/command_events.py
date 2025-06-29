import discord
from discord import app_commands
from discord.app_commands import CheckFailure
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
        elif isinstance(error, CheckFailure):
            # Handle check failure (permission denied, failed check, etc)
            await interaction.followup.send(
                "You do not have permission to use this command.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"An error occurred: {error}", ephemeral=True
            )


async def setup(bot) -> None:
    await bot.add_cog(CommandEvents(bot))
