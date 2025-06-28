import discord


async def broadcast_embed_to_guilds(bot, channel_type: str, embed: discord.Embed):
    for guild in bot.guilds:
        channel_id = await bot.database.guild_db.get_channel(guild.id, channel_type)
        if not channel_id:
            continue

        channel = guild.get_channel(channel_id)
        if channel is None:
            continue

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            bot.logger.warning(
                f"Missing permission to send messages in {channel.name} ({channel.id}) for guild {guild.name} ({guild.id})"
            )
        except discord.HTTPException as e:
            bot.logger.error(
                f"Failed to send embed to {channel.name} ({channel.id}) in guild {guild.name} ({guild.id}): {e}"
            )
