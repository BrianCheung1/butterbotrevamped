from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.formatting import format_number


class Give(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="give", description="Give another player money")
    @app_commands.describe(amount="The amount to give")
    async def give(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: app_commands.Range[int, 1, None],
    ):
        await interaction.response.defer()
        user_id = interaction.user.id
        target_id = user.id
        if user_id in self.bot.active_blackjack_players:
            await interaction.followup.send(
                "You are in a Blackjack game! Please finish the game first",
            )
            return
        if interaction.user.id == target_id:
            await interaction.followup.send("You can't give money to yourself!")
            return
        if user.bot:
            await interaction.followup.send("You can't give money to bots!")
            return

        balance = await self.bot.database.user_db.get_balance(user_id)
        error = validate_amount(amount, balance)
        if error:
            await interaction.edit_original_response(content=error)
            return
        # Deduct the amount from the giver's balance
        await self.bot.database.user_db.increment_balance(user_id, -amount)

        # Add the amount to the recipient's balance
        await self.bot.database.user_db.increment_balance(target_id, amount)

        # Send confirmation
        await interaction.followup.send(
            f"You've successfully given ${format_number(amount)} to {user.mention}!"
        )


def validate_amount(amount: Optional[int], balance: int) -> Optional[str]:
    if amount is None or amount <= 0:
        return "Invalid amount"
    if amount > balance:
        return f"You don't have enough balance to give this amount. Current balance is ${format_number(balance)}."
    return None


async def setup(bot):
    await bot.add_cog(Give(bot))
