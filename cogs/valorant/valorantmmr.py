import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import aiohttp
import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands, tasks
from utils.valorant_helpers import convert_to_datetime, get_rank_value

VAL_KEY = os.getenv("VAL_KEY")


class ValorantMMRHistory(commands.Cog):
    """Valorant MMR History"""

    def __init__(self, bot):
        self.bot = bot
        self.cached_players = {}  # Changed to a dictionary
        self.cached_leaderboard = None
        self.last_leaderboard_update = None
        self.rate_semaphore = asyncio.Semaphore(5)
        self.periodic_mmr_update_loop.start()

    async def cog_load(self):
        await self.load_cached_players()

    async def cog_unload(self):
        self.update_task.cancel()

    @tasks.loop(hours=1)
    async def periodic_mmr_update_loop(self):
        self.bot.logger.info("Starting MMR update cycle...")

        players = await self.bot.database.players_db.get_all_player_mmr()

        # Counters for logging purposes
        updated_players = 0
        skipped_players = 0
        skipped_details = []

        for i in range(0, len(players), 5):
            batch = players[i : i + 5]

            # Filter only players whose last update was more than 10 minutes ago
            eligible_batch = []
            for player in batch:
                last_updated = player.get("last_updated")

                if last_updated is None:
                    eligible_batch.append(player)
                    continue

                try:
                    # If the DB returns a string (e.g. "2025-05-14 17:30:00"), parse it
                    if isinstance(last_updated, str):
                        last_updated = datetime.fromisoformat(last_updated)

                    # Compare to current UTC time
                    if datetime.utcnow() - last_updated > timedelta(minutes=10):
                        eligible_batch.append(player)
                    else:
                        skipped_players += 1
                        skipped_details.append(
                            f"{player['name']}#{player['tag']} (Last updated: {last_updated})"
                        )
                except Exception as e:
                    self.bot.logger.warning(
                        f"Error parsing timestamp for {player['name']}#{player['tag']}: {e}"
                    )
                    skipped_players += 1
                    skipped_details.append(
                        f"{player['name']}#{player['tag']} (Error parsing timestamp)"
                    )

            if not eligible_batch:
                await asyncio.sleep(60)
                continue

            # Fetch MMR data concurrently for eligible players
            fetch_tasks = [
                self.fetch_player_mmr(player["name"], player["tag"])
                for player in eligible_batch
            ]
            results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

            for player, result in zip(eligible_batch, results):
                name, tag = player["name"], player["tag"]

                if isinstance(result, Exception):
                    self.bot.logger.warning(
                        f"Error fetching MMR for {name}#{tag}: {result}"
                    )
                    continue

                if result and "rank" in result and "elo" in result:
                    self.cached_players[(name, tag)] = result
                    try:
                        await self.bot.database.players_db.save_player(
                            name=name,
                            tag=tag,
                            rank=result["rank"],
                            elo=result["elo"],
                        )
                        updated_players += 1
                        self.bot.logger.info(f"Updated MMR for {name}#{tag}")
                    except Exception as e:
                        self.bot.logger.error(
                            f"Failed to update DB for {name}#{tag}: {e}"
                        )

            await asyncio.sleep(60)  # Wait 60s between batches

        # Log the results
        self.bot.logger.info(
            f"Finished MMR update cycle. Updated: {updated_players}, Skipped: {skipped_players}"
        )
        if skipped_players > 0:
            self.bot.logger.info(
                f"Skipped players due to recent update: {', '.join(skipped_details)}"
            )

    async def load_cached_players(self):
        """Load cached players when cog is loaded"""
        mmr_data = await self.bot.database.players_db.get_all_player_mmr()
        self.cached_players = {
            (d["name"], d["tag"]): d for d in mmr_data
        }  # Storing data in cached_players
        self.bot.logger.info(f"Cached {len(mmr_data)} Valorant players.")

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

    async def fetch_player_mmr(self, name: str, tag: str, region: str = "na"):
        async with self.rate_semaphore:
            data = await self.get_player_mmr(name.lower(), tag.lower(), region)
            if data and "data" in data:
                current = data["data"].get("current", {})
                rank = current.get("tier", {}).get("name", "Unknown")
                elo = current.get("rr", 0)

                # Log if fetching new data
                self.bot.logger.info(
                    f"Fetching {name}#{tag} from API. Rank: {rank}, Elo: {elo}"
                )  # Update the last fetched time
                return {"name": name, "tag": tag, "rank": rank, "elo": elo}
            # Log if failed to fetch data
            self.bot.logger.error(f"Failed to fetch data for {name}#{tag}.")

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
        if not self.cached_players:
            return []

        unique_names = sorted(
            set(
                name
                for name, _ in self.cached_players.keys()
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
                for n, tag in self.cached_players.keys()
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

        current = mmr_data["data"].get("current", {})
        current_rank = current.get("tier", {}).get("name", "Unknown")
        current_rr = current.get("rr", 0)
        shields = current.get("rank_protection_shields", 0)

        # Save the player data in the cache if not already there
        self.cached_players[(name, tag)] = {
            "rank": current_rank,
            "elo": current_rr,
        }  # Store data in cached_players
        await self.bot.database.players_db.save_player(
            name=name, tag=tag, rank=current_rank, elo=current_rr
        )

        history = history_data["data"].get("history", [])
        if not history:
            return await interaction.followup.send(
                f"No match history found for {name}#{tag}."
            )

        time_limit = datetime.now(timezone.utc) - timedelta(hours=time)
        recent_matches = [
            m for m in history if convert_to_datetime(m["date"]) >= time_limit
        ]
        earlier_match = next(
            (m for m in history if convert_to_datetime(m["date"]) < time_limit), None
        )
        if not recent_matches:
            current = mmr_data["data"].get("current", {})
            current_rank = current.get("tier", {}).get("name", "Unknown")
            current_rr = current.get("rr", 0)

            embed = discord.Embed(
                title=f"Current Rank and RR for {name}#{tag}",
                description="No recent matches found in the selected time range.",
                color=discord.Color.blue(),
            )
            embed.add_field(name="Current Rank", value=current_rank, inline=True)
            embed.add_field(name="Current RR", value=str(current_rr), inline=True)

            return await interaction.followup.send(embed=embed)

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

        embed = discord.Embed(
            title=f"MMR history for {name}#{tag} (last {time} hours)",
            description="Here is a summary of your recent matches.",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Total Matches", value=str(total_matches), inline=True)
        embed.add_field(name="Wins", value=str(wins), inline=True)
        embed.add_field(name="Losses/Draws", value=f"{losses}/{draws}", inline=True)
        embed.add_field(
            name="Win/Loss Ratio", value=f"{int(win_loss_ratio * 100)}%", inline=True
        )
        embed.add_field(
            name="Total RR Change", value=f"{total_rr_change} RR", inline=True
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Starting Rank", value=starting_rank, inline=True)
        embed.add_field(name="Starting RR", value=str(starting_elo % 100), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Current Rank", value=current_rank, inline=True)
        embed.add_field(name="Current RR", value=str(current_rr), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(
            name="Match History (Latest → Oldest)", value=grouped_matches, inline=False
        )
        embed.add_field(name="Total Shields", value=str(shields), inline=True)

        start_time = convert_to_datetime(recent_matches[-1]["date"])
        end_time = convert_to_datetime(recent_matches[0]["date"])

        embed.add_field(
            name="First Match Start Time",
            value=discord.utils.format_dt(start_time, style="t"),  # Full timestamp
            inline=True,
        )
        embed.add_field(
            name="Most Recent Match Start Time",
            value=discord.utils.format_dt(end_time, style="t"),
            inline=True,
        )

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="valorantleaderboard", description="View the Valorant leaderboard."
    )
    @app_commands.describe(
        name="Player's username to look up their rank", tag="Player's tag"
    )
    @app_commands.autocomplete(name=name_autocomplete, tag=tag_autocomplete)
    async def valorant_leaderboard(
        self,
        interaction: discord.Interaction,
        name: Optional[str] = None,
        tag: Optional[str] = None,
    ):
        await interaction.response.defer()

        # Build leaderboard
        leaderboard_data = [
            {
                "name": n,
                "tag": t,
                "rank": p["rank"],
                "elo": p["elo"],
            }
            for (n, t), p in self.cached_players.items()
        ]

        # Sort from best to worst
        leaderboard_data.sort(
            key=lambda x: (get_rank_value(x["rank"]), x["elo"]), reverse=True
        )

        # If searching for a player
        if name and tag:
            name, tag = name.lower(), tag.lower()
            for index, player in enumerate(leaderboard_data):
                if player["name"].lower() == name and player["tag"].lower() == tag:
                    embed = discord.Embed(
                        title=f"{name}#{tag} Leaderboard Placement",
                        description=(
                            f"**Rank:** {player['rank']}\n"
                            f"**Elo:** {player['elo']}\n"
                            f"**Position:** #{index + 1} out of {len(leaderboard_data)}"
                        ),
                        color=discord.Color.gold(),
                    )
                    return await interaction.followup.send(embed=embed)

            # Not found
            return await interaction.followup.send(
                f"{name}#{tag} was not found in the leaderboard cache."
            )

        # Default to paginated leaderboard
        view = ValorantLeaderboardView(leaderboard_data, interaction)
        embed = view.generate_embed()
        await interaction.followup.send(embed=embed, view=view)


class ValorantLeaderboardView(discord.ui.View):
    def __init__(self, data: List[dict], interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.data = data
        self.interaction = interaction
        self.page = 0
        self.entries_per_page = 10
        self.max_page = (len(data) - 1) // self.entries_per_page

        self.prev_button.disabled = True
        if self.max_page == 0:
            self.next_button.disabled = True

    def generate_embed(self) -> discord.Embed:
        start = self.page * self.entries_per_page
        end = start + self.entries_per_page
        leaderboard_slice = self.data[start:end]

        leaderboard_str = "\n".join(
            f"{i}. {p['name']}#{p['tag']} - {p['rank']} - {p['elo']} Elo"
            for i, p in enumerate(leaderboard_slice, start=start + 1)
        )

        embed = discord.Embed(
            title=f"Valorant Leaderboard (Page {self.page + 1}/{self.max_page + 1})",
            description=leaderboard_str or "No data available.",
            color=discord.Color.red(),
        )
        return embed

    @discord.ui.button(label="⬅ Previous", style=discord.ButtonStyle.gray)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.interaction.user:
            return await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
            )

        self.page -= 1
        self.next_button.disabled = False
        self.prev_button.disabled = self.page == 0

        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="➡ Next", style=discord.ButtonStyle.gray)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.interaction.user:
            return await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
            )

        self.page += 1
        self.prev_button.disabled = False
        self.next_button.disabled = self.page == self.max_page

        await interaction.response.edit_message(embed=self.generate_embed(), view=self)


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantMMRHistory(bot))
