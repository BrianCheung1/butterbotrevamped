import discord
from discord import app_commands
from discord.ext import commands
from utils.formatting import format_number


class GameStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="gamestats",
        description="Check your game stats or someone else's.",
    )
    async def game_stats(
        self, interaction: discord.Interaction, user: discord.User = None
    ) -> None:
        user = user or interaction.user

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

        # Create a structured, readable embed
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

        # Add blocks by game
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

        # add_game_block(
        #     "Wordles",
        #     stats_dict["wordles_won"],
        #     stats_dict["wordles_lost"],
        #     stats_dict["wordles_played"],
        # )

        # add_game_block(
        #     "Roulettes",
        #     stats_dict["roulettes_won"],
        #     stats_dict["roulettes_lost"],
        #     stats_dict["roulettes_played"],
        #     stats_dict["roulettes_won_amt"],
        #     stats_dict["roulettes_lost_amt"],
        # )

        embed.set_footer(text="🧠 Keep grinding and improve your stats!")

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(GameStats(bot))
