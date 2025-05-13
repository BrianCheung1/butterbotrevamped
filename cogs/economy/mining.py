import asyncio
import random
from time import time

import discord
from constants.mining_config import MINING_RARITY_TIERS
from discord import app_commands
from discord.ext import commands
from utils.buffs import apply_buff
from utils.equips import format_tool_display_name, get_tool_bonus
from utils.formatting import format_number
from utils.work import calculate_work_bonuses


async def perform_mining(bot, user_id):
    # 1. Randomly determine rarity
    rarities, weights = zip(*[(r, d["weight"]) for r, d in MINING_RARITY_TIERS.items()])
    selected_rarity = random.choices(rarities, weights)[0]
    rarity_info = MINING_RARITY_TIERS[selected_rarity]
    mined_item = random.choice(rarity_info["items"])
    base_value = random.randint(*rarity_info["value_range"])
    base_xp = random.randint(5, 10)

    # 2. Buffs
    buffs = await bot.database.buffs_db.get_buffs(user_id)
    xp_gained = int(apply_buff(base_xp, buffs, "exp"))
    buff_bonus_xp = xp_gained - base_xp

    # 3. Buff expiry display
    buff_expiry_str = None
    exp_buff = buffs.get("exp")
    if exp_buff:
        if "expires_at" in exp_buff:
            buff_expiry_str = f"<t:{int(exp_buff['expires_at'].timestamp())}:R>"
        elif "uses_left" in exp_buff:
            buff_expiry_str = f"{exp_buff['uses_left']} uses left"

    # 4. Rare chance tool break
    if random.random() < 0.0002:
        await bot.database.inventory_db.set_equipped_tool(user_id, "pickaxe", None)

    # 5. Tool & stats
    equipped = await bot.database.inventory_db.get_equipped_tools(user_id)
    pickaxe_name = equipped.get("pickaxe")
    tool_bonus_pct = get_tool_bonus(pickaxe_name) if pickaxe_name else 0.0

    # 6. XP + value storage
    current_xp, next_level_xp, level, leveled_up = (
        await bot.database.work_db.set_work_stats(
            user_id, base_value, xp_gained, "mining"
        )
    )

    # 7. Bonuses
    tool_bonus, level_bonus = calculate_work_bonuses(base_value, level, tool_bonus_pct)
    total_value = base_value + tool_bonus + level_bonus

    # 8. Balance update
    prev_balance = await bot.database.user_db.get_balance(user_id)
    new_balance = prev_balance + total_value
    await bot.database.user_db.increment_balance(user_id, total_value)

    return (
        mined_item,
        base_value,
        level_bonus,
        tool_bonus,
        current_xp,
        level,
        next_level_xp,
        prev_balance,
        new_balance,
        pickaxe_name,
        base_xp,
        buff_bonus_xp,
        buff_expiry_str,
        leveled_up,
    )


def create_mining_embed(
    user,
    mined_item,
    value,
    level_bonus,
    tool_bonus,
    current_xp,
    current_level,
    next_level_xp,
    prev_balance,
    new_balance,
    pickaxe_name,
    xp_gained_base,
    buff_bonus_xp,
    buff_expiry_str,
):
    tool_display_name = (
        format_tool_display_name(pickaxe_name) if pickaxe_name else "No tool equipped"
    )
    tool_bonus_pct = get_tool_bonus(pickaxe_name) * 100 if pickaxe_name else 0.0
    level_bonus_pct = current_level * 5

    embed = discord.Embed(
        title=f"⛏️ {user.display_name}'s Mining Results",
        description=f"You mined a **{mined_item}** worth **${format_number(value)}**!",
        color=discord.Color.green(),
    )

    embed.add_field(name="💰 Prev Balance", value=f"${prev_balance:,}", inline=True)
    embed.add_field(name="💰 New Balance", value=f"${new_balance:,}", inline=True)
    embed.add_field(
        name="💰 Total Earned", value=f"${new_balance - prev_balance:,}", inline=True
    )

    # XP info with buff bonus
    xp_line = f"LVL: {current_level} | XP: {current_xp}/{next_level_xp}"
    if buff_bonus_xp > 0:
        xp_line += f"\n📊 Gained: {xp_gained_base} + {buff_bonus_xp} (buff)"

    embed.add_field(name="🔹 XP Progress", value=xp_line, inline=True)

    # Level & Tool Bonus
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


class MineAgainView(discord.ui.View):
    def __init__(self, bot, user_id, active_mining_sessions, cooldowns, failures):
        super().__init__(timeout=300)
        self.bot = bot
        self.user_id = user_id
        self.clicks = 0
        self.click_threshold = random.randint(20, 30)
        self.correct_color = None
        self.colors_added = False
        self.mine_again_btn = discord.ui.Button(
            label="Mine Again", style=discord.ButtonStyle.green
        )
        self.mine_again_btn.callback = self.mine_again_button
        self.add_item(self.mine_again_btn)
        self.active_mining_sessions = active_mining_sessions
        self.cooldowns = cooldowns
        self.failures = failures
        self.captcha_active = False
        self.lock = asyncio.Lock()

    async def on_timeout(self):
        self.active_mining_sessions.pop(self.user_id, None)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if hasattr(self, "message_id") and self.channel:
            try:
                message = await self.channel.fetch_message(self.message_id)
                await message.edit(content="Button timed out", view=self)
            except discord.HTTPException:
                self.bot.logger.error("Mining message expired or missing")

    async def mine_again_button(self, interaction: discord.Interaction):
        async with self.lock:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message(
                    "You cannot use this button.", ephemeral=True
                )
                return

            await interaction.response.defer()

            if self.captcha_active:
                self.bot.logger.error("Captcha Active")
                return

            self.clicks += 1

            if self.clicks >= self.click_threshold:
                if self.colors_added:
                    self.bot.logger.error("Colors Already Added")
                    return
                self.correct_color = random.choice(["Red", "Green", "Blue"])
                self.add_color_buttons()
                self.mine_again_btn.disabled = True
                self.captcha_active = True
                self.colors_added = True
                await interaction.edit_original_response(
                    content=f"Pick **{self.correct_color}** to mine again!", view=self
                )
                return

            (
                mined_item,
                value,
                level_bonus,
                tool_bonus,
                current_xp,
                current_level,
                next_level_xp,
                prev_balance,
                new_balance,
                pickaxe_name,
                xp_gained_base,
                buff_bonus_xp,
                buff_expiry_str,
                leveled_up,
            ) = await perform_mining(self.bot, self.user_id)

            embed = create_mining_embed(
                interaction.user,
                mined_item,
                value,
                level_bonus,
                tool_bonus,
                current_xp,
                current_level,
                next_level_xp,
                prev_balance,
                new_balance,
                pickaxe_name,
                xp_gained_base,
                buff_bonus_xp,
                buff_expiry_str,
            )
            if leveled_up:
                await interaction.followup.send(
                    f"🎉 {interaction.user.mention} leveled up to **Mining Level {current_level}**!",
                )
            await interaction.edit_original_response(embed=embed, view=self)

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
        await interaction.response.defer()
        if chosen_color == self.correct_color:
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.label != "Mine Again":
                    self.remove_item(item)
            self.colors_added = False
            self.captcha_active = False
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

            await interaction.edit_original_response(
                content="❌ Wrong color! Cooldown Started.", view=self
            )
            self.captcha_active = False
            now = time()
            self.failures[self.user_id] = self.failures.get(self.user_id, 0) + 1
            penalty = 300 * self.failures[self.user_id]
            self.cooldowns[self.user_id] = now + penalty
            self.active_mining_sessions.pop(self.user_id, None)


class Mining(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_mining_sessions = {}
        self.cooldowns = {}
        self.failures = {}

    @app_commands.command(name="mine", description="Mine ores for money")
    async def mine(self, interaction: discord.Interaction):
        """
        Command to perform mining and get a random item with its value.

        :param interaction: The interaction object from Discord.
        """
        if interaction.user.id in self.active_mining_sessions:
            previous_message = self.active_mining_sessions[interaction.user.id]
            link = previous_message.jump_url
            await interaction.response.send_message(
                f"You are already mining. [Jump to your previous mining message.]({link})",
            )
            return
        now = time()
        user_id = interaction.user.id
        if user_id in self.cooldowns and now < self.cooldowns[user_id]:
            remaining = int(self.cooldowns[user_id] - now)
            await interaction.response.send_message(
                f"⏳ You're on cooldown for another {remaining} seconds.",
            )
            return

        await interaction.response.defer()

        # Perform the mining logic
        (
            mined_item,
            value,
            level_bonus,
            tool_bonus,
            current_xp,
            current_level,
            next_level_xp,
            prev_balance,
            new_balance,
            pickaxe_name,
            xp_gained_base,
            buff_bonus_xp,
            buff_expiry_str,
            leveled_up,
        ) = await perform_mining(self.bot, interaction.user.id)

        # Create the embed with pickaxe_name
        embed = create_mining_embed(
            interaction.user,
            mined_item,
            value,
            level_bonus,
            tool_bonus,
            current_xp,
            current_level,
            next_level_xp,
            prev_balance,
            new_balance,
            pickaxe_name,
            xp_gained_base,
            buff_bonus_xp,
            buff_expiry_str,
        )
        if leveled_up:
            await interaction.followup.send(
                f"🎉 {interaction.user.mention} leveled up to **Mining Level {current_level}**!",
                ephemeral=False,
            )
        view = MineAgainView(
            self.bot,
            interaction.user.id,
            self.active_mining_sessions,
            self.cooldowns,
            self.failures,
        )
        view.message = await interaction.followup.send(embed=embed, view=view)
        self.active_mining_sessions[interaction.user.id] = view.message
        view.message_id = view.message.id
        view.channel = interaction.channel


async def setup(bot):
    await bot.add_cog(Mining(bot))
