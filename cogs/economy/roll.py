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
        """
        Command to roll a dice against the dealer.

        :param interaction: The interaction object from Discord.
        """
        if not amount and not action:
            await interaction.response.send_message(
                "Please specify an amount and an action (all, half, 25%).",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        balance = await self.bot.database.user_db.get_balance(interaction.user.id)
        game_stats = await self.bot.database.game_db.get_user_game_stats(
            interaction.user.id
        )

        if balance < amount:
            await interaction.followup.send(
                "You don't have enough balance to roll this amount.", ephemeral=True
            )
            return
        if amount <= 0:
            await interaction.followup.send("Amount must be positive.", ephemeral=True)
            return

        # Roll the dice
        user_roll = random.randint(0, 100)
        dealer_roll = random.randint(0, 100)

        # Determine the result
        if user_roll > dealer_roll:
            result = "You win!"
            color = discord.Color.green()
            balance += amount
            await self.bot.database.game_db.set_user_game_stats(
                interaction.user.id, GameEventType.GAMBLE, True, amount
            )

        elif user_roll < dealer_roll:
            result = "You lose!"
            color = discord.Color.red()
            balance -= amount
            await self.bot.database.game_db.set_user_game_stats(
                interaction.user.id, GameEventType.GAMBLE, False, amount
            )

        else:
            result = "It's a tie!"
            color = discord.Color.gold()

        await self.bot.database.user_db.set_balance(interaction.user.id, balance)
        # Create the embed
        embed = discord.Embed(
            title="Dice Roll Result",
            description=f"You rolled: {user_roll}\nDealer rolled: {dealer_roll}\n**{result}**",
            color=color,
        )

        # Send the embed
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Roll(bot))
