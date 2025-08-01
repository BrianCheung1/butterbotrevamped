import datetime
from datetime import timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.formatting import format_number


class Daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminded_users = set()
        self.streak_reset_loop.start()
        self.streak_reminder_loop.start()

    def cog_unload(self):
        # Cancel loops cleanly when cog unloads
        self.streak_reset_loop.cancel()
        self.streak_reminder_loop.cancel()

    @app_commands.command(name="daily", description="Claim your daily reward.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def daily(self, interaction: discord.Interaction) -> None:
        user = interaction.user
        daily_streak, last_daily_at_str = await self.bot.database.user_db.get_daily(
            user.id
        )
        daily_base_amount = 1000
        now = datetime.datetime.now(timezone.utc)

        reset_streak = False

        if last_daily_at_str:
            last_claim_time = datetime.datetime.strptime(
                last_daily_at_str, "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)

            days_since_last_claim = (now.date() - last_claim_time.date()).days

            if days_since_last_claim == 0:
                next_reset = (now + datetime.timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                time_until_reset = int(next_reset.timestamp())

                msg = (
                    f"🕒 You’ve already claimed your daily today! "
                    f"Come back <t:{time_until_reset}:R> (at <t:{time_until_reset}:t> your time)."
                )
                await interaction.response.send_message(msg)
                return
            elif days_since_last_claim >= 3:
                reset_streak = True
                daily_streak = 0

        # Calculate bonus
        if daily_streak == 0:
            bonus = 0
        else:
            bonus = daily_base_amount * (2 ** (daily_streak - 1))
        bonus = min(bonus, 1_000_000)

        total_reward = daily_base_amount + bonus

        # Update balance
        new_balance = await self.bot.database.user_db.increment_balance(
            user.id, total_reward
        )

        # Update streak & last claim time
        if reset_streak:
            await self.bot.database.user_db.set_daily(user.id, daily_streak=1)
            current_streak = 1
        else:
            await self.bot.database.user_db.set_daily(user.id)
            current_streak = daily_streak + 1

        embed = discord.Embed(
            title="Daily Reward",
            description=(
                f"Claimed your daily reward of ${format_number(total_reward)}!\n"
                f"Daily base: ${format_number(daily_base_amount)}\n"
                f"Bonus: ${format_number(bonus)}\n"
                f"Streak: {current_streak} day(s)\n"
                f"Your new balance is ${format_number(new_balance)}."
            ),
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    async def reset_streaks(self):
        """Cleanup logic to reset streaks for users who missed claiming 2+ days."""
        now = datetime.datetime.now(timezone.utc)
        users_data = await self.bot.database.user_db.get_all_daily_users()
        self.bot.logger.info("[Daily] Starting streak reset cleanup...")

        for user_id, daily_streak, last_daily_at_str, _ in users_data:
            if not last_daily_at_str or daily_streak == 0:
                continue

            last_claim_time = datetime.datetime.strptime(
                last_daily_at_str, "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
            days_since_last_claim = (now.date() - last_claim_time.date()).days

            if days_since_last_claim >= 3:
                await self.bot.database.user_db.set_daily(user_id, daily_streak=0)

                try:
                    user = self.bot.get_user(user_id)
                    if not user:
                        user = await self.bot.fetch_user(user_id)

                    self.bot.logger.info(
                        f"Reset daily streak for {user.name} ({user.id}), last claimed {last_daily_at_str}"
                    )
                except Exception as e:
                    self.bot.logger.error(
                        f"Error fetching user {user_id} for logging: {e}"
                    )

    @tasks.loop(hours=24)
    async def streak_reset_loop(self):
        await self.reset_streaks()

    @tasks.loop(hours=6)
    async def streak_reminder_loop(self):
        """Remind users 1 day before their streak breaks. Remind once per day."""
        now = datetime.datetime.now(timezone.utc).date()
        users_data = await self.bot.database.user_db.get_all_daily_users()

        # Reset reminded users set daily
        if not hasattr(self, "_last_reminder_day") or self._last_reminder_day != now:
            self.reminded_users.clear()
            self._last_reminder_day = now

        for user_id, daily_streak, last_daily_at_str, reminder_date_str in users_data:
            if not last_daily_at_str or daily_streak == 0:
                continue

            last_claim_time = datetime.datetime.strptime(
                last_daily_at_str, "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
            days_since_last_claim = (now - last_claim_time.date()).days

            if days_since_last_claim == 2 and user_id not in self.reminded_users:
                if reminder_date_str == now.isoformat():
                    continue

                try:
                    user = self.bot.get_user(user_id)
                    if not user:
                        user = await self.bot.fetch_user(user_id)

                    await user.send(
                        f"⏰ Hey! Your daily streak of {daily_streak} day(s) is about to break. "
                        f"Don't forget to claim your daily reward before midnight UTC to keep your streak going!"
                    )

                    self.reminded_users.add(user_id)
                    await self.bot.database.user_db.set_daily_reminder_date(
                        user_id, now.isoformat()
                    )
                    self.bot.logger.info(
                        f"Sent daily streak reminder to {user.name} ({user.id})"
                    )

                except discord.Forbidden:
                    self.bot.logger.warning(
                        f"Cannot DM user {user_id}; DMs might be closed."
                    )
                except Exception as e:
                    self.bot.logger.error(f"Error sending DM to user {user_id}: {e}")


async def setup(bot):
    await bot.add_cog(Daily(bot))
