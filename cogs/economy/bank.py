import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from utils.formatting import format_number


class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def build_bank_embed(
        self, user: discord.User, bank_stats: dict, bank_balance: int
    ) -> discord.Embed:
        return discord.Embed(
            title=f"{user.name}'s Bank Balance",
            description=(
                f"🏦 Bank Balance: ${format_number(bank_balance)}\n"
                f"🏦 Bank Capacity: ${format_number(bank_stats['bank_cap'])}\n"
                f"🏦 Bank Level: {bank_stats['bank_level']}"
            ),
            color=discord.Color.blue(),
        )

    def build_transaction_embed(
        self, action: str, amount: int, new_bank: int, new_wallet: int
    ) -> discord.Embed:
        return discord.Embed(
            title=f"{action} Successful",
            description=(
                f"{action}ed ${format_number(amount)}.\n"
                f"🏦 Bank: ${format_number(new_bank)}\n"
                f"💰 Wallet: ${format_number(new_wallet)}"
            ),
            color=discord.Color.green(),
        )

    async def get_user_stats(self, user_id: int) -> tuple[int, dict]:
        balance = await self.bot.database.user_db.get_balance(user_id)
        bank_raw = await self.bot.database.bank_db.get_user_bank_stats(user_id)
        bank_stats = dict(bank_raw["bank_stats"])
        return balance, bank_stats

    @app_commands.command(name="bankbalance", description="Check your bank balance.")
    async def bank_balance(
        self, interaction: discord.Interaction, user: Optional[discord.User] = None
    ) -> None:
        user = user or interaction.user
        bank_balance = await self.bot.database.bank_db.get_bank_balance(user.id)
        _, bank_stats = await self.get_user_stats(user.id)

        embed = self.build_bank_embed(user, bank_stats, bank_balance)
        await interaction.response.send_message(
            embed=embed, ephemeral=(user == interaction.user)
        )

    @app_commands.command(name="deposit", description="Deposit money into your bank.")
    @app_commands.describe(
        amount="Amount to deposit (choose one option or specify your own amount)",
        action="Deposit option (all, half, 25%)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="All", value="all"),
            app_commands.Choice(name="Half", value="half"),
            app_commands.Choice(name="25%", value="25%"),
        ]
    )
    async def deposit(
        self,
        interaction: discord.Interaction,
        amount: Optional[app_commands.Range[int, 1, None]] = None,
        action: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        user = interaction.user
        balance, bank_stats = await self.get_user_stats(user.id)
        available_space = bank_stats["bank_cap"] - bank_stats["bank_balance"]

        if balance <= 0:
            await interaction.response.send_message(
                "You have no money to deposit.", ephemeral=True
            )
            return

        if not action and not amount:
            await interaction.response.send_message(
                "You must specify an amount or choose a deposit option.", ephemeral=True
            )
            return

        # Determine amount to deposit
        if action:
            percent_map = {"all": 1, "half": 0.5, "25%": 0.25}
            amount_to_deposit = int(balance * percent_map.get(action.value, 0))
        else:
            if amount > balance:
                await interaction.response.send_message(
                    f"You cannot deposit more than your current balance (${format_number(balance)}).",
                    ephemeral=True,
                )
                return
            amount_to_deposit = amount

        # Ensure it fits in the bank
        if amount_to_deposit > available_space:
            amount_to_deposit = available_space

        if amount_to_deposit <= 0:
            await interaction.response.send_message(
                f"You cannot deposit more than your bank capacity.\nCurrent Bank Balance: ${format_number(bank_stats['bank_balance'])}.\nCurrent Bank Cap: ${format_number(bank_stats['bank_balance'])}",
                ephemeral=True,
            )
            return

        # Update DB
        await self.bot.database.user_db.set_balance(
            user.id, balance - amount_to_deposit
        )
        await self.bot.database.bank_db.set_bank_balance(
            user.id, bank_stats["bank_balance"] + amount_to_deposit
        )

        embed = self.build_transaction_embed(
            action="Deposit",
            amount=amount_to_deposit,
            new_bank=bank_stats["bank_balance"] + amount_to_deposit,
            new_wallet=balance - amount_to_deposit,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="withdraw", description="Withdraw money from your bank.")
    @app_commands.describe(
        amount="Amount to withdraw (choose one option or specify your own amount)",
        action="Withdrawal option (all, half, 25%)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="All", value="all"),
            app_commands.Choice(name="Half", value="half"),
            app_commands.Choice(name="25%", value="25%"),
        ]
    )
    async def withdraw(
        self,
        interaction: discord.Interaction,
        amount: Optional[app_commands.Range[int, 1, None]] = None,
        action: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        user = interaction.user
        balance, bank_stats = await self.get_user_stats(user.id)
        bank_balance = bank_stats["bank_balance"]

        if bank_balance <= 0:
            await interaction.response.send_message(
                "You have no money in your bank to withdraw.", ephemeral=True
            )
            return

        if not action and not amount:
            await interaction.response.send_message(
                "You must specify an amount or choose a withdrawal option.",
                ephemeral=True,
            )
            return

        # Determine amount to withdraw
        if action:
            percent_map = {"all": 1, "half": 0.5, "25%": 0.25}
            amount_to_withdraw = int(bank_balance * percent_map.get(action.value, 0))
        else:
            if amount > bank_balance:
                await interaction.response.send_message(
                    f"You cannot withdraw more than your bank balance (${format_number(bank_balance)}).",
                    ephemeral=True,
                )
                return
            amount_to_withdraw = amount

        if amount_to_withdraw <= 0:
            await interaction.response.send_message(
                "Withdrawal amount must be greater than zero.", ephemeral=True
            )
            return

        # Update DB
        await self.bot.database.bank_db.set_bank_balance(
            user.id, bank_balance - amount_to_withdraw
        )
        await self.bot.database.user_db.set_balance(
            user.id, balance + amount_to_withdraw
        )

        embed = self.build_transaction_embed(
            action="Withdrawal",
            amount=amount_to_withdraw,
            new_bank=bank_balance - amount_to_withdraw,
            new_wallet=balance + amount_to_withdraw,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Bank(bot))
