import datetime
from datetime import timezone

import discord
from discord import app_commands
from discord.ext import commands
from utils.formatting import format_number


class Daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="daily", description="Claim your daily reward.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def daily(self, interaction: discord.Interaction) -> None:
        user = interaction.user
        daily_streak, last_daily_at = await self.bot.database.user_db.get_daily(user.id)
        daily_amount = 1000

        reset_streak = False
        now = datetime.datetime.now(timezone.utc)

        if last_daily_at:
            last_time = datetime.datetime.strptime(
                last_daily_at, "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
            days_passed = (now - last_time).days

            if now.date() == last_time.date():
                tomorrow = (now + datetime.timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                time_until_tomorrow = int(tomorrow.timestamp())
                # msg = get_cooldown_response(
                #     last_daily_at, time_until_tomorrow, "Daily cooldown:"
                # )
                # if msg:
                #     await interaction.response.send_message(msg)
                #     return
                msg = (
                    f"🕒 You’ve already claimed your daily! Come back <t:{time_until_tomorrow}:R> "
                    f"(at <t:{time_until_tomorrow}:t> your time)."
                )
                await interaction.response.send_message(msg)
                return
            elif days_passed >= 2:
                reset_streak = True
                daily_streak = 0

        # Calculate reward
        bonus = 0 if daily_streak == 0 else daily_amount * (2 ** (daily_streak - 1))
        bonus = min(bonus, 1_000_000)
        total_reward = daily_amount + bonus

        # Update DB
        # await self.bot.database.user_db.set_balance(user.id, balance + total_reward)
        new_balance = await self.bot.database.user_db.increment_balance(
            user.id, total_reward
        )
        if reset_streak:
            await self.bot.database.user_db.set_daily(user.id, daily_streak=1)
        else:
            await self.bot.database.user_db.set_daily(user.id)

        embed = discord.Embed(
            title="Daily Reward",
            description=f"Claimed your daily reward of ${format_number(total_reward)}!"
            f"\nDaily: ${format_number(daily_amount)}"
            f"\nBonus: ${format_number(bonus)}"
            f"\nStreak: {daily_streak + 1} day(s)"
            f"\nYour new balance is ${format_number(new_balance)}.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Daily(bot))
