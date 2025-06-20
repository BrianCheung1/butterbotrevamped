import asyncio


from datetime import datetime, timedelta, timezone
from typing import List, Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from utils.valorant_helpers import (
    convert_to_datetime,
    fetch_val_api,
    load_cached_players_from_db,
)


class ValorantMMRHistory(commands.Cog):
    """Cog for fetching and displaying Valorant player's MMR history."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.valorant_players = await load_cached_players_from_db(
            self.bot.database.players_db
        )

    async def get_full_mmr_history(
        self, name: str, tag: str, region: str
    ) -> Optional[dict]:
        url = f"https://api.henrikdev.xyz/valorant/v2/stored-mmr-history/{region}/pc/{name}/{tag}"
        return await fetch_val_api(url, name, tag)

    async def get_recent_mmr_history(
        self, name: str, tag: str, region: str
    ) -> Optional[dict]:
        url = f"https://api.henrikdev.xyz/valorant/v2/mmr-history/{region}/pc/{name}/{tag}"
        return await fetch_val_api(url, name, tag)

    async def get_player_mmr(self, name: str, tag: str, region: str) -> Optional[dict]:
        url = f"https://api.henrikdev.xyz/valorant/v3/mmr/{region}/pc/{name}/{tag}"
        return await fetch_val_api(url, name, tag)

    async def name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[Choice[str]]:
        if not getattr(self.bot, "valorant_players", None):
            return []

        current_lower = current.lower()
        unique_names = sorted(
            {
                name
                for name, _ in self.bot.valorant_players.keys()
                if name.startswith(current_lower)
            }
        )
        return [Choice(name=n, value=n) for n in unique_names[:25]]

    async def tag_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[Choice[str]]:
        name = getattr(interaction.namespace, "name", "").lower()
        if not getattr(self.bot, "valorant_players", None):
            return []

        current_lower = current.lower()
        filtered_tags = sorted(
            {
                tag
                for n, tag in self.bot.valorant_players.keys()
                if n.lower() == name and tag.startswith(current_lower)
            }
        )
        return [Choice(name=t, value=t) for t in filtered_tags[:25]]

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
    async def valorant_mmr_history(
        self,
        interaction: discord.Interaction,
        name: str,
        tag: str,
        time: Optional[int] = 12,
        region: Optional[str] = "na",
    ) -> None:
        await interaction.response.defer()

        # Normalize inputs
        name = name.lower()
        tag = tag.lower()
        region = region.lower()
        cache_key = (name, tag)
        now = datetime.now(timezone.utc)

        cached = self.bot.valorant_players.get(cache_key)
        # Use cached data if fresh (<5 mins)
        if cached and (
            now - cached.get("timestamp", now - timedelta(minutes=10))
            < timedelta(minutes=5)
        ):
            self.bot.logger.info(f"Using cached data for {name}#{tag}")
            mmr_data = cached["mmr_data"]
            combined_history = cached["history"]
        else:
            self.bot.logger.info(f"Fetching fresh data for {name}#{tag}")

            # Fetch concurrently
            recent_history_data, full_history_data, mmr_data = await asyncio.gather(
                self.get_recent_mmr_history(name, tag, region),
                self.get_full_mmr_history(name, tag, region),
                self.get_player_mmr(name, tag, region),
            )

            # Validate responses
            if not recent_history_data or "data" not in recent_history_data:
                await interaction.followup.send(
                    f"Error fetching recent MMR history for {name}#{tag}"
                )
                return
            if not full_history_data or "data" not in full_history_data:
                await interaction.followup.send(
                    f"Error fetching full MMR history for {name}#{tag}"
                )
                return
            if not mmr_data or "data" not in mmr_data:
                await interaction.followup.send(
                    f"Error fetching current MMR for {name}#{tag}"
                )
                return

            recent_matches = recent_history_data["data"].get("history", [])
            full_matches = full_history_data["data"]

            # Combine and deduplicate matches by match_id
            seen_match_ids = set()
            combined_history = []
            for match in recent_matches + full_matches:
                match_id = match.get("match_id")
                if match_id and match_id not in seen_match_ids:
                    seen_match_ids.add(match_id)
                    combined_history.append(match)

            if not combined_history:
                await interaction.followup.send(
                    f"No match history found for {name}#{tag}"
                )
                return

            # Sort descending by date
            combined_history.sort(key=lambda m: m["date"], reverse=True)

            # Cache results
            self.bot.valorant_players[cache_key] = {
                "rank": mmr_data["data"]
                .get("current", {})
                .get("tier", {})
                .get("name", "Unknown"),
                "elo": mmr_data["data"].get("current", {}).get("rr", 0),
                "mmr_data": mmr_data,
                "history": combined_history,
                "timestamp": now,
            }

            # Save to DB async (don't await to avoid blocking? If DB supports it, else await)
            await self.bot.database.players_db.save_player(
                name=name,
                tag=tag,
                rank=self.bot.valorant_players[cache_key]["rank"],
                elo=self.bot.valorant_players[cache_key]["elo"],
            )

        # Extract current rank and RR
        current = mmr_data["data"].get("current", {})
        current_rank = current.get("tier", {}).get("name", "Unknown")
        current_rr = current.get("rr", 0)
        shields = current.get("rank_protection_shields", 0)

        # Filter matches within time window
        time_limit = now - timedelta(hours=time)
        matches_in_window = [
            m for m in combined_history if convert_to_datetime(m["date"]) >= time_limit
        ]

        # Find match immediately before the time window, if any
        match_before_window = next(
            (
                m
                for m in combined_history
                if convert_to_datetime(m["date"]) < time_limit
            ),
            None,
        )

        # If no recent matches, show only current rank info
        if not matches_in_window:
            embed = discord.Embed(
                title=f"Current Rank and RR for {name}#{tag}",
                description="No recent matches found in the selected time range.",
                color=discord.Color.blue(),
            )
            embed.add_field(name="Current Rank", value=current_rank, inline=True)
            embed.add_field(name="Current RR", value=str(current_rr), inline=True)
            await interaction.followup.send(embed=embed)
            return

        # Calculate stats
        starting_elo = (
            match_before_window["elo"]
            if match_before_window
            else matches_in_window[-1]["elo"]
        )
        starting_rank = (
            match_before_window["tier"]["name"] if match_before_window else "Unknown"
        )
        ending_elo = matches_in_window[0]["elo"]
        total_rr_change = ending_elo - starting_elo

        wins = sum(1 for m in matches_in_window if m["last_change"] > 0)
        losses = sum(1 for m in matches_in_window if m["last_change"] < 0)
        draws = sum(1 for m in matches_in_window if m["last_change"] == 0)
        total_matches = len(matches_in_window)
        win_loss_ratio = wins / total_matches if total_matches else 0

        def format_match_entry(match: dict) -> List[str]:
            change = match.get("last_change", 0)
            refunded = match.get("refunded_rr", 0)
            emoji = "✅" if change > 0 else "❌" if change < 0 else "➖"
            sign = "+" if change > 0 else ""
            entries = [f"{emoji} ({sign}{change})"]
            if refunded:
                entries.append(f"↩️ (+{refunded})")
            return entries

        # Build flat list of match and refund entries for display
        match_display: List[str] = []
        for match in matches_in_window:
            match_display.extend(format_match_entry(match))

        # Group entries for embed fields (5 per row)
        grouped_rows = [
            "  ".join(match_display[i : i + 5]) for i in range(0, len(match_display), 5)
        ]

        # Get first and last match times safely
        start_time = convert_to_datetime(matches_in_window[-1]["date"])
        end_time = convert_to_datetime(matches_in_window[0]["date"])

        MAX_CHARS = 1024  # Max embed field character length

        # Prepare embed pages
        main_embed = discord.Embed(
            title=f"MMR history for {name}#{tag} (last {time} hours)",
            description="Here is a summary of your recent matches.",
            color=discord.Color.blue(),
        )
        main_embed.add_field(
            name="Total Matches", value=str(total_matches), inline=True
        )
        main_embed.add_field(name="Wins", value=str(wins), inline=True)
        main_embed.add_field(
            name="Losses/Draws", value=f"{losses}/{draws}", inline=True
        )
        main_embed.add_field(
            name="Win/Loss Ratio", value=f"{int(win_loss_ratio * 100)}%", inline=True
        )
        main_embed.add_field(
            name="Total RR Change", value=f"{total_rr_change:+} RR", inline=True
        )
        main_embed.add_field(name="\u200b", value="\u200b", inline=True)  # spacer
        main_embed.add_field(name="Starting Rank", value=starting_rank, inline=True)
        main_embed.add_field(
            name="Starting RR", value=str(starting_elo % 100), inline=True
        )
        main_embed.add_field(name="\u200b", value="\u200b", inline=True)
        main_embed.add_field(name="Current Rank", value=current_rank, inline=True)
        main_embed.add_field(name="Current RR", value=str(current_rr), inline=True)
        main_embed.add_field(name="\u200b", value="\u200b", inline=True)
        main_embed.add_field(name="Total Shields", value=str(shields), inline=True)
        main_embed.add_field(
            name="First Match Start Time",
            value=discord.utils.format_dt(start_time, style="t"),
            inline=True,
        )
        main_embed.add_field(
            name="Most Recent Match Start Time",
            value=discord.utils.format_dt(end_time, style="t"),
            inline=True,
        )

        # Add match history field if fits in embed limit
        match_history_chunk = []
        char_count = 0
        remaining_rows = []

        for row in grouped_rows:
            if char_count + len(row) + 1 <= MAX_CHARS:
                match_history_chunk.append(row)
                char_count += len(row) + 1
            else:
                remaining_rows.append(row)

        if match_history_chunk:
            main_embed.add_field(
                name="Match History (Latest → Oldest)",
                value="\n".join(match_history_chunk),
                inline=False,
            )

        pages = [main_embed]

        # Create additional embeds for remaining match history if overflow
        if remaining_rows:
            chunk: List[str] = []
            length = 0
            for row in remaining_rows:
                if length + len(row) + 1 > MAX_CHARS:
                    embed = discord.Embed(
                        title="Match History (continued)",
                        description="\n".join(chunk),
                        color=discord.Color.dark_purple(),
                    )
                    embed.set_footer(text="↩️ = Refunded RR")
                    pages.append(embed)
                    chunk = [row]
                    length = len(row)
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

        # Send paginated view
        view = PaginatedMMRView(pages, user_id=interaction.user.id)
        await interaction.followup.send(embed=pages[0], view=view)


class PaginatedMMRView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], user_id: int, timeout=120):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.user_id = user_id

        # Disable buttons if needed
        self.update_buttons()

    def update_buttons(self):
        self.go_previous.disabled = self.current_page == 0
        self.go_next.disabled = self.current_page == len(self.pages) - 1

    @discord.ui.button(label="⬅ Previous", style=discord.ButtonStyle.gray)
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

    @discord.ui.button(label="➡ Next", style=discord.ButtonStyle.gray)
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
