import os
import discord
import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from discord import app_commands
from discord.ext import commands
from utils.valorant_helpers import convert_to_datetime
from discord.app_commands import Choice

VAL_KEY = os.getenv("VAL_KEY")


class ValorantMMRHistory(commands.Cog):
    """Valorant MMR History"""

    def __init__(self, bot):
        self.bot = bot
        self.cached_players = (
            set()
        )  # Cache for player names and tags (using set to prevent duplicates)
        self.bot.loop.create_task(
            self.load_cached_players()
        )  # Load cached players asynchronously

    async def load_cached_players(self):
        """Load cached players when cog is loaded"""
        saved_players = await self.bot.database.players_db.get_saved_players()
        self.cached_players = set(
            saved_players
        )  # Convert the list of players to a set to avoid duplicates
        self.bot.logger.info(f"Cached {len(self.cached_players)} Valorant players.")

    async def fetch_val_api(self, url: str, name: str, tag: str) -> Optional[dict]:
        """Handles API requests to HenrikDev API asynchronously using aiohttp."""
        if not VAL_KEY:
            self.bot.logger.error("VAL_KEY is not set in environment variables.")
            return None

        headers = {"Authorization": VAL_KEY}

        try:
            self.bot.logger.info(f"Requesting URL: {url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        self.bot.logger.info(
                            f"Successfully fetched data for {name}#{tag}"
                        )
                        return await response.json()
                    self.bot.logger.error(
                        f"Failed to fetch data for {name}#{tag}. Status: {response.status}"
                    )
        except Exception as e:
            self.bot.logger.error(f"API exception for {name}#{tag}: {e}")
        return None

    async def get_player_mmr_history(
        self, name: str, tag: str, region: str
    ) -> Optional[dict]:
        return await self.fetch_val_api(
            f"https://api.henrikdev.xyz/valorant/v2/mmr-history/{region}/pc/{name}/{tag}",
            name,
            tag,
        )

    async def get_player_mmr(self, name: str, tag: str, region: str) -> Optional[dict]:
        return await self.fetch_val_api(
            f"https://api.henrikdev.xyz/valorant/v3/mmr/{region}/pc/{name}/{tag}",
            name,
            tag,
        )

    async def name_autocomplete(self, interaction: discord.Interaction, current: str):
        # If the cache is still empty, return an empty list
        if not self.cached_players:
            return []

        # Use cached player data (set) for autocomplete
        unique_names = sorted(
            set(
                name
                for name, _ in self.cached_players
                if name.startswith(current.lower())
            )
        )
        return [Choice(name=n, value=n) for n in unique_names[:25]]

    async def tag_autocomplete(self, interaction: discord.Interaction, current: str):
        name = interaction.namespace.name  # what user selected for "name"
        if not self.cached_players:
            return []

        filtered_tags = sorted(
            {
                tag
                for n, tag in self.cached_players
                if n.lower() == name.lower() and tag.startswith(current.lower())
            }
        )
        return [Choice(name=t, value=t) for t in filtered_tags[:25]]

    @app_commands.command(
        name="valorantmmr", description="View a Valorant player's recent MMR history."
    )
    @app_commands.describe(
        name="Player's username",
        tag="Player's tag",
        region="Player's region (e.g. na, eu)",
        time="How far back to look (in hours)",
    )
    @app_commands.autocomplete(name=name_autocomplete, tag=tag_autocomplete)
    async def valorant_mmr_history(
        self,
        interaction: discord.Interaction,
        name: str,
        tag: str,
        time: Optional[int] = 12,
        region: Optional[str] = "na",
    ):
        await interaction.response.defer()
        name, tag, region = name.lower(), tag.lower(), region.lower()

        # Fetch both requests in parallel
        history_data, mmr_data = await asyncio.gather(
            self.get_player_mmr_history(name, tag, region),
            self.get_player_mmr(name, tag, region),
        )

        if not history_data or "data" not in history_data:
            return await interaction.followup.send(
                f"Error fetching MMR history for {name}#{tag}."
            )
        if not mmr_data or "data" not in mmr_data:
            return await interaction.followup.send(
                f"Error fetching current MMR for {name}#{tag}."
            )

        # Save the player data in the cache if not already there
        self.cached_players.add((name, tag))  # Use add() for set, ensures no duplicates
        await self.bot.database.players_db.save_player(name, tag)

        history = history_data["data"].get("history", [])
        if not history:
            return await interaction.followup.send(
                f"No match history found for {name}#{tag}."
            )

        time_limit = datetime.utcnow() - timedelta(hours=time)
        recent_matches = [
            m for m in history if convert_to_datetime(m["date"]) >= time_limit
        ]
        earlier_match = next(
            (m for m in history if convert_to_datetime(m["date"]) < time_limit), None
        )

        if not recent_matches:
            return await interaction.followup.send(
                f"No matches found in the last {time} hours."
            )

        starting_elo = (
            earlier_match["elo"] if earlier_match else recent_matches[-1]["elo"]
        )
        starting_rank = earlier_match["tier"]["name"] if earlier_match else "Unknown"

        ending_elo = recent_matches[0]["elo"]
        total_rr_change = ending_elo - starting_elo

        wins = sum(1 for m in recent_matches if m["last_change"] > 0)
        losses = sum(1 for m in recent_matches if m["last_change"] < 0)
        draws = sum(1 for m in recent_matches if m["last_change"] == 0)
        total_matches = len(recent_matches)
        win_loss_ratio = wins / total_matches if total_matches else 0

        def format_match(m):
            change = m["last_change"]
            emoji = "✅" if change > 0 else "❌" if change < 0 else "➖"
            sign = "+" if change > 0 else ""
            return f"{emoji} ({sign}{change})"

        match_display = [format_match(m) for m in recent_matches[:20]]
        grouped_matches = "\n".join(
            "  ".join(match_display[i : i + 5]) for i in range(0, len(match_display), 5)
        )

        current = mmr_data["data"].get("current", {})
        current_rank = current.get("tier", {}).get("name", "Unknown")
        current_rr = current.get("rr", 0)
        shields = current.get("rank_protection_shields", 0)

        embed = discord.Embed(
            title=f"MMR history for {name}#{tag} (last {time} hours)",
            description="Here is a summary of your recent matches.",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Total Matches", value=str(total_matches), inline=True)
        embed.add_field(name="Wins", value=str(wins), inline=True)
        embed.add_field(name="Losses/Draws", value=f"{losses}/{draws}", inline=True)
        embed.add_field(
            name="Win/Loss Ratio", value=f"{win_loss_ratio:.2f}", inline=True
        )
        embed.add_field(
            name="Total RR Change", value=f"{total_rr_change} RR", inline=True
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Starting Rank", value=starting_rank, inline=True)
        embed.add_field(name="Starting RR", value=str(starting_elo % 100), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Current Rank", value=current_rank, inline=True)
        embed.add_field(name="Current RRR", value=str(current_rr), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(
            name="Match History (Latest → Oldest)", value=grouped_matches, inline=False
        )
        embed.add_field(name="Total Shields", value=str(shields), inline=True)

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantMMRHistory(bot))
