from __future__ import annotations
from typing import Optional, List, Dict

import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("PatchNotesDatabaseManager")


class PatchNotesDatabaseManager:
    def __init__(
        self,
        connection: aiosqlite.Connection,
        db_manager: "DatabaseManager",
    ):
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def add_patch_note(
        self,
        author_id: int,
        author_name: str,
        changes: str,
        image_url: Optional[str] = None,
    ) -> int:
        """Insert a new patch note. Returns the row ID."""
        async with self.db_manager.transaction():
            cursor = await self.connection.execute(
                """
                INSERT INTO patch_notes (author_id, author_name, changes, image_url)
                VALUES (?, ?, ?, ?)
                """,
                (author_id, author_name, changes, image_url),
            )
            return cursor.lastrowid

    @db_error_handler
    async def update_patch_note_changes_and_image(
        self, patch_id: int, changes: str, image_url: Optional[str] = None
    ) -> None:
        """Update the changes and/or image_url for a patch note by ID."""
        async with self.db_manager.transaction():
            await self.connection.execute(
                """
                UPDATE patch_notes
                SET changes = ?, image_url = ?
                WHERE id = ?
                """,
                (changes, image_url, patch_id),
            )

    @db_error_handler
    async def delete_patch_note_by_id(self, patch_id: int) -> None:
        """Delete a patch note by ID."""
        async with self.db_manager.transaction():
            await self.connection.execute(
                "DELETE FROM patch_notes WHERE id = ?", (patch_id,)
            )

    @db_error_handler
    async def get_all_patch_notes(self) -> List[Dict]:
        """Retrieve all patch notes ordered by timestamp descending."""
        async with self.connection.execute(
            "SELECT * FROM patch_notes ORDER BY timestamp DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    @db_error_handler
    async def get_last_patch_id(self) -> int:
        """Retrieve the maximum patch ID (or 0 if none exist)."""
        async with self.connection.execute("SELECT MAX(id) FROM patch_notes") as cursor:
            result = await cursor.fetchone()
        return result[0] if result and result[0] is not None else 0

    @db_error_handler
    async def get_patch_note_by_id(self, patch_id: int) -> Optional[Dict]:
        """Retrieve a single patch note by ID."""
        async with self.connection.execute(
            "SELECT * FROM patch_notes WHERE id = ?", (patch_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))
