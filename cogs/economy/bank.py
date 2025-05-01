import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from utils.formatting import format_number


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
        raw_bank_stats = await self.bot.database.bank_db.get_user_bank_stats(user.id)
        bank_stats = dict(raw_bank_stats["bank_stats"])
        embed = discord.Embed(
            title=f"{user.name}'s Bank Balance",
            description=f"🏦 Bank Balance ${format_number(bank_balance)}\n"
            f"🏦 Bank Capacity: ${format_number(bank_stats['bank_cap'])}\n"
            f"🏦 Bank Level: {bank_stats['bank_level']}\n",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed)

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
        """
        Deposits money into the user's bank account.
        """
        user = interaction.user
        balance = await self.bot.database.user_db.get_balance(user.id)
        raw_bank_stats = await self.bot.database.bank_db.get_user_bank_stats(user.id)
        bank_stats = dict(raw_bank_stats["bank_stats"])

        if balance <= 0:
            await interaction.response.send_message(
                "You have no money to deposit.", ephemeral=True
            )
            return

        if not action and not amount:
            await interaction.response.send_message(
                "You must specify an amount or choose a deposit option.",
                ephemeral=True,
            )
            return

        # Determine amount to deposit
        if action:
            if action.value == "all":
                amount_to_deposit = balance
            elif action.value == "half":
                amount_to_deposit = balance // 2
            elif action.value == "25%":
                amount_to_deposit = balance // 4
            else:
                await interaction.response.send_message(
                    "Invalid deposit option selected.", ephemeral=True
                )
                return
            if amount_to_deposit > bank_stats["bank_cap"]:
                amount_to_deposit = bank_stats["bank_cap"] - bank_stats["bank_balance"]
        else:
            if amount > balance:
                await interaction.response.send_message(
                    f"You cannot deposit more than your current balance. Balance: ${format_number(balance)}",
                    ephemeral=True,
                )
                return
            if (
                amount > bank_stats["bank_cap"]
                or amount + bank_stats["bank_balance"] > bank_stats["bank_cap"]
            ):
                await interaction.response.send_message(
                    f"You cannot deposit more than your bank capacity.\nBank Balance: ${format_number(bank_stats["bank_balance"])}\nBank Capacity: ${format_number(bank_stats['bank_cap'])}",
                    ephemeral=True,
                )
                return

            amount_to_deposit = amount

        # Update balances
        await self.bot.database.bank_db.set_bank_balance(
            user.id, bank_stats["bank_balance"] + amount_to_deposit
        )
        await self.bot.database.user_db.set_balance(
            user.id, balance - amount_to_deposit
        )

        embed = discord.Embed(
            title="Deposit Successful",
            description=(
                f"Deposited ${format_number(amount_to_deposit)} into your bank.\n"
                f"🏦 Bank: ${format_number(bank_stats["bank_balance"] + amount_to_deposit)}\n"
                f"💰 Wallet: ${format_number(balance - amount_to_deposit)}"
            ),
            color=discord.Color.green(),
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
        """
        Withdraws money from the user's bank account.
        """
        user = interaction.user
        balance = await self.bot.database.user_db.get_balance(user.id)
        raw_bank_stats = await self.bot.database.bank_db.get_user_bank_stats(user.id)
        bank_stats = dict(raw_bank_stats["bank_stats"])

        if bank_stats["bank_balance"] <= 0:
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
            if action.value == "all":
                amount_to_withdraw = bank_stats["bank_balance"]
            elif action.value == "half":
                amount_to_withdraw = bank_stats["bank_balance"] // 2
            elif action.value == "25%":
                amount_to_withdraw = bank_stats["bank_balance"] // 4
            else:
                await interaction.response.send_message(
                    "Invalid withdrawal option selected.", ephemeral=True
                )
                return
        else:
            if amount > bank_stats["bank_balance"]:
                await interaction.response.send_message(
                    f"You cannot withdraw more than your bank balance.\nBank Balance: ${format_number(bank_balance)}",
                    ephemeral=True,
                )
                return
            amount_to_withdraw = amount

        # Perform the transaction
        await self.bot.database.bank_db.set_bank_balance(
            user.id, bank_stats["bank_balance"] - amount_to_withdraw
        )
        await self.bot.database.user_db.set_balance(
            user.id, balance + amount_to_withdraw
        )

        # Confirmation embed
        embed = discord.Embed(
            title="Withdrawal Successful",
            description=(
                f"Withdrew ${format_number(amount_to_withdraw)} from your bank.\n"
                f"🏦 Bank: ${format_number(bank_stats["bank_balance"] - amount_to_withdraw)}\n"
                f"💰 Wallet: ${format_number(balance + amount_to_withdraw)}"
            ),
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Bank(bot))
