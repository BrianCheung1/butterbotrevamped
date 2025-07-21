# database/reminders_db.py

from datetime import datetime, timezone

import aiosqlite
from logger import setup_logger

logger = setup_logger("RemindersDatabaseManager")


class RemindersDatabaseManager:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self.connection = connection

    async def add_reminder(self, user_id: int, reminder: str, remind_at: datetime):
        await self.connection.execute(
            "INSERT INTO reminders (user_id, reminder, remind_at) VALUES (?, ?, ?)",
            (str(user_id), reminder, remind_at.isoformat()),
        )
        await self.connection.commit()

    async def get_due_reminders(self) -> list[tuple[int, str, str]]:
        now = datetime.now(timezone.utc).isoformat()
        async with self.connection.execute(
            "SELECT id, user_id, reminder FROM reminders WHERE remind_at <= ?",
            (now,),
        ) as cursor:
            return await cursor.fetchall()

    async def delete_reminder(self, reminder_id: int):
        await self.connection.execute(
            "DELETE FROM reminders WHERE id = ?", (reminder_id,)
        )
        await self.connection.commit()

    async def get_user_reminders(self, user_id: int) -> list[tuple[int, str, str]]:
        """Return list of (id, reminder, remind_at ISO string) for the given user."""
        async with self.connection.execute(
            "SELECT id, reminder, remind_at FROM reminders WHERE user_id = ? ORDER BY remind_at ASC",
            (str(user_id),),
        ) as cursor:
            return await cursor.fetchall()
