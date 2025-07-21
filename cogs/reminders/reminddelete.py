import discord
from discord import app_commands
from discord.ext import commands
from utils.autcomplete import reminder_index_autocomplete

REMINDERS_PER_PAGE = 10


class ReminderDelete(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="reminder-delete",
        description="Delete a reminder by selecting from your list",
    )
    @app_commands.describe(index="Select the reminder to delete")
    @app_commands.autocomplete(index=reminder_index_autocomplete)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def reminder_delete(self, interaction: discord.Interaction, index: int):
        reminders = await self.bot.database.reminders_db.get_user_reminders(
            interaction.user.id
        )
        if not reminders:
            return await interaction.response.send_message(
                "You have no reminders to delete.", ephemeral=True
            )

        if index < 1 or index > len(reminders):
            return await interaction.response.send_message(
                "Invalid reminder selected.", ephemeral=True
            )

        reminder_id = reminders[index - 1][0]

        await self.bot.database.reminders_db.delete_reminder(reminder_id)
        await interaction.response.send_message(
            f"✅ Deleted reminder #{index}.", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(ReminderDelete(bot))
