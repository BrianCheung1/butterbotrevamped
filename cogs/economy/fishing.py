import discord
import random
from discord import app_commands
from discord.ext import commands
from constants.fishing_config import FISHING_RARITY_TIERS
from utils.formatting import format_number
import time


async def perform_fishing(bot, user_id):
    start_time = time.time()  # Record the start time for database operation

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

    # Update user's work stats (total fished value and items fished)
    current_xp, next_level_xp = await bot.database.work_db.set_work_stats(
        user_id, value, xp_gained, "fishing"
    )
    balance = await bot.database.user_db.get_balance(user_id)
    await bot.database.user_db.set_balance(user_id, balance + value)

    end_time = time.time()  # Record the end time for database operation
    db_operation_time = (
        end_time - start_time
    )  # Calculate the time taken for the database operation
    bot.logger.info(f"Database operation took {db_operation_time:.4f} seconds")

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
        description=f"You fished a **{fished_item}** worth **${format_number(value)}**!\nCurrent balance: **${format_number(new_balance)}**. Earned **{xp_gained}** XP.\nXP Progress: {current_xp}/{next_level_xp}",
        color=discord.Color.green(),
    )


class FishAgainView(discord.ui.View):
    def __init__(self, bot, user_id):
        super().__init__()
        self.bot = bot
        self.user_id = user_id
        self.clicks = 0
        self.correct_color = None
        self.fish_again_btn = discord.ui.Button(
            label="Fish Again", style=discord.ButtonStyle.green
        )
        self.fish_again_btn.callback = self.fish_again_button
        self.add_item(self.fish_again_btn)

    async def fish_again_button(self, interaction: discord.Interaction):
        start_time = time.time()  # Record the start time for the message edit

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return

        self.clicks += 1

        if self.clicks >= 500:
            self.fish_again_btn.disabled = True
            self.correct_color = random.choice(["Red", "Green", "Blue"])
            self.add_color_buttons()
            await interaction.response.edit_message(
                content=f"Pick **{self.correct_color}** to fish again!", view=self
            )

        else:
            (
                fished_item,
                value,
                current_xp,
                xp_gained,
                next_level_xp,
                new_balance,
            ) = await perform_fishing(self.bot, self.user_id)

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

        end_time = time.time()  # Record the end time for the message edit
        message_edit_time = (
            end_time - start_time
        )  # Calculate the time taken for the message edit
        self.bot.logger.info(f"Message edit took {message_edit_time:.4f} seconds")

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
            self.fish_again_btn.disabled = False
            self.clicks = 0
            self.clear_items()  # Reset the view
            self.__init__(self.bot, self.user_id)  # Re-initialize the buttons
            await interaction.response.edit_message(
                content="Correct! You can fish again.", view=self
            )
        else:
            await interaction.response.edit_message(
                content="Wrong Color",
                view=None,
            )


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

        # Initialize the FishAgainView with the bot and user_id
        view = FishAgainView(self.bot, interaction.user.id)

        # Send the embed with the FishAgainView
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Fishing(bot))
