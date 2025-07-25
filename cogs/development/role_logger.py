import asyncio
from datetime import datetime

import discord
from discord.ext import commands
from utils.channels import send_to_mod_log


class RoleLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = discord.Embed(
            title="➕ Role Created",
            description=f"Role **{role.name}** (`{role.id}`) was created.",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        await send_to_mod_log(self.bot, role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = discord.Embed(
            title="➖ Role Deleted",
            description=f"Role **{role.name}** (`{role.id}`) was deleted.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )
        await send_to_mod_log(self.bot, role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes = []

        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Color:** `{before.color}` → `{after.color}`")
        if before.permissions != after.permissions:
            changes.append("**Permissions changed**")
        if before.mentionable != after.mentionable:
            changes.append(
                f"**Mentionable:** `{before.mentionable}` → `{after.mentionable}`"
            )
        if before.hoist != after.hoist:
            changes.append(
                f"**Displayed Separately:** `{before.hoist}` → `{after.hoist}`"
            )

        if not changes:
            return  # Nothing meaningful changed

        embed = discord.Embed(
            title="✏️ Role Updated",
            description=f"Role **{after.name}** (`{after.id}`) was updated.",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        await send_to_mod_log(self.bot, after.guild, embed)


async def setup(bot):
    await bot.add_cog(RoleLogger(bot))
