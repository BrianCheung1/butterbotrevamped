import random
import time

import discord
from constants.fishing_config import FISHING_RARITY_TIERS
from discord import app_commands
from discord.ext import commands
from utils.equips import format_tool_display_name, get_tool_bonus
from utils.formatting import format_number


async def perform_fishing(bot, user_id):
    start_time = time.time()

    # Weighted random selection of rarity
    rarities, weights = zip(
        *[(rarity, info["weight"]) for rarity, info in FISHING_RARITY_TIERS.items()]
    )
    selected_rarity = random.choices(rarities, weights, k=1)[0]
    rarity_info = FISHING_RARITY_TIERS[selected_rarity]
    fished_item = random.choice(rarity_info["items"])
    value = random.randint(*rarity_info["value_range"])
    xp_gained_base = random.randint(5, 10)

    # Get buffs
    buffs = await bot.database.buffs_db.get_buffs(user_id)
    buff = buffs.get("exp")
    buff_bonus_xp = 0
    buff_expiry_str = None

    if buff:
        multiplier = buff["multiplier"]
        xp_gained = int(xp_gained_base * multiplier)
        buff_bonus_xp = xp_gained - xp_gained_base

        if "expires_at" in buff:
            expires_at_ts = int(buff["expires_at"].timestamp())
            buff_expiry_str = f"<t:{expires_at_ts}:R>"
        elif "uses_left" in buff:
            buff_expiry_str = f"{buff['uses_left']} uses left"
    else:
        xp_gained = xp_gained_base

    # Get equipped tools
    equipped_tools = await bot.database.inventory_db.get_equipped_tools(user_id)
    fishingrod_name = equipped_tools.get("fishingrod")

    # Update stats
    current_xp, next_level_xp, current_level = (
        await bot.database.work_db.set_work_stats(user_id, value, xp_gained, "fishing")
    )

    # Calculate bonuses
    bonus_pct = get_tool_bonus(fishingrod_name) if fishingrod_name else 0.0
    tool_bonus = int(value * bonus_pct)
    level_bonus = int((current_level * 0.05) * value)

    # Final value to credit
    total_value = value + level_bonus + tool_bonus
    balance = await bot.database.user_db.get_balance(user_id)
    prev_balance = balance
    new_balance = balance + total_value
    # await bot.database.user_db.set_balance(user_id, new_balance)
    await bot.database.user_db.increment_balance(user_id, total_value)

    db_operation_time = time.time() - start_time
    # bot.logger.info(f"Database operation took {db_operation_time:.4f} seconds")

    return (
        fished_item,
        value,
        level_bonus,
        tool_bonus,
        current_xp,
        current_level,
        next_level_xp,
        prev_balance,
        new_balance,
        fishingrod_name,
        xp_gained_base,
        buff_bonus_xp,
        buff_expiry_str,
    )


def create_fishing_embed(
    user,
    fished_item,
    value,
    level_bonus,
    tool_bonus,
    current_xp,
    current_level,
    next_level_xp,
    prev_balance,
    new_balance,
    fishingrod_name,
    xp_gained_base,
    buff_bonus_xp,
    buff_expiry_str,
):
    """
    Generate an embed for the fishing result with level bonus as percentage and tool used.
    """
    # Extract tool name from the equipped fishing rod (e.g., "Wooden Rod" for "rod_wooden")
    tool_display_name = (
        format_tool_display_name(fishingrod_name)
        if fishingrod_name
        else "No tool equipped"
    )

    # Calculate level bonus percentage
    level_bonus_pct = (
        current_level * 5
    )  # Level bonus as percentage (assuming 5% per level)

    # Calculate tool bonus as percentage
    tool_bonus_pct = get_tool_bonus(fishingrod_name) * 100 if fishingrod_name else 0.0

    embed = discord.Embed(
        title=f"🎣 {user.display_name}'s Fishing Results",
        description=f"You fished a **{fished_item}** worth **${format_number(value)}**!",
        color=discord.Color.green(),
    )

    # Add fields to the embed
    # embed.add_field(
    #     name="💰 New Balance", value=f"${format_number(new_balance)}", inline=True
    # )
    embed.add_field(name="💰 Prev Balance", value=f"${prev_balance:,}", inline=True)
    embed.add_field(name="💰 New Balance", value=f"${new_balance:,}", inline=True)
    embed.add_field(
        name="💰 Total Earned", value=f"${new_balance-prev_balance:,}", inline=True
    )
    # XP info with buff bonus
    xp_line = f"LVL: {current_level} | XP: {current_xp}/{next_level_xp}"
    if buff_bonus_xp > 0:
        xp_line += f"\n📊 Gained: {xp_gained_base} + {buff_bonus_xp} (buff)"

    embed.add_field(name="🔹 XP Progress", value=xp_line, inline=True)
    embed.add_field(
        name="📈 Level Bonus",
        value=f"${format_number(level_bonus)} ({level_bonus_pct}% from level {current_level})",
        inline=True,
    )
    # Buff info
    if buff_bonus_xp > 0:
        embed.add_field(
            name="⏳ XP Buff Status",
            value=buff_expiry_str or "Active",
            inline=True,
        )
    else:
        embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(
        name="🛠️ Tool Used",
        value=f"{tool_display_name}",
        inline=True,
    )
    embed.add_field(
        name="🔧 Tool Bonus",
        value=f"${format_number(tool_bonus)} ({int(tool_bonus_pct)}%)",
        inline=True,
    )
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    return embed


class FishAgainView(discord.ui.View):
    def __init__(self, bot, user_id, active_fishing_sessions):
        super().__init__(timeout=1800)
        self.bot = bot
        self.user_id = user_id
        self.clicks = 0
        self.click_threshold = random.randint(20, 30)
        self.correct_color = None
        self.colors_added = False
        self.fish_again_btn = discord.ui.Button(
            label="Fish Again", style=discord.ButtonStyle.green
        )
        self.fish_again_btn.callback = self.fish_again_button
        self.add_item(self.fish_again_btn)
        self.active_fishing_sessions = active_fishing_sessions

    async def on_timeout(self):
        self.active_fishing_sessions.pop(self.user_id, None)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if hasattr(self, "message_id") and self.channel:
            try:
                message = await self.channel.fetch_message(self.message_id)
                await message.edit(
                    content="Button timed out / Cooldown Finished", view=self
                )
            except discord.HTTPException:
                self.bot.logger.error("Fishing message expired or missing")

    async def fish_again_button(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return

        await interaction.response.defer()

        self.clicks += 1

        if self.clicks >= self.click_threshold:
            if self.colors_added:
                return
            self.colors_added = True
            self.fish_again_btn.disabled = True
            self.correct_color = random.choice(["Red", "Green", "Blue"])
            self.add_color_buttons()
            await interaction.edit_original_response(
                content=f"Pick **{self.correct_color}** to fish again!", view=self
            )
            return

        (
            fished_item,
            value,
            level_bonus,
            tool_bonus,
            current_xp,
            current_level,
            next_level_xp,
            prev_balance,
            new_balance,
            fishingrod_name,
            xp_gained_base,
            buff_bonus_xp,
            buff_expiry_str,
        ) = await perform_fishing(self.bot, self.user_id)

        embed = create_fishing_embed(
            interaction.user,
            fished_item,
            value,
            level_bonus,
            tool_bonus,
            current_xp,
            current_level,
            next_level_xp,
            prev_balance,
            new_balance,
            fishingrod_name,
            xp_gained_base,
            buff_bonus_xp,
            buff_expiry_str,
        )

        await interaction.edit_original_response(embed=embed, view=self)

    def add_color_buttons(self):
        # for item in self.children[:]:
        # if isinstance(item, discord.ui.Button) and item.label in {
        #     "Red",
        #     "Green",
        #     "Blue",
        # }:
        #     self.remove_item(item)
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
            self.colors_added = False
            self.fish_again_btn.disabled = False
            self.clicks = 0
            self.click_threshold = 200
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
        self.active_fishing_sessions = {}

    @app_commands.command(name="fish", description="Fish for money")
    async def fish(self, interaction: discord.Interaction):
        if interaction.user.id in self.active_fishing_sessions:
            previous_message = self.active_fishing_sessions[interaction.user.id]
            link = previous_message.jump_url
            await interaction.response.send_message(
                f"You are already fishing or on a cooldown. [Jump to your previous fishing message.]({link})",
            )
            return

        await interaction.response.defer()
        (
            fished_item,
            value,
            level_bonus,
            tool_bonus,
            current_xp,
            current_level,
            next_level_xp,
            prev_balance,
            new_balance,
            fishingrod_name,
            xp_gained_base,
            buff_bonus_xp,
            buff_expiry_str,
        ) = await perform_fishing(self.bot, interaction.user.id)

        embed = create_fishing_embed(
            interaction.user,
            fished_item,
            value,
            level_bonus,
            tool_bonus,
            current_xp,
            current_level,
            next_level_xp,
            prev_balance,
            new_balance,
            fishingrod_name,
            xp_gained_base,
            buff_bonus_xp,
            buff_expiry_str,
        )
        view = FishAgainView(
            self.bot, interaction.user.id, self.active_fishing_sessions
        )
        view.message = await interaction.followup.send(embed=embed, view=view)
        self.active_fishing_sessions[interaction.user.id] = view.message
        view.message_id = view.message.id
        view.channel = interaction.channel


async def setup(bot):
    await bot.add_cog(Fishing(bot))
