import discord
from discord import app_commands
from discord.ext import commands

REMINDERS_PER_PAGE = 10


class ReminderDelete(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="reminder-delete", description="Delete a reminder by its list number"
    )
    @app_commands.describe(index="The reminder number from the reminders list")
    async def reminder_delete(self, interaction: discord.Interaction, index: int):
        reminders = await self.bot.database.reminders_db.get_user_reminders(
            interaction.user.id
        )
        if not reminders:
            return await interaction.response.send_message(
                "You have no reminders to delete.", ephemeral=True
            )

        # Calculate which page and offset this index falls on:
        page = (index - 1) // REMINDERS_PER_PAGE
        offset = (index - 1) % REMINDERS_PER_PAGE

        if page >= ((len(reminders) - 1) // REMINDERS_PER_PAGE) + 1 or index < 1:
            return await interaction.response.send_message(
                "Invalid reminder number.", ephemeral=True
            )

        # Find the actual reminder ID to delete
        reminder_id = reminders[page * REMINDERS_PER_PAGE + offset][0]

        await self.bot.database.reminders_db.delete_reminder(reminder_id)
        await interaction.response.send_message(
            f"✅ Deleted reminder #{index}.", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(ReminderDelete(bot))
