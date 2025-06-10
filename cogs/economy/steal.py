import datetime
import json
import random
from typing import List

import discord
from constants.steal_config import StealEventType
from discord import app_commands
from discord.ext import commands
from utils.buffs import apply_buff
from utils.cooldown import get_cooldown_response
from utils.formatting import format_number


class Steal(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="steal", description="Steal from another user")
    async def steal(self, interaction: discord.Interaction, user: discord.User):
        if user == interaction.user:
            await interaction.response.send_message(
                "You cannot steal from yourself.", ephemeral=True
            )
            return

        target_id = user.id
        thief_id = interaction.user.id
        if (
            target_id in self.bot.active_blackjack_players
            or thief_id in self.bot.active_blackjack_players
        ):
            await interaction.response.send_message(
                "You or target is currently in a Blackjack game! Please try agian later",
                ephemeral=True,
            )
            return

        STEAL_COOLDOWN = datetime.timedelta(hours=1)
        STOLEN_FROM_COOLDOWN = datetime.timedelta(hours=6)
        MIN_BALANCE_TO_STEAL = 100_000
        STEAL_SUCCESS_RATE = 0.5
        STEAL_AMOUNT_RANGE = (0.1, 0.2)

        # Fetch balances and stats
        target_balance = await self.bot.database.user_db.get_balance(target_id)
        thief_balance = await self.bot.database.user_db.get_balance(thief_id)

        if target_balance <= MIN_BALANCE_TO_STEAL:
            await interaction.response.send_message(
                f"{user.mention} has no money to steal!", ephemeral=True
            )
            return

        if thief_balance <= MIN_BALANCE_TO_STEAL:
            await interaction.response.send_message(
                "You have no money to steal!", ephemeral=True
            )
            return

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

        last_stolen_from_at = target_stats.get("last_stolen_from_at")
        last_stole_from_other_at = thief_stats.get("last_stole_from_other_at")

        if last_stolen_from_at:
            msg = get_cooldown_response(
                last_stolen_from_at,
                STOLEN_FROM_COOLDOWN,
                f"{user.mention} was stolen from recently. Try again ",
            )
            if msg:
                await interaction.response.send_message(msg, ephemeral=True)
                return

        if last_stole_from_other_at:
            msg = get_cooldown_response(
                last_stole_from_other_at,
                STEAL_COOLDOWN,
                "You just tried stealing! Try again ",
            )
            if msg:
                await interaction.response.send_message(msg, ephemeral=True)
                return
        wealth_factor = min(target_balance / 500_000, 1)
        more_wealth_factor = min(target_balance / 10_000_000, 1)
        target_buffs = await self.bot.database.buffs_db.get_buffs(target_id)
        thief_buffs = await self.bot.database.buffs_db.get_buffs(thief_id)
        base_rate = STEAL_SUCCESS_RATE + 0.25 * wealth_factor + 0.1 * more_wealth_factor

        # Apply thief buff
        buffed_rate = apply_buff(base_rate, thief_buffs, "steal_success")

        # Apply target resistance buff
        final_rate = apply_buff(buffed_rate, target_buffs, "steal_resistance")
        self.bot.logger.info(final_rate)
        # Determine outcome
        success = random.random() < final_rate
        base_rate_pct = round(base_rate * 100, 1)
        final_rate_pct = round(final_rate * 100, 1)

        if success:
            tiers = [
                (0.05, 0.075),  # Common
                (0.075, 0.10),  # Uncommon
                (0.10, 0.15),  # Rare
                (0.15, 0.20),  # Super rare
            ]
            weights = [85, 10, 4, 1]  # Adjust to taste — total = 100

            # Choose a tier based on weight
            low, high = random.choices(tiers, weights=weights, k=1)[0]

            # Choose a percent within that tier
            percent = random.uniform(low, high)
            if target_balance > 10_000_000:
                percent *= 0.1
            stolen_amount = max(1, int(target_balance * percent))
            stolen_amount = min(stolen_amount, target_balance)

            # await self.bot.database.user_db.set_balance(
            #     thief_id, thief_balance + stolen_amount
            # )
            await self.bot.database.user_db.increment_balance(thief_id, stolen_amount)
            # await self.bot.database.user_db.set_balance(
            #     target_id, target_balance - stolen_amount
            # )
            await self.bot.database.user_db.increment_balance(target_id, -stolen_amount)

            await self.bot.database.steal_db.set_user_steal_stats(
                thief_id, stolen_amount, StealEventType.STEAL_SUCCESS
            )
            await self.bot.database.steal_db.set_user_steal_stats(
                target_id, stolen_amount, StealEventType.VICTIM_SUCCESS
            )

            embed = discord.Embed(
                title="💰 Theft Success!",
                description=f"You stole **${format_number(stolen_amount)}** from {user.mention}!",
                color=discord.Color.green(),
            )
        else:
            lost_amount = int(thief_balance * random.uniform(*STEAL_AMOUNT_RANGE))
            lost_amount = min(lost_amount, thief_balance)

            # await self.bot.database.user_db.set_balance(
            #     thief_id, thief_balance - lost_amount
            # )
            await self.bot.database.user_db.increment_balance(target_id, lost_amount)
            await self.bot.database.user_db.increment_balance(thief_id, -lost_amount)

            await self.bot.database.steal_db.set_user_steal_stats(
                thief_id, lost_amount, StealEventType.STEAL_FAIL
            )
            await self.bot.database.steal_db.set_user_steal_stats(
                target_id, lost_amount, StealEventType.VICTIM_FAIL
            )

            embed = discord.Embed(
                title="🚨 Theft Failed!",
                description=f"You tried to steal from {user.mention} and got caught! You lost **${format_number(lost_amount)}**.",
                color=discord.Color.red(),
            )
        embed.set_footer(
            text=f"Base success rate: {base_rate_pct}%, Final with buffs: {final_rate_pct}%"
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="stealstatus", description="Check all active cooldowns")
    async def steal_status(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer()
        raw_data = await self.bot.database.steal_db.get_all_steal_stats()
        filtered_data = [
            row for row in raw_data if interaction.guild.get_member(row["user_id"])
        ]

        STOLEN_FROM_COOLDOWN = datetime.timedelta(hours=6)

        stealstatus_data = []

        for row in filtered_data:
            if row.get("last_stolen_from_at"):
                msg = get_cooldown_response(
                    row["last_stolen_from_at"],
                    STOLEN_FROM_COOLDOWN,
                    "",
                )
                if msg:  # Ensure msg is not None
                    stealstatus_data.append(row)

        view = StealStatusView(stealstatus_data, interaction)
        embed = view.generate_embed()

        await interaction.followup.send(embed=embed, view=view)


class StealStatusView(discord.ui.View):
    def __init__(self, data: List[dict], interaction: discord.Interaction):
        super().__init__(timeout=60)
        # Filter to only include members still in the guild
        self.data = data
        self.interaction = interaction
        self.page = 0
        self.entries_per_page = 10
        self.max_page = max(0, (len(data) - 1) // self.entries_per_page)

        self.prev_button.disabled = True
        if self.max_page <= 0:
            self.next_button.disabled = True

    def generate_embed(self) -> discord.Embed:
        STOLEN_FROM_COOLDOWN = datetime.timedelta(hours=6)

        start = self.page * self.entries_per_page
        end = start + self.entries_per_page
        slice_data = self.data[start:end]

        lines = []

        for i, row in enumerate(slice_data, start=0):
            user_id = row["user_id"]
            user = self.interaction.guild.get_member(user_id)

            if row.get("last_stolen_from_at"):
                msg = get_cooldown_response(
                    row["last_stolen_from_at"],
                    STOLEN_FROM_COOLDOWN,
                    f"{i}. {user.mention} can be stolen from ",
                )
                if msg:  # Ensure msg is not None
                    lines.append(msg)

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
        if interaction.user != self.interaction.user:
            await interaction.response.send_message(
                "You're not allowed to control this pagination.", ephemeral=True
            )
            return

        self.page -= 1
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = False
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="➡ Next", style=discord.ButtonStyle.gray)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message(
                "You're not allowed to control this pagination.", ephemeral=True
            )
            return

        self.page += 1
        self.next_button.disabled = self.page == self.max_page
        self.prev_button.disabled = False
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)


async def setup(bot):
    await bot.add_cog(Steal(bot))
