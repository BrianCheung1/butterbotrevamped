import discord
from discord import app_commands
from discord.ext import commands
from utils.formatting import format_number


class WorkStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="workstats",
        description="Check your work stats or someone else's.",
    )
    async def work_stats(
        self, interaction: discord.Interaction, user: discord.User = None
    ) -> None:
        """Check the work stats of yourself or another user."""
        user = user or interaction.user

        stats = await self.bot.database.work_db.get_user_work_stats(user.id)
        work_stats = dict(stats["work_stats"])

        embed = discord.Embed(
            title=f"{user.display_name}'s Work Stats",
            color=user.accent_color or discord.Color.blue(),
        )

        # Mining Stats
        mining_xp = work_stats.get("mining_xp", 0)
        mining_next_level_xp = work_stats.get("mining_next_level_xp", 100)

        embed.add_field(
            name="⛏️ __Mining Stats__",
            value=(
                f"**Total Mining:** {work_stats.get('total_mining', 0)}\n"
                f"**Total Value:** ${format_number(work_stats.get('total_mining_value', 0))}\n"
                f"**Level:** {work_stats.get('mining_level', 1)}\n"
                f"**XP:** {mining_xp}/{mining_next_level_xp} "
            ),
            inline=False,
        )

        # Fishing Stats
        fishing_xp = work_stats.get("fishing_xp", 0)
        fishing_next_level_xp = work_stats.get("fishing_next_level_xp", 100)

        embed.add_field(
            name="🎣 __Fishing Stats__",
            value=(
                f"**Total Fishing:** {work_stats.get('total_fishing', 0)}\n"
                f"**Total Value:** ${format_number(work_stats.get('total_fishing_value', 0))}\n"
                f"**Level:** {work_stats.get('fishing_level', 1)}\n"
                f"**XP:** {fishing_xp}/{fishing_next_level_xp} "
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(WorkStats(bot))
