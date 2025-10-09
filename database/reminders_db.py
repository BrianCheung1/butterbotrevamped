from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("RemindersDatabaseManager")


class RemindersDatabaseManager:
    def __init__(self, connection: aiosqlite.Connection, db_manager: "DatabaseManager"):
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def add_reminder(self, user_id: int, reminder: str, remind_at: datetime):
        """Add a new reminder for a user."""
        async with self.db_manager.transaction():
            await self.connection.execute(
                "INSERT INTO reminders (user_id, reminder, remind_at) VALUES (?, ?, ?)",
                (str(user_id), reminder, remind_at.isoformat()),
            )

    @db_error_handler
    async def get_due_reminders(self) -> List[Tuple[int, str, str]]:
        """Fetch reminders whose time is due."""
        now = datetime.now(timezone.utc).isoformat()
        async with self.connection.execute(
            "SELECT id, user_id, reminder FROM reminders WHERE remind_at <= ?",
            (now,),
        ) as cursor:
            return await cursor.fetchall()

    @db_error_handler
    async def delete_reminder(self, reminder_id: int):
        """Delete a reminder by its ID."""
        async with self.db_manager.transaction():
            await self.connection.execute(
                "DELETE FROM reminders WHERE id = ?", (reminder_id,)
            )

    @db_error_handler
    async def get_user_reminders(self, user_id: int) -> List[Tuple[int, str, str]]:
        """Return list of (id, reminder, remind_at ISO string) for the given user."""
        async with self.connection.execute(
            "SELECT id, reminder, remind_at FROM reminders WHERE user_id = ? ORDER BY remind_at ASC",
            (str(user_id),),
        ) as cursor:
            return await cursor.fetchall()
