from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from utils.valorant_helpers import (convert_to_datetime, fetch_val_api,
                                    load_cached_players_from_db, parse_season)


class ValorantStats(commands.Cog):
    """Valorant Stats"""

    def __init__(self, bot):
        self.bot = bot
        self.cached_stats = {}

    async def cog_load(self):
        self.bot.valorant_players = await load_cached_players_from_db(
            self.bot.database.players_db
        )

    async def get_player_match_history(
        self, name: str, tag: str, region: str
    ) -> Optional[dict]:
        return await fetch_val_api(
            f"https://api.henrikdev.xyz/valorant/v1/stored-matches/{region}/{name}/{tag}",
            name,
            tag,
        )

    async def name_autocomplete(self, interaction: discord.Interaction, current: str):
        if not self.bot.valorant_players:
            return []

        unique_names = sorted(
            set(
                name
                for name, _ in self.bot.valorant_players.keys()
                if name.startswith(current.lower())
            )
        )
        return [Choice(name=n, value=n) for n in unique_names[:25]]

    async def tag_autocomplete(self, interaction: discord.Interaction, current: str):
        name = interaction.namespace.name  # what user selected for "name"
        if not self.bot.valorant_players:
            return []

        filtered_tags = sorted(
            {
                tag
                for n, tag in self.bot.valorant_players.keys()
                if n.lower() == name.lower() and tag.startswith(current.lower())
            }
        )
        return [Choice(name=t, value=t) for t in filtered_tags[:25]]

    @app_commands.command(name="valorant-stats", description="Show player stats")
    @app_commands.describe(
        name="Player's username", tag="Player's tag", region="Region (e.g., na, eu)"
    )
    @app_commands.autocomplete(name=name_autocomplete, tag=tag_autocomplete)
    async def valorant_stats(
        self,
        interaction: discord.Interaction,
        name: str,
        tag: str,
        region: Optional[str] = "na",
        time: Optional[int] = 12,
    ):
        await interaction.response.defer()

        name = name.lower()
        tag = tag.lower()
        region = region.lower()

        cache_key = (name, tag, region)
        now = datetime.now(timezone.utc)

        cached = self.cached_stats.get(cache_key)

        if cached and (
            now - cached.get("timestamp", now - timedelta(minutes=10))
        ) < timedelta(minutes=5):
            self.bot.logger.info(f"Using cached stats for {name}#{tag}")
            data = cached["data"]
        else:
            self.bot.logger.info(f"Fetching fresh stats for {name}#{tag}")
            data = await self.get_player_match_history(name, tag, region)

            if data.get("status") != 200 or "data" not in data:
                return await interaction.followup.send("Could not fetch match history.")

            self.cached_stats[cache_key] = {
                "data": data,
                "timestamp": now,
            }

        matches = data["data"]

        if not matches:
            return await interaction.followup.send("No matches found for this player.")

        # Filter to Competitive only
        competitive_matches = [
            m for m in matches if m["meta"].get("mode") == "Competitive"
        ]

        if not competitive_matches:
            return await interaction.followup.send("No Competitive matches found.")

        season_codes = {
            m["meta"]["season"]["short"]
            for m in competitive_matches
            if "meta" in m and "season" in m["meta"]
        }

        if not season_codes:
            return await interaction.followup.send("No season info found in matches.")

        latest_season = max(season_codes, key=parse_season)

        latest_season_matches = [
            m
            for m in competitive_matches
            if m["meta"]["season"]["short"] == latest_season
        ]

        if not latest_season_matches:
            return await interaction.followup.send("No matches in the latest season.")

        time_limit = now - timedelta(hours=time)

        matches_in_time_window = [
            m
            for m in latest_season_matches
            if convert_to_datetime(m["meta"]["started_at"]) >= time_limit
        ]

        if not matches_in_time_window:
            return await interaction.followup.send(
                f"No Competitive matches found in the last {time} hours for {name}#{tag}."
            )

        # Stats per cluster
        cluster_stats = defaultdict(
            lambda: {"wins": 0, "losses": 0, "draws": 0, "total": 0}
        )
        map_stats = defaultdict(
            lambda: {"wins": 0, "losses": 0, "draws": 0, "total": 0}
        )

        for match in matches_in_time_window:
            meta = match["meta"]
            cluster = meta.get("cluster", "Unknown")
            map_name = meta.get("map", {}).get("name", "Unknown")

            player_team = match["stats"]["team"].lower()
            teams = {k.lower(): v for k, v in match["teams"].items()}

            player_score = teams.get(player_team, 0)
            opponent_score = teams["red"] if player_team == "blue" else teams["blue"]

            # Update cluster stats
            cluster_stats[cluster]["total"] += 1
            map_stats[map_name]["total"] += 1

            if player_score > opponent_score:
                cluster_stats[cluster]["wins"] += 1
                map_stats[map_name]["wins"] += 1
            elif player_score < opponent_score:
                cluster_stats[cluster]["losses"] += 1
                map_stats[map_name]["losses"] += 1
            else:
                cluster_stats[cluster]["draws"] += 1
                map_stats[map_name]["draws"] += 1

        # Build embed
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
        kda_lines = []

        for match in matches_in_time_window:
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

            # Headshot calculations
            head = shots.get("head", 0)
            body = shots.get("body", 0)
            leg = shots.get("leg", 0)
            total_shots = head + body + leg
            hs_rate = (
                f"{(head / total_shots * 100):.1f}%" if total_shots > 0 else "0.0%"
            )

            # Score and map round info
            player_team = stats.get("team", "").lower()
            red_score = teams.get("red", 0)
            blue_score = teams.get("blue", 0)
            team_score = red_score if player_team == "red" else blue_score
            opp_score = blue_score if player_team == "red" else red_score
            total_rounds = red_score + blue_score
            avg_score = round(score / total_rounds) if total_rounds > 0 else 0
            map_score = f"{team_score}-{opp_score}"

            kda_lines.append(
                f"📍 **{map_name}** — `{kills}/{deaths}/{assists}` | 🧠 {agent} | 🧮 {map_score}\n"
                f"🩸 HS: {hs_rate} | 🧾 ACS: {avg_score}"
            )

        kda_text = "\n".join(kda_lines[:10])  # Limit to 10 matches

        embed.add_field(
            name="🔫 Match Details (last 10 Competitive matches)",
            value=kda_text or "No match data available.",
            inline=False,
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantStats(bot))
