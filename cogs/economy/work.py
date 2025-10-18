import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from time import time
from typing import Optional

import discord
from constants.fishing_config import FISHING_RARITY_TIERS
from constants.mining_config import MINING_RARITY_TIERS
from discord import app_commands
from utils.base_cog import BaseGameCog
from utils.bonus_calculator import (calculate_value_bonuses,
                                    calculate_xp_bonuses)
from utils.equips import format_tool_display_name, get_tool_bonus
from utils.formatting import format_number


class WorkType(Enum):
    """Enum for work types."""

    MINING = "mining"
    FISHING = "fishing"


@dataclass
class WorkResult:
    """Unified result for both mining and fishing."""

    item: str
    base_value: int
    level_bonus: int
    tool_bonus: int
    pet_bonus: int
    total_value: int
    base_xp: int
    buff_bonus_xp: int
    pet_bonus_xp: int
    total_xp: int
    current_xp: int
    next_level_xp: int
    current_level: int
    prev_balance: int
    new_balance: int
    tool_name: Optional[str]
    buff_expiry_str: Optional[str]
    leveled_up: bool


WORK_CONFIG = {
    WorkType.MINING: {
        "rarity_tiers": MINING_RARITY_TIERS,
        "tool_type": "pickaxe",
        "emoji": "⛏️",
    },
    WorkType.FISHING: {
        "rarity_tiers": FISHING_RARITY_TIERS,
        "tool_type": "fishingrod",
        "emoji": "🎣",
    },
}


async def perform_work(bot, user_id, work_type: WorkType) -> WorkResult:
    """Execute a single work action (mining or fishing)."""
    config = WORK_CONFIG[work_type]
    rarity_tiers = config["rarity_tiers"]
    tool_type = config["tool_type"]

    # Step 1: Random rarity/item
    rarities, weights = zip(*[(r, d["weight"]) for r, d in rarity_tiers.items()])
    selected_rarity = random.choices(rarities, weights)[0]
    rarity_info = rarity_tiers[selected_rarity]
    work_item = random.choice(rarity_info["items"])
    base_value = random.randint(*rarity_info["value_range"])
    base_xp = random.randint(5, 10)

    # Step 2: Buffs & buff expiry
    buffs = await bot.database.buffs_db.get_buffs(user_id)
    exp_buff = buffs.get("exp")
    buff_expiry_str = None
    if exp_buff:
        if "expires_at" in exp_buff:
            buff_expiry_str = f"<t:{int(exp_buff['expires_at'].timestamp())}:R>"
        elif "uses_left" in exp_buff:
            buff_expiry_str = f"{exp_buff['uses_left']} uses left"

    # Step 3: Equipped tools
    equipped = await bot.database.inventory_db.get_equipped_tools(user_id)
    tool_name = equipped.get(tool_type)
    tool_bonus_pct = get_tool_bonus(tool_name) if tool_name else 0.0

    # Step 4: Calculate XP bonuses
    buff_bonus_xp, pet_bonus_xp, total_xp = calculate_xp_bonuses(base_xp, buffs)

    # Step 5: Update XP and level
    current_xp, next_level_xp, level, leveled_up = (
        await bot.database.work_db.set_work_stats(
            user_id, base_value, total_xp, work_type.value
        )
    )

    # Step 6: Calculate value bonuses
    level_bonus, tool_bonus, pet_bonus, total_value = calculate_value_bonuses(
        base_value, level, tool_bonus_pct=tool_bonus_pct
    )

    # Step 7: Update balance
    cog = bot.cogs.get("Work")
    prev_balance = await cog.get_balance(user_id)
    await cog.add_balance(user_id, total_value)

    return WorkResult(
        item=work_item,
        base_value=base_value,
        level_bonus=level_bonus,
        tool_bonus=tool_bonus,
        pet_bonus=pet_bonus,
        total_value=total_value,
        base_xp=base_xp,
        buff_bonus_xp=buff_bonus_xp,
        pet_bonus_xp=pet_bonus_xp,
        total_xp=total_xp,
        current_xp=current_xp,
        next_level_xp=next_level_xp,
        current_level=level,
        prev_balance=prev_balance,
        new_balance=prev_balance + total_value,
        tool_name=tool_name,
        buff_expiry_str=buff_expiry_str,
        leveled_up=leveled_up,
    )


def create_work_embed(
    user: discord.User, result: WorkResult, work_type: WorkType
) -> discord.Embed:
    """Create work result embed."""
    config = WORK_CONFIG[work_type]
    work_name = work_type.value.capitalize()
    emoji = config["emoji"]
    past_tense = "mined" if work_type == WorkType.MINING else "fished"

    tool_display = (
        format_tool_display_name(result.tool_name)
        if result.tool_name
        else "No tool equipped"
    )
    tool_bonus_pct = get_tool_bonus(result.tool_name) * 100 if result.tool_name else 0.0
    level_bonus_pct = result.current_level * 5

    embed = discord.Embed(
        title=f"{emoji} {user.display_name}'s {work_name} Results",
        description=f"You {past_tense} a **{result.item}** worth **${format_number(result.base_value)}**!",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="💰 Prev Balance", value=f"${result.prev_balance:,}", inline=True
    )
    embed.add_field(
        name="💰 New Balance", value=f"${result.new_balance:,}", inline=True
    )
    embed.add_field(
        name="💰 Total Earned", value=f"${result.total_value:,}", inline=True
    )

    xp_line = (
        f"LVL: {result.current_level} | XP: {result.current_xp}/{result.next_level_xp}"
    )
    if result.buff_bonus_xp > 0 or result.pet_bonus_xp > 0:
        buffs_display = []
        if result.buff_bonus_xp > 0:
            buffs_display.append(f"{result.buff_bonus_xp} (buff)")
        if result.pet_bonus_xp > 0:
            buffs_display.append(f"{result.pet_bonus_xp} (pet)")
        xp_line += f"\n📊 Gained: {result.base_xp} + {' + '.join(buffs_display)}"

    embed.add_field(name="🔹 XP Progress", value=xp_line, inline=True)
    embed.add_field(
        name="📈 Level Bonus",
        value=f"${format_number(result.level_bonus)} ({level_bonus_pct}% from level {result.current_level})",
        inline=True,
    )

    if result.buff_bonus_xp > 0:
        embed.add_field(
            name="⏳ XP Buff Status",
            value=result.buff_expiry_str or "Active",
            inline=True,
        )
    else:
        embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(name="🛠️ Tool Used", value=tool_display, inline=True)
    embed.add_field(
        name="🔧 Tool Bonus",
        value=f"${format_number(result.tool_bonus)} ({int(tool_bonus_pct)}%)",
        inline=True,
    )
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    return embed


class WorkAgainView(discord.ui.View):
    """Reusable view for mining/fishing continue buttons."""

    def __init__(
        self, bot, user_id, work_type: WorkType, active_sessions, cooldowns, failures
    ):
        super().__init__(timeout=900)
        self.bot = bot
        self.user_id = user_id
        self.work_type = work_type
        self.active_sessions = active_sessions
        self.cooldowns = cooldowns
        self.failures = failures
        self.clicks = 0
        self.click_threshold = random.randint(20, 30)
        self.captcha_active = False
        self.correct_color = None
        self.lock = asyncio.Lock()

        button_label = "Mine Again" if work_type == WorkType.MINING else "Fish Again"
        work_btn = discord.ui.Button(
            label=button_label, style=discord.ButtonStyle.green
        )
        work_btn.callback = self.work_again_button
        self.work_btn = work_btn
        self.add_item(work_btn)

    async def work_again_button(self, interaction: discord.Interaction):
        """Handle work again button."""
        async with self.lock:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message(
                    "You cannot use this button.", ephemeral=True
                )
                return

            if self.captcha_active:
                return await interaction.response.defer()

            self.clicks += 1
            await interaction.response.defer()

            if self.clicks >= self.click_threshold:
                self.correct_color = random.choice(["Red", "Green", "Blue"])
                self._add_color_buttons()
                self.work_btn.disabled = True
                self.captcha_active = True
                await interaction.edit_original_response(
                    content=f"Pick **{self.correct_color}** to continue!", view=self
                )
                return

            result = await perform_work(self.bot, self.user_id, self.work_type)
            embed = create_work_embed(interaction.user, result, self.work_type)
            if result.leveled_up:
                work_name = self.work_type.value.capitalize()
                await interaction.followup.send(
                    f"🎉 {interaction.user.mention} leveled up to **{work_name} Level {result.current_level}**!"
                )

            await interaction.edit_original_response(embed=embed, view=self)

    def _add_color_buttons(self):
        """Add color choice buttons for captcha."""
        for color, style in [
            ("Green", discord.ButtonStyle.green),
            ("Red", discord.ButtonStyle.red),
            ("Blue", discord.ButtonStyle.blurple),
        ]:
            button = discord.ui.Button(label=color, style=style)
            button.callback = lambda i, c=color: asyncio.create_task(
                self.handle_color_choice(i, c)
            )
            self.add_item(button)

    async def handle_color_choice(
        self, interaction: discord.Interaction, chosen_color: str
    ):
        """Handle color choice."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return
        await interaction.response.defer()

        if chosen_color == self.correct_color:
            # Correct choice
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.label not in [
                    "Mine Again",
                    "Fish Again",
                ]:
                    self.remove_item(item)
            self.captcha_active = False
            self.work_btn.disabled = False
            self.clicks = 0
            self.click_threshold = 200
            await interaction.edit_original_response(
                content="✅ Correct! You can continue.", view=self
            )
        else:
            # Wrong choice
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            now = time()
            penalty = 300 * (self.failures.get(self.user_id, 0) + 1)
            self.cooldowns[self.user_id] = now + penalty
            session_key = f"{self.user_id}_{self.work_type.value}"
            self.active_sessions.pop(session_key, None)
            await interaction.edit_original_response(
                content="❌ Wrong color! Cooldown started.", view=self
            )

    async def on_timeout(self):
        """Handle timeout."""
        self.active_sessions[self.work_type].pop(self.user_id, None)
        try:
            message = await self.channel.fetch_message(self.message_id)
            work_name = self.work_type.value.capitalize()
            await message.edit(content=f"{work_name} timed out", embed=None, view=None)
        except Exception:
            pass


class Work(BaseGameCog):
    """Combined mining and fishing work cog."""

    def __init__(self, bot):
        super().__init__(bot)
        self.active_sessions = {"Mining": {}, "Fishing": {}}
        self.cooldowns = {}
        self.failures = {}

    @app_commands.command(name="mine", description="Mine ores for money")
    async def mine(self, interaction: discord.Interaction):
        """Mine command."""
        await self._do_work(interaction, WorkType.MINING)

    @app_commands.command(name="fish", description="Fish for money")
    async def fish(self, interaction: discord.Interaction):
        """Fish command."""
        await self._do_work(interaction, WorkType.FISHING)

    async def _do_work(self, interaction: discord.Interaction, work_type: WorkType):
        """Execute work action (mining or fishing)."""
        user_id = interaction.user.id
        work_name = work_type.value.capitalize()

        if user_id in self.active_sessions[work_name]:
            msg = self.active_sessions[work_name][user_id]
            try:
                await interaction.response.send_message(
                    f"You are already {work_name.lower()}. [Jump to session]({msg.jump_url})",
                    ephemeral=True,
                )
            except Exception as e:
                self.active_sessions.pop(user_id, None)
                self.bot.logger.error(f"Error fetching active session message: {e}")
                await interaction.response.defer()
            else:
                return

        now = time()
        if user_id in self.cooldowns and now < self.cooldowns[user_id]:
            remaining = int(self.cooldowns[user_id] - now)
            await interaction.response.send_message(
                f"⏳ You're on cooldown for another {remaining} seconds."
            )
            return

        await interaction.response.defer()
        result = await perform_work(self.bot, user_id, work_type)
        embed = create_work_embed(interaction.user, result, work_type)

        if result.leveled_up:
            await interaction.followup.send(
                f"🎉 {interaction.user.mention} leveled up to **{work_name} Level {result.current_level}**!"
            )

        view = WorkAgainView(
            self.bot,
            user_id,
            work_type,
            self.active_sessions,
            self.cooldowns,
            self.failures,
        )
        view.message = await interaction.followup.send(embed=embed, view=view)
        view.message_id = view.message.id
        view.channel = interaction.channel

        self.active_sessions[work_name][user_id] = view.message


async def setup(bot):
    await bot.add_cog(Work(bot))
