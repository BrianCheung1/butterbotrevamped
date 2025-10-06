from __future__ import annotations

from typing import List, Optional

import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("MessageLoggerDatabaseManager")


class MessageLoggerDatabaseManager:
    def __init__(
        self,
        connection: aiosqlite.Connection,
        db_manager: "DatabaseManager",
    ) -> None:
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def log_new_message(
        self,
        message_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        content: Optional[str],
        attachments_json: Optional[str],
        created_at: str,
    ) -> None:
        """Insert a new message log. If it already exists, ignore."""
        async with self.db_manager.transaction():
            await self.connection.execute(
                """
                INSERT OR IGNORE INTO message_logs (
                    message_id, guild_id, channel_id, author_id, content, attachments, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    guild_id,
                    channel_id,
                    author_id,
                    content,
                    attachments_json,
                    created_at,
                ),
            )

    @db_error_handler
    async def update_message_edit(
        self,
        message_id: int,
        edited_before: Optional[str],
        edited_after: Optional[str],
        edited_at: str,
    ) -> None:
        """Update a message log to record an edit."""
        async with self.db_manager.transaction():
            await self.connection.execute(
                """
                UPDATE message_logs
                SET edited_before = ?, edited_after = ?, edited_at = ?
                WHERE message_id = ?
                """,
                (edited_before, edited_after, edited_at, message_id),
            )

    @db_error_handler
    async def update_message_content(
        self, message_id: int, new_content: Optional[str]
    ) -> None:
        """Update the message content (e.g., after an edit)."""
        async with self.db_manager.transaction():
            await self.connection.execute(
                """
                UPDATE message_logs
                SET content = ?
                WHERE message_id = ?
                """,
                (new_content, message_id),
            )

    @db_error_handler
    async def mark_message_deleted(self, message_id: int, deleted_at: str) -> None:
        """Mark a message as deleted."""
        async with self.db_manager.transaction():
            await self.connection.execute(
                """
                UPDATE message_logs
                SET deleted_at = ?
                WHERE message_id = ?
                """,
                (deleted_at, message_id),
            )

    @db_error_handler
    async def get_message_log(self, message_id: int) -> Optional[dict]:
        """Fetch a logged message by its ID."""
        async with self.connection.execute(
            "SELECT * FROM message_logs WHERE message_id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))

    @db_error_handler
    async def get_guild_logs(self, guild_id: int) -> List[dict]:
        """Fetch all message logs for a specific guild."""
        async with self.connection.execute(
            "SELECT * FROM message_logs WHERE guild_id = ? ORDER BY created_at DESC",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    @db_error_handler
    async def delete_old_logs(self, cutoff_iso_timestamp: str) -> None:
        """Delete message logs older than a given ISO timestamp."""
        async with self.db_manager.transaction():
            await self.connection.execute(
                """
                DELETE FROM message_logs
                WHERE created_at < ?
                """,
                (cutoff_iso_timestamp,),
            )
