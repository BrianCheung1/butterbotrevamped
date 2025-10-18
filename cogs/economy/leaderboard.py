import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import discord
from discord import app_commands
from logger import setup_logger
from utils.base_cog import BaseGameCog
from utils.formatting import format_number

logger = setup_logger("Leaderboard")


class LeaderboardView(discord.ui.View):
    def __init__(
        self,
        data: List[dict],
        leaderboard_type: str,
        interaction: Optional[discord.Interaction] = None,
        *,
        open_access: bool = False,
        guild: Optional[discord.Guild] = None,
        timeout: float = 300,
    ):
        super().__init__(timeout=timeout)
        self.guild = guild or (interaction.guild if interaction else None)

        # Filter to only include members still in the guild if guild is known
        if self.guild:
            self.data = [
                row
                for row in data
                if (member := self.guild.get_member(row["user_id"])) and not member.bot
            ]
        else:
            self.data = data

        self.leaderboard_type = leaderboard_type
        self.interaction = interaction
        self.page = 0
        self.entries_per_page = 10
        self.max_page = (
            (len(self.data) - 1) // self.entries_per_page if self.data else 0
        )
        self.open_access = open_access

        self.prev_button.disabled = True
        if self.max_page == 0:
            self.next_button.disabled = True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.interaction:
            try:
                await self.interaction.edit_original_response(view=self)
            except discord.HTTPException:
                pass

    def generate_embed(self) -> discord.Embed:
        start = self.page * self.entries_per_page
        end = start + self.entries_per_page
        leaderboard_slice = self.data[start:end]

        leaderboard_str = ""
        for i, row in enumerate(leaderboard_slice, start=start + 1):
            user_id = row["user_id"]
            user = self.guild.get_member(user_id) if self.guild else None
            username = (
                user.nick
                if user and user.nick
                else (user.name if user else f"User {user_id}")
            )

            if self.leaderboard_type == "mining_level":
                leaderboard_str += f"{i}. {username} - Level {row['mining_level']} (XP: {row['mining_xp']})\n"
            elif self.leaderboard_type == "fishing_level":
                leaderboard_str += f"{i}. {username} - Level {row['fishing_level']} (XP: {row['fishing_xp']})\n"
            elif self.leaderboard_type == "balance":
                leaderboard_str += (
                    f"{i}. {username} - ${format_number(row['balance'])}\n"
                )
            elif self.leaderboard_type == "bank_balance":
                leaderboard_str += (
                    f"{i}. {username} - Bank ${format_number(row['bank_balance'])}\n"
                )

        embed = discord.Embed(
            title=f"{self.leaderboard_type.replace('_', ' ').title()} Leaderboard (Page {self.page + 1}/{self.max_page + 1})",
            description=leaderboard_str or "No data available.",
            color=discord.Color.blue(),
        )
        return embed

    @discord.ui.button(label="⬅ Previous", style=discord.ButtonStyle.gray)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not self.open_access and interaction.user != getattr(
            self.interaction, "user", None
        ):
            await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
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
        if not self.open_access and interaction.user != getattr(
            self.interaction, "user", None
        ):
            await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
            )
            return

        self.page = min(self.page + 1, self.max_page)
        self.next_button.disabled = self.page == self.max_page
        self.prev_button.disabled = False

        await interaction.response.edit_message(embed=self.generate_embed(), view=self)


class Leaderboard(BaseGameCog):
    def __init__(self, bot):
        super().__init__(bot)
        self.leaderboard_types = [
            "balance",
            "mining_level",
            "fishing_level",
            "bank_balance",
        ]
        self.daily_leaderboard_task = self.bot.loop.create_task(
            self.start_daily_leaderboard_loop()
        )

    def cog_unload(self):
        if self.daily_leaderboard_task:
            self.daily_leaderboard_task.cancel()

    async def start_daily_leaderboard_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            now = datetime.now(timezone.utc)
            next_midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            wait_seconds = (next_midnight - now).total_seconds()

            logger.info(
                f"Sleeping {wait_seconds:.0f}s until next 12:00 AM UTC broadcast"
            )

            await asyncio.sleep(wait_seconds)

            try:
                await self.send_daily_leaderboards()
                logger.info("Daily leaderboard sent.")
            except Exception as e:
                logger.error(f"Failed to send leaderboard: {e}")

            await asyncio.sleep(1)

    async def send_daily_leaderboards(self):
        for guild in self.bot.guilds:
            channel_id = await self.bot.database.guild_db.get_channel(
                guild_id=guild.id,
                channel_type="leaderboard_announcements_channel_id",
            )
            if not channel_id:
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            for lb_type in self.leaderboard_types:
                data = await self.bot.database.get_leaderboard_data(lb_type)
                view = LeaderboardView(
                    data,
                    lb_type,
                    interaction=None,
                    open_access=True,
                    guild=guild,
                    timeout=86400,
                )

                embed = view.generate_embed()
                try:
                    await channel.send(embed=embed, view=view)
                except Exception as e:
                    logger.error(
                        f"Failed to send leaderboard to channel {channel_id} in guild {guild.id}: {e}"
                    )

    @app_commands.command(name="leaderboard", description="View the leaderboard")
    @app_commands.choices(
        leaderboard_type=[
            app_commands.Choice(name="Balance", value="balance"),
            app_commands.Choice(name="Mining Level", value="mining_level"),
            app_commands.Choice(name="Fishing Level", value="fishing_level"),
            app_commands.Choice(name="Bank Balance", value="bank_balance"),
        ]
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        leaderboard_type: app_commands.Choice[str],
    ) -> None:
        await interaction.response.defer()

        leaderboard_data = await self.bot.database.get_leaderboard_data(
            leaderboard_type.value
        )

        view = LeaderboardView(leaderboard_data, leaderboard_type.value, interaction)
        embed = view.generate_embed()

        await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
