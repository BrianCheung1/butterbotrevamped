from typing import Optional
import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("SteamGamesDatabaseManager")


class SteamGamesDatabaseManager:
    def __init__(self, connection: aiosqlite.Connection):
        self.connection = connection

    @db_error_handler
    async def upsert_game(
        self,
        title: str,
        add_type: str,
        download_link: str,
        steam_link: str,
        description: str,
        image: str,
        build: Optional[str],
        notes: Optional[str],
        price: str,
        reviews: str,
        app_id: str,
        genres: str,
        categories: str,
        added_by_id: str,
        added_by_name: str,
    ):
        """Insert or update a game."""
        await self.connection.execute(
            """
            INSERT INTO steam_games (
                title, add_type, download_link, steam_link, description, image,
                build, notes, price, reviews, app_id, genres, categories, added_by_id, added_by_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(title) DO UPDATE SET
                add_type=excluded.add_type,
                download_link=excluded.download_link,
                steam_link=excluded.steam_link,
                description=excluded.description,
                image=excluded.image,
                build=excluded.build,
                notes=excluded.notes,
                price=excluded.price,
                reviews=excluded.reviews,
                app_id=excluded.app_id,
                genres=excluded.genres,
                categories=excluded.categories,
                added_by_id=excluded.added_by_id,
                added_by_name=excluded.added_by_name,
                added_at=CURRENT_TIMESTAMP
            """,
            (
                title,
                add_type,
                download_link,
                steam_link,
                description,
                image,
                build,
                notes,
                price,
                reviews,
                app_id,
                genres,
                categories,
                added_by_id,
                added_by_name,
            ),
        )
        await self.connection.commit()

    @db_error_handler
    async def get_game_by_title(self, title: str) -> Optional[dict]:
        """Fetch a game's details by its title."""
        async with self.connection.execute(
            "SELECT * FROM steam_games WHERE title = ?", (title,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, row))

    @db_error_handler
    async def delete_game_by_title(self, title: str) -> bool:
        """Delete a game from the table."""
        await self.connection.execute(
            "DELETE FROM steam_games WHERE title = ?", (title,)
        )
        await self.connection.commit()
        return True

    @db_error_handler
    async def get_all_games(self) -> list[dict]:
        """Fetch all games."""
        async with self.connection.execute("SELECT * FROM steam_games") as cursor:
            rows = await cursor.fetchall()
            columns = [col[0] for col in cursor.description]

        return [dict(zip(columns, row)) for row in rows]
