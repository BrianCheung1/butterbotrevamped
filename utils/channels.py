import discord


# Maps display name to DB field name
CHANNEL_TYPES = {
    "Interest": "interest_channel_id",
    "Patch Notes": "patchnotes_channel_id",
    "Steam Games": "steam_games_channel_id",
    "Leaderboard Announcements": "leaderboard_announcements_channel_id",
    "Mod Logs": "mod_log_channel_id",
    # Add more here as needed
}

# Extract valid DB keys for validation
VALID_CHANNEL_TYPES = set(CHANNEL_TYPES.values())


async def broadcast_embed_to_guilds(
    bot, channel_type: str, embed: discord.Embed, view: discord.ui.View = None
):
    for guild in bot.guilds:
        channel_id = await bot.database.guild_db.get_channel(guild.id, channel_type)
        if not channel_id:
            continue

        channel = guild.get_channel(channel_id)
        if channel is None:
            continue

        try:
            await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            bot.logger.warning(
                f"Missing permission to send messages in {channel.name} ({channel.id}) for guild {guild.name} ({guild.id})"
            )
        except discord.HTTPException as e:
            bot.logger.error(
                f"Failed to send embed to {channel.name} ({channel.id}) in guild {guild.name} ({guild.id}): {e}"
            )


async def send_to_mod_log(bot, guild: discord.Guild, embed: discord.Embed):
    if not guild:
        return

    try:
        mod_log_id = await bot.database.guild_db.get_channel(
            guild.id, "mod_log_channel_id"
        )
        if not mod_log_id:
            return

        channel = guild.get_channel(mod_log_id)
        if not channel:
            return

        await channel.send(embed=embed)

    except discord.Forbidden:
        bot.logger.warning(
            f"Missing permissions to send to mod log in guild {guild.id}."
        )
    except Exception as e:
        bot.logger.error(f"Failed to send mod log message in guild {guild.id}: {e}")
