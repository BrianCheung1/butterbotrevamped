import asyncio
import random
from enum import Enum
from time import time

import discord
from constants.fishing_config import FISHING_RARITY_TIERS
from constants.mining_config import MINING_RARITY_TIERS
from discord import app_commands
from utils.base_cog import BaseGameCog
from utils.equips import get_tool_bonus
from utils.work import (
    FishingResult,
    MiningResult,
    calculate_value_bonuses,
    calculate_xp_bonuses,
    create_work_embed,
)


class WorkType(Enum):
    """Enum for work types."""

    MINING = "mining"
    FISHING = "fishing"


WORK_CONFIG = {
    WorkType.MINING: {
        "rarity_tiers": MINING_RARITY_TIERS,
        "tool_type": "pickaxe",
        "result_class": MiningResult,
        "embed_title": "Mining",
    },
    WorkType.FISHING: {
        "rarity_tiers": FISHING_RARITY_TIERS,
        "tool_type": "fishingrod",
        "result_class": FishingResult,
        "embed_title": "Fishing",
    },
}


async def perform_work(bot, user_id, work_type: WorkType):
    """Execute a single work action (mining or fishing)."""
    config = WORK_CONFIG[work_type]
    rarity_tiers = config["rarity_tiers"]
    tool_type = config["tool_type"]
    result_class = config["result_class"]

    # Step 1: Random rarity/item
    rarities, weights = zip(*[(r, d["weight"]) for r, d in rarity_tiers.items()])
    selected_rarity = random.choices(rarities, weights)[0]
    rarity_info = rarity_tiers[selected_rarity]
    work_item = random.choice(rarity_info["items"])
    base_value = random.randint(*rarity_info["value_range"])
    base_xp = random.randint(5, 10)

    # Step 2: Buffs
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
    buff_bonus_xp, pet_bonus_xp, total_xp_gained = calculate_xp_bonuses(base_xp, buffs)

    # Step 5: Update XP and level
    current_xp, next_level_xp, level, leveled_up = (
        await bot.database.work_db.set_work_stats(
            user_id, base_value, total_xp_gained, work_type.value
        )
    )

    # Step 6: Calculate value bonuses
    level_bonus, tool_bonus, pet_bonus, total_value = calculate_value_bonuses(
        base_value, level, tool_bonus_pct
    )

    # Step 7: Update balance
    cog = bot.cogs.get("Work")
    prev_balance = await cog.get_balance(user_id)
    new_balance = prev_balance + total_value
    await cog.add_balance(user_id, total_value)

    return result_class(
        work_item,
        base_value,
        level_bonus,
        tool_bonus,
        pet_bonus,
        total_value,
        base_xp,
        buff_bonus_xp,
        pet_bonus_xp,
        total_xp_gained,
        current_xp,
        next_level_xp,
        level,
        prev_balance,
        new_balance,
        tool_name,
        buff_expiry_str,
        leveled_up,
    )


def create_work_result_embed(user, result, work_type: WorkType):
    """Create work result embed."""
    config = WORK_CONFIG[work_type]
    return create_work_embed(user, result, config["embed_title"])


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
        self.work_btn = discord.ui.Button(
            label=button_label, style=discord.ButtonStyle.green
        )
        self.work_btn.callback = self.work_again_button
        self.add_item(self.work_btn)

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
                self.add_color_buttons()
                self.work_btn.disabled = True
                self.captcha_active = True
                await interaction.edit_original_response(
                    content=f"Pick **{self.correct_color}** to continue!", view=self
                )
                return

            result = await perform_work(self.bot, self.user_id, self.work_type)
            embed = create_work_result_embed(interaction.user, result, self.work_type)
            if result.leveled_up:
                work_name = "Mining" if self.work_type == WorkType.MINING else "Fishing"
                await interaction.followup.send(
                    f"🎉 {interaction.user.mention} leveled up to **{work_name} Level {result.current_level}**!"
                )

            await interaction.edit_original_response(embed=embed, view=self)

    def add_color_buttons(self):
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
        session_key = f"{self.user_id}_{self.work_type.value}"
        self.active_sessions.pop(session_key, None)
        try:
            message = await self.channel.fetch_message(self.message_id)
            work_name = "Mining" if self.work_type == WorkType.MINING else "Fishing"
            await message.edit(content=f"{work_name} timed out", embed=None, view=None)
        except Exception:
            pass


class Work(BaseGameCog):
    """Combined mining and fishing work cog."""

    def __init__(self, bot):
        super().__init__(bot)
        self.active_sessions = {}
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
        work_name = "Mining" if work_type == WorkType.MINING else "Fishing"

        if user_id in self.active_sessions:
            link = self.active_sessions[user_id].jump_url
            await interaction.response.send_message(
                f"You are already {work_name.lower()}. [Jump]({link})"
            )
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
        embed = create_work_result_embed(interaction.user, result, work_type)

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
        # Store session with work type key to avoid mixing mining and fishing
        session_key = f"{user_id}_{work_type.value}"
        self.active_sessions[session_key] = view.message


async def setup(bot):
    await bot.add_cog(Work(bot))
