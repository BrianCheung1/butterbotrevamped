import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.balance_helper import calculate_percentage_amount, validate_amount
from utils.channels import broadcast_embed_to_guilds
from utils.formatting import format_number


class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.hours = 0
        self.hourly_interest_task.start()

    def cog_unload(self):
        self.hourly_interest_task.cancel()

    async def wait_until_next_hour(self):
        now = datetime.utcnow()
        next_hour = (now + timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0
        )
        wait_seconds = (next_hour - now).total_seconds()
        return wait_seconds

    @tasks.loop(hours=1)
    async def hourly_interest_task(self):
        await self.bot.wait_until_ready()
        self.hours += 1

        user_ids = await self.bot.database.bank_db.get_all_bank_users()
        interest_rate = 0.001
        user_count = 0

        for user_id in user_ids:
            user = await self.bot.fetch_user(user_id)
            if user is None:
                self.bot.logger.warning(f"User with ID {user_id} not found.")
                continue

            bank_stats_raw = await self.bot.database.bank_db.get_user_bank_stats(
                user_id
            )
            bank_stats = dict(bank_stats_raw["bank_stats"])
            bank_balance = bank_stats["bank_balance"]

            if bank_balance <= 0:
                continue

            interest = int(bank_balance * interest_rate)
            if interest == 0:
                continue

            new_balance = bank_balance + interest
            await self.bot.database.bank_db.set_bank_balance(user_id, new_balance)
            user_count += 1

        # 🔽 Send announcement if bank channel is set
        if self.hours % 24 == 0:
            embed = discord.Embed(
                title="💸 Interest has been applied to all active bank accounts!",
                description=f"A total of {user_count} users have received their interest for the day.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc),
            )
            await broadcast_embed_to_guilds(self.bot, "interest_channel_id", embed)
        else:
            self.bot.logger.info(
                f"💸 Interest has been applied to all active bank accounts! ({user_count} users updated)"
            )

    @hourly_interest_task.before_loop
    async def before_interest_task(self):
        wait_seconds = await self.wait_until_next_hour()
        time_left = str(
            timedelta(seconds=wait_seconds)
        )  # Convert to a readable time format
        self.bot.logger.info(f"Next interest update in {time_left}")
        await asyncio.sleep(wait_seconds)

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

    @app_commands.command(name="bank-balance", description="Check your bank balance.")
    async def bank_balance(
        self, interaction: discord.Interaction, user: Optional[discord.User] = None
    ) -> None:
        user = user or interaction.user
        bank_balance = await self.bot.database.bank_db.get_bank_balance(user.id)
        _, bank_stats = await self.get_user_stats(user.id)

        embed = self.build_bank_embed(user, bank_stats, bank_balance)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="deposit", description="Deposit money into your bank.")
    @app_commands.describe(
        amount="Amount to deposit (choose one option or specify your own amount)",
        action="Deposit option (all, half, 25%)",
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
    async def deposit(
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
                content="You must specify an amount or choose a deposit option.",
            )
            return

        if amount and action:
            await interaction.edit_original_response(
                content="You can only choose one option: amount or action."
            )
            return
        balance, bank_stats = await self.get_user_stats(user_id)
        available_space = bank_stats["bank_cap"] - bank_stats["bank_balance"]

        if action and not amount:
            amount_to_deposit = calculate_percentage_amount(balance, action.value)
        elif amount and not action:
            amount_to_deposit = amount

        error = validate_amount(amount_to_deposit, balance)
        if error:
            await interaction.edit_original_response(content=error)
            return

        # Ensure it fits in the bank
        if amount_to_deposit > available_space:
            amount_to_deposit = available_space

        if amount_to_deposit <= 0:
            await interaction.edit_original_response(
                content=f"You cannot deposit more than your bank capacity.\nCurrent Bank Balance: ${format_number(bank_stats['bank_balance'])}.\nCurrent Bank Cap: ${format_number(bank_stats['bank_cap'])}",
            )
            return

        # Update DB
        # await self.bot.database.user_db.set_balance(
        #     user_id, balance - amount_to_deposit
        # )
        await self.bot.database.user_db.increment_balance(user_id, -amount_to_deposit)
        await self.bot.database.bank_db.set_bank_balance(
            user_id, bank_stats["bank_balance"] + amount_to_deposit
        )

        embed = self.build_transaction_embed(
            action="Deposit",
            amount=amount_to_deposit,
            new_bank=bank_stats["bank_balance"] + amount_to_deposit,
            new_wallet=balance - amount_to_deposit,
        )
        await interaction.edit_original_response(embed=embed)

    @app_commands.command(name="withdraw", description="Withdraw money from your bank.")
    @app_commands.describe(
        amount="Amount to withdraw (choose one option or specify your own amount)",
        action="Withdrawal option (all, half, 25%)",
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
    async def withdraw(
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
        balance, bank_stats = await self.get_user_stats(user_id)
        bank_balance = bank_stats["bank_balance"]
        if not action and not amount:
            await interaction.edit_original_response(
                content="You must specify an amount or choose a withdraw option.",
            )
            return

        if amount and action:
            await interaction.edit_original_response(
                content="You can only choose one option: amount or action."
            )
            return

        if action and not amount:
            amount_to_withdraw = calculate_percentage_amount(bank_balance, action.value)
        elif amount and not action:
            amount_to_withdraw = amount
        error = validate_amount(amount_to_withdraw, bank_balance)
        if error:
            await interaction.edit_original_response(content=error)
            return

        # Update DB
        await self.bot.database.bank_db.set_bank_balance(
            user_id, bank_balance - amount_to_withdraw
        )
        # await self.bot.database.user_db.set_balance(
        #     user_id, balance + amount_to_withdraw
        # )
        await self.bot.database.user_db.increment_balance(user_id, amount_to_withdraw)

        embed = self.build_transaction_embed(
            action="Withdrawal",
            amount=amount_to_withdraw,
            new_bank=bank_balance - amount_to_withdraw,
            new_wallet=balance + amount_to_withdraw,
        )
        await interaction.edit_original_response(embed=embed)


async def setup(bot):
    await bot.add_cog(Bank(bot))
