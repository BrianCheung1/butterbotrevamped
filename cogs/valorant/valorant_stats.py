from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.valorant_helpers import (
    convert_to_datetime,
    name_autocomplete,
    parse_season,
    tag_autocomplete,
)
from utils.valorant_data_manager import (
    PlayerNotFoundError,
    RateLimitError,
    APIUnavailableError,
)


class ValorantStats(commands.Cog):
    """Valorant Stats with centralized data management."""

    def __init__(self, bot):
        self.bot = bot
        # Use centralized data manager
        self.data_manager = bot.valorant_data

    def filter_matches(self, matches, mode=None, season=None, since=None):
        """Filter matches by mode, season, and time."""
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
        """Build win/loss statistics from matches."""
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

    async def get_player_kill_stats(self, match_id: str, player_puuid: str):
        """
        Fetch detailed match data and calculate various kill stats for a player.

        Returns: dict with {
            'first_bloods': int,
            'first_deaths': int,
            'total_kills': int,
            'total_deaths': int,
            'headshot_kills': int,
            'bodyshot_kills': int,
            'legshot_kills': int,
            'kill_details': list of kill event dicts
        }
        """
        try:
            match_data = await self.data_manager.get_match_details(match_id)
            if not match_data or "data" not in match_data:
                return {
                    "first_bloods": 0,
                    "first_deaths": 0,
                    "total_kills": 0,
                    "total_deaths": 0,
                    "headshot_kills": 0,
                    "bodyshot_kills": 0,
                    "legshot_kills": 0,
                    "kill_details": [],
                }

            rounds = match_data["data"].get("rounds", [])
            first_bloods = 0
            first_deaths = 0
            total_kills = 0
            total_deaths = 0
            headshot_kills = 0
            bodyshot_kills = 0
            legshot_kills = 0
            kill_details = []

            for round_data in rounds:
                # Collect all kill events for this round from each player's data
                kill_events = []
                for player_stat in round_data.get("player_stats", []):
                    kill_events.extend(player_stat.get("kill_events", []))

                if not kill_events:
                    continue

                # Sort by time to find the earliest kill of the round
                sorted_kills = sorted(
                    kill_events, key=lambda k: k.get("kill_time_in_round", float("inf"))
                )

                # First blood/death tracking
                first_kill = sorted_kills[0]
                if first_kill.get("killer_puuid") == player_puuid:
                    first_bloods += 1
                if first_kill.get("victim_puuid") == player_puuid:
                    first_deaths += 1

                # Process all kills in the round
                for kill_event in kill_events:
                    killer_puuid = kill_event.get("killer_puuid")
                    victim_puuid = kill_event.get("victim_puuid")

                    # Player got a kill
                    if killer_puuid == player_puuid:
                        total_kills += 1
                        kill_details.append(kill_event)

                        # Track kill location (headshot/bodyshot/legshot)
                        damage_bodyshot = kill_event.get("damage_bodyshot", "")
                        if damage_bodyshot:
                            if "Head" in damage_bodyshot:
                                headshot_kills += 1
                            elif "Body" in damage_bodyshot:
                                bodyshot_kills += 1
                            elif "Leg" in damage_bodyshot:
                                legshot_kills += 1

                    # Player died
                    if victim_puuid == player_puuid:
                        total_deaths += 1

            return {
                "first_bloods": first_bloods,
                "first_deaths": first_deaths,
                "total_kills": total_kills,
                "total_deaths": total_deaths,
                "headshot_kills": headshot_kills,
                "bodyshot_kills": bodyshot_kills,
                "legshot_kills": legshot_kills,
                "kill_details": kill_details,
            }

        except Exception as e:
            self.bot.logger.warning(
                f"Error fetching kill stats for match {match_id}: {e}"
            )
            return {
                "first_bloods": 0,
                "first_deaths": 0,
                "total_kills": 0,
                "total_deaths": 0,
                "headshot_kills": 0,
                "bodyshot_kills": 0,
                "legshot_kills": 0,
                "kill_details": [],
            }

    async def get_first_blood_stats(self, match_id: str, player_puuid: str):
        """
        Fetch detailed match data and calculate first bloods/deaths for a player.
        Backwards compatibility wrapper.

        Returns: (first_bloods, first_deaths)
        """
        stats = await self.get_player_kill_stats(match_id, player_puuid)
        return stats["first_bloods"], stats["first_deaths"]

    async def get_all_first_blood_stats(self, match_id: str):
        """
        Get first blood/death stats for ALL players in a match.

        Returns: Dict[puuid, (first_bloods, first_deaths)]
        """
        try:
            match_data = await self.data_manager.get_match_details(match_id)
            if not match_data or "data" not in match_data:
                return {}

            rounds = match_data["data"].get("rounds", [])
            player_stats = defaultdict(lambda: {"fb": 0, "fd": 0})

            for round_data in rounds:
                # Collect all kill events for this round
                kill_events = []
                for player_stat in round_data.get("player_stats", []):
                    kill_events.extend(player_stat.get("kill_events", []))

                if not kill_events:
                    continue

                # Find first kill
                sorted_kills = sorted(
                    kill_events, key=lambda k: k.get("kill_time_in_round", float("inf"))
                )
                first_kill = sorted_kills[0]

                killer_puuid = first_kill.get("killer_puuid")
                victim_puuid = first_kill.get("victim_puuid")

                if killer_puuid:
                    player_stats[killer_puuid]["fb"] += 1
                if victim_puuid:
                    player_stats[victim_puuid]["fd"] += 1

            return player_stats

        except Exception as e:
            self.bot.logger.warning(
                f"Error fetching all first blood stats for match {match_id}: {e}"
            )
            return {}

    async def build_scoreboard_embed(
        self, match_data: dict, requesting_player_puuid: str
    ):
        """
        Build a detailed scoreboard embed for a match.

        Args:
            match_data: The full match data from stored-matches
            requesting_player_puuid: PUUID of the player who requested stats

        Returns:
            discord.Embed with full scoreboard
        """

        match_data = await self.data_manager.get_match_details(match_data["meta"]["id"])
        match_data = match_data.get("data", {}) if match_data else {}
        meta = match_data.get("metadata", {})
        teams = match_data.get("teams", {})

        map_name = meta.get("map", {})
        mode = meta.get("mode", "Unknown")
        red_score = teams.get("red", {}).get("rounds_won", 0)
        blue_score = teams.get("blue", {}).get("rounds_won", 0)
        started_at = meta.get("started_at", "")

        # Determine match result
        if red_score > blue_score:
            result = f"Red Victory {red_score}-{blue_score}"
            color = discord.Color.red()
        elif blue_score > red_score:
            result = f"Blue Victory {blue_score}-{red_score}"
            color = discord.Color.blue()
        else:
            result = f"Draw {red_score}-{blue_score}"
            color = discord.Color.greyple()

        embed = discord.Embed(
            title=f"🎮 Match Scoreboard - {map_name}",
            description=f"**{result}** • {mode}",
            color=color,
        )

        # Get first blood stats for all players
        match_id = meta.get("id")
        fb_stats = await self.get_all_first_blood_stats(match_id) if match_id else {}

        players_data = match_data.get("players", {})

        # Handle both formats safely
        if isinstance(players_data, dict):
            all_players = players_data.get("all_players", [])
        else:
            all_players = players_data or []

        # Separate by team
        red_team = [p for p in all_players if p.get("team", "").lower() == "red"]
        blue_team = [p for p in all_players if p.get("team", "").lower() == "blue"]

        # Sort by score (descending)
        red_team.sort(key=lambda p: p.get("stats", {}).get("score", 0), reverse=True)
        blue_team.sort(key=lambda p: p.get("stats", {}).get("score", 0), reverse=True)

        def format_player_line(player):
            """Format a single player's stats line."""
            stats = player.get("stats", {})
            print(stats)
            character = stats.get("character", {})

            name = player.get("name", "Unknown")
            tag = player.get("tag", "")
            puuid = stats.get("puuid", "")

            # Highlight requesting player
            is_me = puuid == requesting_player_puuid
            prefix = "➤ " if is_me else "  "

            kills = stats.get("kills", 0)
            deaths = stats.get("deaths", 0)
            assists = stats.get("assists", 0)
            agent = character.get("name", "?")[:3]  # Short agent name

            # Calculate headshot %
            head = stats.get("headshots", 0)
            body = stats.get("bodyshots", 0)
            leg = stats.get("legshots", 0)
            total_shots = head + body + leg
            hs_pct = int((head / total_shots * 100)) if total_shots > 0 else 0

            # Calculate ACS
            score = stats.get("score", 0)
            total_rounds = red_score + blue_score
            acs = round(score / total_rounds) if total_rounds > 0 else 0

            # First blood stats
            fb_data = fb_stats.get(puuid, {"fb": 0, "fd": 0})
            fb = fb_data["fb"]
            fd = fb_data["fd"]
            fb_str = f" 🩸{fb}" if fb > 0 else ""
            fd_str = f" 💀{fd}" if fd > 0 else ""

            return f"{prefix}`{kills:2}/{deaths:2}/{assists:2}` **{name}#{tag}** ({agent}) HS:{hs_pct}% ACS:{acs}{fb_str}{fd_str}"

        # Red Team
        red_lines = [format_player_line(p) for p in red_team]
        embed.add_field(
            name=f"🔴 Red Team ({red_score})",
            value="\n".join(red_lines) or "No players",
            inline=False,
        )

        # Blue Team
        blue_lines = [format_player_line(p) for p in blue_team]
        embed.add_field(
            name=f"🔵 Blue Team ({blue_score})",
            value="\n".join(blue_lines) or "No players",
            inline=False,
        )

        # Footer
        if started_at:
            try:
                match_time = convert_to_datetime(started_at)
                embed.timestamp = match_time
            except:
                pass

        embed.set_footer(text="➤ = You | 🩸 = First Bloods | 💀 = First Deaths")

        return embed

    async def build_overall_stats(self, matches, player_puuid: str):
        """Build comprehensive overall statistics from matches."""
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        total_headshots = 0
        total_body_shots = 0
        total_leg_shots = 0
        total_score = 0
        total_rounds = 0
        first_bloods = 0
        first_deaths = 0

        wins = 0
        losses = 0
        draws = 0

        # Fetch first blood stats for recent matches (limit to last 10 to avoid rate limits)
        recent_matches = matches[:10]
        self.bot.logger.info(
            f"Fetching detailed stats for {len(recent_matches)} matches..."
        )

        for match in matches:
            stats = match.get("stats", {})
            shots = stats.get("shots", {})
            teams = match.get("teams", {})

            # KDA
            total_kills += stats.get("kills", 0)
            total_deaths += stats.get("deaths", 0)
            total_assists += stats.get("assists", 0)

            # Shots
            total_headshots += shots.get("head", 0)
            total_body_shots += shots.get("body", 0)
            total_leg_shots += shots.get("leg", 0)

            # Score
            total_score += stats.get("score", 0)
            red_score = teams.get("red", 0)
            blue_score = teams.get("blue", 0)
            total_rounds += red_score + blue_score

            # Win/Loss
            player_team = stats.get("team", "").lower()
            player_score = red_score if player_team == "red" else blue_score
            opp_score = blue_score if player_team == "red" else red_score

            if player_score > opp_score:
                wins += 1
            elif player_score < opp_score:
                losses += 1
            else:
                draws += 1

        # Fetch first blood stats for recent matches
        for match in recent_matches:
            match_id = match.get("meta", {}).get("id")
            if match_id and player_puuid:
                fb, fd = await self.get_first_blood_stats(match_id, player_puuid)
                first_bloods += fb
                first_deaths += fd

        # Calculate aggregates
        total_shots = total_headshots + total_body_shots + total_leg_shots
        hs_percentage = (total_headshots / total_shots * 100) if total_shots > 0 else 0
        kd_ratio = (total_kills / total_deaths) if total_deaths > 0 else total_kills
        avg_combat_score = (total_score / total_rounds) if total_rounds > 0 else 0
        win_rate = (wins / len(matches) * 100) if matches else 0

        return {
            "matches": len(matches),
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_rate": win_rate,
            "kills": total_kills,
            "deaths": total_deaths,
            "assists": total_assists,
            "kd_ratio": kd_ratio,
            "hs_percentage": hs_percentage,
            "avg_combat_score": avg_combat_score,
            "first_bloods": first_bloods,
            "first_deaths": first_deaths,
            "fb_analyzed_matches": len(recent_matches),
        }

    async def build_kda_lines(self, matches, player_puuid: str):
        """Build KDA display lines from matches with first blood/death stats."""
        lines = []

        # Only fetch detailed stats for most recent matches to avoid rate limits
        detailed_matches = matches[:8]

        for match in detailed_matches:
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
            hs_rate = f"{(head / total_shots * 100):.0f}%" if total_shots > 0 else "0%"

            player_team = stats.get("team", "").lower()
            red_score = teams.get("red", 0)
            blue_score = teams.get("blue", 0)
            team_score = red_score if player_team == "red" else blue_score
            opp_score = blue_score if player_team == "red" else red_score
            total_rounds = red_score + blue_score
            avg_score = round(score / total_rounds) if total_rounds > 0 else 0
            map_score = f"{team_score}-{opp_score}"

            # Win/Loss indicator
            result_emoji = (
                "✅"
                if team_score > opp_score
                else "❌" if team_score < opp_score else "➖"
            )

            # Fetch first blood/death stats
            match_id = meta.get("id")
            fb_indicator = ""
            fd_indicator = ""

            if match_id and player_puuid:
                first_bloods, first_deaths = await self.get_first_blood_stats(
                    match_id, player_puuid
                )
                fb_indicator = f" 🩸×{first_bloods}" if first_bloods > 0 else ""
                fd_indicator = f" 💀×{first_deaths}" if first_deaths > 0 else ""

            lines.append(
                f"{result_emoji} **{map_name}** ({map_score}) • {agent}\n"
                f"└ `{kills}/{deaths}/{assists}` • HS: {hs_rate} • ACS: {avg_score}{fb_indicator}{fd_indicator}"
            )
        return lines

    @app_commands.command(
        name="valorant-stats", description="Show player competitive stats"
    )
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

        try:
            # Use data manager to fetch match history (with caching)
            data = await self.data_manager.get_match_history(name, tag, region)

            if not data or data.get("status") != 200 or "data" not in data:
                return await interaction.followup.send(
                    f"❌ Could not fetch match history for {name}#{tag}", ephemeral=True
                )

            matches = data["data"]
            if not matches:
                return await interaction.followup.send(
                    f"No matches found for {name}#{tag}.", ephemeral=True
                )

            # Get player PUUID from first match
            player_puuid = matches[0].get("stats", {}).get("puuid")

            # Step 1: Filter for Competitive
            competitive_matches = self.filter_matches(matches, mode="Competitive")
            if not competitive_matches:
                return await interaction.followup.send(
                    f"No Competitive matches found for {name}#{tag}.", ephemeral=True
                )

            # Step 2: Get latest season
            season_codes = {
                m["meta"]["season"]["short"]
                for m in competitive_matches
                if "meta" in m and "season" in m["meta"]
            }
            if not season_codes:
                return await interaction.followup.send(
                    "No season info found in matches.", ephemeral=True
                )

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
                    f"No Competitive matches found in the last {time} hours for {name}#{tag}.",
                    ephemeral=True,
                )

            # Step 4: Build stats
            overall = await self.build_overall_stats(
                matches_in_time_window, player_puuid
            )
            map_stats = self.build_stats(
                matches_in_time_window,
                lambda meta: meta.get("map", {}).get("name", "Unknown"),
            )
            kda_lines = await self.build_kda_lines(matches_in_time_window, player_puuid)

            # Step 5: Build main stats embed
            embed = discord.Embed(
                title=f"📊 {name}#{tag}",
                description=f"**Season {latest_season}** • Last {time} hours • {overall['matches']} matches",
                color=discord.Color.red(),
            )

            # Overall Performance Section
            fb_note = (
                f" (from {overall['fb_analyzed_matches']} matches)"
                if overall["fb_analyzed_matches"] < overall["matches"]
                else ""
            )
            embed.add_field(
                name="🎯 Overall Performance",
                value=(
                    f"**Record:** {overall['wins']}W - {overall['losses']}L - {overall['draws']}D ({overall['win_rate']:.1f}%)\n"
                    f"**K/D/A:** {overall['kills']}/{overall['deaths']}/{overall['assists']} "
                    f"(KD: {overall['kd_ratio']:.2f})\n"
                    f"**Headshot %:** {overall['hs_percentage']:.1f}%\n"
                    f"**Avg Combat Score:** {overall['avg_combat_score']:.0f}\n"
                    f"**First Bloods:** {overall['first_bloods']} 🩸 | **First Deaths:** {overall['first_deaths']} 💀{fb_note}"
                ),
                inline=False,
            )

            # Map Performance Section
            if map_stats:
                map_lines = []
                for map_name, stats in sorted(
                    map_stats.items(), key=lambda x: -x[1]["total"]
                )[
                    :5
                ]:  # Top 5 maps
                    w, l, d = stats["wins"], stats["losses"], stats["draws"]
                    total = stats["total"]
                    wr = (w / total * 100) if total > 0 else 0
                    map_lines.append(f"**{map_name}:** {w}-{l}-{d} ({wr:.0f}%)")

                embed.add_field(
                    name="🗺️ Map Performance",
                    value="\n".join(map_lines),
                    inline=False,
                )

            # Recent Matches Section
            embed.add_field(
                name="🔫 Recent Matches",
                value="\n".join(kda_lines) or "No match data available.",
                inline=False,
            )

            embed.set_footer(text="🩸 = First Bloods | 💀 = First Deaths")

            # Step 6: Build scoreboard for most recent match
            most_recent_match = matches_in_time_window[0]
            scoreboard_embed = await self.build_scoreboard_embed(
                most_recent_match, player_puuid
            )

            # Send both embeds
            await interaction.followup.send(embeds=[embed, scoreboard_embed])

        except PlayerNotFoundError:
            await interaction.followup.send(
                f"❌ Player {name}#{tag} not found. They may not exist or have no public match history.",
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
                f"Error fetching stats for {name}#{tag}: {e}", exc_info=True
            )
            await interaction.followup.send(
                "❌ An unexpected error occurred while fetching stats.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantStats(bot))
