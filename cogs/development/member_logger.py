from datetime import datetime, timezone

import discord
from discord.ext import commands
from utils.channels import send_to_mod_log


class MemberLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="📥 Member Joined",
            description=f"{member.mention} (`{member.id}`) joined the server.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        await send_to_mod_log(self.bot, member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            title="📤 Member Left",
            description=f"{member.mention} (`{member.id}`) left or was removed from the server.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        await send_to_mod_log(self.bot, member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="🔨 Member Banned",
            description=f"{user.mention} (`{user.id}`) was banned from the server.",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        await send_to_mod_log(self.bot, guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="🛡️ Member Unbanned",
            description=f"{user.mention} (`{user.id}`) was unbanned from the server.",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        await send_to_mod_log(self.bot, guild, embed)


async def setup(bot):
    await bot.add_cog(MemberLogger(bot))
