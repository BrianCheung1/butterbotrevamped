import discord
from discord.ext import commands, tasks
from logger import setup_logger

logger = setup_logger("RemindLoop")


class RemindLoop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    @tasks.loop(seconds=30)
    async def reminder_loop(self):
        await self.process_due_reminders()

    async def process_due_reminders(self):
        try:
            due_reminders = await self.bot.database.reminders_db.get_due_reminders()
            for reminder_id, user_id, reminder in due_reminders:
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    await user.send(f"🔔 Reminder: **{reminder}**")
                except discord.Forbidden:
                    logger.warning(f"Cannot send DM to user {user_id}.")
                except Exception as e:
                    logger.exception(f"Error sending reminder to {user_id}: {e}")
                finally:
                    await self.bot.database.reminders_db.delete_reminder(reminder_id)
        except Exception as loop_err:
            logger.exception(f"Error in reminder loop: {loop_err}")

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()
        # Run immediately once before starting the loop
        await self.process_due_reminders()


async def setup(bot):
    await bot.add_cog(RemindLoop(bot))
