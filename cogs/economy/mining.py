import asyncio
import random
from time import time

import discord
from constants.mining_config import MINING_RARITY_TIERS
from discord import app_commands
from discord.ext import commands
from utils.equips import get_tool_bonus
from utils.work import (MiningResult, calculate_value_bonuses,
                        calculate_xp_bonuses, create_work_embed)


async def perform_mining(bot, user_id):
    # Step 1: Random rarity/item
    rarities, weights = zip(*[(r, d["weight"]) for r, d in MINING_RARITY_TIERS.items()])
    selected_rarity = random.choices(rarities, weights)[0]
    rarity_info = MINING_RARITY_TIERS[selected_rarity]
    mined_item = random.choice(rarity_info["items"])
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
    pickaxe_name = equipped.get("pickaxe")
    tool_bonus_pct = get_tool_bonus(pickaxe_name) if pickaxe_name else 0.0

    # Step 5: Calculate XP bonuses
    buff_bonus_xp, pet_bonus_xp, total_xp_gained = calculate_xp_bonuses(base_xp, buffs)

    # Step 6: Update XP and level (to get current level)
    current_xp, next_level_xp, level, leveled_up = (
        await bot.database.work_db.set_work_stats(
            user_id, base_value, total_xp_gained, "mining"
        )
    )

    # Step 7: Calculate value bonuses (now with level available)
    level_bonus, tool_bonus, pet_bonus, total_value = calculate_value_bonuses(
        base_value, level, tool_bonus_pct
    )

    # Step 8: Balance
    prev_balance = await bot.database.user_db.get_balance(user_id)
    new_balance = prev_balance + total_value
    await bot.database.user_db.increment_balance(user_id, total_value)

    return MiningResult(
        mined_item,
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
        pickaxe_name,
        buff_expiry_str,
        leveled_up,
    )


def create_mining_embed(user, result):
    return create_work_embed(user, result, "Mining")


class MineAgainView(discord.ui.View):
    def __init__(self, bot, user_id, active_sessions, cooldowns, failures):
        super().__init__(timeout=900)
        self.bot = bot
        self.user_id = user_id
        self.active_sessions = active_sessions
        self.cooldowns = cooldowns
        self.failures = failures
        self.clicks = 0
        self.click_threshold = random.randint(20, 30)
        self.captcha_active = False
        self.colors_added = False
        self.correct_color = None
        self.lock = asyncio.Lock()

        self.mine_again_btn = discord.ui.Button(
            label="Mine Again", style=discord.ButtonStyle.green
        )
        self.mine_again_btn.callback = self.mine_again_button
        self.add_item(self.mine_again_btn)

    async def mine_again_button(self, interaction: discord.Interaction):
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
                self.mine_again_btn.disabled = True
                self.captcha_active = True
                await interaction.edit_original_response(
                    content=f"Pick **{self.correct_color}** to mine again!", view=self
                )
                return

            result = await perform_mining(self.bot, self.user_id)
            embed = create_mining_embed(interaction.user, result)
            if result.leveled_up:
                await interaction.followup.send(
                    f"🎉 {interaction.user.mention} leveled up to **Mining Level {result.current_level}**!"
                )

            await interaction.edit_original_response(embed=embed, view=self)

    def add_color_buttons(self):
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
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot use this button.", ephemeral=True
            )
            return
        await interaction.response.defer()

        if chosen_color == self.correct_color:
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.label != "Mine Again":
                    self.remove_item(item)
            self.captcha_active = False
            self.colors_added = False
            self.mine_again_btn.disabled = False
            self.clicks = 0
            self.click_threshold = 200
            await interaction.edit_original_response(
                content="✅ Correct! You can mine again.", view=self
            )
        else:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            now = time()
            penalty = 300 * (self.failures.get(self.user_id, 0) + 1)
            self.cooldowns[self.user_id] = now + penalty
            self.active_sessions.pop(self.user_id, None)
            await interaction.edit_original_response(
                content="❌ Wrong color! Cooldown started.", view=self
            )

    async def on_timeout(self):
        self.active_sessions.pop(self.user_id, None)
        try:
            message = await self.channel.fetch_message(self.message_id)
            await message.edit(content="Mining timed out", embed=None, view=None)
        except Exception:
            pass


class Mining(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_sessions = {}
        self.cooldowns = {}
        self.failures = {}

    @app_commands.command(name="mine", description="Mine ores for money")
    async def mine(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        if user_id in self.active_sessions:
            link = self.active_sessions[user_id].jump_url
            await interaction.response.send_message(
                f"You are already mining. [Jump]({link})"
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
        result = await perform_mining(self.bot, user_id)
        embed = create_mining_embed(interaction.user, result)

        if result.leveled_up:
            await interaction.followup.send(
                f"🎉 {interaction.user.mention} leveled up to **Mining Level {result.current_level}**!"
            )

        view = MineAgainView(
            self.bot, user_id, self.active_sessions, self.cooldowns, self.failures
        )
        view.message = await interaction.followup.send(embed=embed, view=view)
        view.message_id = view.message.id
        view.channel = interaction.channel
        self.active_sessions[user_id] = view.message


async def setup(bot):
    await bot.add_cog(Mining(bot))
