from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner_or_mod_check


class Mute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="mute", description="Mute a member for a certain duration."
    )
    @app_commands.describe(
        member="The member to mute",
        duration="Mute duration in minutes (leave empty for indefinite mute)",
        reason="Reason for the mute",
    )
    @app_commands.check(is_owner_or_mod_check)
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: Optional[int] = None,
        reason: str = "No reason provided",
    ):
        await interaction.response.defer(ephemeral=True)

        # Prevent muting self or bot
        if member.id == interaction.user.id:
            return await interaction.followup.send(
                "❌ You cannot mute yourself.", ephemeral=True
            )
        if member.id == self.bot.user.id:
            return await interaction.followup.send(
                "❌ You cannot mute the bot.", ephemeral=True
            )

        # Optional: Prevent muting the server owner
        if interaction.guild and member.id == interaction.guild.owner_id:
            return await interaction.followup.send(
                "❌ You cannot mute the server owner.", ephemeral=True
            )

        # Sanitize reason
        reason = reason.strip()
        if len(reason) > 500:
            reason = reason[:500] + "..."

        try:
            if duration is not None:
                mute_duration = timedelta(minutes=duration)
                await member.timeout_for(mute_duration, reason=reason)
                description = f"**{member.mention}** has been muted for `{duration}` minutes.\n**Reason:** {reason}"
            else:
                # Discord max timeout = 28 days
                max_duration = timedelta(days=28)
                await member.timeout_for(max_duration, reason=reason)
                description = f"**{member.mention}** has been muted indefinitely (max 28 days).\n**Reason:** {reason}"

            embed = discord.Embed(
                title="✅ Member Muted",
                description=description,
                color=0xE74C3C,
            )
            await interaction.followup.send(embed=embed)

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to mute this member.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ An unexpected error occurred:\n```{e}```", ephemeral=True
            )

    @app_commands.command(
        name="unmute", description="Unmute a member (remove their timeout)."
    )
    @app_commands.describe(
        member="The member to unmute",
        reason="Reason for unmuting",
    )
    @app_commands.check(is_owner_or_mod_check)
    async def unmute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            await member.edit(timeout=None, reason=reason)

            embed = discord.Embed(
                title="✅ Member Unmuted",
                description=f"**{member.mention}** has been unmuted.\n**Reason:** {reason}",
                color=0x2ECC71,
            )
            await interaction.followup.send(embed=embed)

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to unmute this member.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ An unexpected error occurred:\n```{e}```", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Mute(bot))
