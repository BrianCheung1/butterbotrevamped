import random
from collections import defaultdict
from typing import Optional

import discord
from constants.game_config import GameEventType
from discord import app_commands
from utils.balance_helper import calculate_percentage_amount, validate_amount
from utils.base_cog import BaseGameCog
from utils.formatting import format_number
from logger import setup_logger

logger = setup_logger("Slots")


async def perform_slots(bot, interaction, user_id, amount, action, prev_balance=None):
    """Execute a single slots game."""
    if prev_balance is None:
        prev_balance = await bot.database.user_db.get_balance(user_id)

    stats_raw = await bot.database.game_db.get_user_game_stats(user_id)
    stats = defaultdict(int, stats_raw.get("game_stats", {}))
    stats["slots_played"] += 1

    # Board setup
    EMOJIS = ["🍎", "🍊", "🍐", "🍋", "🍉", "🍇", "🍓", "🍒"]
    SPECIAL_EMOJIS = ["🍉", "🍒", "🍐"]
    board = random.choices(EMOJIS, k=9)
    board_display = "\n".join(
        " ".join(board[i : i + 3]) for i in range(0, len(board), 3)
    )

    # Check for winning combinations
    winning_combinations = [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
        [0, 3, 6],
        [1, 4, 7],
        [2, 5, 8],
        [0, 4, 8],
        [2, 4, 6],
    ]
    three_line_win = any(
        board[i] == board[j] == board[k] for i, j, k in winning_combinations
    )
    special_fruits_count = {emoji: board.count(emoji) for emoji in SPECIAL_EMOJIS}
    max_special_fruits = max(special_fruits_count.values(), default=0)

    # Fruit rewards lookup
    fruit_rewards = {3: 1, 4: 5, 5: 35, 6: 100, 7: 1000, 8: 10000, 9: 100000}

    # Determine outcome
    if three_line_win:
        multiplier = 2
        result = f"3 in a line! You win! ${format_number(amount * 2)}"
        color = discord.Color.green()
        final_balance = prev_balance + amount * 2
        outcome = amount * 2
        stats["slots_won"] += 1
        win_status = True
    elif max_special_fruits >= 3:
        multiplier = fruit_rewards.get(max_special_fruits, 0)
        emoji = next(
            emoji
            for emoji, count in special_fruits_count.items()
            if count == max_special_fruits
        )
        result = f"{max_special_fruits} {emoji} fruits! You win! ${format_number(amount * multiplier)}"
        color = discord.Color.green()
        final_balance = prev_balance + amount * multiplier
        outcome = amount * multiplier
        stats["slots_won"] += 1
        win_status = True
    else:
        multiplier = 1
        result = "No Matches"
        color = discord.Color.red()
        final_balance = prev_balance - amount
        outcome = -amount
        stats["slots_lost"] += 1
        win_status = False

    # Batch DB updates
    await bot.database.user_db.increment_balance(user_id, outcome)
    await bot.database.game_db.set_user_game_stats(
        user_id,
        GameEventType.SLOT,
        win_status,
        (amount * multiplier if win_status else amount),
    )

    # Create embed
    cog = bot.cogs.get("Slots")
    embed = cog.create_balance_embed(
        title="🎰 Slots",
        description=result,
        prev_balance=prev_balance,
        new_balance=final_balance,
        amount=amount,
        color=color,
        footer_text=f"Slots Won: {stats['slots_won']} | Slots Lost: {stats['slots_lost']} | Slots Played: {stats['slots_played']}",
    )

    view = SlotsAgainView(bot, user_id, None if action else amount, action)
    view.message = await interaction.edit_original_response(
        content=board_display, embed=embed, view=view
    )
    view.message_id = view.message.id
    view.channel = interaction.channel


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


class SlotsAgainView(discord.ui.View):
    def __init__(self, bot, user_id, amount, action):
        super().__init__(timeout=300)
        self.bot = bot
        self.user_id = user_id
        self.amount = amount
        self.action = action

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        if hasattr(self, "message_id") and self.channel:
            try:
                message = await self.channel.fetch_message(self.message_id)
                await message.edit(view=self)
            except discord.HTTPException:
                logger.debug("Slots message expired or timed out")

    @discord.ui.button(label="Spin Again", style=discord.ButtonStyle.green)
    async def spin_again(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.followup.send(
                content="You can't use this button.", ephemeral=True
            )
            return

        await interaction.response.defer()

        current_balance = await self.bot.database.user_db.get_balance(self.user_id)
        amount = (
            calculate_percentage_amount(current_balance, self.action)
            if self.action
            else self.amount
        )

        error = validate_amount(amount, current_balance)
        if error:
            await interaction.edit_original_response(content=error, view=None)
            return

        await perform_slots(
            self.bot,
            interaction,
            self.user_id,
            amount,
            self.action,
            prev_balance=current_balance,
        )


async def setup(bot):
    await bot.add_cog(Slots(bot))
