# cogs/logging/message_logger.py
import json
from datetime import datetime, timezone

import discord
from discord.ext import commands
from utils.channels import send_to_mod_log


class MessageLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_cache = {}
        self.cache_limit = 2000

    def cog_unload(self):
        self.message_cache.clear()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        timestamp = message.created_at.strftime("%I:%M:%S:%p")

        if message.guild:
            guild_name = message.guild.name
            channel_name = f"#{message.channel.name}"
            prefix = f"[{guild_name}][{channel_name}]"
        else:
            author_tag = f"{message.author.name}#{message.author.discriminator}"
            prefix = f"[DM][{author_tag}]"

        user_display = message.author.display_name

        if message.content.strip():
            content_to_log = message.content
        else:
            parts = []
            # Add attachments URLs if any
            if message.attachments:
                parts.extend(a.url for a in message.attachments)
            # Add sticker names if any
            if message.stickers:
                parts.extend(
                    f"[Sticker: {sticker.name}]" for sticker in message.stickers
                )

            content_to_log = " ".join(parts)

        log_line = f"{prefix}[{timestamp}] {user_display}: {content_to_log}"

        self.bot.logger.info(log_line)

        if not message.attachments and not message.stickers:
            return

        self.message_cache[message.id] = {
            "content": message.content,
            "author_id": message.author.id,
            "attachments": [a.url for a in message.attachments],
            "stickers": [sticker.name for sticker in message.stickers],
            "channel_id": message.channel.id,
        }

        if len(self.message_cache) > self.cache_limit:
            self.message_cache.pop(next(iter(self.message_cache)))

        await self.save_message_to_db(message)

    async def save_message_to_db(self, message: discord.Message):
        try:
            await self.bot.database.message_db.log_new_message(
                message.id,
                message.guild.id,
                message.channel.id,
                message.author.id,
                message.content,
                json.dumps([a.url for a in message.attachments]),
                message.created_at.replace(tzinfo=None).isoformat(),
            )
        except Exception as e:
            self.bot.logger.error(f"Failed to save message {message.id} to DB: {e}")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return

        embed = discord.Embed(
            description=(
                f"📝 [Message edited]({after.jump_url}) in {before.channel.mention} by {before.author.mention}\n\n"
                f"**Before:**\n{before.content or '*No content*'}\n\n"
                f"**After:**\n{after.content or '*No content*'}"
            ),
            color=discord.Color.orange(),
            timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        )
        embed.set_author(
            name=str(before.author), icon_url=before.author.display_avatar.url
        )

        await send_to_mod_log(self.bot, before.guild, embed)

        if after.id in self.message_cache:
            self.message_cache[after.id]["content"] = after.content

        try:
            await self.bot.database.message_db.update_message_content(
                after.id, after.content
            )
        except Exception as e:
            self.bot.logger.error(f"Failed to update message {after.id}: {e}")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        cached = self.message_cache.get(message.id)
        attachments = cached["attachments"] if cached else []
        content = cached["content"] if cached else message.content or "*No content*"

        embed = discord.Embed(
            description=(
                f"🗑️ Message deleted in {message.channel.mention} by {message.author.mention}\n\n"
                f"**Content:**\n{content}\n\n"
                + "\n".join(
                    f"**Attachment {i+1}:** {url}" for i, url in enumerate(attachments)
                )
            ),
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )
        embed.set_author(
            name=str(message.author), icon_url=message.author.display_avatar.url
        )

        await send_to_mod_log(self.bot, message.guild, embed)

        try:
            await self.bot.database.message_db.mark_message_deleted(
                message.id, datetime.utcnow().isoformat()
            )
        except Exception as e:
            self.bot.logger.error(f"Failed to mark message deleted: {e}")

        self.message_cache.pop(message.id, None)


async def setup(bot):
    await bot.add_cog(MessageLogger(bot))
