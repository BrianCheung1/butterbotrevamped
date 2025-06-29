import discord
from discord import app_commands
from discord.ext import commands


class Ping(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Get the bot's latency.")
    async def ping(self, interaction: discord.Interaction):
        # Fetching bot's latency
        latency = self.bot.latency * 1000  # convert from seconds to milliseconds
        await interaction.response.send_message(f"Pong! 🏓 Latency: {latency:.2f}ms")


async def setup(bot):
    await bot.add_cog(Ping(bot))
