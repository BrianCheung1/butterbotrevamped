-- Users Table
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0
);

-- User Game Stats Table
CREATE TABLE IF NOT EXISTS user_game_stats (
    user_id INTEGER PRIMARY KEY,
    gambles_won INTEGER DEFAULT 0,
    gambles_lost INTEGER DEFAULT 0,
    gambles_played INTEGER DEFAULT 0,
    gambles_total_winnings INTEGER DEFAULT 0,
    gambles_total_losses INTEGER DEFAULT 0,
    blackjacks_won INTEGER DEFAULT 0,
    blackjacks_lost INTEGER DEFAULT 0,
    blackjacks_played INTEGER DEFAULT 0,
    blackjacks_total_winnings INTEGER DEFAULT 0,
    blackjacks_total_losses INTEGER DEFAULT 0,
    slots_won INTEGER DEFAULT 0,
    slots_lost INTEGER DEFAULT 0,
    slots_played INTEGER DEFAULT 0,
    slots_total_winnings INTEGER DEFAULT 0,
    slots_total_losses INTEGER DEFAULT 0,
    wordles_won INTEGER DEFAULT 0,
    wordles_lost INTEGER DEFAULT 0,
    wordles_played INTEGER DEFAULT 0,
    roulette_won INTEGER DEFAULT 0,
    roulette_lost INTEGER DEFAULT 0,
    roulette_played INTEGER DEFAULT 0,
    roulette_total_winnings INTEGER DEFAULT 0,
    roulette_total_losses INTEGER DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS inventory (
    user_id INTEGER,
    item_name TEXT,
    quantity INTEGER DEFAULT 1,
    PRIMARY KEY(user_id, item_name),
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
    mining_level INTEGER DEFAULT 1,
    mining_next_level_xp INTEGER DEFAULT 0,
    next_level_xp INTEGER DEFAULT 50,
    fishing_level INTEGER DEFAULT 1,
    fishing_xp INTEGER DEFAULT 0,
    fishing_next_level_xp INTEGER DEFAULT 50,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
