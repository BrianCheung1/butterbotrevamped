import random

import discord
from constants.steal_config import (BASE_SUCCESS_RATE, EXTRA_WEALTH_CAP,
                                    EXTRA_WEALTH_MULTIPLIER,
                                    LARGE_BALANCE_MULTIPLIER,
                                    LARGE_BALANCE_THRESHOLD,
                                    MIN_BALANCE_TO_STEAL, STEAL_AMOUNT_RANGE,
                                    STEAL_COOLDOWN, STOLEN_FROM_COOLDOWN,
                                    THEFT_TIER_WEIGHTS, THEFT_TIERS,
                                    WEALTH_FACTOR_CAP, WEALTH_MULTIPLIER,
                                    StealEventType)
from discord import app_commands
from utils.base_cog import BaseGameCog
from utils.cooldown import get_cooldown_response
from utils.formatting import format_number
from utils.pagination import PaginatedView
from utils.steal_helpers import (calculate_lost_amount,
                                 calculate_steal_success_rate,
                                 calculate_stolen_amount)


class StealStatusView(PaginatedView):
    """Paginated view for steal cooldown status."""

    def generate_embed(self) -> discord.Embed:
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

        return discord.Embed(
            title=f"🕒 Steal Cooldowns (Page {self.page + 1}/{self.max_page + 1})",
            description="\n".join(lines) or "No active cooldowns.",
            color=discord.Color.orange(),
        )


class Steal(BaseGameCog):
    """Steal from other players with risk/reward mechanics."""

    async def _check_cooldowns(
        self, thief_id: int, target_id: int, interaction: discord.Interaction
    ) -> bool:
        """Check if either player is on cooldown."""
        target_stats = dict(
            (await self.bot.database.steal_db.get_user_steal_stats(target_id))[
                "steal_stats"
            ]
        )
        thief_stats = dict(
            (await self.bot.database.steal_db.get_user_steal_stats(thief_id))[
                "steal_stats"
            ]
        )

        if target_stats.get("last_stolen_from_at"):
            msg = get_cooldown_response(
                target_stats["last_stolen_from_at"],
                STOLEN_FROM_COOLDOWN,
                f"{interaction.user.mention} was stolen from recently. Try again ",
            )
            if msg:
                await interaction.response.send_message(msg, ephemeral=True)
                return True

        if thief_stats.get("last_stole_from_other_at"):
            msg = get_cooldown_response(
                thief_stats["last_stole_from_other_at"],
                STEAL_COOLDOWN,
                "You just tried stealing! Try again ",
            )
            if msg:
                await interaction.response.send_message(msg, ephemeral=True)
                return True

        return False

    @app_commands.command(name="steal", description="Steal from another user")
    async def steal(self, interaction: discord.Interaction, user: discord.User):
        """Attempt to steal from another user."""
        thief_id = interaction.user.id
        target_id = user.id

        # Validation checks
        if await self.check_self_transaction(thief_id, target_id, interaction):
            return
        if await self.check_bot_target(user, interaction):
            return
        if await self.check_blackjack_conflict(thief_id, interaction):
            return

        if target_id in self.bot.active_blackjack_players:
            await interaction.response.send_message(
                "Target is currently in a Blackjack game!",
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
                content=f"{user.mention} has only ${format_number(target_balance)} but needs ${format_number(MIN_BALANCE_TO_STEAL)} to steal from!"
            )
            return

        if thief_balance < MIN_BALANCE_TO_STEAL:
            await interaction.edit_original_response(
                content=f"You need ${format_number(MIN_BALANCE_TO_STEAL)} to steal!"
            )
            return

        # Check cooldowns
        if await self._check_cooldowns(thief_id, target_id, interaction):
            return

        # Get buffs
        thief_buffs = await self.bot.database.buffs_db.get_buffs(thief_id)
        target_buffs = await self.bot.database.buffs_db.get_buffs(target_id)

        # Calculate success rate
        base_rate, buffed_rate, final_rate = calculate_steal_success_rate(
            target_balance,
            thief_buffs,
            target_buffs,
            BASE_SUCCESS_RATE,
            WEALTH_MULTIPLIER,
            EXTRA_WEALTH_MULTIPLIER,
            WEALTH_FACTOR_CAP,
            EXTRA_WEALTH_CAP,
        )

        base_rate_pct = round(base_rate * 100, 1)
        final_rate_pct = round(final_rate * 100, 1)

        # Determine outcome
        success = random.random() < final_rate

        if success:
            stolen_amount = calculate_stolen_amount(
                target_balance,
                THEFT_TIERS,
                THEFT_TIER_WEIGHTS,
                LARGE_BALANCE_THRESHOLD,
                LARGE_BALANCE_MULTIPLIER,
            )

            # Use new BaseGameCog method
            await self.transfer_balance(
                target_id, thief_id, stolen_amount, "STEAL_SUCCESS"
            )

            await self.bot.database.steal_db.set_user_steal_stats(
                thief_id, stolen_amount, StealEventType.STEAL_SUCCESS
            )
            await self.bot.database.steal_db.set_user_steal_stats(
                target_id, stolen_amount, StealEventType.VICTIM_SUCCESS
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
            lost_amount = calculate_lost_amount(thief_balance, STEAL_AMOUNT_RANGE)

            # Use new BaseGameCog method
            await self.transfer_balance(thief_id, target_id, lost_amount, "STEAL_FAIL")

            await self.bot.database.steal_db.set_user_steal_stats(
                thief_id, lost_amount, StealEventType.STEAL_FAIL
            )
            await self.bot.database.steal_db.set_user_steal_stats(
                target_id, lost_amount, StealEventType.VICTIM_FAIL
            )

            percent_lost = lost_amount / thief_balance * 100 if thief_balance > 0 else 0
            embed = discord.Embed(
                title="🚨 Theft Failed!",
                description=(
                    f"You got caught stealing from {user.mention}!\n"
                    f"You lost **${format_number(lost_amount)}** ({percent_lost:.2f}%)"
                ),
                color=discord.Color.red(),
            )

        embed.set_footer(text=f"Base rate: {base_rate_pct}% → Final: {final_rate_pct}%")
        await interaction.edit_original_response(embed=embed)

    @app_commands.command(name="steal-status", description="Check steal cooldowns")
    async def steal_status(self, interaction: discord.Interaction) -> None:
        """View steal cooldown status for active users."""
        await interaction.response.defer()

        raw_data = await self.bot.database.steal_db.get_all_steal_stats()
        filtered_data = [
            row
            for row in raw_data
            if (member := interaction.guild.get_member(row["user_id"]))
            and not member.bot
        ]

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


async def setup(bot):
    await bot.add_cog(Steal(bot))
