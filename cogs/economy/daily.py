import discord
from discord import app_commands
from discord.ext import commands
from utils.formatting import format_number
import datetime
from datetime import timezone
from utils.cooldown import get_cooldown_response


class Daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="daily", description="Claim your daily reward.")
    async def daily(self, interaction: discord.Interaction) -> None:
        """
        This command allows users to claim their daily reward. If no user is specified, it defaults to the command invoker.

        :param interaction: The interaction object from Discord.
        """
        user = interaction.user
        balance = await self.bot.database.user_db.get_balance(user.id)
        daily_streak, last_daily_at = await self.bot.database.user_db.get_daily(user.id)
        daily_amount = 1000
        bonus = 0 if daily_streak == 0 else daily_amount * (2 ** (daily_streak - 1))
        bonus = min(bonus, 250000)  # Cap bonus at 1 million
        total_reward = daily_amount + bonus
        if last_daily_at:
            msg = get_cooldown_response(
                last_daily_at, datetime.timedelta(days=0), "Daily cooldown: "
            )
            if msg:
                await interaction.response.send_message(msg)
                return
        await self.bot.database.user_db.set_balance(user.id, balance + total_reward)
        await self.bot.database.user_db.set_daily(user.id)
        embed = discord.Embed(
            title="Daily Reward",
            description=f"Claimed your daily reward of ${format_number(daily_amount + bonus)}! "
            f"\nDaily: ${format_number(daily_amount)}"
            f"\nBonus: ${format_number(bonus)}"
            f"\nStreak: {daily_streak + 1} day(s)"
            f"\nYour new balance is ${format_number(balance + total_reward)}.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Daily(bot))
