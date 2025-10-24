import discord
from logger import setup_logger

logger = setup_logger("ChannelsUtil")

# Maps display name to DB field name
CHANNEL_TYPES = {
    "Interest": "interest_channel_id",
    "Patch Notes": "patchnotes_channel_id",
    "Steam Games": "steam_games_channel_id",
    "Leaderboard Announcements": "leaderboard_announcements_channel_id",
    "Mod Logs": "mod_log_channel_id",
    "OSRS Margin Alerts": "osrs_margin_channel_id",
    "OSRS Below Average Alerts": "osrs_below_avg_channel_id",
}

# Extract valid DB keys for validation
VALID_CHANNEL_TYPES = set(CHANNEL_TYPES.values())


def get_channel_display_info(channel_type: str) -> dict:
    """
    Get display information for a channel type.

    Args:
        channel_type: Database field name

    Returns:
        Dict with display_name, description, emoji
    """
    channel_info = {
        "interest_channel_id": {
            "name": "Interest",
            "description": "For sharing interesting links and discussions",
            "emoji": "💬",
        },
        "patchnotes_channel_id": {
            "name": "Patch Notes",
            "description": "For game and software patch announcements",
            "emoji": "📝",
        },
        "steam_games_channel_id": {
            "name": "Steam Games",
            "description": "For Steam game announcements and updates",
            "emoji": "🎮",
        },
        "leaderboard_announcements_channel_id": {
            "name": "Leaderboard Announcements",
            "description": "For ranking and leaderboard updates",
            "emoji": "🏆",
        },
        "mod_log_channel_id": {
            "name": "Mod Logs",
            "description": "For moderation actions and logs",
            "emoji": "🔨",
        },
        "osrs_margin_channel_id": {
            "name": "OSRS Margin Alerts",
            "description": "For high margin OSRS item alerts",
            "emoji": "💰",
        },
        "osrs_below_avg_channel_id": {
            "name": "OSRS Below Average Alerts",
            "description": "For OSRS items below average price",
            "emoji": "📉",
        },
    }
    return channel_info.get(
        channel_type,
        {
            "name": "Unknown",
            "description": "Unknown channel type",
            "emoji": "❓",
        },
    )


async def broadcast_embed_to_guilds(
    bot, channel_type: str, embed: discord.Embed, view: discord.ui.View = None
) -> dict:
    """
    Broadcast an embed to a specific channel type across all guilds.

    Args:
        bot: Discord bot instance
        channel_type: Database field name (e.g., 'leaderboard_announcements_channel_id')
        embed: Discord embed to send
        view: Optional Discord view with buttons/interactions

    Returns:
        Dict with statistics about the broadcast
    """
    stats = {
        "sent": 0,
        "failed": 0,
        "no_channel": 0,
        "permission_error": 0,
        "not_found": 0,
    }

    for guild in bot.guilds:
        try:
            channel_id = await bot.database.guild_db.get_channel(guild.id, channel_type)

            if not channel_id:
                stats["no_channel"] += 1
                continue

            try:
                # Fetch channel (works even for archived threads)
                channel = await bot.fetch_channel(channel_id)
            except discord.NotFound:
                logger.warning(
                    f"Channel {channel_id} not found in guild {guild.id} ({guild.name})"
                )
                stats["not_found"] += 1
                continue
            except discord.Forbidden:
                logger.warning(
                    f"Cannot access channel {channel_id} in guild {guild.id} ({guild.name})"
                )
                stats["permission_error"] += 1
                continue

            # Unarchive thread if necessary
            if isinstance(channel, discord.Thread) and channel.archived:
                try:
                    await channel.edit(archived=False)
                    logger.debug(
                        f"Unarchived thread {channel.name} in guild {guild.name}"
                    )
                except discord.Forbidden:
                    logger.warning(
                        f"Cannot unarchive thread {channel.name} ({channel.id}) in guild {guild.id}"
                    )
                    stats["permission_error"] += 1
                    continue

            # Send the embed
            try:
                await channel.send(embed=embed, view=view)
                stats["sent"] += 1
                logger.debug(f"Sent embed to {channel.name} in guild {guild.name}")
            except discord.Forbidden:
                logger.warning(
                    f"Missing permission to send messages in {channel.name} ({channel.id}) for guild {guild.name} ({guild.id})"
                )
                stats["permission_error"] += 1
            except discord.HTTPException as e:
                logger.error(
                    f"Failed to send embed to {channel.name} ({channel.id}) in guild {guild.name} ({guild.id}): {e}"
                )
                stats["failed"] += 1

        except Exception as e:
            logger.error(
                f"Unexpected error broadcasting to guild {guild.id}: {e}",
                exc_info=True,
            )
            stats["failed"] += 1

    # Log summary
    logger.info(
        f"Broadcast complete: {stats['sent']} sent, "
        f"{stats['failed']} failed, {stats['no_channel']} no channel set, "
        f"{stats['permission_error']} permission errors, "
        f"{stats['not_found']} not found"
    )

    return stats


async def send_to_mod_log(
    bot, guild: discord.Guild, embed: discord.Embed, reason: str = None
) -> bool:
    """
    Send a message to a guild's mod log channel.

    Args:
        bot: Discord bot instance
        guild: Discord guild
        embed: Discord embed to send
        reason: Optional reason for logging

    Returns:
        True if successful, False otherwise
    """
    if not guild:
        logger.warning("Cannot send mod log: guild is None")
        return False

    try:
        mod_log_id = await bot.database.guild_db.get_channel(
            guild.id, "mod_log_channel_id"
        )

        if not mod_log_id:
            logger.debug(f"No mod log channel set for guild {guild.id}")
            return False

        channel = guild.get_channel(mod_log_id)

        if not channel:
            logger.warning(
                f"Mod log channel {mod_log_id} not found in guild {guild.id}"
            )
            return False

        # Add reason to embed if provided
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)

        await channel.send(embed=embed)
        logger.info(f"Sent mod log to guild {guild.id}")
        return True

    except discord.Forbidden:
        logger.warning(f"Missing permissions to send to mod log in guild {guild.id}")
        return False
    except discord.NotFound:
        logger.warning(f"Mod log channel not found in guild {guild.id}")
        return False
    except Exception as e:
        logger.error(
            f"Failed to send mod log message in guild {guild.id}: {e}",
            exc_info=True,
        )
        return False


async def get_or_create_notification_embed(
    title: str,
    description: str,
    color: discord.Color = discord.Color.blue(),
    footer_text: str = None,
) -> discord.Embed:
    """
    Create a standardized notification embed.

    Args:
        title: Embed title
        description: Embed description
        color: Embed color
        footer_text: Optional footer text

    Returns:
        Formatted Discord embed
    """
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
    )

    if footer_text:
        embed.set_footer(text=footer_text)

    return embed
