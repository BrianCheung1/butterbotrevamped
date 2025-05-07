import discord
import random
from discord import app_commands
from discord.ext import commands
from typing import Optional
from constants.game_config import GameEventType
from collections import defaultdict
from utils.formatting import format_number
from utils.balance_helper import validate_amount


def calculate_percentage_amount(balance: int, action: Optional[str]) -> Optional[int]:
    if action == "all":
        return balance
    elif action == "half":
        return balance // 2
    elif action == "25%":
        return balance // 4
    return None



class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="slots", description="Play a game of slots")
    @app_commands.describe(
        amount="The amount to bet", action="Choose a percentage of your balance"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="All", value="all"),
            app_commands.Choice(name="Half", value="half"),
            app_commands.Choice(name="25%", value="25%"),
        ]
    )
    async def slots(
        self,
        interaction: discord.Interaction,
        amount: Optional[app_commands.Range[int, 1, None]] = None,
        action: Optional[app_commands.Choice[str]] = None,
    ) -> None:

        user_id = interaction.user.id
        if user_id in self.bot.active_blackjack_players:
            await interaction.response.send_message(
                "You are in a Blackjack game! Please finish the game first",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        balance = await self.bot.database.user_db.get_balance(user_id)

        if amount and action:
            await interaction.edit_original_response(
                content="You can only choose one option: amount or action."
            )
            return

        if action and not amount:
            amount = calculate_percentage_amount(balance, action.value)

        error = validate_amount(amount, balance)
        if error:
            await interaction.edit_original_response(content=error)
            return

        await perform_slots(
            self.bot,
            interaction,
            user_id,
            amount,
            action.value if action else None,
        )


async def perform_slots(bot, interaction, user_id, amount, action):
    prev_balance = await bot.database.user_db.get_balance(user_id)
    stats_raw = await bot.database.game_db.get_user_game_stats(user_id)
    stats = defaultdict(int, stats_raw.get("game_stats", {}))
    stats["slots_played"] += 1

    EMOJIS = ["🍎", "🍊", "🍐", "🍋", "🍉", "🍇", "🍓", "🍒"]
    SPECIAL_EMOJIS = ["🍉", "🍒", "🍐"]
    board = random.choices(EMOJIS, k=9)
    board_display = "\n".join(
        " ".join(board[i : i + 3]) for i in range(0, len(board), 3)
    )

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

    if three_line_win:
        multiplier = 2
        result = f"3 in a line! You win! ${format_number(amount * 2)}"
        color = discord.Color.green()
        final_balance = prev_balance + amount * 2
        outcome = amount * 2
        stats["slots_won"] += 1
        win_status = True  # Win status is True when there's a line win
    elif max_special_fruits >= 3:
        multiplier = fruit_rewards.get(max_special_fruits, 0)

        # Find the emoji corresponding to the max count of special fruits
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
        win_status = True  # Win status is True when special fruits are 3 or more
    else:
        result = "No Matches"
        color = discord.Color.red()
        final_balance = prev_balance - amount
        stats["slots_lost"] += 1
        outcome = -amount
        win_status = False  # Win status is False when there are no matches

    # Update the user's balance and game stats
    # await bot.database.user_db.set_balance(user_id, final_balance)
    await bot.database.user_db.increment_balance(user_id, outcome)

    # Store the win status correctly for the event
    await bot.database.game_db.set_user_game_stats(
        user_id,
        GameEventType.SLOT,
        win_status,  # Use the win_status directly here
        (
            amount * multiplier if win_status else amount
        ),  # Multiply only if win_status is True
    )

    embed = discord.Embed(title="🎰 Slots", color=color)
    embed.add_field(name="Result", value=result, inline=False)
    embed.add_field(name="Bet", value=f"${amount:,}", inline=True)
    embed.add_field(name="Previous Balance", value=f"${prev_balance:,}", inline=True)
    embed.add_field(name="Current Balance", value=f"${final_balance:,}", inline=True)
    embed.set_footer(
        text=f"Slots Won: {stats['slots_won']} | Slots Lost: {stats['slots_lost']} | Slots Played: {stats['slots_played']}"
    )

    view = SlotsAgainView(bot, user_id, None if action else amount, action)
    view.message = await interaction.edit_original_response(
        content=board_display, embed=embed, view=view
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
        try:
            await self.message.edit(view=self)
        except discord.NotFound:
            self.bot.logger.debug("Message not found when disabling buttons.")
            pass

    @discord.ui.button(label="Spin Again", style=discord.ButtonStyle.green)
    async def spin_again(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.followup.send(content="You can't use this button.")
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

        await perform_slots(self.bot, interaction, self.user_id, amount, self.action)


async def setup(bot):
    await bot.add_cog(Slots(bot))
