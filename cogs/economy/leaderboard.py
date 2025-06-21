from typing import List

import discord
from discord import app_commands
from discord.ext import commands
from utils.formatting import format_number


class LeaderboardView(discord.ui.View):
    def __init__(
        self, data: List[dict], leaderboard_type: str, interaction: discord.Interaction
    ):
        super().__init__(timeout=60)
        # Filter to only include members still in the guild
        self.data = [
            row
            for row in data
            if (member := interaction.guild.get_member(row["user_id"]))
            and not member.bot
        ]
        self.leaderboard_type = leaderboard_type
        self.interaction = interaction
        self.page = 0
        self.entries_per_page = 10
        self.max_page = (len(data) - 1) // self.entries_per_page

        self.prev_button.disabled = True  # Initially disable prev
        if self.max_page == 0:
            self.next_button.disabled = True

    def generate_embed(self) -> discord.Embed:
        start = self.page * self.entries_per_page
        end = start + self.entries_per_page
        leaderboard_slice = self.data[start:end]

        leaderboard_str = ""
        for i, row in enumerate(leaderboard_slice, start=start + 1):
            user_id = row["user_id"]
            user = self.interaction.guild.get_member(user_id)
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
        if interaction.user != self.interaction.user:
            await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
            )
            return

        self.page -= 1
        if self.page == 0:
            button.disabled = True
        self.next_button.disabled = False

        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="➡ Next", style=discord.ButtonStyle.gray)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
            )
            return

        self.page += 1
        if self.page == self.max_page:
            button.disabled = True
        self.prev_button.disabled = False

        await interaction.response.edit_message(embed=self.generate_embed(), view=self)


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
