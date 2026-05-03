import asyncio
import aiosqlite
from database import DatabaseManager

BASE_XP = 100
POWER = 2.5  # new formula that makes level 100 ~ 10M XP


async def migrate_xp_system():
    """Migrate users to new XP formula and push them close to leveling up."""
    db_path = r"C:\Users\ohitz\Downloads\butterbotrevamped\database\database.db"

    async with aiosqlite.connect(db_path) as connection:
        db = DatabaseManager(connection=connection)

        try:
            async with connection.execute(
                """
                SELECT user_id, mining_level, fishing_level
                FROM user_work_stats
                """
            ) as cursor:
                users = await cursor.fetchall()

            print(f"Found {len(users)} users to migrate...")

            for user_id, mining_level, fishing_level in users:

                # ----------------------------
                # MINING
                # ----------------------------
                new_mining_next = int(BASE_XP * (mining_level**POWER))

                # place XP near leveling (90% of required)
                new_mining_xp = int(new_mining_next * 0.99)

                # ----------------------------
                # FISHING
                # ----------------------------
                new_fishing_next = int(BASE_XP * (fishing_level**POWER))
                new_fishing_xp = int(new_fishing_next * 0.99)

                await connection.execute(
                    """
                    UPDATE user_work_stats
                    SET
                        mining_xp = ?, mining_next_level_xp = ?,
                        fishing_xp = ?, fishing_next_level_xp = ?
                    WHERE user_id = ?
                    """,
                    (
                        new_mining_xp,
                        new_mining_next,
                        new_fishing_xp,
                        new_fishing_next,
                        user_id,
                    ),
                )

            await connection.commit()
            print(
                f"✅ Successfully migrated {len(users)} users and placed them near level-up progress"
            )

        except Exception as e:
            print(f"❌ Error during migration: {e}")
            await connection.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(migrate_xp_system())
