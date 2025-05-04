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
    current_xp, next_level_xp, current_level = (
        await bot.database.work_db.set_work_stats(user_id, value, xp_gained, "mining")
    )
    level_bonus = int((current_level * 0.05) * value)

    balance = await bot.database.user_db.get_balance(user_id)
    await bot.database.user_db.set_balance(user_id, balance + value + level_bonus)

    return (
        mined_item,
        value,
        level_bonus,
        current_xp,
        current_level,
        next_level_xp,
        balance + value + level_bonus,
    )


def create_mining_embed(
    user,
    mined_item,
    value,
    level_bonus,
    current_xp,
    current_level,
    next_level_xp,
    new_balance,
):
    """
    Generate an embed for the mining result.

    :param user: The user who performed the mining operation.
    :param mined_item: The item that was mined.
    :param value: The value of the mined item.
    :param xp_gained: The XP earned from the mining operation.
    :param new_balance: The new balance of the user after the mining operation.
    """
    embed = discord.Embed(
        title=f"⛏️ {user.display_name}'s Mining Results",
        description=f"You mined a **{mined_item}** worth **${format_number(value)}**!",
        color=discord.Color.green(),
    )
    embed.add_field(
        name="💰 New Balance", value=f"${format_number(new_balance)}", inline=True
    )
    embed.add_field(
        name="🔹 XP Progress",
        value=f"LVL: {current_level} | XP:{current_xp}/{next_level_xp}",
        inline=True,
    )
    embed.add_field(
        name="Level Bonus",
        value=f"${format_number(level_bonus)}",
        inline=True,
    )

    return embed


class MineAgainView(discord.ui.View):
    def __init__(self, bot, user_id, active_mining_sessions):
        super().__init__(timeout=300)
        self.bot = bot
        self.user_id = user_id
        self.clicks = 0
        self.correct_color = None
        self.mine_again_btn = discord.ui.Button(
            label="Mine Again", style=discord.ButtonStyle.green
        )
        self.mine_again_btn.callback = self.mine_again_button
        self.add_item(self.mine_again_btn)
        self.active_mining_sessions = active_mining_sessions

    async def on_timeout(self):
        self.active_mining_sessions.discard(self.user_id)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            await self.message.edit(
                content="Button timed out/Cooldown Finished", view=self
            )

    async def mine_again_button(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return

        self.clicks += 1

        if self.clicks >= 100:
            self.mine_again_btn.disabled = True
            self.correct_color = random.choice(["Red", "Green", "Blue"])
            self.add_color_buttons()
            await interaction.response.edit_message(
                content=f"Pick **{self.correct_color}** to mine again!", view=self
            )
            return

        # Assume perform_mining & create_mining_embed are defined elsewhere
        (
            mined_item,
            value,
            level_bonus,
            current_xp,
            current_level,
            next_level_xp,
            new_balance,
        ) = await perform_mining(self.bot, self.user_id)

        embed = create_mining_embed(
            interaction.user,
            mined_item,
            value,
            level_bonus,
            current_xp,
            current_level,
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
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.label != "Mine Again":
                    self.remove_item(item)
            self.mine_again_btn.disabled = False  # Enable mining button again
            self.clicks = 0  # Reset clicks
            await interaction.response.edit_message(
                content="✅ Correct! You can mine again.", view=self
            )
        else:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True  # Disable all buttons

            await interaction.response.edit_message(
                content="❌ Wrong color! Cooldown Started.", view=self
            )


class Mining(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_mining_sessions = set()

    @app_commands.command(name="mine", description="Mine ores for money")
    async def mine(self, interaction: discord.Interaction):
        """
        Command to perform mining and get a random item with its value.

        :param interaction: The interaction object from Discord.
        """
        if interaction.user.id in self.active_mining_sessions:
            await interaction.response.send_message(
                "You are already mining or on a cooldown. Please wait.",
            )
            return

        await interaction.response.defer()

        # Perform the mining logic
        (
            mined_item,
            value,
            level_bonus,
            current_xp,
            current_level,
            next_level_xp,
            new_balance,
        ) = await perform_mining(self.bot, interaction.user.id)

        # Create the embed
        embed = create_mining_embed(
            interaction.user,
            mined_item,
            value,
            level_bonus,
            current_xp,
            current_level,
            next_level_xp,
            new_balance,
        )
        self.active_mining_sessions.add(interaction.user.id)
        # Initialize the MineAgainView with the bot and user_id
        view = MineAgainView(self.bot, interaction.user.id, self.active_mining_sessions)
        # Send the embed with the MineAgainView
        view.message = await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Mining(bot))
