from typing import Optional

import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("PatchNotesDatabaseManager")


class PatchNotesDatabaseManager:
    def __init__(self, connection: aiosqlite.Connection):
        self.connection = connection

    @db_error_handler
    async def add_patch_note(
        self,
        author_id: int,
        author_name: str,
        changes: str,
        image_url: str | None = None,
    ) -> int:
        query = """
        INSERT INTO patch_notes (author_id, author_name, changes, image_url)
        VALUES (?, ?, ?, ?)
        """
        cursor = await self.connection.execute(
            query, (author_id, author_name, changes, image_url)
        )
        await self.connection.commit()
        return cursor.lastrowid

    @db_error_handler
    async def get_all_patch_notes(self) -> list[dict]:
        query = "SELECT * FROM patch_notes ORDER BY timestamp DESC"
        cursor = await self.connection.execute(query)
        rows = await cursor.fetchall()
        await cursor.close()
        return rows

    @db_error_handler
    async def get_last_patch_id(self) -> int:
        query = "SELECT MAX(id) FROM patch_notes"
        cursor = await self.connection.execute(query)
        result = await cursor.fetchone()
        await cursor.close()
        return result[0] if result else 0

    @db_error_handler
    async def get_patch_note_by_id(self, patch_id: int):
        query = "SELECT * FROM patch_notes WHERE id = ?"
        cursor = await self.connection.execute(query, (patch_id,))
        row = await cursor.fetchone()
        await cursor.close()
        return row

    @db_error_handler
    async def delete_patch_note_by_id(self, patch_id: int):
        query = "DELETE FROM patch_notes WHERE id = ?"
        await self.connection.execute(query, (patch_id,))
        await self.connection.commit()

    @db_error_handler
    async def update_patch_note_changes_and_image(
        self, patch_id: int, changes: str, image_url: Optional[str] = None
    ):
        query = "UPDATE patch_notes SET changes = ?, image_url = ? WHERE id = ?"
        await self.connection.execute(query, (changes, image_url, patch_id))
        await self.connection.commit()
