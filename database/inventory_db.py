from typing import Optional

import aiosqlite
from logger import setup_logger
from utils.database_errors import db_error_handler

logger = setup_logger("InventoryDatabaseManager")


class InventoryDatabaseManager:

    def __init__(
        self, connection: aiosqlite.Connection, db_manager: "DatabaseManager"
    ) -> None:
        self.connection = connection
        self.db_manager = db_manager

    @db_error_handler
    async def get_user_inventory(self, user_id: int):
        """
        Returns a list of all items the user has in their inventory.

        :param user_id: Discord user ID.
        """
        await self.db_manager._create_user_if_not_exists(user_id)
        async with self.connection.execute(
            "SELECT item_name, quantity FROM user_inventory WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        return [{"item_name": row[0], "quantity": row[1]} for row in rows]

    @db_error_handler
    async def add_item(self, user_id: int, item_name: str):
        """
        Adds an item to the user's inventory. If it already exists, increments the quantity.

        :param user_id: Discord user ID.
        :param item_name: Name of the item to add.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.connection.execute(
            "SELECT quantity FROM user_inventory WHERE user_id = ? AND item_name = ?",
            (user_id, item_name),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            await self.connection.execute(
                "UPDATE user_inventory SET quantity = quantity + 1 WHERE user_id = ? AND item_name = ?",
                (user_id, item_name),
            )
        else:
            await self.connection.execute(
                "INSERT INTO user_inventory (user_id, item_name, quantity) VALUES (?, ?, ?)",
                (user_id, item_name, 1),
            )

        await self.connection.commit()

    @db_error_handler
    async def remove_item(self, user_id: int, item_name: str, quantity: int = 1):
        """
        Removes an item (or quantity) from the user's inventory. Deletes row if quantity reaches 0.

        :param user_id: Discord user ID.
        :param item_name: Name of the item to remove.
        :param quantity: Amount to remove (default = 1).
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.connection.execute(
            "SELECT quantity FROM user_inventory WHERE user_id = ? AND item_name = ?",
            (user_id, item_name),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            current_quantity = row[0]
            if current_quantity > quantity:
                await self.connection.execute(
                    "UPDATE user_inventory SET quantity = quantity - ? WHERE user_id = ? AND item_name = ?",
                    (quantity, user_id, item_name),
                )
            else:
                await self.connection.execute(
                    "DELETE FROM user_inventory WHERE user_id = ? AND item_name = ?",
                    (user_id, item_name),
                )
            await self.connection.commit()

    @db_error_handler
    async def set_equipped_tool(
        self, user_id: int, tool_type: str, tool_name: Optional[str]
    ) -> Optional[str]:
        """
        Sets the equipped tool for a user. Removes 1 from inventory and equips the tool.
        If the tool_name is None, it sets the equipped tool to NULL and does not return a tool to inventory.

        :param user_id: Discord user ID.
        :param tool_type: Either 'pickaxe' or 'fishingrod'.
        :param tool_name: The name of the tool to equip or None to set the tool to NULL.
        :return: The name of the previously equipped tool (if any), else None.
        """
        if tool_type not in ("pickaxe", "fishingrod"):
            raise ValueError("tool_type must be either 'pickaxe' or 'fishingrod'")

        await self.db_manager._create_user_if_not_exists(user_id)

        # If tool_name is None, handle the case where we are setting the tool to NULL
        if tool_name is None:
            # Get current equipped tool
            async with self.connection.execute(
                f"SELECT {tool_type} FROM user_equipped_tools WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                equipped_row = await cursor.fetchone()

            previous_tool = (
                equipped_row[0] if equipped_row and equipped_row[0] else None
            )

            # Set the tool to NULL in the database
            if equipped_row:
                await self.connection.execute(
                    f"UPDATE user_equipped_tools SET {tool_type} = NULL WHERE user_id = ?",
                    (user_id,),
                )
            else:
                await self.connection.execute(
                    "INSERT INTO user_equipped_tools (user_id, pickaxe, fishingrod) VALUES (?, NULL, NULL)",
                    (user_id,),
                )
            await self.connection.commit()

            # Do not return the tool to inventory when setting to NULL
            return previous_tool

        # Ensure the user has the tool in inventory
        async with self.connection.execute(
            "SELECT quantity FROM user_inventory WHERE user_id = ? AND item_name = ?",
            (user_id, tool_name),
        ) as cursor:
            row = await cursor.fetchone()

        if not row or row[0] < 1:
            raise ValueError(f"User does not have '{tool_name}' in their inventory.")

        # Remove the tool from inventory
        await self.remove_item(user_id, tool_name, 1)

        # Get current equipped tool
        async with self.connection.execute(
            f"SELECT {tool_type} FROM user_equipped_tools WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            equipped_row = await cursor.fetchone()

        previous_tool = equipped_row[0] if equipped_row and equipped_row[0] else None

        # Equip the new tool
        if equipped_row:
            await self.connection.execute(
                f"UPDATE user_equipped_tools SET {tool_type} = ? WHERE user_id = ?",
                (tool_name, user_id),
            )
        else:
            if tool_type == "pickaxe":
                await self.connection.execute(
                    "INSERT INTO user_equipped_tools (user_id, pickaxe) VALUES (?, ?)",
                    (user_id, tool_name),
                )
            else:
                await self.connection.execute(
                    "INSERT INTO user_equipped_tools (user_id, fishingrod) VALUES (?, ?)",
                    (user_id, tool_name),
                )

        await self.connection.commit()

        # Optionally return previous tool back to inventory:
        if previous_tool:
            await self.add_item(user_id, previous_tool)

        return previous_tool

    @db_error_handler
    async def get_equipped_tools(self, user_id: int) -> dict:
        """
        Retrieves the currently equipped pickaxe and fishing rod for a user.

        :param user_id: Discord user ID.
        :return: A dictionary with keys 'pickaxe' and 'fishingrod'.
        """
        await self.db_manager._create_user_if_not_exists(user_id)

        async with self.connection.execute(
            "SELECT pickaxe, fishingrod FROM user_equipped_tools WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            return {"pickaxe": row[0], "fishingrod": row[1]}
        return {"pickaxe": None, "fishingrod": None}
