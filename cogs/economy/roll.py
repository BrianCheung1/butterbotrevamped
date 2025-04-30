import discord
import random
from discord import app_commands
from discord.ext import commands
from typing import Optional
from constants.game_config import GameEventType


class Roll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="roll", description="Roll a dice against the dealer")
    async def roll(
        self,
        interaction: discord.Interaction,
        amount: Optional[app_commands.Range[int, 1, None]] = None,
        action: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        if not amount and not action:
            await interaction.response.send_message(
                "Please specify an amount and an action (all, half, 25%).",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        user_id = interaction.user.id
        balance = await self.bot.database.user_db.get_balance(user_id)
        prev_balance = balance

        if balance < amount:
            await interaction.followup.send(
                "You don't have enough balance to roll this amount.", ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.followup.send("Amount must be positive.", ephemeral=True)
            return

        # Fetch current stats and convert to mutable dict
        stats = dict(
            (await self.bot.database.game_db.get_user_game_stats(user_id))["game_stats"]
        )

        # Dice roll
        user_roll = random.randint(0, 100)
        dealer_roll = random.randint(0, 100)

        # Handle game outcome
        if user_roll > dealer_roll:
            result = "You win!"
            color = discord.Color.green()
            balance += amount
            await self.bot.database.game_db.set_user_game_stats(
                user_id, GameEventType.GAMBLE, True, amount
            )
            stats["gambles_won"] += 1
        elif user_roll < dealer_roll:
            result = "You lose!"
            color = discord.Color.red()
            balance -= amount
            await self.bot.database.game_db.set_user_game_stats(
                user_id, GameEventType.GAMBLE, False, amount
            )
            stats["gambles_lost"] += 1
        else:
            result = "It's a tie!"
            color = discord.Color.gold()
            # Optionally: track ties separately in DB

        stats["gambles_played"] += 1
        await self.bot.database.user_db.set_balance(user_id, balance)

        # Create embed
        embed = discord.Embed(
            title="Dice Roll Result",
            description=f"You rolled: {user_roll}\nDealer rolled: {dealer_roll}\n**{result}**",
            color=color,
        )
        embed.add_field(
            name="Prev Balance", value=f"**{prev_balance}** coins", inline=True
        )
        embed.add_field(
            name="Current Balance", value=f"**{balance}** coins", inline=True
        )

        tied_count = (
            stats["gambles_played"] - stats["gambles_won"] - stats["gambles_lost"]
        )
        embed.set_footer(
            text=f"Gambles Won: {stats['gambles_won']} | Lost: {stats['gambles_lost']} | Tied: {tied_count}"
        )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Roll(bot))
