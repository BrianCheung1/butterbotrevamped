from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional, Dict
from collections import defaultdict

import discord
from constants.valorant_config import RANK_ORDER
from discord.app_commands import Choice
from logger import setup_logger

logger = setup_logger("ValorantHelpers")


def convert_to_datetime(date_str: str) -> datetime:
    """Convert ISO 8601 string to a UTC-aware datetime object."""
    date_str = date_str.rstrip("Z")  # Remove trailing Z if present

    # Try parsing with microseconds
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")

    return dt.replace(tzinfo=timezone.utc)


def get_rank_value(rank_name: str) -> int:
    """Get numeric value for rank comparison."""
    return RANK_ORDER.get(rank_name.lower(), -1)


def parse_season(season_code: str):
    """Parse season code (e.g., 'e8a3') into (episode, act) tuple."""
    roman_map = {
        "I": 1,
        "II": 2,
        "III": 3,
        "IV": 4,
        "V": 5,
        "VI": 6,
        "VII": 7,
        "VIII": 8,
        "IX": 9,
        "X": 10,
    }

    try:
        episode = int(season_code[1 : season_code.index("a")])
        act_part = season_code[season_code.index("a") + 1 :]

        try:
            act = int(act_part)
        except ValueError:
            act = roman_map.get(act_part.upper(), 0)

        return (episode, act)
    except Exception:
        return (0, 0)


def parse_player_rank(current_data: dict) -> Tuple[str, int, int]:
    """
    Parse player rank information from current MMR data.

    Args:
        current_data: Current player data dict from API

    Returns:
        Tuple of (rank_name, current_rr, games_needed)

    Raises:
        ValueError: If current_data is invalid or missing required fields
    """
    if not current_data:
        raise ValueError("current_data cannot be None or empty")

    games_needed = current_data.get("games_needed_for_rating", 0)

    if games_needed > 0:
        return "Unrated", 0, games_needed

    try:
        rank = current_data.get("tier", {}).get("name", "Unknown")
        rr = current_data.get("rr", 0)

        if rank == "Unknown":
            logger.warning("Could not determine rank from current data")

        return rank, rr, 0
    except (KeyError, TypeError) as e:
        logger.warning(f"Error parsing player rank: {e}")
        raise ValueError(f"Invalid current_data structure: {e}")


def should_update_player(last_updated_str: Optional[str], hours: int = 2) -> bool:
    """
    Check if a player's MMR needs updating based on last update time.

    Args:
        last_updated_str: ISO 8601 datetime string from database
        hours: Update threshold in hours (default 2)

    Returns:
        bool: True if player needs updating, False otherwise
    """
    if not last_updated_str:
        return True

    try:
        last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        return now - last_updated >= timedelta(hours=hours)
    except Exception as e:
        logger.warning(f"Error parsing update timestamp: {e}")
        return True


def build_leaderboard_from_cache(all_players: dict) -> list[dict]:
    """
    Build sorted leaderboard from player cache.

    Args:
        all_players: Dict mapping (name, tag) -> {rank, elo, ...}

    Returns:
        List of player dicts sorted by rank and elo (descending)
    """
    leaderboard_data = [
        {
            "name": n,
            "tag": t,
            "rank": p["rank"],
            "elo": p["elo"],
        }
        for (n, t), p in all_players.items()
        if p["rank"].lower() != "unrated"
    ]

    leaderboard_data.sort(
        key=lambda x: (get_rank_value(x["rank"]), x["elo"]), reverse=True
    )

    return leaderboard_data


async def load_cached_players_from_db(db):
    """
    Load cached players from the database on bot startup.

    Args:
        db: Database manager instance

    Returns:
        Dict mapping (name, tag) -> {rank, elo, ...}
    """
    mmr_data = await db.get_all_player_mmr()
    logger.info(f"Loaded {len(mmr_data)} Valorant players from DB.")

    # Return as dict with tuple keys for batch_set()
    return {
        (d["name"], d["tag"]): {
            "rank": d["rank"],
            "elo": d["elo"],
        }
        for d in mmr_data
    }


async def name_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for player names from cached player list."""
    bot = interaction.client

    # Use thread-safe cache manager
    if not hasattr(bot, "valorant_players"):
        return []

    try:
        all_players = await bot.valorant_players.get_all()

        if not all_players:
            return []

        unique_names = sorted(
            set(
                name
                for name, tag in all_players.keys()
                if name.lower().startswith(current.lower())
            )
        )
        return [Choice(name=n, value=n) for n in unique_names[:25]]
    except Exception as e:
        logger.warning(f"Error in name_autocomplete: {e}")
        return []


async def tag_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for player tags based on selected name."""
    bot = interaction.client
    name = interaction.namespace.name  # what user selected for "name"

    # Use thread-safe cache manager
    if not hasattr(bot, "valorant_players") or not name:
        return []

    try:
        all_players = await bot.valorant_players.get_all()

        if not all_players:
            return []

        filtered_tags = sorted(
            {
                tag
                for n, tag in all_players.keys()
                if n.lower() == name.lower() and tag.lower().startswith(current.lower())
            }
        )
        return [Choice(name=t, value=t) for t in filtered_tags[:25]]
    except Exception as e:
        logger.warning(f"Error in tag_autocomplete: {e}")
        return []


def extract_match_stats_default() -> dict:
    """Return default match stats structure."""
    return {
        "player_fb": 0,
        "player_fd": 0,
        "all_player_acs": {},
        "all_player_fb_fd": {},
        "player_placement": None,
    }


async def extract_match_player_stats(
    match_data: dict, player_puuid: Optional[str] = None
) -> dict:
    """
    Extract all player stats from a match in a single pass.

    Consolidates extraction of:
    - First blood/death counts (per player and for specific player)
    - ACS (combat score) for all players
    - Player placement by ACS ranking

    Args:
        match_data: Full match data from Valorant API
        player_puuid: Optional PUUID of specific player to track

    Returns:
        Dict with keys:
        - player_fb (int): First bloods for player_puuid
        - player_fd (int): First deaths for player_puuid
        - all_player_acs (dict): {puuid: acs_score}
        - all_player_fb_fd (dict): {puuid: {fb: count, fd: count}}
        - player_placement (int or None): 1-10 placement by ACS
    """
    if not match_data or "data" not in match_data:
        return extract_match_stats_default()

    try:
        match_info = match_data["data"]
        rounds = match_info.get("rounds", [])

        # Initialize trackers
        all_player_acs = {}
        all_player_fb_fd = defaultdict(lambda: {"fb": 0, "fd": 0})
        player_fb = 0
        player_fd = 0

        # === Extract ACS for all players ===
        teams = match_info.get("teams", {})
        total_rounds = (
            sum(m.get("rounds_won", 0) for m in teams.values() if isinstance(m, dict))
            or 1
        )

        players_data = match_info.get("players", {})
        if isinstance(players_data, dict):
            all_players = players_data.get("all_players", [])
        else:
            all_players = players_data or []

        for player in all_players:
            puuid = player.get("puuid", "")
            score = player.get("stats", {}).get("score", 0)
            acs = round(score / total_rounds) if total_rounds > 0 else 0
            if puuid:
                all_player_acs[puuid] = acs

        # === Extract first blood data from rounds ===
        for round_data in rounds:
            kill_events = []
            for player_stat in round_data.get("player_stats", []):
                kill_events.extend(player_stat.get("kill_events", []))

            if not kill_events:
                continue

            # Find first kill of round
            sorted_kills = sorted(
                kill_events,
                key=lambda k: k.get("kill_time_in_round", float("inf")),
            )
            first_kill = sorted_kills[0]

            killer_puuid = first_kill.get("killer_puuid")
            victim_puuid = first_kill.get("victim_puuid")

            if killer_puuid:
                all_player_fb_fd[killer_puuid]["fb"] += 1
                if killer_puuid == player_puuid:
                    player_fb += 1

            if victim_puuid:
                all_player_fb_fd[victim_puuid]["fd"] += 1
                if victim_puuid == player_puuid:
                    player_fd += 1

        # === Calculate placement ===
        player_placement = None
        if player_puuid and all_player_acs:
            sorted_players = sorted(
                all_player_acs.items(), key=lambda x: x[1], reverse=True
            )
            for placement, (puuid, _) in enumerate(sorted_players, 1):
                if puuid == player_puuid:
                    player_placement = placement
                    break

        return {
            "player_fb": player_fb,
            "player_fd": player_fd,
            "all_player_acs": all_player_acs,
            "all_player_fb_fd": dict(all_player_fb_fd),
            "player_placement": player_placement,
        }

    except Exception as e:
        logger.error(f"Error extracting match stats: {e}", exc_info=True)
        return extract_match_stats_default()
