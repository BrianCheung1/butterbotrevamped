import discord
import random
from discord import app_commands
from discord.ext import commands
from constants.economy_config import MINING_RARITY_TIERS


async def perform_mining(bot, user_id):
    """Perform the mining operation and return the mined item, value, and new balance."""
    # Weighted Random Selection of Rarity using random.choices
    rarities, weights = zip(
        *[(rarity, info["weight"]) for rarity, info in MINING_RARITY_TIERS.items()]
    )
    selected_rarity = random.choices(rarities, weights, k=1)[
        0
    ]  # Select a rarity based on weight

    # Randomly pick an item from the selected rarity tier
    rarity_info = MINING_RARITY_TIERS[selected_rarity]
    mined_item = random.choice(rarity_info["items"])

    # Randomly determine the value of the mined item within the value range
    value = random.randint(rarity_info["value_range"][0], rarity_info["value_range"][1])

    # Update user's work stats (total mined value and items mined)
    await bot.database.set_work_stats(user_id, value, "mining")
    balance = await bot.database.get_balance(user_id)
    await bot.database.set_balance(user_id, balance + value)

    return mined_item, value, balance + value


def create_mining_embed(user, mined_item, value, new_balance):
    """Generate an embed for the mining result."""
    return discord.Embed(
        title=f"{user.display_name}'s Mining Results",
        description=f"You mined a **{mined_item}** worth **{value}** coins!\nCurrent balance: **{new_balance}** coins.",
        color=discord.Color.green(),
    )


class MineAgainView(discord.ui.View):
    def __init__(self, bot, user_id):
        super().__init__()
        self.bot = bot
        self.user_id = user_id

    @discord.ui.button(label="Mine Again", style=discord.ButtonStyle.green)
    async def mine_again(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        mined_item, value, new_balance = await perform_mining(self.bot, self.user_id)

        embed = create_mining_embed(interaction.user, mined_item, value, new_balance)
        await interaction.response.edit_message(embed=embed, view=self)


class Mining(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mine", description="Mine ores for money")
    async def mine(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Perform the mining logic
        mined_item, value, new_balance = await perform_mining(
            self.bot, interaction.user.id
        )

        # Create the embed
        embed = create_mining_embed(interaction.user, mined_item, value, new_balance)

        # Initialize the MineAgainView with the bot and user_id
        view = MineAgainView(self.bot, interaction.user.id)

        # Send the embed with the MineAgainView
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Mining(bot))
