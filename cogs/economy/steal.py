import discord
import random
import datetime
from discord import app_commands
from discord.ext import commands
from constants.steal_config import StealEventType
from utils.formatting import format_number
from utils.cooldown import get_cooldown_response


class Steal(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="steal", description="Steal from another user")
    async def steal(self, interaction: discord.Interaction, user: discord.User):
        if user == interaction.user:
            await interaction.response.send_message(
                "You cannot steal from yourself.", ephemeral=True
            )
            return

        target_id = user.id
        thief_id = interaction.user.id

        STEAL_COOLDOWN = datetime.timedelta(hours=1)
        STOLEN_FROM_COOLDOWN = datetime.timedelta(hours=6)
        MIN_BALANCE_TO_STEAL = 100_000
        STEAL_SUCCESS_RATE = 0.5
        STEAL_AMOUNT_RANGE = (0.1, 0.2)

        # Fetch balances and stats
        target_balance = await self.bot.database.user_db.get_balance(target_id)
        thief_balance = await self.bot.database.user_db.get_balance(thief_id)

        if target_balance <= MIN_BALANCE_TO_STEAL:
            await interaction.response.send_message(
                f"{user.mention} has no money to steal!", ephemeral=True
            )
            return

        if thief_balance <= MIN_BALANCE_TO_STEAL:
            await interaction.response.send_message(
                "You have no money to steal!", ephemeral=True
            )
            return

        target_stats = dict(
            (await self.bot.database.steal_db.get_user_steal_stats(target_id))[
                "steal_stats"
            ]
        )
        thief_stats = dict(
            (await self.bot.database.steal_db.get_user_steal_stats(thief_id))[
                "steal_stats"
            ]
        )

        last_stolen_from_at = target_stats.get("last_stolen_from_at")
        last_stole_from_other_at = thief_stats.get("last_stole_from_other_at")

        if last_stolen_from_at:
            msg = get_cooldown_response(
                last_stolen_from_at,
                STOLEN_FROM_COOLDOWN,
                f"{user.mention} was stolen from recently.",
            )
            if msg:
                await interaction.response.send_message(msg, ephemeral=True)
                return

        if last_stole_from_other_at:
            msg = get_cooldown_response(
                last_stole_from_other_at, STEAL_COOLDOWN, "You just tried stealing!"
            )
            if msg:
                await interaction.response.send_message(msg, ephemeral=True)
                return

        success = random.random() < STEAL_SUCCESS_RATE

        if success:
            stolen_amount = int(target_balance * random.uniform(*STEAL_AMOUNT_RANGE))
            stolen_amount = min(stolen_amount, target_balance)

            await self.bot.database.user_db.set_balance(
                thief_id, thief_balance + stolen_amount
            )
            await self.bot.database.user_db.set_balance(
                target_id, target_balance - stolen_amount
            )

            await self.bot.database.steal_db.set_user_steal_stats(
                thief_id, stolen_amount, StealEventType.STEAL_SUCCESS
            )
            await self.bot.database.steal_db.set_user_steal_stats(
                target_id, stolen_amount, StealEventType.VICTIM_SUCCESS
            )

            embed = discord.Embed(
                title="💰 Theft Success!",
                description=f"You stole **${format_number(stolen_amount)}** from {user.mention}!",
                color=discord.Color.green(),
            )
        else:
            lost_amount = int(thief_balance * random.uniform(*STEAL_AMOUNT_RANGE))
            lost_amount = min(lost_amount, thief_balance)

            await self.bot.database.user_db.set_balance(
                thief_id, thief_balance - lost_amount
            )

            await self.bot.database.steal_db.set_user_steal_stats(
                thief_id, lost_amount, StealEventType.STEAL_FAIL
            )
            await self.bot.database.steal_db.set_user_steal_stats(
                target_id, lost_amount, StealEventType.VICTIM_FAIL
            )

            embed = discord.Embed(
                title="🚨 Theft Failed!",
                description=f"You tried to steal from {user.mention} and got caught! You lost **${format_number(lost_amount)}**.",
                color=discord.Color.red(),
            )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Steal(bot))
