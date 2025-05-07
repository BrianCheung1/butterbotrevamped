import discord
from discord import app_commands
from discord.ext import commands
from utils.equips import format_tool_display_name


class Equip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="equip", description="Equip a tool from your inventory")
    @app_commands.describe(tool_name="The name of the tool to equip")
    async def equip(self, interaction: discord.Interaction, tool_name: str):
        user_id = interaction.user.id
        inventory_manager = self.bot.database.inventory_db

        # Check if item is in inventory
        inventory = await inventory_manager.get_user_inventory(user_id)
        owned_item_names = [item["item_name"].lower() for item in inventory]
        if tool_name.lower() not in owned_item_names:
            await interaction.response.send_message(
                "❌ You do not own this item.", ephemeral=True
            )
            return

        # Infer tool type from name
        if tool_name.lower().startswith("pickaxe_"):
            tool_type = "pickaxe"
        elif tool_name.lower().startswith("fishingrod_"):
            tool_type = "fishingrod"
        else:
            await interaction.response.send_message(
                "❌ This item cannot be equipped.", ephemeral=True
            )
            return

        # Equip tool
        await inventory_manager.set_equipped_tool(user_id, tool_type, tool_name)
        await interaction.response.send_message(
            f"✅ Equipped `{format_tool_display_name(tool_name)}` as your {tool_type}.",
            ephemeral=True,
        )

    @equip.autocomplete("tool_name")
    async def tool_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        inventory_manager = self.bot.database.inventory_db
        inventory = await inventory_manager.get_user_inventory(interaction.user.id)

        tool_items = [
            item["item_name"]
            for item in inventory
            if item["item_name"].lower().startswith(("pickaxe_", "fishingrod_"))
        ]

        return [
            app_commands.Choice(name=format_tool_display_name(name), value=name)
            for name in tool_items
            if current.lower() in name.lower()
        ]


async def setup(bot):
    await bot.add_cog(Equip(bot))
