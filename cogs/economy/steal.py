import datetime
import random
from enum import Enum
from typing import List, Tuple

import discord
from constants.steal_config import StealEventType
from discord import app_commands
from utils.base_cog import BaseGameCog
from utils.cooldown import get_cooldown_response
from utils.formatting import format_number

# ============ CONSTANTS ============

STEAL_COOLDOWN = datetime.timedelta(hours=1)
STOLEN_FROM_COOLDOWN = datetime.timedelta(hours=3)
MIN_BALANCE_TO_STEAL = 100_000
BASE_SUCCESS_RATE = 0.5
STEAL_AMOUNT_RANGE = (0.1, 0.2)

# Wealth multipliers
WEALTH_FACTOR_CAP = 500_000
WEALTH_MULTIPLIER = 0.25
EXTRA_WEALTH_CAP = 10_000_000
EXTRA_WEALTH_MULTIPLIER = 0.1


# Theft tiers with weights (rarity distribution)
class TheftTier(Enum):
    """Theft amount tiers based on rarity."""

    COMMON = (0.05, 0.075, 85)  # (low, high, weight)
    UNCOMMON = (0.075, 0.10, 10)
    RARE = (0.10, 0.15, 4)
    SUPER_RARE = (0.15, 0.20, 1)


THEFT_TIERS = [
    (TheftTier.COMMON.value[0], TheftTier.COMMON.value[1]),
    (TheftTier.UNCOMMON.value[0], TheftTier.UNCOMMON.value[1]),
    (TheftTier.RARE.value[0], TheftTier.RARE.value[1]),
    (TheftTier.SUPER_RARE.value[0], TheftTier.SUPER_RARE.value[1]),
]
THEFT_TIER_WEIGHTS = [
    TheftTier.COMMON.value[2],
    TheftTier.UNCOMMON.value[2],
    TheftTier.RARE.value[2],
    TheftTier.SUPER_RARE.value[2],
]

LARGE_BALANCE_THRESHOLD = 1_000_000
LARGE_BALANCE_MULTIPLIER = 0.1


# ============ HELPER FUNCTIONS ============


def calculate_wealth_factors(balance: int) -> Tuple[float, float]:
    """Calculate wealth-based success rate multipliers."""
    wealth_factor = min(balance / WEALTH_FACTOR_CAP, 1)
    extra_wealth_factor = min(balance / EXTRA_WEALTH_CAP, 1)
    return wealth_factor, extra_wealth_factor


def apply_buff_multiplier(base_value: float, buffs: dict, buff_key: str) -> float:
    """Apply buff multiplier to a value."""
    buff = buffs.get(buff_key)
    if not buff:
        return base_value
    return base_value * buff.get("multiplier", 1.0)


def calculate_steal_success_rate(
    target_balance: int, thief_buffs: dict, target_buffs: dict
) -> Tuple[float, float, float]:
    """
    Calculate final steal success rate with all modifiers.

    Returns:
        (base_rate, buffed_rate, final_rate)
    """
    wealth_factor, extra_wealth_factor = calculate_wealth_factors(target_balance)
    base_rate = (
        BASE_SUCCESS_RATE
        + WEALTH_MULTIPLIER * wealth_factor
        + EXTRA_WEALTH_MULTIPLIER * extra_wealth_factor
    )

    # Apply thief buff
    buffed_rate = apply_buff_multiplier(base_rate, thief_buffs, "steal_success")

    # Apply target resistance buff
    final_rate = apply_buff_multiplier(buffed_rate, target_buffs, "steal_resistance")

    return base_rate, buffed_rate, final_rate


def calculate_stolen_amount(target_balance: int) -> int:
    """Calculate amount stolen on successful steal."""
    low, high = random.choices(THEFT_TIERS, weights=THEFT_TIER_WEIGHTS, k=1)[0]
    percent = random.uniform(low, high)

    # Reduce steal % for very wealthy targets
    if target_balance > LARGE_BALANCE_THRESHOLD:
        percent *= LARGE_BALANCE_MULTIPLIER

    stolen_amount = max(1, int(target_balance * percent))
    return min(stolen_amount, target_balance)


def calculate_lost_amount(thief_balance: int) -> int:
    """Calculate amount lost on failed steal."""
    lost_amount = int(thief_balance * random.uniform(*STEAL_AMOUNT_RANGE))
    return min(lost_amount, thief_balance)


async def check_cooldowns(
    bot, thief_id: int, target_id: int, interaction: discord.Interaction
) -> bool:
    """
    Check if either player is on cooldown.
    Returns True if cooldown exists (error), False if clear to proceed.
    """
    target_stats = dict(
        (await bot.database.steal_db.get_user_steal_stats(target_id))["steal_stats"]
    )
    thief_stats = dict(
        (await bot.database.steal_db.get_user_steal_stats(thief_id))["steal_stats"]
    )

    last_stolen_from_at = target_stats.get("last_stolen_from_at")
    last_stole_from_other_at = thief_stats.get("last_stole_from_other_at")

    if last_stolen_from_at:
        msg = get_cooldown_response(
            last_stolen_from_at,
            STOLEN_FROM_COOLDOWN,
            f"{interaction.user.mention} was stolen from recently. Try again ",
        )
        if msg:
            await interaction.response.send_message(msg, ephemeral=True)
            return True

    if last_stole_from_other_at:
        msg = get_cooldown_response(
            last_stole_from_other_at,
            STEAL_COOLDOWN,
            "You just tried stealing! Try again ",
        )
        if msg:
            await interaction.response.send_message(msg, ephemeral=True)
            return True

    return False


async def process_steal_success(
    bot, thief_id: int, target_id: int, target_balance: int, stolen_amount: int
) -> None:
    """Handle successful steal - update balances and stats."""
    await bot.database.user_db.increment_balance(thief_id, stolen_amount)
    await bot.database.user_db.increment_balance(target_id, -stolen_amount)
    await bot.database.steal_db.set_user_steal_stats(
        thief_id, stolen_amount, StealEventType.STEAL_SUCCESS
    )
    await bot.database.steal_db.set_user_steal_stats(
        target_id, stolen_amount, StealEventType.VICTIM_SUCCESS
    )


async def process_steal_failure(
    bot, thief_id: int, target_id: int, thief_balance: int, lost_amount: int
) -> None:
    """Handle failed steal - update balances and stats."""
    await bot.database.user_db.increment_balance(target_id, lost_amount)
    await bot.database.user_db.increment_balance(thief_id, -lost_amount)
    await bot.database.steal_db.set_user_steal_stats(
        thief_id, lost_amount, StealEventType.STEAL_FAIL
    )
    await bot.database.steal_db.set_user_steal_stats(
        target_id, lost_amount, StealEventType.VICTIM_FAIL
    )


# ============ COGS ============


class Steal(BaseGameCog):
    """Steal from other players with risk/reward mechanics."""

    @app_commands.command(name="steal", description="Steal from another user")
    async def steal(self, interaction: discord.Interaction, user: discord.User):
        """Attempt to steal from another user."""
        thief_id = interaction.user.id
        target_id = user.id

        # Validation checks (using BaseGameCog helpers)
        if await self.check_self_transaction(thief_id, target_id, interaction):
            return

        if await self.check_bot_target(user, interaction):
            return

        if await self.check_blackjack_conflict(thief_id, interaction):
            return

        if target_id in self.bot.active_blackjack_players:
            await interaction.response.send_message(
                "Target is currently in a Blackjack game! Please try again later",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        # Fetch balances
        target_balance = await self.get_balance(target_id)
        thief_balance = await self.get_balance(thief_id)

        # Validate minimum balances
        if target_balance < MIN_BALANCE_TO_STEAL:
            await interaction.edit_original_response(
                content=f"{user.mention} has only ${format_number(target_balance)} but needs at least ${format_number(MIN_BALANCE_TO_STEAL)} to be stolen from!"
            )
            return

        if thief_balance < MIN_BALANCE_TO_STEAL:
            await interaction.edit_original_response(
                content=f"You have only ${format_number(thief_balance)} but need at least ${format_number(MIN_BALANCE_TO_STEAL)} to steal!"
            )
            return

        # Check cooldowns
        if await check_cooldowns(self.bot, thief_id, target_id, interaction):
            return

        # Get buffs
        thief_buffs = await self.bot.database.buffs_db.get_buffs(thief_id)
        target_buffs = await self.bot.database.buffs_db.get_buffs(target_id)

        # Calculate success rate
        base_rate, buffed_rate, final_rate = calculate_steal_success_rate(
            target_balance, thief_buffs, target_buffs
        )
        base_rate_pct = round(base_rate * 100, 1)
        final_rate_pct = round(final_rate * 100, 1)

        # Determine outcome
        success = random.random() < final_rate

        if success:
            stolen_amount = calculate_stolen_amount(target_balance)
            await process_steal_success(
                self.bot, thief_id, target_id, target_balance, stolen_amount
            )

            percent_stolen = stolen_amount / target_balance * 100
            embed = discord.Embed(
                title="💰 Theft Success!",
                description=(
                    f"You stole **${format_number(stolen_amount)}** from {user.mention}!\n"
                    f"({percent_stolen:.2f}% of their balance)"
                ),
                color=discord.Color.green(),
            )
        else:
            lost_amount = calculate_lost_amount(thief_balance)
            await process_steal_failure(
                self.bot, thief_id, target_id, thief_balance, lost_amount
            )

            percent_lost = lost_amount / thief_balance * 100 if thief_balance > 0 else 0
            embed = discord.Embed(
                title="🚨 Theft Failed!",
                description=(
                    f"You tried to steal from {user.mention} and got caught! "
                    f"You lost **${format_number(lost_amount)}**.\n"
                    f"({percent_lost:.2f}% of your balance)"
                ),
                color=discord.Color.red(),
            )

        embed.set_footer(
            text=f"Base success rate: {base_rate_pct}%, Final with buffs: {final_rate_pct}%"
        )

        await interaction.edit_original_response(embed=embed)

    @app_commands.command(name="steal-status", description="Check all active cooldowns")
    async def steal_status(self, interaction: discord.Interaction) -> None:
        """View steal cooldown status for all users."""
        await interaction.response.defer()
        raw_data = await self.bot.database.steal_db.get_all_steal_stats()
        filtered_data = [
            row
            for row in raw_data
            if (member := interaction.guild.get_member(row["user_id"]))
            and not member.bot
        ]

        # Filter to only those with active cooldowns
        active_cooldowns = [
            row
            for row in filtered_data
            if row.get("last_stolen_from_at")
            and get_cooldown_response(
                row["last_stolen_from_at"], STOLEN_FROM_COOLDOWN, ""
            )
        ]

        view = StealStatusView(active_cooldowns, interaction)
        embed = view.generate_embed()

        await interaction.followup.send(embed=embed, view=view)


class StealStatusView(discord.ui.View):
    """Paginated view for steal cooldown status."""

    def __init__(self, data: List[dict], interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.data = data
        self.interaction = interaction
        self.page = 0
        self.entries_per_page = 10
        self.max_page = max(0, (len(data) - 1) // self.entries_per_page)

        self.prev_button.disabled = True
        if self.max_page <= 0:
            self.next_button.disabled = True

    def generate_embed(self) -> discord.Embed:
        """Generate embed for current page."""
        start = self.page * self.entries_per_page
        end = start + self.entries_per_page
        slice_data = self.data[start:end]

        lines = []

        for i, row in enumerate(slice_data, start=start):
            user_id = row["user_id"]
            user = self.interaction.guild.get_member(user_id)

            if user and row.get("last_stolen_from_at"):
                cooldown_msg = get_cooldown_response(
                    row["last_stolen_from_at"],
                    STOLEN_FROM_COOLDOWN,
                    f"{i + 1}. {user.mention} can be stolen from ",
                )
                if cooldown_msg:
                    lines.append(cooldown_msg)

        embed = discord.Embed(
            title=f"🕒 Steal Cooldowns (Page {self.page + 1}/{self.max_page + 1})",
            description="\n".join(lines) or "No active cooldowns.",
            color=discord.Color.orange(),
        )
        return embed

    @discord.ui.button(label="⬅ Previous", style=discord.ButtonStyle.gray)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Previous page button."""
        if interaction.user != self.interaction.user:
            await interaction.response.send_message(
                "You're not allowed to control this pagination.", ephemeral=True
            )
            return

        self.page = max(self.page - 1, 0)
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = False
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="➡ Next", style=discord.ButtonStyle.gray)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Next page button."""
        if interaction.user != self.interaction.user:
            await interaction.response.send_message(
                "You're not allowed to control this pagination.", ephemeral=True
            )
            return

        self.page = min(self.page + 1, self.max_page)
        self.next_button.disabled = self.page == self.max_page
        self.prev_button.disabled = False
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)


async def setup(bot):
    await bot.add_cog(Steal(bot))
