import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.channels import broadcast_embed_to_guilds
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
        self.daily_leaderboard_task = self.bot.loop.create_task(
            self.start_daily_leaderboard_loop()
        )
        self.periodic_mmr_update_task = self.bot.loop.create_task(
            self.periodic_mmr_update_loop()
        )

    def cog_unload(self):
        if self.daily_leaderboard_task:
            self.daily_leaderboard_task.cancel()
        if self.periodic_mmr_update_task:
            self.periodic_mmr_update_task.cancel()

    async def start_daily_leaderboard_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            now = datetime.now(timezone.utc)
            next_midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            wait_seconds = (next_midnight - now).total_seconds()

            self.bot.logger.info(
                f"[Valorant Leaderboard] Sleeping {wait_seconds:.0f}s until next 12:00 AM UTC broadcast"
            )

            await asyncio.sleep(wait_seconds)

            try:
                await self.send_daily_leaderboards()
                self.bot.logger.info("Daily leaderboard sent.")
            except Exception as e:
                self.bot.logger.error(f"Error sending leaderboard: {e}")

            await asyncio.sleep(1)  # Avoid tight loop

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

        view = ValorantLeaderboardView(
            leaderboard_data, interaction=None, timeout=86400
        )
        embed = view.generate_embed()

        await broadcast_embed_to_guilds(
            self.bot, "leaderboard_announcements_channel_id", embed, view=view
        )

    async def periodic_mmr_update_loop(self):
        """Custom periodic loop waking at fixed times: 00:00, 06:00, 12:00, 18:00 UTC"""
        await self.bot.wait_until_ready()
        scheduled_hours = [0, 6, 12, 18]  # UTC hours to run at

        while not self.bot.is_closed():
            now = datetime.utcnow()
            # Find the next scheduled hour after 'now'
            next_run_hour = None
            for h in scheduled_hours:
                if h > now.hour or (
                    h == now.hour and now.minute == 0 and now.second == 0
                ):
                    next_run_hour = h
                    break
            if next_run_hour is None:
                # Next run is tomorrow's first scheduled hour
                next_run_hour = scheduled_hours[0]
                next_run_day = now.date() + timedelta(days=1)
            else:
                next_run_day = now.date()

            next_run = datetime(
                year=next_run_day.year,
                month=next_run_day.month,
                day=next_run_day.day,
                hour=next_run_hour,
                minute=0,
                second=0,
                microsecond=0,
            )

            wait_seconds = (next_run - now).total_seconds()
            if wait_seconds <= 0:
                # Safety fallback to avoid negative or zero sleep
                wait_seconds = 1

            self.bot.logger.info(
                f"[Valorant MMR Update] Sleeping {wait_seconds:.0f}s until next run at {next_run} UTC"
            )
            await asyncio.sleep(wait_seconds)

            try:
                await self.run_mmr_update()
            except Exception as e:
                self.bot.logger.error(f"Error during periodic MMR update: {e}")

    async def run_mmr_update(self):
        """The main MMR update logic, refactored from your original periodic_mmr_update_loop"""

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

                    if datetime.utcnow() - last_updated >= timedelta(minutes=120):
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
                # Respect rate limit, sleep 60 seconds after each batch
                await asyncio.sleep(60)

        self.bot.logger.info(
            f"Finished MMR update cycle. Updated: {updated_players}, Skipped: {skipped_players}"
        )
        if updated_players > 0:
            self.bot.logger.info(f"Updated players: {', '.join(processed_details)}")
        if skipped_players > 0:
            self.bot.logger.info(f"Skipped players: {', '.join(skipped_details)}")

    async def fetch_player_mmr(self, name: str, tag: str, region: str = "na"):
        async with self.rate_semaphore:
            data = await get_player_mmr(name.lower(), tag.lower(), region)

            if not data or (isinstance(data, dict) and data.get("status") == 404):
                return "not_found"

            if "data" in data:
                current = data["data"].get("current", {})
                games_needed = current.get("games_needed_for_rating", 0)

                if games_needed > 0:
                    rank, elo = "Unrated", 0
                else:
                    rank = current.get("tier", {}).get("name", "Unknown")
                    elo = current.get("rr", 0)

                return {"name": name, "tag": tag, "rank": rank, "elo": elo}

        return None

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
        self,
        data: List[dict],
        interaction: Optional[discord.Interaction] = None,
        timeout: float = 300,
    ):
        super().__init__(timeout=timeout)
        self.data = data
        self.interaction = interaction
        self.page = 0
        self.entries_per_page = 10
        self.max_page = (len(data) - 1) // self.entries_per_page if data else 0

        self.prev_button.disabled = True
        if self.max_page == 0:
            self.next_button.disabled = True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.interaction:
            try:
                await self.interaction.edit_original_response(view=self)
            except discord.HTTPException:
                pass

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

        return discord.Embed(
            title=f"Valorant Leaderboard (Page {self.page + 1}/{self.max_page + 1})",
            description=leaderboard_str or "No data available.",
            color=discord.Color.red(),
        )

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
