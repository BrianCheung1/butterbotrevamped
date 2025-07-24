import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import json


class MessageLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_cache = (
            {}
        )  # message_id: {content, author_id, attachments, channel_id}
        self.cache_limit = 2000
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if not message.attachments:  # Only cache & save if there are attachments
            return

        # Cache message info
        self.message_cache[message.id] = {
            "content": message.content,
            "author_id": message.author.id,
            "attachments": [a.url for a in message.attachments],
            "channel_id": message.channel.id,
        }

        # Enforce cache size limit (FIFO)
        if len(self.message_cache) > self.cache_limit:
            self.message_cache.pop(next(iter(self.message_cache)))

        # Save to DB asynchronously only for messages with attachments
        await self.save_message_to_db(message)

    async def save_message_to_db(self, message: discord.Message):
        attachments_json = json.dumps([a.url for a in message.attachments])
        created_at = message.created_at.isoformat()
        try:
            await self.bot.database.message_db.log_new_message(
                message.id,
                message.guild.id,
                message.channel.id,
                message.author.id,
                message.content,
                attachments_json,
                created_at,
            )
        except Exception as e:
            self.bot.logger.error(f"Failed to save message {message.id} to DB: {e}")

    async def get_message_info(self, message: discord.Message):
        # Try cache first
        cached = self.message_cache.get(message.id)
        if cached:
            # Resolve author and channel from cache and bot cache
            author = self.bot.get_user(cached["author_id"])
            channel = self.bot.get_channel(cached["channel_id"])
            return {
                "content": cached["content"],
                "attachments": cached["attachments"],
                "author": author,
                "channel": channel,
            }

        # Fallback to DB query
        try:
            db_data = await self.bot.database.message_db.get_message_log(message.id)
        except Exception as e:
            self.bot.logger.error(f"Failed to get message {message.id} from DB: {e}")
            return None

        if not db_data:
            return None

        attachments = json.loads(db_data.get("attachments") or "[]")
        author = self.bot.get_user(db_data.get("author_id"))
        channel = self.bot.get_channel(db_data.get("channel_id"))

        return {
            "content": db_data.get("content"),
            "attachments": attachments,
            "author": author,
            "channel": channel,
        }

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        info = await self.get_message_info(message)
        content = (
            info["content"]
            if info and info["content"]
            else (message.content or "*No content*")
        )
        attachments = info["attachments"] if info else []

        description_lines = [
            f"🗑️ Message sent by {message.author.mention} deleted in {message.channel.mention}",
            "",
            "**Content:**",
            content,
            "",
        ]
        for i, url in enumerate(attachments, 1):
            description_lines.append(f"**Attachment {i}:** {url}")

        embed = discord.Embed(
            description="\n".join(description_lines),
            color=discord.Color.red(),
            timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        )
        embed.set_author(
            name=str(message.author),
            icon_url=message.author.display_avatar.url,
        )

        await self.send_to_mod_log(message.guild, embed)

        # Mark message as deleted in DB (optional)
        try:
            await self.bot.database.message_db.mark_message_deleted(
                message.id, datetime.utcnow().isoformat()
            )
        except Exception as e:
            self.bot.logger.error(
                f"Failed to mark message {message.id} deleted in DB: {e}"
            )

        # Remove from cache
        self.message_cache.pop(message.id, None)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return

        # Compare content and attachments
        before_attachments = [a.url for a in before.attachments]
        after_attachments = [a.url for a in after.attachments]

        if before.content == after.content and before_attachments == after_attachments:
            # No change in content or attachments, ignore
            return

        message_link = f"https://discord.com/channels/{before.guild.id}/{before.channel.id}/{before.id}"

        # Build description with changes
        description_lines = [
            f"📝 Message sent by {before.author.mention} edited in {before.channel.mention}\n"
        ]

        if before.content != after.content:
            description_lines.append(
                f"**Old message**\n{before.content or '*No content*'}\n"
            )
            description_lines.append(
                f"**New message**\n{after.content or '*No content*'}\n"
            )

        if before_attachments != after_attachments:
            description_lines.append("**Attachments changed:**\n")
            description_lines.append(f"**Before:**\n")
            if before_attachments:
                for i, url in enumerate(before_attachments, 1):
                    description_lines.append(f"{i}. {url}")
            else:
                description_lines.append("No attachments")
            description_lines.append(f"\n**After:**\n")
            if after_attachments:
                for i, url in enumerate(after_attachments, 1):
                    description_lines.append(f"{i}. {url}")
            else:
                description_lines.append("No attachments")
            description_lines.append("")

        description_lines.append(f"[Jump to message]({message_link})")

        description = "\n".join(description_lines)

        embed = discord.Embed(
            description=description,
            color=discord.Color.orange(),
            timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        )
        embed.set_author(
            name=str(before.author),
            icon_url=before.author.display_avatar.url,
        )

        await self.send_to_mod_log(before.guild, embed)

        # Update cache & DB with new content and attachments
        if after.id in self.message_cache:
            self.message_cache[after.id]["content"] = after.content
            self.message_cache[after.id]["attachments"] = after_attachments

        try:
            await self.bot.database.message_db.update_message_content(
                after.id, after.content
            )
            # Optionally, also update attachments in DB if you track them
            await self.bot.database.message_db.update_message_attachments(
                after.id, json.dumps(after_attachments)
            )
        except Exception as e:
            self.bot.logger.error(
                f"Failed to update message {after.id} content or attachments in DB: {e}"
            )

    async def send_to_mod_log(self, guild: discord.Guild, embed: discord.Embed):
        if not guild:
            return
        try:
            mod_log_id = await self.bot.database.guild_db.get_channel(
                guild.id, "mod_log_channel_id"
            )
            if not mod_log_id:
                return
            channel = guild.get_channel(mod_log_id)
            if not channel:
                return
            await channel.send(embed=embed)
        except discord.Forbidden:
            self.bot.logger.warning(
                f"Missing permissions to send to mod log in guild {guild.id}."
            )
        except Exception as e:
            self.bot.logger.error(
                f"Failed to send mod log message in guild {guild.id}: {e}"
            )

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        # Runs once a day to delete logs older than 30 days
        try:
            cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
            await self.bot.database.message_db.delete_old_logs(cutoff)
            self.bot.logger.info("Cleaned up old message logs older than 30 days")
        except Exception as e:
            self.bot.logger.error(f"Error during message logs cleanup: {e}")

    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(MessageLogger(bot))
