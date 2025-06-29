from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.valorant_helpers import (convert_to_datetime, fetch_val_api,
                                    name_autocomplete, parse_season,
                                    tag_autocomplete)


class ValorantStats(commands.Cog):
    """Valorant Stats"""

    def __init__(self, bot):
        self.bot = bot
        self.cached_stats = {}

    async def get_player_match_history(
        self, name: str, tag: str, region: str
    ) -> Optional[dict]:
        return await fetch_val_api(
            f"https://api.henrikdev.xyz/valorant/v1/stored-matches/{region}/{name}/{tag}",
            name,
            tag,
        )

    async def get_cached_match_history(
        self, name: str, tag: str, region: str
    ) -> Optional[dict]:
        cache_key = (name, tag, region)
        now = datetime.now(timezone.utc)

        cached = self.cached_stats.get(cache_key)
        if cached and (
            now - cached.get("timestamp", now - timedelta(minutes=10))
        ) < timedelta(minutes=5):
            self.bot.logger.info(f"Using cached stats for {name}#{tag}")
            return cached["data"]

        self.bot.logger.info(f"Fetching fresh stats for {name}#{tag}")
        data = await self.get_player_match_history(name, tag, region)

        if data.get("status") == 200 and "data" in data:
            self.cached_stats[cache_key] = {"data": data, "timestamp": now}

        return data

    def filter_matches(self, matches, mode=None, season=None, since=None):
        result = matches
        if mode:
            result = [m for m in result if m["meta"].get("mode") == mode]
        if season:
            result = [m for m in result if m["meta"]["season"]["short"] == season]
        if since:
            result = [
                m
                for m in result
                if convert_to_datetime(m["meta"]["started_at"]) >= since
            ]
        return result

    def build_stats(self, matches, key_func):
        stats = defaultdict(lambda: {"wins": 0, "losses": 0, "draws": 0, "total": 0})

        for match in matches:
            meta = match["meta"]
            stats_key = key_func(meta)
            player_team = match["stats"]["team"].lower()
            teams = {k.lower(): v for k, v in match["teams"].items()}
            player_score = teams.get(player_team, 0)
            opponent_score = teams["red"] if player_team == "blue" else teams["blue"]

            stats[stats_key]["total"] += 1
            if player_score > opponent_score:
                stats[stats_key]["wins"] += 1
            elif player_score < opponent_score:
                stats[stats_key]["losses"] += 1
            else:
                stats[stats_key]["draws"] += 1

        return stats

    def build_kda_lines(self, matches):
        lines = []
        for match in matches:
            meta = match.get("meta", {})
            stats = match.get("stats", {})
            shots = stats.get("shots", {})
            character = stats.get("character", {})
            teams = match.get("teams", {})

            map_name = meta.get("map", {}).get("name", "Unknown")
            kills = stats.get("kills", 0)
            deaths = stats.get("deaths", 0)
            assists = stats.get("assists", 0)
            agent = character.get("name", "Unknown")
            score = stats.get("score", 0)

            head, body, leg = (
                shots.get("head", 0),
                shots.get("body", 0),
                shots.get("leg", 0),
            )
            total_shots = head + body + leg
            hs_rate = (
                f"{(head / total_shots * 100):.1f}%" if total_shots > 0 else "0.0%"
            )

            player_team = stats.get("team", "").lower()
            red_score = teams.get("red", 0)
            blue_score = teams.get("blue", 0)
            team_score = red_score if player_team == "red" else blue_score
            opp_score = blue_score if player_team == "red" else red_score
            total_rounds = red_score + blue_score
            avg_score = round(score / total_rounds) if total_rounds > 0 else 0
            map_score = f"{team_score}-{opp_score}"

            lines.append(
                f"📍 **{map_name}** — `{kills}/{deaths}/{assists}` | 🧠 {agent} | 🧮 {map_score}\n"
                f"🩸 HS: {hs_rate} | 🧾 ACS: {avg_score}"
            )
        return lines

    @app_commands.command(name="valorant-stats", description="Show player stats")
    @app_commands.describe(
        name="Player's username",
        tag="Player's tag",
        region="Region (e.g., na, eu)",
        time="Time window in hours",
    )
    @app_commands.autocomplete(name=name_autocomplete, tag=tag_autocomplete)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def valorant_stats(
        self,
        interaction: discord.Interaction,
        name: str,
        tag: str,
        region: Optional[str] = "na",
        time: Optional[int] = 12,
    ):
        await interaction.response.defer()

        name, tag, region = name.lower(), tag.lower(), region.lower()
        now = datetime.now(timezone.utc)
        time_limit = now - timedelta(hours=time)

        data = await self.get_cached_match_history(name, tag, region)

        if not data or data.get("status") != 200 or "data" not in data:
            return await interaction.followup.send("Could not fetch match history.")

        matches = data["data"]
        if not matches:
            return await interaction.followup.send("No matches found for this player.")

        # Step 1: Filter for Competitive
        competitive_matches = self.filter_matches(matches, mode="Competitive")
        if not competitive_matches:
            return await interaction.followup.send("No Competitive matches found.")

        # Step 2: Get latest season
        season_codes = {
            m["meta"]["season"]["short"]
            for m in competitive_matches
            if "meta" in m and "season" in m["meta"]
        }
        if not season_codes:
            return await interaction.followup.send("No season info found in matches.")

        latest_season = max(season_codes, key=parse_season)

        # Step 3: Filter for latest season and time window
        latest_season_matches = self.filter_matches(
            competitive_matches, season=latest_season
        )
        matches_in_time_window = self.filter_matches(
            latest_season_matches, since=time_limit
        )

        if not matches_in_time_window:
            return await interaction.followup.send(
                f"No Competitive matches found in the last {time} hours for {name}#{tag}."
            )

        # Step 4: Build stats
        cluster_stats = self.build_stats(
            matches_in_time_window, lambda meta: meta.get("cluster", "Unknown")
        )
        map_stats = self.build_stats(
            matches_in_time_window,
            lambda meta: meta.get("map", {}).get("name", "Unknown"),
        )
        kda_lines = self.build_kda_lines(matches_in_time_window)

        # Step 5: Build embed
        embed = discord.Embed(
            title=f"Valorant Stats for {name}#{tag} (Season: {latest_season}) (last {time}h)",
            color=discord.Color.purple(),
        )

        embed.add_field(
            name="📍 Clusters", value="Stats by server location:", inline=False
        )
        for cluster, stats in sorted(
            cluster_stats.items(), key=lambda x: -x[1]["total"]
        ):
            embed.add_field(
                name=cluster,
                value=(
                    f"**Wins:** {stats['wins']} | **Losses:** {stats['losses']} | "
                    f"**Draws:** {stats['draws']} | **Total:** {stats['total']}"
                ),
                inline=False,
            )

        embed.add_field(name="🗺️ Maps", value="Stats by map played:", inline=False)
        for map_name, stats in sorted(map_stats.items(), key=lambda x: -x[1]["total"]):
            embed.add_field(
                name=map_name,
                value=(
                    f"**Wins:** {stats['wins']} | **Losses:** {stats['losses']} | "
                    f"**Draws:** {stats['draws']} | **Total:** {stats['total']}"
                ),
                inline=False,
            )

        embed.add_field(
            name="🔫 Match Details (last 10 Competitive matches)",
            value="\n".join(kda_lines[:10]) or "No match data available.",
            inline=False,
        )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantStats(bot))
