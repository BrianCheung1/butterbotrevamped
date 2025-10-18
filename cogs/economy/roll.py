import random
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from logger import setup_logger
from utils.base_cog import BaseGameCog
from utils.formatting import format_number
from utils.gambling_handler import GameResult

logger = setup_logger("Roll")


async def perform_roll(bot, user_id: int, amount: int, prev_balance: int) -> GameResult:
    """
    Execute a single roll game.

    Returns GameResult with all necessary data for embed creation.
    """
    MAX_ROLL = 100
    MIN_ROLL = 0

    user_roll = random.randint(MIN_ROLL, MAX_ROLL)
    dealer_roll = random.randint(MIN_ROLL, MAX_ROLL)

    # Fetch stats
    stats_raw = await bot.database.game_db.get_user_game_stats(user_id)
    stats = dict(stats_raw.get("game_stats", {}))

    stats["rolls_played"] = stats.get("rolls_played", 0) + 1
    stats["rolls_won"] = stats.get("rolls_won", 0)
    stats["rolls_lost"] = stats.get("rolls_lost", 0)

    # Determine outcome
    if user_roll > dealer_roll:
        result = "You win!"
        color = discord.Color.green()
        outcome = amount
        stats["rolls_won"] += 1
        win_status = True
    elif user_roll < dealer_roll:
        result = "You lose!"
        color = discord.Color.red()
        outcome = -amount
        stats["rolls_lost"] += 1
        win_status = False
    else:
        result = "It's a tie!"
        color = discord.Color.gold()
        outcome = 0
        win_status = None

    tied_count = stats["rolls_played"] - stats["rolls_won"] - stats["rolls_lost"]

    # Log roll history
    await bot.database.game_db.log_roll_history(
        user_id=user_id,
        user_roll=user_roll,
        dealer_roll=dealer_roll,
        result=(
            "win"
            if user_roll > dealer_roll
            else "loss" if user_roll < dealer_roll else "tie"
        ),
        amount=amount,
    )

    # Fetch roll history for embed
    history = await bot.database.game_db.get_roll_history(user_id)
    history_text = ""
    if history:
        history_lines = []
        for entry in history:
            emoji = (
                "✅"
                if entry["result"] == "win"
                else "❌" if entry["result"] == "loss" else "➖"
            )
            dt = datetime.fromisoformat(entry["timestamp"]).replace(tzinfo=timezone.utc)
            unix_timestamp = int(dt.timestamp())
            history_lines.append(
                f"{emoji} Bet: ${format_number(entry['amount'])} — <t:{unix_timestamp}:R>"
            )
        history_text = "\n".join(history_lines)

    return GameResult(
        win_status=win_status,
        outcome_amount=outcome,
        title="🎲 Dice Roll Result",
        description=f"You rolled: **{user_roll}**\nDealer rolled: **{dealer_roll}**\n\n**{result}**",
        color=color,
        footer_text=f"Rolls Won: {stats['rolls_won']} | Lost: {stats['rolls_lost']} | Tied: {tied_count} | Total Played: {stats['rolls_played']}",
        extra_fields={"Last 10 Rolls": history_text} if history_text else None,
        multiplier=1,
    )


class Roll(BaseGameCog):
    def __init__(self, bot):
        super().__init__(bot)

    @app_commands.command(name="roll", description="Roll a dice against the dealer")
    @app_commands.describe(
        amount="The amount to bet", action="Choose a percentage of your balance"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="100%", value="100%"),
            app_commands.Choice(name="75%", value="75%"),
            app_commands.Choice(name="50%", value="50%"),
            app_commands.Choice(name="25%", value="25%"),
        ]
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def roll(
        self,
        interaction: discord.Interaction,
        amount: Optional[app_commands.Range[int, 1, None]] = None,
        action: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        """Roll command using unified handler."""
        await self.run_gambling_command(
            interaction,
            amount,
            action.value if action else None,
            game_func=perform_roll,
            game_name="Roll",
        )


async def setup(bot):
    await bot.add_cog(Roll(bot))
