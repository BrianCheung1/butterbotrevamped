import os
import platform
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner_or_mod_check


class BotStats(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bot-stats", description="Show stats of the bot.")
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


async def setup(bot):
    await bot.add_cog(BotStats(bot))
