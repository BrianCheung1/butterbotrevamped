-- Users Table
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    daily_streak INTEGER DEFAULT 0,
    last_daily_at TIMESTAMP DEFAULT NULL
);

-- User Game Stats Table
CREATE TABLE IF NOT EXISTS user_game_stats (
    user_id INTEGER PRIMARY KEY,
    rolls_won INTEGER DEFAULT 0,
    rolls_lost INTEGER DEFAULT 0,
    rolls_played INTEGER DEFAULT 0,
    rolls_total_won INTEGER DEFAULT 0,
    rolls_total_lost INTEGER DEFAULT 0,
    blackjacks_won INTEGER DEFAULT 0,
    blackjacks_lost INTEGER DEFAULT 0,
    blackjacks_played INTEGER DEFAULT 0,
    blackjacks_total_won INTEGER DEFAULT 0,
    blackjacks_total_lost INTEGER DEFAULT 0,
    slots_won INTEGER DEFAULT 0,
    slots_lost INTEGER DEFAULT 0,
    slots_played INTEGER DEFAULT 0,
    slots_total_won INTEGER DEFAULT 0,
    slots_total_lost INTEGER DEFAULT 0,
    wordles_won INTEGER DEFAULT 0,
    wordles_lost INTEGER DEFAULT 0,
    wordles_played INTEGER DEFAULT 0,
    roulettes_won INTEGER DEFAULT 0,
    roulettes_lost INTEGER DEFAULT 0,
    roulettes_played INTEGER DEFAULT 0,
    roulettes_total_won INTEGER DEFAULT 0,
    roulettes_total_lost INTEGER DEFAULT 0,
    duel_stats TEXT DEFAULT '{}',  -- Store duel stats as a JSON
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- User Heist Stats Table
CREATE TABLE IF NOT EXISTS user_heist_stats (
    user_id INTEGER PRIMARY KEY,
    heists_joined INTEGER DEFAULT 0,
    heists_won INTEGER DEFAULT 0,
    heists_lost INTEGER DEFAULT 0,
    total_loot_gained INTEGER DEFAULT 0,
    total_loot_lost INTEGER DEFAULT 0,
    backstabs INTEGER DEFAULT 0,
    times_betrayed INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- User Steal Stats Table
CREATE TABLE IF NOT EXISTS user_steal_stats (
    user_id INTEGER PRIMARY KEY,
    steals_attempted INTEGER DEFAULT 0,
    steals_successful INTEGER DEFAULT 0,
    steals_failed INTEGER DEFAULT 0,
    total_amount_stolen INTEGER DEFAULT 0,
    amount_lost_to_failed_steals INTEGER DEFAULT 0,
    amount_stolen_by_others INTEGER DEFAULT 0,
    times_stolen_from INTEGER DEFAULT 0,
    amount_gained_from_failed_steals INTEGER DEFAULT 0,
    last_stolen_from_at TIMESTAMP DEFAULT NULL,
    last_stole_from_other_at TIMESTAMP DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- User Player Stats Table
CREATE TABLE IF NOT EXISTS user_player_stats (
    user_id INTEGER PRIMARY KEY,
    player_hp INTEGER DEFAULT 100,
    player_attack INTEGER DEFAULT 5,
    player_defense INTEGER DEFAULT 5,
    player_speed INTEGER DEFAULT 5,
    player_level INTEGER DEFAULT 1,
    player_xp INTEGER DEFAULT 0,
    player_next_level_xp INTEGER DEFAULT 50,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Inventory Table
CREATE TABLE IF NOT EXISTS user_inventory (
    user_id INTEGER,
    item_name TEXT,
    quantity INTEGER DEFAULT 1,
    PRIMARY KEY(user_id, item_name),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- User Tools Table
CREATE TABLE IF NOT EXISTS user_equipped_tools (
    user_id INTEGER PRIMARY KEY,
    pickaxe TEXT,
    fishingrod TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- User Bank Table
CREATE TABLE IF NOT EXISTS user_bank_stats (
    user_id INTEGER PRIMARY KEY,
    bank_balance INTEGER DEFAULT 0,
    bank_cap INTEGER DEFAULT 1000000,
    bank_level INTEGER DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- User Work Table
CREATE TABLE IF NOT EXISTS user_work_stats (
    user_id INTEGER PRIMARY KEY,
    total_mining INTEGER DEFAULT 0,
    total_mining_value INTEGER DEFAULT 0,
    mining_level INTEGER DEFAULT 1,
    mining_xp INTEGER DEFAULT 0,
    mining_next_level_xp INTEGER DEFAULT 50,
    total_fishing INTEGER DEFAULT 0,
    total_fishing_value INTEGER DEFAULT 0,
    fishing_level INTEGER DEFAULT 1,
    fishing_xp INTEGER DEFAULT 0,
    fishing_next_level_xp INTEGER DEFAULT 50,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- User Buffs Table
CREATE TABLE IF NOT EXISTS user_buffs (
    user_id INTEGER,
    buff_type TEXT NOT NULL,             
    multiplier REAL NOT NULL DEFAULT 1,  
    expires_at TIMESTAMP NOT NULL,       
    PRIMARY KEY (user_id, buff_type),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Valorant Player Table
CREATE TABLE IF NOT EXISTS players (
    name TEXT NOT NULL,
    tag TEXT NOT NULL,
    rank TEXT,
    elo INTEGER,
    last_updated TIMESTAMP,
    PRIMARY KEY (name, tag)
);

CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    title TEXT NOT NULL,
    imdb_id TEXT NOT NULL,
    imdb_link TEXT,
    added_by_id TEXT NOT NULL,
    added_by_name TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    UNIQUE (guild_id, imdb_id)
);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    interest_channel_id INTEGER
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_message TEXT NOT NULL,
    bot_response TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
