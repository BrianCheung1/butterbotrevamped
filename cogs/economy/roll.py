import random
from datetime import datetime, timezone
from typing import Optional

import discord
from constants.game_config import GameEventType
from discord import app_commands
from discord.ext import commands
from utils.balance_helper import calculate_percentage_amount, validate_amount


class Roll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
    async def roll(
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
        if not action and not amount:
            await interaction.edit_original_response(
                content="You must specify an amount or choose a roll option.",
            )
            return
        if amount and action:
            await interaction.edit_original_response(
                content="You can only choose one option: amount or action."
            )
            return
        balance = await self.bot.database.user_db.get_balance(user_id)

        if action and not amount:
            amount = calculate_percentage_amount(balance, action.value)

        error = validate_amount(amount, balance)
        if error:
            await interaction.edit_original_response(content=error)
            return

        await perform_roll(
            self.bot,
            interaction,
            user_id,
            amount,
            action.value if action else None,
        )


async def perform_roll(bot, interaction, user_id, amount, action):
    prev_balance = await bot.database.user_db.get_balance(user_id)

    MAX_ROLL = 100
    MIN_ROLL = 0

    user_roll = random.randint(MIN_ROLL, MAX_ROLL)
    dealer_roll = random.randint(MIN_ROLL, MAX_ROLL)

    stats_raw = await bot.database.game_db.get_user_game_stats(user_id)
    stats = dict(stats_raw.get("game_stats", {}))

    # Ensure stat keys exist
    stats["rolls_played"] = stats.get("rolls_played", 0) + 1
    stats["rolls_won"] = stats.get("rolls_won", 0)
    stats["rolls_lost"] = stats.get("rolls_lost", 0)

    if user_roll > dealer_roll:
        result = "You win!"
        color = discord.Color.green()
        final_balance = prev_balance + amount
        outcome = amount
        stats["rolls_won"] += 1
        await bot.database.game_db.set_user_game_stats(
            user_id, GameEventType.ROLL, True, amount
        )
    elif user_roll < dealer_roll:
        result = "You lose!"
        color = discord.Color.red()
        final_balance = prev_balance - amount
        outcome = -amount
        stats["rolls_lost"] += 1
        await bot.database.game_db.set_user_game_stats(
            user_id, GameEventType.ROLL, False, amount
        )
    else:
        result = "It's a tie!"
        color = discord.Color.gold()
        final_balance = prev_balance
        outcome = 0
        await bot.database.game_db.set_user_game_stats(
            user_id, GameEventType.ROLL, None, 0
        )

    tied_count = stats["rolls_played"] - stats["rolls_won"] - stats["rolls_lost"]

    # await bot.database.user_db.set_balance(user_id, final_balance)
    await bot.database.user_db.increment_balance(user_id, outcome)
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

    embed = discord.Embed(
        title="🎲 Dice Roll Result",
        description=f"You rolled: **{user_roll}**\nDealer rolled: **{dealer_roll}**\n\n**{result}**",
        color=color,
    )
    embed.add_field(name="Bet Amount", value=f"${amount:,}", inline=True)
    embed.add_field(name="Previous Balance", value=f"${prev_balance:,}", inline=True)
    embed.add_field(name="Current Balance", value=f"${final_balance:,}", inline=True)
    embed.set_footer(
        text=f"Rolls Won: {stats['rolls_won']} | Lost: {stats['rolls_lost']} | Tied: {tied_count} | Total Played: {stats['rolls_played']}"
    )

    # Fetch last 10 roll results
    history = await bot.database.game_db.get_roll_history(user_id)

    if history:
        history_lines = []
        for entry in history:
            emoji = (
                "✅"
                if entry["result"] == "win"
                else "❌" if entry["result"] == "loss" else "➖"
            )

            # Parse SQLite timestamp (stored in UTC)
            dt = datetime.fromisoformat(entry["timestamp"]).replace(tzinfo=timezone.utc)
            unix_timestamp = int(dt.timestamp())

            history_lines.append(
                f"{emoji} Bet: ${entry['amount']:,} — <t:{unix_timestamp}:R>"
            )

        embed.add_field(
            name="Last 10 Rolls", value="\n".join(history_lines), inline=False
        )

    view = RollAgainView(bot, user_id, None if action else amount, action)
    view.message = await interaction.edit_original_response(embed=embed, view=view)


class RollAgainView(discord.ui.View):
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

    @discord.ui.button(label="Roll Again", style=discord.ButtonStyle.green)
    async def roll_again(
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

        await perform_roll(self.bot, interaction, self.user_id, amount, self.action)


async def setup(bot):
    await bot.add_cog(Roll(bot))
