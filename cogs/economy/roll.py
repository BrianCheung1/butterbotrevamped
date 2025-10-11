import random
from datetime import datetime, timezone
from typing import Optional

import discord
from constants.game_config import GameEventType
from discord import app_commands
from utils.balance_helper import calculate_percentage_amount, validate_amount
from utils.base_cog import BaseGameCog
from utils.formatting import format_number


async def perform_roll(bot, interaction, user_id, amount, action, prev_balance=None):
    """Execute a single roll game."""
    if prev_balance is None:
        prev_balance = await bot.database.user_db.get_balance(user_id)

    MAX_ROLL = 100
    MIN_ROLL = 0

    user_roll = random.randint(MIN_ROLL, MAX_ROLL)
    dealer_roll = random.randint(MIN_ROLL, MAX_ROLL)

    stats_raw = await bot.database.game_db.get_user_game_stats(user_id)
    stats = dict(stats_raw.get("game_stats", {}))

    stats["rolls_played"] = stats.get("rolls_played", 0) + 1
    stats["rolls_won"] = stats.get("rolls_won", 0)
    stats["rolls_lost"] = stats.get("rolls_lost", 0)

    # Determine outcome
    if user_roll > dealer_roll:
        result = "You win!"
        color = discord.Color.green()
        final_balance = prev_balance + amount
        outcome = amount
        stats["rolls_won"] += 1
        win_status = True
    elif user_roll < dealer_roll:
        result = "You lose!"
        color = discord.Color.red()
        final_balance = prev_balance - amount
        outcome = -amount
        stats["rolls_lost"] += 1
        win_status = False
    else:
        result = "It's a tie!"
        color = discord.Color.gold()
        final_balance = prev_balance
        outcome = 0
        win_status = None

    tied_count = stats["rolls_played"] - stats["rolls_won"] - stats["rolls_lost"]

    # Batch DB updates
    await bot.database.user_db.increment_balance(user_id, outcome)
    await bot.database.game_db.set_user_game_stats(
        user_id, GameEventType.ROLL, win_status, amount
    )
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

    # Create embed
    cog = bot.cogs.get("Roll")
    embed = cog.create_balance_embed(
        title="🎲 Dice Roll Result",
        description=f"You rolled: **{user_roll}**\nDealer rolled: **{dealer_roll}**\n\n**{result}**",
        prev_balance=prev_balance,
        new_balance=final_balance,
        amount=amount,
        color=color,
        footer_text=f"Rolls Won: {stats['rolls_won']} | Lost: {stats['rolls_lost']} | Tied: {tied_count} | Total Played: {stats['rolls_played']}",
    )

    # Add roll history
    history = await bot.database.game_db.get_roll_history(user_id)
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

        embed.add_field(
            name="Last 10 Rolls", value="\n".join(history_lines), inline=False
        )

    view = RollAgainView(bot, user_id, None if action else amount, action)
    view.message = await interaction.edit_original_response(embed=embed, view=view)


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


class RollAgainView(discord.ui.View):
    def __init__(self, bot, user_id, amount, action):
        super().__init__(timeout=300)
        self.bot = bot
        self.user_id = user_id
        self.amount = amount
        self.action = action

    async def on_timeout(self):
        try:
            await self.message.edit(content="Roll game timed out.", view=None)
        except discord.NotFound:
            self.bot.logger.debug("Message not found when disabling buttons.")

    @discord.ui.button(label="Roll Again", style=discord.ButtonStyle.green)
    async def roll_again(
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

        await perform_roll(
            self.bot,
            interaction,
            self.user_id,
            amount,
            self.action,
            prev_balance=current_balance,
        )


async def setup(bot):
    await bot.add_cog(Roll(bot))
