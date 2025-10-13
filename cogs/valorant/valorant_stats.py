
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.valorant_data_manager import (
    APIUnavailableError,
    PlayerNotFoundError,
    RateLimitError,
)
from utils.valorant_helpers import (
    convert_to_datetime,
    name_autocomplete,
    parse_season,
    tag_autocomplete,
    extract_match_player_stats,
)
from logger import setup_logger

logger = setup_logger("ValorantStats")

MAX_RECENT_MATCHES = 50
MAX_KDA_DISPLAY = 8
MAX_MAP_DISPLAY = 5


class ValorantStats(commands.Cog):
    """Valorant Stats with centralized data management and optimized API calls."""

    def __init__(self, bot):
        self.bot = bot
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

    @staticmethod
    def _default_kill_stats() -> dict:
        """Return default kill stats structure."""
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

    # ===== CONSOLIDATED: OLD _extract_first_blood_stats, _extract_all_player_acs,
    #       _get_player_placement, _calculate_player_placement_in_match REMOVED =====
    # These are now handled by extract_match_player_stats() in utils/valorant_helpers.py

    async def build_scoreboard_embed(
        self, match_data: dict, requesting_player_puuid: str
    ):
        """
        Build a detailed scoreboard embed for a match with placement rankings.

        REFACTORED: Now uses consolidated extract_match_player_stats()
        """
        try:
            match_id = match_data.get("meta", {}).get("id")
            if not match_id:
                return self._build_error_embed("Invalid match data")

            # Fetch full match details
            full_match_data = await self.data_manager.get_match_details(match_id)
            if not full_match_data or "data" not in full_match_data:
                return self._build_error_embed("Could not fetch match details")

            match_info = full_match_data["data"]
            meta = match_info.get("metadata", {})
            teams = match_info.get("teams", {})

            map_name = meta.get("map", {})
            mode = meta.get("mode", "Unknown")
            red_score = teams.get("red", {}).get("rounds_won", 0)
            blue_score = teams.get("blue", {}).get("rounds_won", 0)
            started_at = meta.get("started_at", "")

            # === NEW: Single consolidated call ===
            stats = await extract_match_player_stats(
                full_match_data, requesting_player_puuid
            )
            fb_stats = stats["all_player_fb_fd"]
            all_player_acs = stats["all_player_acs"]
            # ====================================

            # Determine match result and color
            if red_score > blue_score:
                result = f"Red Victory {red_score}-{blue_score}"
                winner_color = discord.Color.from_rgb(220, 20, 60)
            elif blue_score > red_score:
                result = f"Blue Victory {blue_score}-{red_score}"
                winner_color = discord.Color.from_rgb(65, 105, 225)
            else:
                result = f"Draw {red_score}-{blue_score}"
                winner_color = discord.Color.from_rgb(128, 128, 128)

            embed = discord.Embed(
                title=f"🎮 {map_name}",
                description=f"**{result}** • {mode}",
                color=winner_color,
            )

            players_data = match_info.get("players", {})
            if isinstance(players_data, dict):
                all_players = players_data.get("all_players", [])
            else:
                all_players = players_data or []

            # Sort all players by ACS (descending) to get overall rankings
            all_players_sorted = sorted(
                all_players,
                key=lambda p: all_player_acs.get(p.get("puuid", ""), 0),
                reverse=True,
            )

            # Create mapping of puuid to overall placement
            puuid_to_placement = {
                p.get("puuid", ""): i + 1 for i, p in enumerate(all_players_sorted)
            }

            # Separate by team and sort by ACS within each team
            red_team = sorted(
                [p for p in all_players if p.get("team", "").lower() == "red"],
                key=lambda p: all_player_acs.get(p.get("puuid", ""), 0),
                reverse=True,
            )
            blue_team = sorted(
                [p for p in all_players if p.get("team", "").lower() == "blue"],
                key=lambda p: all_player_acs.get(p.get("puuid", ""), 0),
                reverse=True,
            )

            def format_player_line(player):
                """Format a single player's stats line with overall placement."""
                stats = player.get("stats", {})
                character = player.get("character", {})
                rank = player.get("currenttier_patched", "Unranked")

                name = player.get("name", "Unknown")
                tag = player.get("tag", "")
                puuid = player.get("puuid", "")

                is_me = puuid == requesting_player_puuid
                prefix = "**➤**" if is_me else "  "

                kills = stats.get("kills", 0)
                deaths = stats.get("deaths", 0)
                assists = stats.get("assists", 0)
                agent = (
                    character.get("name", "Unknown")
                    if isinstance(character, dict)
                    else character
                )

                # Headshot %
                head = stats.get("headshots", 0)
                body = stats.get("bodyshots", 0)
                leg = stats.get("legshots", 0)
                total_shots = head + body + leg
                hs_pct = int((head / total_shots * 100)) if total_shots > 0 else 0

                # ACS
                score = stats.get("score", 0)
                total_rounds = red_score + blue_score
                acs = round(score / total_rounds) if total_rounds > 0 else 0

                # First blood stats
                fb_data = fb_stats.get(puuid, {"fb": 0, "fd": 0})
                fb = fb_data["fb"]
                fd = fb_data["fd"]
                fb_str = f" 🩸{fb}" if fb > 0 else ""
                fd_str = f" 💀{fd}" if fd > 0 else ""

                # Overall placement
                overall_placement = puuid_to_placement.get(puuid, "?")

                return (
                    f"{prefix} `{kills:2d}/{deaths:2d}/{assists:2d}` "
                    f"**{name}#{tag}** | {agent} [{rank}]\n"
                    f"         HS: {hs_pct:2d}% | ACS: {acs:3d} • #{overall_placement}{fb_str}{fd_str}"
                )

            # Format red team with overall placements
            red_lines = [format_player_line(p) for p in red_team]
            red_field_value = "\n".join(red_lines) if red_lines else "No players"

            # Format blue team with overall placements
            blue_lines = [format_player_line(p) for p in blue_team]
            blue_field_value = "\n".join(blue_lines) if blue_lines else "No players"

            # Add team fields
            embed.add_field(
                name=f"🔴 Red Team ({red_score})",
                value=red_field_value,
                inline=False,
            )

            embed.add_field(
                name=f"🔵 Blue Team ({blue_score})",
                value=blue_field_value,
                inline=False,
            )

            # Add match stats footer
            if started_at:
                try:
                    match_time = convert_to_datetime(started_at)
                    embed.timestamp = match_time
                except Exception:
                    pass

            total_rounds = red_score + blue_score
            footer_text = f"➤ = You | # = Overall ACS Placement (1-10) | 🩸 = First Bloods | 💀 = First Deaths | Total Rounds: {total_rounds}"
            embed.set_footer(text=footer_text)

            return embed

        except Exception as e:
            logger.error(f"Error building scoreboard: {e}", exc_info=True)
            return self._build_error_embed("Failed to build scoreboard")

    def _build_error_embed(self, error_msg: str) -> discord.Embed:
        """Build a simple error embed."""
        return discord.Embed(
            title="❌ Error",
            description=error_msg,
            color=discord.Color.red(),
        )

    async def build_overall_stats(self, matches, player_puuid: str):
        """
        Build comprehensive overall statistics from matches.

        REFACTORED: Uses consolidated extract_match_player_stats() for detailed stats
        """
        total_kills = total_deaths = total_assists = 0
        total_headshots = total_body_shots = total_leg_shots = 0
        total_score = total_rounds = 0
        first_bloods = first_deaths = 0
        wins = losses = draws = 0
        placements_per_game = []

        recent_matches = matches[:MAX_RECENT_MATCHES]
        logger.info(
            f"Fetching detailed stats for {len(recent_matches)} matches (limited from {len(matches)})..."
        )

        # Aggregate basic stats from all matches
        for match in matches:
            stats = match.get("stats", {})
            shots = stats.get("shots", {})
            teams = match.get("teams", {})

            total_kills += stats.get("kills", 0)
            total_deaths += stats.get("deaths", 0)
            total_assists += stats.get("assists", 0)

            total_headshots += shots.get("head", 0)
            total_body_shots += shots.get("body", 0)
            total_leg_shots += shots.get("leg", 0)

            total_score += stats.get("score", 0)
            red_score = teams.get("red", 0)
            blue_score = teams.get("blue", 0)
            total_rounds += red_score + blue_score

            player_team = stats.get("team", "").lower()
            player_score = red_score if player_team == "red" else blue_score
            opp_score = blue_score if player_team == "red" else red_score

            if player_score > opp_score:
                wins += 1
            elif player_score < opp_score:
                losses += 1
            else:
                draws += 1

        # Batch fetch detailed stats for recent matches ONLY (reduced API calls)
        match_ids = [
            m.get("meta", {}).get("id")
            for m in recent_matches
            if m.get("meta", {}).get("id") and player_puuid
        ]

        if match_ids:
            match_details = await self.data_manager.batch_get_match_details(match_ids)

            for mid in match_ids:
                match_data = match_details.get(mid)
                if not match_data:
                    continue

                try:
                    # === REFACTORED: Single consolidated call ===
                    stats = await extract_match_player_stats(match_data, player_puuid)
                    first_bloods += stats["player_fb"]
                    first_deaths += stats["player_fd"]

                    if stats["player_placement"]:
                        placements_per_game.append(stats["player_placement"])
                    # =========================================

                except Exception as e:
                    logger.warning(f"Error processing stats for match {mid}: {e}")

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
            "fb_analyzed_matches": len(match_ids),
            "placements_per_game": placements_per_game,
        }

    async def build_kda_lines(self, matches, player_puuid: str):
        """
        Build KDA display lines from matches with placement information.

        REFACTORED: Uses consolidated extract_match_player_stats()
        """
        lines = []
        detailed_matches = matches[:MAX_KDA_DISPLAY]

        # Batch fetch match details
        match_ids = [
            m.get("meta", {}).get("id")
            for m in detailed_matches
            if m.get("meta", {}).get("id")
        ]

        match_details_map = {}
        if match_ids:
            match_details = await self.data_manager.batch_get_match_details(match_ids)
            match_details_map = {
                mid: data for mid, data in match_details.items() if data
            }

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
            agent = (
                character.get("name", "Unknown")
                if isinstance(character, dict)
                else character
            )
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

            result_emoji = (
                "✅"
                if team_score > opp_score
                else "❌" if team_score < opp_score else "➖"
            )

            # Get first blood stats and placement from pre-fetched data
            fb_indicator = fd_indicator = ""
            placement_indicator = ""
            match_id = meta.get("id")

            if match_id in match_details_map:
                try:
                    match_data = match_details_map[match_id]

                    match_stats = await extract_match_player_stats(
                        match_data, player_puuid
                    )
                    fb_count = match_stats["player_fb"]
                    fd_count = match_stats["player_fd"]
                    placement = match_stats["player_placement"]

                    fb_indicator = f" 🩸×{fb_count}" if fb_count > 0 else ""
                    fd_indicator = f" 💀×{fd_count}" if fd_count > 0 else ""

                    if placement:
                        placement_indicator = f" • 📊 #{placement}"
                    # =========================================

                except Exception as e:
                    logger.warning(f"Error getting match stats: {e}")

            lines.append(
                f"{result_emoji} **{map_name}** ({map_score}) • {agent}\n"
                f"└ `{kills}/{deaths}/{assists}` • HS: {hs_rate} • ACS: {avg_score}{placement_indicator}{fb_indicator}{fd_indicator}"
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

            player_puuid = matches[0].get("stats", {}).get("puuid")

            competitive_matches = self.filter_matches(matches, mode="Competitive")
            if not competitive_matches:
                return await interaction.followup.send(
                    f"No Competitive matches found for {name}#{tag}.", ephemeral=True
                )

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

            overall = await self.build_overall_stats(
                matches_in_time_window, player_puuid
            )
            map_stats = self.build_stats(
                matches_in_time_window,
                lambda meta: meta.get("map", {}).get("name", "Unknown"),
            )
            kda_lines = await self.build_kda_lines(matches_in_time_window, player_puuid)

            embed = discord.Embed(
                title=f"📊 {name}#{tag}",
                description=f"**Season {latest_season}** • Last {time} hours • {overall['matches']} matches",
                color=discord.Color.red(),
            )

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

            if overall["placements_per_game"]:
                placements_list = " ".join(
                    f"#{p}" for p in overall["placements_per_game"]
                )
                avg_placement = sum(overall["placements_per_game"]) / len(
                    overall["placements_per_game"]
                )
                embed.add_field(
                    name="📊 Placements",
                    value=(
                        f"**Per Match:** {placements_list}\n"
                        f"**Average:** #{avg_placement:.1f}"
                    ),
                    inline=False,
                )

            if map_stats:
                map_lines = []
                for map_name, stats in sorted(
                    map_stats.items(), key=lambda x: -x[1]["total"]
                )[:MAX_MAP_DISPLAY]:
                    w, l, d = stats["wins"], stats["losses"], stats["draws"]
                    total = stats["total"]
                    wr = (w / total * 100) if total > 0 else 0
                    map_lines.append(f"**{map_name}:** {w}-{l}-{d} ({wr:.0f}%)")

                embed.add_field(
                    name="🗺️ Map Performance",
                    value="\n".join(map_lines),
                    inline=False,
                )

            embed.add_field(
                name="🔫 Recent Matches",
                value="\n".join(kda_lines) or "No match data available.",
                inline=False,
            )

            embed.set_footer(text="🩸 = First Bloods | 💀 = First Deaths")

            most_recent_match = matches_in_time_window[0]
            scoreboard_embed = await self.build_scoreboard_embed(
                most_recent_match, player_puuid
            )

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
            logger.error(f"Error fetching stats for {name}#{tag}: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An unexpected error occurred while fetching stats.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantStats(bot))
