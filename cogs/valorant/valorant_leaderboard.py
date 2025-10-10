"""
Updated ValorantLeaderboard cog using centralized data manager.
Replace your existing valorant_leaderboard.py with this version.
"""

import asyncio
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.channels import broadcast_embed_to_guilds
from utils.valorant_helpers import get_rank_value, name_autocomplete, tag_autocomplete
from utils.valorant_data_manager import PlayerNotFoundError, RateLimitError


class ValorantLeaderboard(commands.Cog):
    """Valorant Leaderboard with centralized data management."""

    def __init__(self, bot):
        self.bot = bot
        # Use centralized data manager
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
            self.bot.logger.info("✅ Daily leaderboard sent successfully")
        except Exception as e:
            self.bot.logger.error(
                f"❌ Error sending daily leaderboard: {e}", exc_info=True
            )

    @daily_leaderboard_task.before_loop
    async def before_daily_leaderboard(self):
        """Wait until bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
        self.bot.logger.info("[ValorantLeaderboard] Daily leaderboard task started")

    @tasks.loop(hours=6)  # Runs every 6 hours
    async def periodic_mmr_update_task(self):
        """Update MMR for all players every 6 hours."""
        try:
            await self.run_mmr_update()
            self.bot.logger.info("✅ MMR update cycle completed")
        except Exception as e:
            self.bot.logger.error(f"❌ Error in MMR update: {e}", exc_info=True)

    @periodic_mmr_update_task.before_loop
    async def before_mmr_update(self):
        """Wait until bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
        self.bot.logger.info("[ValorantLeaderboard] MMR update task started")

    async def send_daily_leaderboards(self):
        """Generate and broadcast daily leaderboard."""
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

    async def run_mmr_update(self):
        """Update MMR for all players using the data manager."""
        self.bot.logger.info("🔄 Starting MMR update cycle...")

        # Get all players from database
        players = await self.bot.database.players_db.get_all_player_mmr()

        if not players:
            self.bot.logger.info("No players to update")
            return

        updated_count = 0
        skipped_count = 0
        deleted_count = 0
        error_count = 0

        # Filter players that need updating (haven't been updated in 2 hours)
        now = datetime.now(timezone.utc)
        players_to_update = []

        for player in players:
            last_updated = player.get("last_updated")

            # Always update if never updated
            if last_updated is None:
                players_to_update.append(player)
                continue

            try:
                if isinstance(last_updated, str):
                    last_updated = datetime.fromisoformat(
                        last_updated.replace("Z", "+00:00")
                    )

                # Update if more than 2 hours old
                if now - last_updated >= timedelta(hours=2):
                    players_to_update.append(player)
                else:
                    skipped_count += 1
            except Exception as e:
                self.bot.logger.warning(
                    f"⚠️ Error parsing timestamp for {player['name']}#{player['tag']}: {e}"
                )
                # Update anyway if there's an error
                players_to_update.append(player)

        self.bot.logger.info(
            f"📊 Players to update: {len(players_to_update)}, Skipped (recently updated): {skipped_count}"
        )

        # Process players in batches using data manager
        batch_size = 5
        for i in range(0, len(players_to_update), batch_size):
            batch = players_to_update[i : i + batch_size]

            self.bot.logger.info(
                f"Processing batch {i // batch_size + 1}/{(len(players_to_update) + batch_size - 1) // batch_size}"
            )

            # Use data manager's batch function
            player_tuples = [(p["name"], p["tag"]) for p in batch]
            results = await self.data_manager.batch_get_player_mmr(player_tuples)

            # Process results
            for player in batch:
                name, tag = player["name"], player["tag"]
                mmr_data = results.get((name, tag))

                # Handle player not found (404)
                if mmr_data is None:
                    # Check if this was a PlayerNotFoundError
                    try:
                        # Try one more time to confirm
                        await self.data_manager.get_player_mmr(name, tag)
                    except PlayerNotFoundError:
                        self.bot.logger.info(f"🗑️ Deleting {name}#{tag} (not found)")
                        try:
                            await self.bot.database.players_db.delete_player(name, tag)
                            self.bot.valorant_players.pop((name, tag), None)
                            deleted_count += 1
                        except Exception as e:
                            self.bot.logger.error(f"Failed to delete {name}#{tag}: {e}")
                        continue
                    except Exception:
                        # Other error, skip for now
                        error_count += 1
                        continue

                # Parse MMR data
                try:
                    parsed = self.data_manager.parse_mmr_data(mmr_data)
                    rank = parsed["rank"]
                    elo = parsed["elo"]

                    # Update in-memory cache
                    self.bot.valorant_players[(name, tag)] = {
                        "rank": rank,
                        "elo": elo,
                    }

                    # Save to database
                    await self.bot.database.players_db.save_player(
                        name=name,
                        tag=tag,
                        rank=rank,
                        elo=elo,
                    )

                    updated_count += 1
                except Exception as e:
                    self.bot.logger.error(f"❌ Error processing {name}#{tag}: {e}")
                    error_count += 1

            # Wait between batches (data manager handles rate limiting, but this is extra safety)
            if i + batch_size < len(players_to_update):
                await asyncio.sleep(60)

        # Log summary
        self.bot.logger.info(
            f"✅ MMR Update Complete - Updated: {updated_count}, "
            f"Skipped: {skipped_count}, Deleted: {deleted_count}, Errors: {error_count}"
        )

        # Log cache statistics
        stats = self.data_manager.get_cache_stats()
        self.bot.logger.info(
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

    @app_commands.command(
        name="valorant-refresh", description="Force refresh a player's MMR data"
    )
    @app_commands.describe(name="Player's username", tag="Player's tag")
    @app_commands.autocomplete(name=name_autocomplete, tag=tag_autocomplete)
    async def valorant_refresh(
        self,
        interaction: discord.Interaction,
        name: str,
        tag: str,
    ):
        """Force refresh a specific player's MMR."""
        await interaction.response.defer()

        name, tag = name.lower(), tag.lower()

        try:
            # Force refresh through data manager
            mmr_data = await self.data_manager.get_player_mmr(
                name, tag, force_refresh=True
            )

            # Parse and update
            parsed = self.data_manager.parse_mmr_data(mmr_data)

            # Update cache
            self.bot.valorant_players[(name, tag)] = {
                "rank": parsed["rank"],
                "elo": parsed["elo"],
            }

            # Save to database
            await self.bot.database.players_db.save_player(
                name=name,
                tag=tag,
                rank=parsed["rank"],
                elo=parsed["elo"],
            )

            embed = discord.Embed(
                title=f"✅ Refreshed {name}#{tag}",
                description=(
                    f"**Rank:** {parsed['rank']}\n"
                    f"**RR:** {parsed['elo']}\n"
                    f"{'**Placement Games Needed:** ' + str(parsed['games_needed']) if parsed['games_needed'] > 0 else ''}"
                ),
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed)

        except PlayerNotFoundError:
            await interaction.followup.send(
                f"❌ Player {name}#{tag} not found. They may not exist or haven't played ranked.",
                ephemeral=True,
            )
        except RateLimitError as e:
            await interaction.followup.send(
                f"⏰ Rate limited. Please try again in {e.retry_after:.0f} seconds.",
                ephemeral=True,
            )
        except Exception as e:
            self.bot.logger.error(f"Error refreshing {name}#{tag}: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error refreshing player data: {str(e)}", ephemeral=True
            )


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
