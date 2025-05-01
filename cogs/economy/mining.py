import discord
import random
from discord import app_commands
from discord.ext import commands
from constants.mining_config import MINING_RARITY_TIERS
from utils.formatting import format_number


async def perform_mining(bot, user_id):
    """
    Perform the mining operation and return the fished item, value, and new balance.

    :param bot: The bot instance.
    :param user_id: The ID of the user performing the mining operation.
    """
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
    xp_gained = random.randint(5, 10)
    # Update user's work stats (total mined value and items mined)
    current_xp, next_level_xp = await bot.database.work_db.set_work_stats(
        user_id, value, xp_gained, "mining"
    )
    balance = await bot.database.user_db.get_balance(user_id)
    await bot.database.user_db.set_balance(user_id, balance + value)

    return (
        mined_item,
        value,
        current_xp,
        xp_gained,
        next_level_xp,
        balance + value,
    )


def create_mining_embed(
    user, mined_item, value, current_xp, xp_gained, next_level_xp, new_balance
):
    """
    Generate an embed for the mining result.

    :param user: The user who performed the mining operation.
    :param mined_item: The item that was mined.
    :param value: The value of the mined item.
    :param xp_gained: The XP earned from the mining operation.
    :param new_balance: The new balance of the user after the mining operation.
    """
    return discord.Embed(
        title=f"{user.display_name}'s Mining Results",
        description=f"You mined a **{mined_item}** worth **${format_number(value)}**!\nCurrent balance: **${format_number(new_balance)}**. Earned **{xp_gained}** XP.\nXP Progress: {current_xp}/{next_level_xp}",
        color=discord.Color.green(),
    )


import discord
import random


class MineAgainView(discord.ui.View):
    def __init__(self, bot, user_id):
        super().__init__()
        self.bot = bot
        self.user_id = user_id
        self.clicks = 0
        self.correct_color = None
        self.mine_again_btn = discord.ui.Button(
            label="Mine Again", style=discord.ButtonStyle.green
        )
        self.mine_again_btn.callback = self.mine_again_button
        self.add_item(self.mine_again_btn)

    async def mine_again_button(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return

        self.clicks += 1

        if self.clicks >= 500:
            self.mine_again_btn.disabled = True
            self.correct_color = random.choice(["Red", "Green", "Blue"])
            self.add_color_buttons()
            await interaction.response.edit_message(
                content=f"Pick **{self.correct_color}** to mine again!", view=self
            )
            return

        # Assume perform_mining & create_mining_embed are defined elsewhere
        mined_item, value, current_xp, xp_gained, next_level_xp, new_balance = (
            await perform_mining(self.bot, self.user_id)
        )

        embed = create_mining_embed(
            interaction.user,
            mined_item,
            value,
            current_xp,
            xp_gained,
            next_level_xp,
            new_balance,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    def add_color_buttons(self):
        # Create buttons dynamically
        for color, style in [
            ("Green", discord.ButtonStyle.green),
            ("Red", discord.ButtonStyle.red),
            ("Blue", discord.ButtonStyle.blurple),
        ]:
            button = discord.ui.Button(label=color, style=style)
            button.callback = lambda interaction, c=color: self.handle_color_choice(
                interaction, c
            )
            self.add_item(button)

    async def handle_color_choice(
        self, interaction: discord.Interaction, chosen_color: str
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return

        if chosen_color == self.correct_color:
            self.mine_again_btn.disabled = False
            self.clicks = 0
            self.clear_items()  # Reset the view
            self.__init__(self.bot, self.user_id)  # Re-initialize the buttons
            await interaction.response.edit_message(
                content="Correct! You can mine again.", view=self
            )
        else:
            await interaction.response.edit_message(
                content="Wrong Color",
                view=None,
            )


class Mining(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mine", description="Mine ores for money")
    async def mine(self, interaction: discord.Interaction):
        """
        Command to perform mining and get a random item with its value.

        :param interaction: The interaction object from Discord.
        """
        await interaction.response.defer()

        # Perform the mining logic
        mined_item, value, current_xp, xp_gained, next_level_xp, new_balance = (
            await perform_mining(self.bot, interaction.user.id)
        )

        # Create the embed
        embed = create_mining_embed(
            interaction.user,
            mined_item,
            value,
            current_xp,
            xp_gained,
            next_level_xp,
            new_balance,
        )

        # Initialize the MineAgainView with the bot and user_id
        view = MineAgainView(self.bot, interaction.user.id)

        # Send the embed with the MineAgainView
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Mining(bot))
