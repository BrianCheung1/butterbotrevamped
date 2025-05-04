import discord
from discord import app_commands
from discord.ext import commands
from utils.formatting import format_number
from utils.shop_helpers import get_all_shop_items, get_shop_item_data


class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="shop", description="Buy items from the shop.")
    @app_commands.describe(item="Item you want to buy")
    @app_commands.choices(
        item=[
            app_commands.Choice(name=data["name"], value=key)
            for key, data in get_all_shop_items()
        ]
    )
    async def shop(
        self, interaction: discord.Interaction, item: app_commands.Choice[str] = None
    ):
        user_id = interaction.user.id

        if user_id in self.bot.active_blackjack_players:
            await interaction.response.send_message(
                "You are in a Blackjack game! Please finish the game first.",
                ephemeral=True,
            )
            return

        balance = await self.bot.database.user_db.get_balance(user_id)
        await interaction.response.defer()

        if item is None:
            embed = discord.Embed(
                title="🛒 Welcome to the Shop!",
                description="Here are the available items:",
                color=discord.Color.gold(),
            )

            for key, data in get_all_shop_items():
                if key == "bank_upgrade":
                    bank_raw = await self.bot.database.bank_db.get_user_bank_stats(
                        user_id
                    )
                    level = max(1, dict(bank_raw["bank_stats"]).get("bank_level", 1))
                    cost = data["base_price"] + (level - 1) * data["price_increment"]
                else:
                    cost = data["price"]

                embed.add_field(
                    name=f"{data['name']} - ${format_number(cost)}",
                    value=data["description"],
                    inline=False,
                )

            await interaction.followup.send(embed=embed)
            return

        # Item selected
        item_key = item.value
        item_data = get_shop_item_data(item_key)

        if not item_data:
            await interaction.followup.send("Item not found.")
            return

        if item_key == "bank_upgrade":
            bank_raw = await self.bot.database.bank_db.get_user_bank_stats(user_id)
            level = max(1, dict(bank_raw["bank_stats"]).get("bank_level", 1))
            cost = item_data["base_price"] + (level - 1) * item_data["price_increment"]
        else:
            cost = item_data["price"]

        if balance < cost:
            await interaction.followup.send(
                f"You need ${format_number(cost)} to buy **{item_data['name']}**, "
                f"but you only have ${format_number(balance)}."
            )
            return

        # Deduct balance
        await self.bot.database.user_db.set_balance(user_id, balance - cost)

        # Apply item
        if item_key == "bank_upgrade":
            await self.bot.database.bank_db.upgrade_bank(user_id)
        else:
            await self.bot.database.inventory_db.add_item(user_id, item_key)

        await interaction.followup.send(
            f"You bought **{item_data['name']}** for ${format_number(cost)}!"
        )


async def setup(bot):
    await bot.add_cog(Shop(bot))
