import discord
from discord import app_commands
from discord.ext import commands
from utils.equips import format_tool_display_name, get_tool_bonus
from utils.formatting import format_number


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="stats",
        description="Check your stats or someone else's.",
    )
    @app_commands.describe(
        user="The user to check stats for",
        stat_type="Which stats to view (game or work)",
    )
    @app_commands.choices(
        stat_type=[
            app_commands.Choice(name="Game Stats", value="game"),
            app_commands.Choice(name="Work Stats", value="work"),
        ]
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def stats(
        self,
        interaction: discord.Interaction,
        user: discord.User = None,
        stat_type: app_commands.Choice[str] = None,
    ) -> None:
        """View game or work stats for yourself or another user."""
        user = user or interaction.user
        stat_type = stat_type.value if stat_type else "game"

        if stat_type == "game":
            await self._show_game_stats(interaction, user)
        elif stat_type == "work":
            await self._show_work_stats(interaction, user)

    async def _show_game_stats(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        """Display game statistics."""
        stats = await self.bot.database.game_db.get_user_game_stats(user.id)
        game_stats = stats["game_stats"]

        # Convert list to dict with descriptive keys
        keys = [
            "user_id",
            "rolls_won",
            "rolls_lost",
            "rolls_played",
            "rolls_won_amt",
            "rolls_lost_amt",
            "blackjacks_won",
            "blackjacks_lost",
            "blackjacks_played",
            "blackjacks_won_amt",
            "blackjacks_lost_amt",
            "slots_won",
            "slots_lost",
            "slots_played",
            "slots_won_amt",
            "slots_lost_amt",
            "wordles_won",
            "wordles_lost",
            "wordles_played",
            "roulettes_won",
            "roulettes_lost",
            "roulettes_played",
            "roulettes_won_amt",
            "roulettes_lost_amt",
            "duel_stats_json",
        ]
        stats_dict = dict(zip(keys, game_stats))

        # Create structured embed
        embed = discord.Embed(
            title=f"{user.display_name}'s Game Stats", color=discord.Color.teal()
        )

        def add_game_block(
            name: str,
            wins: int,
            losses: int,
            played: int,
            winnings: int = None,
            losses_amt: int = None,
        ):
            embed.add_field(
                name=f"🎮 {name}",
                value=(
                    f"**Won**: {wins} | "
                    f"**Lost**: {losses} | "
                    f"**Played**: {played}"
                    + (
                        f"\n**Winnings**: ${format_number(winnings)}"
                        if winnings is not None
                        else ""
                    )
                    + (
                        f" | **Losses**: ${format_number(losses_amt)}"
                        if losses_amt is not None
                        else ""
                    )
                ),
                inline=False,
            )

        # Add game blocks
        add_game_block(
            "Rolls",
            stats_dict["rolls_won"],
            stats_dict["rolls_lost"],
            stats_dict["rolls_played"],
            stats_dict["rolls_won_amt"],
            stats_dict["rolls_lost_amt"],
        )

        add_game_block(
            "Blackjacks",
            stats_dict["blackjacks_won"],
            stats_dict["blackjacks_lost"],
            stats_dict["blackjacks_played"],
            stats_dict["blackjacks_won_amt"],
            stats_dict["blackjacks_lost_amt"],
        )

        add_game_block(
            "Slots",
            stats_dict["slots_won"],
            stats_dict["slots_lost"],
            stats_dict["slots_played"],
            stats_dict["slots_won_amt"],
            stats_dict["slots_lost_amt"],
        )

        embed.set_footer(text="🧠 Keep grinding and improve your stats!")
        await interaction.response.send_message(embed=embed)

    async def _show_work_stats(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        """Display work statistics."""
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
    await bot.add_cog(Stats(bot))
