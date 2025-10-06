-- Leaderboard indexes
CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance DESC) WHERE balance > 0;
CREATE INDEX IF NOT EXISTS idx_bank_balance ON user_bank_stats(bank_balance DESC) WHERE bank_balance > 0;
CREATE INDEX IF NOT EXISTS idx_work_mining ON user_work_stats(mining_level DESC, mining_xp DESC);
CREATE INDEX IF NOT EXISTS idx_work_fishing ON user_work_stats(fishing_level DESC, fishing_xp DESC);

-- Cooldown lookups
CREATE INDEX IF NOT EXISTS idx_steal_cooldowns ON user_steal_stats(last_stolen_from_at, last_stole_from_other_at);
CREATE INDEX IF NOT EXISTS idx_daily_streak ON users(daily_streak) WHERE daily_streak > 0;

-- Foreign key lookups
CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_roll_history_user ON roll_history(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_reminders_time ON reminders(remind_at);
CREATE INDEX IF NOT EXISTS idx_message_logs_guild ON message_logs(guild_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_message_logs_created ON message_logs(created_at);

-- Buff expiration lookups
CREATE INDEX IF NOT EXISTS idx_buffs_expiry ON user_buffs(expires_at);