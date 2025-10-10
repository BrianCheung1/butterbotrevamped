import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.valorant_helpers import (
    convert_to_datetime,
    name_autocomplete,
    tag_autocomplete,
)
from utils.valorant_data_manager import (
    PlayerNotFoundError,
    RateLimitError,
    APIUnavailableError,
)


class ValorantMMRHistory(commands.Cog):
    """Cog for fetching and displaying Valorant player's MMR history."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Use centralized data manager
        self.data_manager = bot.valorant_data

    def _combine_and_deduplicate_history(self, recent_data, full_data):
        """Combine and deduplicate match history from two sources."""
        seen_match_ids = set()
        combined = []

        recent_matches = (
            recent_data.get("data", {}).get("history", []) if recent_data else []
        )
        full_matches = full_data.get("data", []) if full_data else []

        for match in recent_matches + full_matches:
            match_id = match.get("match_id")
            if match_id and match_id not in seen_match_ids:
                seen_match_ids.add(match_id)
                combined.append(match)

        combined.sort(key=lambda m: m["date"], reverse=True)
        return combined

    def _filter_matches_by_time_window(self, history, now, hours):
        """Filter matches within a time window."""
        time_limit = now - timedelta(hours=hours)
        matches = [m for m in history if convert_to_datetime(m["date"]) >= time_limit]
        before = next(
            (m for m in history if convert_to_datetime(m["date"]) < time_limit), None
        )
        return matches, before

    def _calculate_mmr_stats(self, matches, before_window):
        """Calculate MMR statistics from match history."""
        starting_elo = before_window["elo"] if before_window else matches[-1]["elo"]
        starting_rank = before_window["tier"]["name"] if before_window else "Unknown"
        ending_elo = matches[0]["elo"]
        total_rr_change = ending_elo - starting_elo

        wins = sum(1 for m in matches if m["last_change"] > 0)
        losses = sum(1 for m in matches if m["last_change"] < 0)
        draws = sum(1 for m in matches if m["last_change"] == 0)
        total_matches = len(matches)
        win_loss_ratio = wins / total_matches if total_matches else 0

        start_time = convert_to_datetime(matches[-1]["date"])
        end_time = convert_to_datetime(matches[0]["date"])

        return {
            "starting_elo": starting_elo,
            "starting_rank": starting_rank,
            "ending_elo": ending_elo,
            "total_rr_change": total_rr_change,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_loss_ratio": win_loss_ratio,
            "start_time": start_time,
            "end_time": end_time,
            "total_matches": total_matches,
        }

    def _format_match_history_entries(self, matches):
        """Format match history entries for display."""
        rows = []
        for match in matches:
            change = match.get("last_change", 0)
            refunded = match.get("refunded_rr", 0)
            emoji = "✅" if change > 0 else "❌" if change < 0 else "➖"
            sign = "+" if change > 0 else ""
            entry = f"{emoji} ({sign}{change})"
            if refunded:
                entry += f" ↩️ (+{refunded})"
            rows.append(entry)
        grouped_rows = ["  ".join(rows[i : i + 5]) for i in range(0, len(rows), 5)]
        return grouped_rows

    def _parse_player_rank(self, current_data):
        """Parse player rank from MMR data."""
        games_needed = current_data.get("games_needed_for_rating", 0)
        if games_needed > 0:
            return "Unrated", 0, games_needed
        rank = current_data.get("tier", {}).get("name", "Unknown")
        rr = current_data.get("rr", 0)
        return rank, rr, 0

    def _build_empty_history_embed(self, name, tag, mmr_data):
        """Build embed when no matches found."""
        current = mmr_data.get("data", {}).get("current", {})
        current_rank, current_rr, games_needed = self._parse_player_rank(current)

        embed = discord.Embed(
            title=f"Current Rank and RR for {name}#{tag}",
            description="No recent matches found in the selected time range.",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Current Rank", value=current_rank, inline=True)
        embed.add_field(name="Current RR", value=str(current_rr), inline=True)

        if games_needed > 0:
            embed.add_field(
                name="Placement Games Needed",
                value=f"{games_needed}",
                inline=False,
            )

        return embed

    def _build_paginated_embeds(
        self, name, tag, mmr_data, stats, match_display_rows, time
    ):
        """Build paginated embeds for match history."""
        MAX_CHARS = 1024
        pages = []

        current = mmr_data.get("data", {}).get("current", {})
        current_rank, current_rr, games_needed = self._parse_player_rank(current)
        shields = current.get("rank_protection_shields", 0)

        # Build main embed
        main_embed = discord.Embed(
            title=f"MMR history for {name}#{tag} (last {time} hours)",
            description="Here is a summary of your recent matches.",
            color=discord.Color.blue(),
        )
        main_embed.add_field(
            name="Total Matches", value=str(stats["total_matches"]), inline=True
        )
        main_embed.add_field(name="Wins", value=str(stats["wins"]), inline=True)
        main_embed.add_field(
            name="Losses/Draws",
            value=f"{stats['losses']}/{stats['draws']}",
            inline=True,
        )
        main_embed.add_field(
            name="Win/Loss Ratio",
            value=f"{int(stats['win_loss_ratio'] * 100)}%",
            inline=True,
        )
        main_embed.add_field(
            name="Total RR Change",
            value=f"{stats['total_rr_change']:+} RR",
            inline=True,
        )
        main_embed.add_field(name="\u200b", value="\u200b", inline=True)
        main_embed.add_field(
            name="Starting Rank", value=stats["starting_rank"], inline=True
        )
        main_embed.add_field(
            name="Starting RR", value=str(stats["starting_elo"] % 100), inline=True
        )
        main_embed.add_field(name="\u200b", value="\u200b", inline=True)
        main_embed.add_field(name="Current Rank", value=current_rank, inline=True)
        main_embed.add_field(name="Current RR", value=str(current_rr), inline=True)
        if games_needed > 0:
            main_embed.add_field(
                name="Placement Games Needed",
                value=f"{games_needed}",
                inline=True,
            )
        main_embed.add_field(name="\u200b", value="\u200b", inline=True)
        main_embed.add_field(name="Total Shields", value=str(shields), inline=True)
        main_embed.add_field(
            name="First Match Start Time",
            value=discord.utils.format_dt(stats["start_time"], style="t"),
            inline=True,
        )
        main_embed.add_field(
            name="Most Recent Match Start Time",
            value=discord.utils.format_dt(stats["end_time"], style="t"),
            inline=True,
        )

        # Fit as many match rows as possible into first embed
        match_chunk = []
        char_count = 0
        remaining_rows = []

        for row in match_display_rows:
            if char_count + len(row) + 1 <= MAX_CHARS:
                match_chunk.append(row)
                char_count += len(row) + 1
            else:
                remaining_rows.append(row)

        if match_chunk:
            main_embed.add_field(
                name="Match History (Latest → Oldest)",
                value="\n".join(match_chunk),
                inline=False,
            )

        pages.append(main_embed)

        # Overflow embeds
        if remaining_rows:
            chunk, length = [], 0
            for row in remaining_rows:
                if length + len(row) + 1 > MAX_CHARS:
                    embed = discord.Embed(
                        title="Match History (continued)",
                        description="\n".join(chunk),
                        color=discord.Color.dark_purple(),
                    )
                    embed.set_footer(text="↩️ = Refunded RR")
                    pages.append(embed)
                    chunk, length = [row], len(row)
                else:
                    chunk.append(row)
                    length += len(row) + 1

            if chunk:
                embed = discord.Embed(
                    title="Match History (continued)",
                    description="\n".join(chunk),
                    color=discord.Color.dark_purple(),
                )
                embed.set_footer(text="↩️ = Refunded RR")
                pages.append(embed)

        return pages

    @app_commands.command(
        name="valorant-mmr", description="View a Valorant player's recent MMR history."
    )
    @app_commands.describe(
        name="Player's username",
        tag="Player's tag",
        region="Player's region (e.g., na, eu)",
        time="How far back to look (in hours)",
    )
    @app_commands.autocomplete(name=name_autocomplete, tag=tag_autocomplete)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def valorant_mmr_history(
        self,
        interaction: discord.Interaction,
        name: str,
        tag: str,
        time: Optional[int] = 12,
        region: Optional[str] = "na",
    ) -> None:
        await interaction.response.defer()

        name, tag, region = name.lower(), tag.lower(), region.lower()
        now = datetime.now(timezone.utc)

        try:
            # Fetch all data using data manager (with caching)
            mmr_data, mmr_history, stored_mmr = await asyncio.gather(
                self.data_manager.get_player_mmr(name, tag, region),
                self.data_manager.get_mmr_history(name, tag, region),
                self.data_manager.get_stored_mmr_history(name, tag, region),
            )

            # Validate data
            if not mmr_data or "data" not in mmr_data:
                return await interaction.followup.send(
                    f"❌ Could not fetch MMR data for {name}#{tag}", ephemeral=True
                )

            # Parse data
            parsed = self.data_manager.parse_mmr_data(mmr_data)

            # Save to database
            await self.bot.database.players_db.save_player(
                name=name,
                tag=tag,
                rank=parsed["rank"],
                elo=parsed["elo"],
            )

            # Update in-memory cache
            self.bot.valorant_players[(name, tag)] = {
                "rank": parsed["rank"],
                "elo": parsed["elo"],
            }

            # Combine and deduplicate history
            combined_history = self._combine_and_deduplicate_history(
                mmr_history, stored_mmr
            )

            if not combined_history:
                embed = self._build_empty_history_embed(name, tag, mmr_data)
                return await interaction.followup.send(embed=embed)

            # Filter matches by time window
            matches_in_window, match_before_window = (
                self._filter_matches_by_time_window(combined_history, now, time)
            )

            if not matches_in_window:
                embed = self._build_empty_history_embed(name, tag, mmr_data)
                return await interaction.followup.send(embed=embed)

            # Calculate stats and format display
            stats = self._calculate_mmr_stats(matches_in_window, match_before_window)
            match_display_rows = self._format_match_history_entries(matches_in_window)
            pages = self._build_paginated_embeds(
                name, tag, mmr_data, stats, match_display_rows, time
            )

            # Send with pagination
            view = PaginatedMMRView(pages, user_id=interaction.user.id)
            await interaction.followup.send(embed=pages[0], view=view)

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
        except APIUnavailableError:
            await interaction.followup.send(
                "⚠️ Valorant API is currently unavailable. Please try again later.",
                ephemeral=True,
            )
        except Exception as e:
            self.bot.logger.error(
                f"Error fetching MMR history for {name}#{tag}: {e}", exc_info=True
            )
            await interaction.followup.send(
                f"❌ An unexpected error occurred while fetching data.", ephemeral=True
            )


class PaginatedMMRView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], user_id: int, timeout=180):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.user_id = user_id

        # Disable buttons if needed
        self.update_buttons()

    def update_buttons(self):
        """Update button states based on current page."""
        self.go_previous.disabled = self.current_page == 0
        self.go_next.disabled = self.current_page == len(self.pages) - 1

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.gray)
    async def go_previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "You can't use this button.", ephemeral=True
            )

        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current_page], view=self
        )

    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.gray)
    async def go_next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "You can't use this button.", ephemeral=True
            )

        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current_page], view=self
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantMMRHistory(bot))
