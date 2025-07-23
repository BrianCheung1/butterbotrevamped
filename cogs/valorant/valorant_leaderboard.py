import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.channels import broadcast_embed_to_guilds  # Import your helper here
from utils.valorant_helpers import (
    get_player_mmr,
    get_rank_value,
    name_autocomplete,
    tag_autocomplete,
)


class ValorantLeaderboard(commands.Cog):
    """Valorant Leaderboard"""

    def __init__(self, bot):
        self.bot = bot
        self.rate_semaphore = asyncio.Semaphore(5)
        self.periodic_mmr_update_loop.start()
        self.daily_leaderboard_task.start()

    def cog_unload(self):
        self.periodic_mmr_update_loop.cancel()
        self.daily_leaderboard_task.cancel()

    @tasks.loop(hours=24)
    async def periodic_mmr_update_loop(self):
        self.bot.logger.info("Starting MMR update cycle...")

        players = await self.bot.database.players_db.get_all_player_mmr()

        updated_players = 0
        skipped_players = 0
        processed_details = []
        skipped_details = []

        for i in range(0, len(players), 5):
            batch = players[i : i + 5]
            self.bot.logger.info(
                f"Processing players {i + 1}-{min(i + len(batch), len(players))} out of {len(players)}"
            )

            eligible_batch = []
            for player in batch:
                last_updated = player.get("last_updated")

                if last_updated is None:
                    eligible_batch.append(player)
                    continue

                try:
                    if isinstance(last_updated, str):
                        last_updated = datetime.fromisoformat(last_updated)

                    if datetime.utcnow() - last_updated >= timedelta(minutes=60):
                        eligible_batch.append(player)
                        processed_details.append(
                            f"{player['name']}#{player['tag']} (Last updated: {last_updated})"
                        )
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
                continue

            fetch_tasks = [
                self.fetch_player_mmr(player["name"], player["tag"])
                for player in eligible_batch
            ]
            results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

            for player, result in zip(eligible_batch, results):
                name, tag = player["name"], player["tag"]

                # Handle 404 (player no longer exists)
                if result == "not_found":
                    self.bot.logger.info(
                        f"Deleting {name}#{tag} from DB (404 not found)."
                    )
                    try:
                        await self.bot.database.players_db.delete_player(name, tag)
                    except Exception as e:
                        self.bot.logger.error(
                            f"Failed to delete {name}#{tag} from DB: {e}"
                        )
                    continue

                if isinstance(result, Exception):
                    self.bot.logger.warning(
                        f"Error fetching MMR for {name}#{tag}: {result}"
                    )
                    continue

                if result and "rank" in result and "elo" in result:
                    self.bot.valorant_players[(name, tag)] = result
                    try:
                        await self.bot.database.players_db.save_player(
                            name=name,
                            tag=tag,
                            rank=result["rank"],
                            elo=result["elo"],
                        )
                        updated_players += 1
                    except Exception as e:
                        self.bot.logger.error(
                            f"Failed to update DB for {name}#{tag}: {e}"
                        )

            if eligible_batch:
                await asyncio.sleep(60)  # wait 60s between batches

        self.bot.logger.info(
            f"Finished MMR update cycle. Updated: {updated_players}, Skipped: {skipped_players} "
        )
        if updated_players > 0:
            self.bot.logger.info(
                f"Updated players due to recent update: {', '.join(processed_details)}"
            )
        if skipped_players > 0:
            self.bot.logger.info(
                f"Skipped players due to recent update: {', '.join(skipped_details)}"
            )

    async def fetch_player_mmr(self, name: str, tag: str, region: str = "na"):
        async with self.rate_semaphore:
            data = await get_player_mmr(name.lower(), tag.lower(), region)

            if not data:
                return "not_found"

            if isinstance(data, dict) and data.get("status") == 404:
                return "not_found"

            if "data" in data:
                current = data["data"].get("current", {})

                games_needed = current.get("games_needed_for_rating", 0)
                if games_needed > 0:
                    rank = "Unrated"
                    elo = 0
                else:
                    rank = current.get("tier", {}).get("name", "Unknown")
                    elo = current.get("rr", 0)

                return {"name": name, "tag": tag, "rank": rank, "elo": elo}

        return None

    @tasks.loop(minutes=1)
    async def daily_leaderboard_task(self):
        now = datetime.now(timezone.utc)
        if now.hour == 0 and now.minute == 0:
            await self.send_daily_leaderboards()

    async def send_daily_leaderboards(self):
        leaderboard_data = [
            {
                "name": n,
                "tag": t,
                "rank": p["rank"],
                "elo": p["elo"],
            }
            for (n, t), p in self.bot.valorant_players.items()
            if p["rank"].lower() != "unrated"
        ]

        leaderboard_data.sort(
            key=lambda x: (get_rank_value(x["rank"]), x["elo"]), reverse=True
        )

        view = ValorantLeaderboardView(leaderboard_data, interaction=None)
        embed = view.generate_embed()

        await broadcast_embed_to_guilds(
            self.bot, "leaderboard_announcements_channel_id", embed, view=view
        )

    @app_commands.command(
        name="valorant-leaderboard", description="View the Valorant leaderboard."
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

        leaderboard_data = [
            {
                "name": n,
                "tag": t,
                "rank": p["rank"],
                "elo": p["elo"],
            }
            for (n, t), p in self.bot.valorant_players.items()
            if p["rank"].lower() != "unrated"
        ]

        leaderboard_data.sort(
            key=lambda x: (get_rank_value(x["rank"]), x["elo"]), reverse=True
        )

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

            return await interaction.followup.send(
                f"{name}#{tag} was not found in the leaderboard cache."
            )

        view = ValorantLeaderboardView(leaderboard_data, interaction)
        embed = view.generate_embed()
        await interaction.followup.send(embed=embed, view=view)


class ValorantLeaderboardView(discord.ui.View):
    def __init__(
        self, data: List[dict], interaction: Optional[discord.Interaction] = None
    ):
        super().__init__(timeout=300)
        self.data = data
        self.interaction = interaction
        self.page = 0
        self.entries_per_page = 10
        self.max_page = (len(data) - 1) // self.entries_per_page if data else 0

        self.prev_button.disabled = True
        if self.max_page == 0:
            self.next_button.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.interaction is None:
            return True
        return interaction.user == self.interaction.user

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
        if not await self.interaction_check(interaction):
            return await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
            )

        self.page = max(self.page - 1, 0)
        self.next_button.disabled = False
        self.prev_button.disabled = self.page == 0
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="➡ Next", style=discord.ButtonStyle.gray)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.interaction_check(interaction):
            return await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
            )

        self.page = min(self.page + 1, self.max_page)
        self.prev_button.disabled = False
        self.next_button.disabled = self.page == self.max_page
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantLeaderboard(bot))
