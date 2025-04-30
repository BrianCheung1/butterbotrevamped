import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from discord.app_commands import Range


class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bankbalance", description="Check your bank balance.")
    async def bank_balance(
        self, interaction: discord.Interaction, user: Optional[discord.User] = None
    ) -> None:
        """
        This command checks the bank balance of a user. If no user is specified, it checks the balance of the command invoker.

        :param interaction: The interaction object from Discord.
        :param user: The user whose bank balance to check. If None, defaults to the command invoker.
        """
        user = user or interaction.user
        bank_balance = await self.bot.database.bank_db.get_bank_balance(user.id)

        embed = discord.Embed(
            title=f"{user.name}'s Bank Balance",
            description=f"🏦 {bank_balance} coins",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="deposit", description="Deposit money into your bank.")
    async def deposit(
        self, interaction: discord.Interaction, amount: Range[int, 1, None]
    ) -> None:
        """
        This command deposits money into the user's bank account.
        """
        user = interaction.user
        balance = await self.bot.database.user_db.get_balance(user.id)
        bank_balance = await self.bot.database.bank_db.get_bank_balance(user.id)

        if balance <= 0:
            await interaction.response.send_message(
                "You have no money to deposit.", ephemeral=True
            )
            return

        await self.bot.database.bank_db.set_bank_balance(user.id, bank_balance + amount)
        await self.bot.database.user_db.set_balance(user.id, balance - amount)

        embed = discord.Embed(
            title="Deposit Successful",
            description=f"Deposited {amount} coins into your bank.\nCurrent bank balance: {bank_balance + amount} coins.\nCurrent balance: {balance - amount} coins.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="withdraw", description="Withdraw money from your bank.")
    async def withdraw(
        self, interaction: discord.Interaction, amount: Range[int, 1, None]
    ) -> None:
        """
        This command withdraws money from the user's bank account.
        """
        user = interaction.user
        balance = await self.bot.database.user_db.get_balance(user.id)
        bank_balance = await self.bot.database.bank_db.get_bank_balance(user.id)

        if bank_balance <= 0:
            await interaction.response.send_message(
                "You have no money in your bank to withdraw.", ephemeral=True
            )
            return
        if bank_balance < amount:
            await interaction.response.send_message(
                "You don't have enough coins in your bank to withdraw this amount.",
                ephemeral=True,
            )
            return

        await self.bot.database.bank_db.set_bank_balance(user.id, bank_balance - amount)
        await self.bot.database.user_db.set_balance(user.id, balance + amount)

        embed = discord.Embed(
            title="Withdrawal Successful",
            description=f"Withdrew {amount} coins from your bank.\nCurrent bank balance: {bank_balance - amount} coins.\nCurrent balance: {balance + amount} coins.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Bank(bot))
