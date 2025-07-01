from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import discord

from utils.buffs import apply_buff
from utils.equips import format_tool_display_name, get_tool_bonus
from utils.formatting import format_number


@dataclass
class MiningResult:
    mined_item: str
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
    pickaxe_name: Optional[str]
    buff_expiry_str: Optional[str]
    leveled_up: bool


@dataclass
class FishingResult:
    fished_item: str
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
    fishingrod_name: Optional[str]
    buff_expiry_str: Optional[str]
    leveled_up: bool


def calculate_value_bonuses(base_value, level, tool_bonus_pct, pet_bonus_pct=0.0):
    level_bonus = int(base_value * (level * 0.05))
    tool_bonus = int(base_value * tool_bonus_pct)
    pet_bonus = int(base_value * pet_bonus_pct)
    total_value = base_value + level_bonus + tool_bonus + pet_bonus
    return level_bonus, tool_bonus, pet_bonus, total_value


def calculate_xp_bonuses(base_xp, buffs, pet_xp_pct=0.0):
    xp_with_buffs = int(apply_buff(base_xp, buffs, "exp"))
    buff_bonus_xp = xp_with_buffs - base_xp
    pet_bonus_xp = int(xp_with_buffs * pet_xp_pct)
    total_xp = xp_with_buffs + pet_bonus_xp
    return buff_bonus_xp, pet_bonus_xp, total_xp


def create_work_embed(user, result, work_type: str):
    # work_type = "Mining" or "Fishing"
    tool_name_attr = "pickaxe_name" if work_type == "Mining" else "fishingrod_name"
    item_name_attr = "mined_item" if work_type == "Mining" else "fished_item"

    tool_name = getattr(result, tool_name_attr, None)
    tool_display_name = (
        format_tool_display_name(tool_name) if tool_name else "No tool equipped"
    )
    tool_bonus_pct = get_tool_bonus(tool_name) * 100 if tool_name else 0.0
    level_bonus_pct = result.current_level * 5

    embed = discord.Embed(
        title=f"{'⛏️' if work_type == 'Mining' else '🎣'} {user.display_name}'s {work_type} Results",
        description=f"You {('mined' if work_type == 'Mining' else 'fished')} a **{getattr(result, item_name_attr)}** worth **${format_number(result.base_value)}**!",
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

    embed.add_field(name="🛠️ Tool Used", value=tool_display_name, inline=True)
    embed.add_field(
        name="🔧 Tool Bonus",
        value=f"${format_number(result.tool_bonus)} ({int(tool_bonus_pct)}%)",
        inline=True,
    )
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    return embed
