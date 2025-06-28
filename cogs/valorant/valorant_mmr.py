import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from utils.valorant_helpers import (convert_to_datetime, fetch_val_api,
                                    get_player_mmr)


class ValorantMMRHistory(commands.Cog):
    """Cog for fetching and displaying Valorant player's MMR history."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

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

    def _get_cached_player_data(self, cache_key, now):
        cached = self.bot.valorant_players.get(cache_key)
        if cached and (
            now - cached.get("timestamp", now - timedelta(minutes=10))
        ) < timedelta(minutes=5):
            self.bot.logger.info(f"Using cached data for {cache_key[0]}#{cache_key[1]}")
            return cached["mmr_data"], cached["history"]
        return None

    async def _fetch_and_cache_player_data(
        self, interaction, name, tag, region, cache_key, now
    ):
        self.bot.logger.info(f"Fetching fresh data for {name}#{tag}")
        recent_history_data, full_history_data, mmr_data = await asyncio.gather(
            self.get_recent_mmr_history(name, tag, region),
            self.get_full_mmr_history(name, tag, region),
            get_player_mmr(name, tag, region),
        )

        if (
            not all([recent_history_data, full_history_data, mmr_data])
            or "data" not in recent_history_data
            or "data" not in full_history_data
            or "data" not in mmr_data
        ):
            await interaction.followup.send(f"Error fetching data for {name}#{tag}.")
            return None, None

        combined_history = self._combine_and_deduplicate_history(
            recent_history_data, full_history_data
        )

        if not combined_history:
            await interaction.followup.send(f"No match history found for {name}#{tag}.")
            return None, None

        current = mmr_data["data"].get("current", {})
        games_needed = current.get("games_needed_for_rating", 0)
        rank = (
            "Unrated"
            if games_needed > 0
            else current.get("tier", {}).get("name", "Unknown")
        )
        elo = 0 if games_needed > 0 else current.get("rr", 0)

        self.bot.valorant_players[cache_key] = {
            "rank": rank,
            "elo": elo,
            "mmr_data": mmr_data,
            "history": combined_history,
            "timestamp": now,
        }

        await self.bot.database.players_db.save_player(
            name=name, tag=tag, rank=rank, elo=elo
        )

        return mmr_data, combined_history

    def _combine_and_deduplicate_history(self, recent_data, full_data):
        seen_match_ids = set()
        combined = []

        recent_matches = recent_data["data"].get("history", [])
        full_matches = full_data["data"]

        for match in recent_matches + full_matches:
            match_id = match.get("match_id")
            if match_id and match_id not in seen_match_ids:
                seen_match_ids.add(match_id)
                combined.append(match)

        combined.sort(key=lambda m: m["date"], reverse=True)
        return combined

    def _filter_matches_by_time_window(self, history, now, hours):
        time_limit = now - timedelta(hours=hours)
        matches = [m for m in history if convert_to_datetime(m["date"]) >= time_limit]
        before = next(
            (m for m in history if convert_to_datetime(m["date"]) < time_limit), None
        )
        return matches, before

    def _calculate_mmr_stats(self, matches, before_window):
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
        games_needed = current_data.get("games_needed_for_rating", 0)
        if games_needed > 0:
            return "Unrated", 0
        rank = current_data.get("tier", {}).get("name", "Unknown")
        rr = current_data.get("rr", 0)
        return rank, rr

    def _build_empty_history_embed(self, name, tag, mmr_data):
        current = mmr_data["data"].get("current", {})
        current_rank, current_rr = self._parse_player_rank(current)

        embed = discord.Embed(
            title=f"Current Rank and RR for {name}#{tag}",
            description="No recent matches found in the selected time range.",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Current Rank", value=current_rank, inline=True)
        embed.add_field(name="Current RR", value=str(current_rr), inline=True)
        return embed

    def _build_paginated_embeds(
        self, name, tag, mmr_data, stats, match_display_rows, time
    ):
        MAX_CHARS = 1024
        pages = []

        current = mmr_data["data"].get("current", {})
        current_rank, current_rr = self._parse_player_rank(current)
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
        cache_key = (name, tag)
        now = datetime.now(timezone.utc)

        cached_result = self._get_cached_player_data(cache_key, now)
        if cached_result:
            mmr_data, combined_history = cached_result
        else:
            mmr_data, combined_history = await self._fetch_and_cache_player_data(
                interaction, name, tag, region, cache_key, now
            )
            if not mmr_data:
                return  # Error already sent to user

        matches_in_window, match_before_window = self._filter_matches_by_time_window(
            combined_history, now, time
        )

        if not matches_in_window:
            embed = self._build_empty_history_embed(name, tag, mmr_data)
            await interaction.followup.send(embed=embed)
            return

        stats = self._calculate_mmr_stats(matches_in_window, match_before_window)
        match_display_rows = self._format_match_history_entries(matches_in_window)
        pages = self._build_paginated_embeds(
            name, tag, mmr_data, stats, match_display_rows, time
        )

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
