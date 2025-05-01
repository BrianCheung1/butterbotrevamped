import discord
from discord import app_commands
from discord.ext import commands


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="View the leaderboard")
    @app_commands.choices(
        leaderboard_type=[
            app_commands.Choice(name="Balance", value="balance"),
            app_commands.Choice(name="Mining Level", value="mining_level"),
            app_commands.Choice(name="Fishing Level", value="fishing_level"),
            app_commands.Choice(name="Bank Balance", value="bank_balance"),
        ]
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        leaderboard_type: app_commands.Choice[str],
    ) -> None:
        await interaction.response.defer()

        # Fetch the leaderboard data using leaderboard_type.value
        leaderboard_data = await self.bot.database.get_leaderboard_data(
            leaderboard_type.value
        )

        leaderboard_str = ""
        for i, entry in enumerate(leaderboard_data):
            user_id = entry["user_id"]
            user = interaction.guild.get_member(user_id)
            username = (
                user.nick
                if user and user.nick
                else (user.name if user else f"User {user_id}")
            )

            if leaderboard_type.value in ("mining_level", "fishing_level"):
                leaderboard_str += (
                    f"{i+1}. {username} - Level {entry['score']} (XP: {entry['xp']})\n"
                )
            else:
                leaderboard_str += f"{i+1}. {username} - {entry['score']}\n"

        await interaction.followup.send(
            embed=discord.Embed(
                title=f"{leaderboard_type.name} Leaderboard",
                description=leaderboard_str or "No data available.",
                color=discord.Color.blue(),
            )
        )


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
