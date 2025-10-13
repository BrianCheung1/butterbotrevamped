import asyncio
from datetime import time
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.channels import broadcast_embed_to_guilds
from utils.valorant_data_manager import RateLimitError
from utils.valorant_helpers import (
    build_leaderboard_from_cache,
    should_update_player,
    name_autocomplete,
    tag_autocomplete,
)
from logger import setup_logger

logger = setup_logger("ValorantLeaderboard")


class ValorantLeaderboard(commands.Cog):
    """Valorant Leaderboard with optimized batch processing and thread-safe caching."""

    def __init__(self, bot):
        self.bot = bot
        self.data_manager = bot.valorant_data

        # Start background tasks
        self.daily_leaderboard_task.start()
        self.periodic_mmr_update_task.start()

    def cog_unload(self):
        """Clean up tasks on cog unload."""
        self.daily_leaderboard_task.cancel()
        self.periodic_mmr_update_task.cancel()

    @tasks.loop(time=time(hour=0, minute=0))  # Runs at midnight UTC
    async def daily_leaderboard_task(self):
        """Send daily leaderboard at midnight UTC."""
        try:
            await self.send_daily_leaderboards()
            logger.info("✅ Daily leaderboard sent successfully")
        except Exception as e:
            logger.error(f"❌ Error sending daily leaderboard: {e}", exc_info=True)

    @daily_leaderboard_task.before_loop
    async def before_daily_leaderboard(self):
        """Wait until bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
        logger.info("Daily leaderboard task started")

    @tasks.loop(hours=6)  # Runs every 6 hours
    async def periodic_mmr_update_task(self):
        """Update MMR for all players every 6 hours."""
        try:
            await self.run_mmr_update()
            logger.info("✅ MMR update cycle completed")
        except Exception as e:
            logger.error(f"❌ Error in MMR update: {e}", exc_info=True)

    @periodic_mmr_update_task.before_loop
    async def before_mmr_update(self):
        """Wait until bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
        logger.info("MMR update task started")

    async def send_daily_leaderboards(self):
        """Generate and broadcast daily leaderboard."""
        # Get all players from thread-safe cache
        all_players = await self.bot.valorant_players.get_all()

        leaderboard_data = build_leaderboard_from_cache(all_players)

        view = ValorantLeaderboardView(
            leaderboard_data, interaction=None, timeout=86400
        )
        embed = view.generate_embed()

        await broadcast_embed_to_guilds(
            self.bot, "leaderboard_announcements_channel_id", embed, view=view
        )

    async def run_mmr_update(self):
        """Update MMR for all players with parallelized batch processing."""
        logger.info("🔄 Starting MMR update cycle...")

        players = await self.bot.database.players_db.get_all_player_mmr()
        if not players:
            logger.info("No players to update")
            return

        updated_count = 0
        skipped_count = 0
        deleted_count = 0
        error_count = 0

        # Filter players that need updating
        players_to_update = [
            p for p in players if should_update_player(p.get("last_updated"), hours=2)
        ]
        skipped_count = len(players) - len(players_to_update)

        logger.info(
            f"📊 Players to update: {len(players_to_update)}, Skipped: {skipped_count}"
        )

        batch_size = 5
        batches = [
            players_to_update[i : i + batch_size]
            for i in range(0, len(players_to_update), batch_size)
        ]

        for batch_num, batch in enumerate(batches, 1):
            logger.info(
                f"Processing batch {batch_num}/{len(batches)} ({len(batch)} players)"
            )

            player_tuples = [(p["name"], p["tag"]) for p in batch]

            try:
                # Fetch MMR data for all players in batch
                results = await self.data_manager.batch_get_player_mmr(player_tuples)
            except RateLimitError as e:
                logger.warning(f"Rate limited: {e}")
                # Stop processing but don't crash
                break

            # Collect updates and deletions
            updates = []
            deletions = []

            for player in batch:
                name, tag = player["name"], player["tag"]
                mmr_data = results.get((name, tag))

                if mmr_data is None:
                    # Player not found or error
                    logger.info(f"🗑️ Deleting {name}#{tag} (not found or error)")
                    deletions.append((name, tag))
                    deleted_count += 1
                    continue

                try:
                    # Parse MMR data
                    parsed = self.data_manager.parse_mmr_data(mmr_data)
                    updates.append((name, tag, parsed["rank"], parsed["elo"]))
                    updated_count += 1
                except Exception as e:
                    logger.error(
                        f"❌ Error parsing MMR for {name}#{tag}: {e}", exc_info=True
                    )
                    error_count += 1

            # Batch insert/update database records
            if updates:
                try:
                    await self.bot.database.players_db.batch_save_players(updates)

                    # Update thread-safe cache
                    cache_updates = {
                        (name, tag): {"rank": rank, "elo": elo}
                        for name, tag, rank, elo in updates
                    }
                    await self.bot.valorant_players.batch_set(cache_updates)
                except Exception as e:
                    logger.error(f"Error saving batch to database: {e}", exc_info=True)

            # Batch delete players
            if deletions:
                try:
                    await self.bot.database.players_db.batch_delete_players(deletions)
                    # Remove from thread-safe cache
                    await self.bot.valorant_players.batch_delete(deletions)
                except Exception as e:
                    logger.error(
                        f"Error deleting batch from database: {e}", exc_info=True
                    )

            if batch_num < len(batches):
                await asyncio.sleep(60)

        logger.info(
            f"✅ MMR Update Complete - Updated: {updated_count}, "
            f"Skipped: {skipped_count}, Deleted: {deleted_count}, Errors: {error_count}"
        )

        stats = self.data_manager.get_cache_stats()
        logger.info(
            f"📊 Cache Stats - Hit Rate: {stats['cache_hit_rate']:.1f}%, "
            f"API Calls: {stats['api_calls']}, Cached: {stats['total_cached']}"
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

        # Get all players from thread-safe cache
        all_players = await self.bot.valorant_players.get_all()

        # === REFACTORED: Use consolidated helper ===
        leaderboard_data = build_leaderboard_from_cache(all_players)
        # ===========================================

        # If specific player requested
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
                f"❌ {name}#{tag} was not found in the leaderboard cache."
            )

        # Show full leaderboard
        view = ValorantLeaderboardView(leaderboard_data, interaction)
        embed = view.generate_embed()
        await interaction.followup.send(embed=embed, view=view)


class ValorantLeaderboardView(discord.ui.View):
    """View for paginated leaderboard display."""

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
            f"{i}. **{p['name']}#{p['tag']}** - {p['rank']} - {p['elo']} RR"
            for i, p in enumerate(leaderboard_slice, start=start + 1)
        )

        embed = discord.Embed(
            title=f"🏆 Valorant Leaderboard (Page {self.page + 1}/{self.max_page + 1})",
            description=leaderboard_str or "No data available.",
            color=discord.Color.red(),
        )

        embed.set_footer(text=f"Total Players: {len(self.data)}")

        return embed

    @discord.ui.button(label="⏮️ First", style=discord.ButtonStyle.gray)
    async def first_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.interaction_check(interaction):
            return await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
            )

        self.page = 0
        self.prev_button.disabled = True
        self.first_button.disabled = True
        self.next_button.disabled = False
        self.last_button.disabled = False
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.blurple)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.interaction_check(interaction):
            return await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
            )

        self.page = max(self.page - 1, 0)
        self.next_button.disabled = False
        self.last_button.disabled = False
        if self.page == 0:
            self.prev_button.disabled = True
            self.first_button.disabled = True
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.blurple)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.interaction_check(interaction):
            return await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
            )

        self.page = min(self.page + 1, self.max_page)
        self.prev_button.disabled = False
        self.first_button.disabled = False
        if self.page == self.max_page:
            self.next_button.disabled = True
            self.last_button.disabled = True
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="⏭️ Last", style=discord.ButtonStyle.gray)
    async def last_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.interaction_check(interaction):
            return await interaction.response.send_message(
                "You're not allowed to use this leaderboard.", ephemeral=True
            )

        self.page = self.max_page
        self.prev_button.disabled = False
        self.first_button.disabled = False
        self.next_button.disabled = True
        self.last_button.disabled = True
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantLeaderboard(bot))
