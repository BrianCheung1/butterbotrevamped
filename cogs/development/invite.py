import discord
from discord import app_commands
from discord.ext import commands


class Invite(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="invite", description="Get the bot's invite link")
    async def invite(self, interaction: discord.Interaction):
        app_info = await self.bot.application_info()
        invite_url = discord.utils.oauth_url(
            client_id=app_info.id,
            permissions=discord.Permissions(
                administrator=True
            ),  # Customize perms if needed
            scopes=("bot", "applications.commands"),
        )
        embed = discord.Embed(
            title="Invite Me!",
            description=f"[Click here to invite the bot!]({invite_url})",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Invite(bot))
