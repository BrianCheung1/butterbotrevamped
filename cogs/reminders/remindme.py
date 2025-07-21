import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands


def parse_duration(time_str: str) -> timedelta | None:
    pattern = r"(\d+)\s*(mo|[smhd])"
    matches = re.findall(pattern, time_str.lower())
    if not matches:
        return None

    total = timedelta()
    for value, unit in matches:
        value = int(value)
        if unit == "s":
            total += timedelta(seconds=value)
        elif unit == "m":
            total += timedelta(minutes=value)
        elif unit == "h":
            total += timedelta(hours=value)
        elif unit == "d":
            total += timedelta(days=value)
        elif unit == "mo":
            total += timedelta(days=value * 30)  # approximate month as 30 days

    if total < timedelta(minutes=1):
        return None

    return total


class Reminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="remindme", description="Set a reminder with a time and note"
    )
    @app_commands.describe(
        time="Duration format: combine units like '1m 1s', '2h 30m', or '1d 1m'. Units: s (seconds), m (minutes), h (hours), d (days), mo (months)"
    )
    async def remindme(self, interaction: discord.Interaction, time: str, note: str):
        duration = parse_duration(time)
        if not duration:
            return await interaction.response.send_message(
                "❌ Invalid time format. Use formats like `10m`, `2h 15m`, or `1d 3h`.",
                ephemeral=True,
            )

        remind_at = datetime.now(timezone.utc) + duration

        await self.bot.database.reminders_db.add_reminder(
            user_id=interaction.user.id,
            reminder=note,
            remind_at=remind_at,
        )

        await interaction.response.send_message(
            f"✅ Reminder set for <t:{int(remind_at.timestamp())}:F> (<t:{int(remind_at.timestamp())}:R>): **{note}**",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Reminder(bot))
