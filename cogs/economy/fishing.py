import discord
import random
import time
from discord import app_commands
from discord.ext import commands
from constants.fishing_config import FISHING_RARITY_TIERS
from utils.formatting import format_number


async def perform_fishing(bot, user_id):
    start_time = time.time()

    rarities, weights = zip(
        *[(rarity, info["weight"]) for rarity, info in FISHING_RARITY_TIERS.items()]
    )
    selected_rarity = random.choices(rarities, weights, k=1)[0]
    rarity_info = FISHING_RARITY_TIERS[selected_rarity]
    fished_item = random.choice(rarity_info["items"])
    value = random.randint(*rarity_info["value_range"])
    xp_gained = random.randint(5, 10)

    current_xp, next_level_xp = await bot.database.work_db.set_work_stats(
        user_id, value, xp_gained, "fishing"
    )
    balance = await bot.database.user_db.get_balance(user_id)
    await bot.database.user_db.set_balance(user_id, balance + value)

    db_operation_time = time.time() - start_time
    bot.logger.info(f"Database operation took {db_operation_time:.4f} seconds")

    return fished_item, value, current_xp, xp_gained, next_level_xp, balance + value


def create_fishing_embed(
    user, fished_item, value, current_xp, xp_gained, next_level_xp, new_balance
):
    embed = discord.Embed(
        title=f"🎣 {user.display_name}'s Fishing Results",
        description=f"You fished a **{fished_item}** worth **${format_number(value)}**!",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="💰 New Balance", value=f"${format_number(new_balance)}", inline=True
    )
    embed.add_field(name="📈 XP Gained", value=f"+{xp_gained} XP", inline=True)
    embed.add_field(
        name="🔹 XP Progress", value=f"{current_xp}/{next_level_xp}", inline=False
    )
    return embed


class FishAgainView(discord.ui.View):
    def __init__(self, bot, user_id, active_fishing_sessions):
        super().__init__(timeout=300)
        self.bot = bot
        self.user_id = user_id
        self.clicks = 0
        self.correct_color = None
        self.active_fishing_sessions = active_fishing_sessions

        self.fish_again_btn = discord.ui.Button(
            label="Fish Again", style=discord.ButtonStyle.green
        )
        self.fish_again_btn.callback = self.fish_again_button
        self.add_item(self.fish_again_btn)
        self.message = None

    async def on_timeout(self):
        self.active_fishing_sessions.discard(self.user_id)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            await self.message.edit(
                content="Button timed out/Cooldown Finished", view=self
            )

    async def fish_again_button(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return

        self.clicks += 1

        if self.clicks >= 100:
            self.fish_again_btn.disabled = True
            self.correct_color = random.choice(["Red", "Green", "Blue"])
            self.add_color_buttons()
            await interaction.response.edit_message(
                content=f"Pick **{self.correct_color}** to fish again!", view=self
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

    def add_color_buttons(self):
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
            for item in self.children[:]:
                if isinstance(item, discord.ui.Button) and item.label != "Fish Again":
                    self.remove_item(item)
            self.fish_again_btn.disabled = False
            self.clicks = 0
            await interaction.response.edit_message(
                content="✅ Correct! You can fish again.", view=self
            )
        else:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            await interaction.response.edit_message(
                content="❌ Wrong color! Cooldown Started.", view=self
            )


class Fishing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_fishing_sessions = set()

    @app_commands.command(name="fish", description="Fish for money")
    async def fish(self, interaction: discord.Interaction):
        if interaction.user.id in self.active_fishing_sessions:
            await interaction.response.send_message(
                "You're already fishing or in cooldown!", ephemeral=True
            )
            return

        await interaction.response.defer()
        fished_item, value, current_xp, xp_gained, next_level_xp, new_balance = (
            await perform_fishing(self.bot, interaction.user.id)
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
        self.active_fishing_sessions.add(interaction.user.id)

        view = FishAgainView(
            self.bot, interaction.user.id, self.active_fishing_sessions
        )
        view.message = await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Fishing(bot))
