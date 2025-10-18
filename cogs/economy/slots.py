import random
from collections import defaultdict
from typing import Optional

import discord
from discord import app_commands
from logger import setup_logger
from utils.base_cog import BaseGameCog
from utils.formatting import format_number
from utils.gambling_handler import GameResult

logger = setup_logger("Slots")


# Slots Configuration
EMOJIS = ["🍎", "🍊", "🍐", "🍋", "🍉", "🍇", "🍓", "🍒"]
SPECIAL_EMOJIS = ["🍉", "🍒", "🍐"]
FRUIT_REWARDS = {3: 1, 4: 5, 5: 35, 6: 100, 7: 1000, 8: 10000, 9: 100000}

WINNING_COMBINATIONS = [
    [0, 1, 2],  # Top row
    [3, 4, 5],  # Middle row
    [6, 7, 8],  # Bottom row
    [0, 3, 6],  # Left column
    [1, 4, 7],  # Middle column
    [2, 5, 8],  # Right column
    [0, 4, 8],  # Diagonal
    [2, 4, 6],  # Reverse diagonal
]


async def perform_slots(
    bot, user_id: int, amount: int, prev_balance: int
) -> GameResult:
    """
    Execute a single slots game.

    Returns GameResult with board display and outcome.
    """
    # Fetch stats
    stats_raw = await bot.database.game_db.get_user_game_stats(user_id)
    stats = defaultdict(int, stats_raw.get("game_stats", {}))
    stats["slots_played"] += 1

    # Generate board
    board = random.choices(EMOJIS, k=9)
    board_display = "\n".join(
        " ".join(board[i : i + 3]) for i in range(0, len(board), 3)
    )

    # Check for three in a line
    three_line_win = any(
        board[i] == board[j] == board[k] for i, j, k in WINNING_COMBINATIONS
    )

    # Check for special fruits
    special_fruits_count = {emoji: board.count(emoji) for emoji in SPECIAL_EMOJIS}
    max_special_fruits = max(special_fruits_count.values(), default=0)

    # Determine outcome
    if three_line_win:
        multiplier = 2
        result = f"3 in a line! You win! ${format_number(amount * 2)}"
        color = discord.Color.green()
        outcome = amount * 2
        stats["slots_won"] += 1
        win_status = True
    elif max_special_fruits >= 3:
        multiplier = FRUIT_REWARDS.get(max_special_fruits, 0)
        emoji = next(
            emoji
            for emoji, count in special_fruits_count.items()
            if count == max_special_fruits
        )
        result = f"{max_special_fruits} {emoji} fruits! You win! ${format_number(amount * multiplier)}"
        color = discord.Color.green()
        outcome = amount * multiplier
        stats["slots_won"] += 1
        win_status = True
    else:
        multiplier = 1
        result = "No Matches"
        color = discord.Color.red()
        outcome = -amount
        stats["slots_lost"] += 1
        win_status = False

    return GameResult(
        win_status=win_status,
        outcome_amount=outcome,
        title="🎰 Slots",
        description=result,
        color=color,
        content=board_display,
        footer_text=f"Slots Won: {stats['slots_won']} | Slots Lost: {stats['slots_lost']} | Slots Played: {stats['slots_played']}",
        multiplier=multiplier,
    )


class Slots(BaseGameCog):
    def __init__(self, bot):
        super().__init__(bot)

    @app_commands.command(name="slots", description="Play a game of slots")
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
    async def slots(
        self,
        interaction: discord.Interaction,
        amount: Optional[app_commands.Range[int, 1, None]] = None,
        action: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        """Slots command using unified handler."""
        await self.run_gambling_command(
            interaction,
            amount,
            action.value if action else None,
            game_func=perform_slots,
            game_name="Slots",
        )


async def setup(bot):
    await bot.add_cog(Slots(bot))
