# Existing RANK_ORDER should stay in this file
RANK_ORDER = {
    "radiant": 28,
    "immortal 3": 27,
    "immortal 2": 26,
    "immortal 1": 25,
    "ascendant 3": 24,
    "ascendant 2": 23,
    "ascendant 1": 22,
    "diamond 3": 21,
    "diamond 2": 20,
    "diamond 1": 19,
    "platinum 3": 18,
    "platinum 2": 17,
    "platinum 1": 16,
    "gold 3": 15,
    "gold 2": 14,
    "gold 1": 13,
    "silver 3": 12,
    "silver 2": 11,
    "silver 1": 10,
    "bronze 3": 9,
    "bronze 2": 8,
    "bronze 1": 7,
    "iron 3": 6,
    "iron 2": 5,
    "iron 1": 4,
    "unrated": 0,
}

# FIXED: Centralized configuration for Valorant module
VALORANT_CONFIG = {
    # API Caching durations (in seconds)
    "cache_ttl": {
        "mmr": 300,  # 5 minutes
        "match_history": 300,  # 5 minutes
        "match_details": 3600,  # 60 minutes
        "mmr_history": 300,  # 5 minutes
        "stored_mmr": 600,  # 10 minutes
    },
    # Pagination settings
    "pagination": {
        "leaderboard_entries_per_page": 10,
        "stats_recent_matches": 8,
        "max_kda_display": 8,
        "max_map_display": 5,
        "max_recent_matches_detailed": 50,  # Limit detailed processing
    },
    # Batch processing settings
    "batch_processing": {
        "mmr_update_batch_size": 5,
        "mmr_update_delay": 60,
        "match_details_batch_size": 10,
    },
    # UI timeouts (in seconds)
    "ui_timeouts": {
        "mmr_view": 180,
        "leaderboard_view": 86400,
        "stats_view": 300,
    },
    # Rate limiting
    "rate_limiting": {
        "max_requests_per_minute": 60,
        "rate_limit_window": 60,  # seconds
        "concurrent_requests": 5,  # max concurrent API calls
    },
    # Default values
    "defaults": {
        "region": "na",
        "time_window": 12,  # hours
        "stat_season": "latest",
    },
}
