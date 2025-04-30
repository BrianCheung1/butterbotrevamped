import discord
import random
from discord import app_commands
from discord.ext import commands
from constants.fishing_config import FISHING_RARITY_TIERS


async def perform_fishing(bot, user_id):
    """
    Perform the fishing operation and return the fished item, value, and new balance.

    :param bot: The bot instance.
    :param user_id: The ID of the user performing the fishing operation.
    """
    # Weighted Random Selection of Rarity using random.choices
    rarities, weights = zip(
        *[(rarity, info["weight"]) for rarity, info in FISHING_RARITY_TIERS.items()]
    )
    selected_rarity = random.choices(rarities, weights, k=1)[
        0
    ]  # Select a rarity based on weight

    # Randomly pick an item from the selected rarity tier
    rarity_info = FISHING_RARITY_TIERS[selected_rarity]
    fished_item = random.choice(rarity_info["items"])

    # Randomly determine the value of the fished item within the value range
    value = random.randint(rarity_info["value_range"][0], rarity_info["value_range"][1])
    xp_gained = random.randint(5, 10)
    # Update user's work stats (total mined value and items mined)
    current_xp, next_level_xp = await bot.database.work_db.set_work_stats(
        user_id, value, xp_gained, "fishing"
    )
    balance = await bot.database.user_db.get_balance(user_id)
    await bot.database.user_db.set_balance(user_id, balance + value)

    return (
        fished_item,
        value,
        current_xp,
        xp_gained,
        next_level_xp,
        balance + value,
    )


def create_fishing_embed(
    user, fished_item, value, current_xp, xp_gained, next_level_xp, new_balance
):
    """
    Generate an embed for the fishing result.

    :param user: The user who performed the fishing operation.
    :param fished_item: The item that was fished.
    :param value: The value of the fished item.
    :param xp_gained: The XP earned from the fishing operation.
    :param new_balance: The new balance of the user after the fishing operation.
    """
    return discord.Embed(
        title=f"{user.display_name}'s Fishing Results",
        description=f"You fished a **{fished_item}** worth **{value}** coins!\nCurrent balance: **{new_balance}** coins. Earned **{xp_gained}** XP.\nXP Progress: {current_xp}/{next_level_xp}",
        color=discord.Color.green(),
    )


class FishAgainView(discord.ui.View):
    def __init__(self, bot, user_id):
        super().__init__()
        self.bot = bot
        self.user_id = user_id

    @discord.ui.button(label="Fish Again", style=discord.ButtonStyle.green)
    async def fish_again(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """
        Button callback to perform fishing again.

        :param interaction: The interaction object from Discord.
        :param button: The button that was clicked."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return
        fished_item, value, current_xp, xp_gained, next_level_xp, new_balance = (
            await perform_fishing(self.bot, self.user_id)
        )

        embed = create_fishing_embed(
            interaction.user,
            fished_item,
            value,
            current_xp,
            xp_gained,
            next_level_xp,
            new_balance,
        )
        await interaction.response.edit_message(embed=embed, view=self)


class Fishing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="fish", description="Fish for money")
    async def fish(self, interaction: discord.Interaction):
        """
        Command to perform fishing and get a random item with its value.

        :param interaction: The interaction object from Discord.
        """
        await interaction.response.defer()

        # Perform the mining logic
        fished_item, value, current_xp, xp_gained, next_level_xp, new_balance = (
            await perform_fishing(self.bot, interaction.user.id)
        )

        # Create the embed
        embed = create_fishing_embed(
            interaction.user,
            fished_item,
            value,
            current_xp,
            xp_gained,
            next_level_xp,
            new_balance,
        )

        # Initialize the MineAgainView with the bot and user_id
        view = FishAgainView(self.bot, interaction.user.id)

        # Send the embed with the MineAgainView
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Fishing(bot))
