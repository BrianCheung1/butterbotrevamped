import datetime
from datetime import timedelta, timezone

import discord
from constants.shop_config import SHOP_ITEMS
from discord import app_commands

from utils.base_cog import BaseGameCog
from utils.formatting import format_number
from utils.shop_helpers import get_all_shop_items, get_shop_item_data


class Shop(BaseGameCog):
    def __init__(self, bot):
        super().__init__(bot)

    @app_commands.command(name="shop", description="Buy items from the shop.")
    @app_commands.describe(item="Item you want to buy")
    @app_commands.choices(
        item=[
            app_commands.Choice(name=data["name"], value=key)
            for key, data in get_all_shop_items()
        ]
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def shop(
        self, interaction: discord.Interaction, item: app_commands.Choice[str] = None
    ):
        user_id = interaction.user.id

        # Check blackjack conflict
        if await self.check_blackjack_conflict(user_id, interaction):
            return

        # balance = await self.get_balance(user_id)
        work_stats_raw = await self.bot.database.work_db.get_user_work_stats(user_id)
        work_stats = dict(work_stats_raw["work_stats"])
        await interaction.response.defer()

        if item is None:
            bank_raw = await self.bot.database.bank_db.get_user_bank_stats(user_id)
            user_levels = {
                "bank_level": dict(bank_raw["bank_stats"]).get("bank_level", 1),
                **work_stats,
            }

            pages = generate_shop_pages(user_id, SHOP_ITEMS, user_levels)
            view = ShopView(user_id, pages)
            await interaction.followup.send(embed=pages[0], view=view)
            return

        # Item selected
        item_key = item.value
        item_data = get_shop_item_data(item_key)

        if not item_data:
            await interaction.followup.send("Item not found.")
            return

        # Check if the item requires a specific level (for tools)
        level_required = item_data.get("level_required", None)

        if level_required:
            # Define a mapping between tool names and work stats
            tool_to_work_stat_map = {
                "pickaxe": "mining_level",
                "fishingrod": "fishing_level",
            }

            # Extract tool type from the item key (e.g., "pickaxe_wooden" -> "pickaxe")
            tool_type = item_key.split("_")[0]

            # Check if this tool type has a corresponding work stat
            if tool_type in tool_to_work_stat_map:
                work_stat_key = tool_to_work_stat_map[tool_type]
                user_level = work_stats.get(work_stat_key, 0)

                # If the user does not meet the required level, send a message
                if user_level < level_required:
                    await interaction.followup.send(
                        f"You need **{work_stat_key.replace('_', ' ').capitalize()} Level {level_required}** to buy **{item_data['name']}**, "
                        f"but you are **Level {user_level}** in {work_stat_key.replace('_', ' ').capitalize()}."
                    )
                    return

        if item_key == "bank_upgrade":
            bank_raw = await self.bot.database.bank_db.get_user_bank_stats(user_id)
            level = max(1, dict(bank_raw["bank_stats"]).get("bank_level", 1))
            cost = item_data["base_price"] + (level - 1) * item_data["price_increment"]
        else:
            cost = item_data["price"]

        # Validate balance
        if not await self.validate_balance(user_id, cost, interaction, deferred=True):
            return

        # Deduct balance
        await self.deduct_balance(user_id, cost)

        # Apply item
        if item_key == "bank_upgrade":
            await self.bot.database.bank_db.set_bank_level_and_cap(user_id)
        elif "buff_type" in item_data:
            buff_type = item_data["buff_type"]
            multiplier = item_data["multiplier"]
            duration = item_data["duration"]
            await self.bot.database.buffs_db.set_buff(
                user_id, buff_type, multiplier, duration
            )

        else:
            await self.bot.database.inventory_db.add_item(user_id, item_key)

        message = f"You bought **{item_data['name']}** for ${format_number(cost)}!"

        # Suggest equipping if it's a tool
        if item_key.startswith("pickaxe") or item_key.startswith("fishingrod"):
            message += "\nUse the `/equip` command to equip it and gain its benefits."
        if "buff_type" in item_data:
            expires_at = datetime.datetime.now(timezone.utc) + timedelta(
                minutes=duration
            )
            relative = discord.utils.format_dt(expires_at, style="R")
            message += f"\nYour buff expires {relative}"

        # Log transaction
        self.log_transaction(user_id, "SHOP_BUY", cost, f"Item: {item_data['name']}")

        await interaction.followup.send(message)


class ShopView(discord.ui.View):
    def __init__(self, user_id, pages):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.pages = pages
        self.current_page = 0

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.user_id

    @discord.ui.button(
        label="Previous", style=discord.ButtonStyle.secondary, disabled=True
    )
    async def previous_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page -= 1
        await self.update_buttons(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page += 1
        await self.update_buttons(interaction)

    async def update_buttons(self, interaction: discord.Interaction):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page == len(self.pages) - 1
        await interaction.response.edit_message(
            embed=self.pages[self.current_page], view=self
        )


def generate_shop_pages(user_id, shop_data, user_levels):
    pages = []

    # Page 1: Bank Upgrade
    bank_data = shop_data["bank_upgrade"]
    embed = discord.Embed(title="🏦 Bank Upgrade", color=discord.Color.gold())
    level = max(1, user_levels.get("bank_level", 1))
    cost = bank_data["base_price"] + (level - 1) * bank_data["price_increment"]
    embed.add_field(
        name=bank_data["name"],
        value=f"{bank_data['description']}\nCost: ${format_number(cost)}",
        inline=False,
    )
    pages.append(embed)

    # Tool pages
    for tool_type, variants in shop_data["tools"].items():
        tool_type = tool_type.replace("fishingrod", "fishing rod")
        embed = discord.Embed(
            title=f"🛠️ {tool_type.capitalize()}s", color=discord.Color.green()
        )
        stat_key = "mining_level" if tool_type == "pickaxe" else "fishing_level"

        for rarity, data in variants.items():
            cost = data["price"]
            level_required = data.get("level_required", 0)
            req_text = f"Requires {stat_key.replace('_', ' ').capitalize()} Level {level_required}"
            embed.add_field(
                name=data["name"],
                value=f"{data['description']}\nCost: ${format_number(cost)}\n{req_text}",
                inline=False,
            )
        pages.append(embed)

    for buff_key, buff_data in shop_data.get("buffs", {}).items():
        embed = discord.Embed(
            title=f"{buff_key.capitalize()} Buffs", color=discord.Color.purple()
        )
        for rarity, data in buff_data.items():
            cost = data["price"]
            embed.add_field(
                name=data["name"],
                value=f"{data['description']}\nCost: ${format_number(cost)}",
                inline=False,
            )
        pages.append(embed)
    return pages


async def setup(bot):
    await bot.add_cog(Shop(bot))
