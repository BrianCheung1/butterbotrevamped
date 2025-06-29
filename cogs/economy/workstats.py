import discord
from discord import app_commands
from discord.ext import commands
from utils.equips import format_tool_display_name, get_tool_bonus
from utils.formatting import format_number


class WorkStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="work-stats",
        description="Check your work stats or someone else's.",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def work_stats(
        self, interaction: discord.Interaction, user: discord.User = None
    ) -> None:
        """Check the work stats of yourself or another user."""
        user = user or interaction.user

        stats = await self.bot.database.work_db.get_user_work_stats(user.id)
        work_stats = dict(stats["work_stats"])
        # Get equipped tools
        equipped_tools = await self.bot.database.inventory_db.get_equipped_tools(
            user.id
        )
        pickaxe_name = equipped_tools.get("pickaxe", "none")
        fishingrod_name = equipped_tools.get("fishingrod", "none")

        pickaxe_bonus = get_tool_bonus(pickaxe_name) * 100 if pickaxe_name else 0.0
        fishingrod_bonus = (
            get_tool_bonus(fishingrod_name) * 100 if fishingrod_name else 0.0
        )

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
                f"**Total Mining Clicks:** {work_stats.get('total_mining', 0):,}\n"
                f"**Total Value Collected:** ${format_number(work_stats.get('total_mining_value', 0))}\n"
                f"**Level:** {work_stats.get('mining_level', 1)}\n"
                f"**XP:** {mining_xp}/{mining_next_level_xp}\n"
                f"**Pickaxe:** {format_tool_display_name(pickaxe_name)} - {pickaxe_bonus}% Bonus"
            ),
            inline=False,
        )

        # Fishing Stats
        fishing_xp = work_stats.get("fishing_xp", 0)
        fishing_next_level_xp = work_stats.get("fishing_next_level_xp", 100)

        embed.add_field(
            name="🎣 __Fishing Stats__",
            value=(
                f"**Total Fishing Clicks:** {work_stats.get('total_fishing', 0):,}\n"
                f"**Total Value Collected:** ${format_number(work_stats.get('total_fishing_value', 0))}\n"
                f"**Level:** {work_stats.get('fishing_level', 1)}\n"
                f"**XP:** {fishing_xp}/{fishing_next_level_xp}\n"
                f"**Fishing Rod:** {format_tool_display_name(fishingrod_name)} - {fishingrod_bonus}% Bonus"
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(WorkStats(bot))
